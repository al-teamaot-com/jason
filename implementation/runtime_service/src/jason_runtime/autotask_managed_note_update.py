from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

from connectors.autotask.connector import AutotaskConnector
from connectors.autotask.impersonating_connector import TrustedPrincipalBindingResolver
from connectors.autotask.mutation_connector import (
    AUTOTASK_MUTATION_ENABLED_ENV,
    AutotaskMutationConnector,
    autotask_mutation_execution_enabled,
)
from connectors.core.connector_base import PreparedRequest
from connectors.core.contracts import (
    AuditSink,
    ConnectorAuthorizationError,
    ConnectorError,
    ConnectorRequest,
    ConnectorResult,
    HttpTransport,
)
from connectors.core.openbao_secrets import OpenBaoSecretResolver
from kernel.capabilities import CapabilityEvidence, CapabilityLifecycle, CapabilityRegistryService
from kernel.execution_providers import (
    ExecutionProvider,
    ExecutionProviderRegistryService,
    ProviderApproval,
    ProviderFeatures,
    ProviderHealth,
    ProviderLifecycle,
    ProviderLimits,
    ProviderStewardship,
    ProviderType,
)
from orchestrator.connector_invoker import GovernedConnectorCapabilityInvoker, ProviderPreparedExecution
from orchestrator.execution_plan import normalize_provider_relative_path
from orchestrator.invokers import CapabilityInvokerRegistry
from orchestrator.provider_mutation_capability_catalog import (
    SERVICE_TICKET_NOTE_UPDATE,
    autotask_mutation_capability_definitions,
)
from orchestrator.service import CapabilityInvoker

from .autotask_internal_note import (
    AUTOTASK_INTERNAL_NOTE_AUTONOMY_PRINCIPAL,
    AUTOTASK_INTERNAL_NOTE_PROFILE,
    AUTOTASK_INTERNAL_NOTE_PROFILE_ENV,
    configured_autotask_internal_note_autonomy_resource_id,
)

AUTOTASK_MANAGED_NOTE_UPDATE_PROVIDER = "autotask_managed_note_update"
_ALLOWED_TITLE_PREFIXES = ("GPT Insights", "Jason Activity")


class AutotaskManagedNoteUpdateActivationError(RuntimeError):
    pass


class AutotaskManagedNoteUpdateVerificationError(ConnectorError):
    error_code = "AUTOTASK_MANAGED_NOTE_UPDATE_VERIFICATION_FAILED"


@dataclass(frozen=True, slots=True)
class AutotaskManagedNoteUpdateActivationState:
    profile: str
    enabled: bool
    provider_ids: tuple[str, ...]
    capability_names: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _PreparedManagedNoteUpdate:
    request: ConnectorRequest
    expected: Mapping[str, Any]
    prepared: PreparedRequest
    prior_description: str
    prior_hash: str
    owner_resource_id: int


def autotask_managed_note_update_surface_enabled() -> bool:
    return (
        os.getenv(AUTOTASK_INTERNAL_NOTE_PROFILE_ENV, "").strip().casefold()
        == AUTOTASK_INTERNAL_NOTE_PROFILE
        and os.getenv(AUTOTASK_MUTATION_ENABLED_ENV, "").strip().casefold() == "true"
    )


def _definition(*, now: datetime):
    matches = [
        item
        for item in autotask_mutation_capability_definitions(now=now)
        if item.capability_name == SERVICE_TICKET_NOTE_UPDATE
    ]
    if len(matches) != 1:
        raise AutotaskManagedNoteUpdateActivationError(
            "managed ticket-note update capability definition is not unique"
        )
    base = matches[0]
    metadata = dict(base.metadata)
    metadata.update(
        {
            "activation_state": "managed_note_update_source_only_not_activated",
            "mcp_action_enabled": "true",
            "mcp_tool_name": "execute_governed_capability",
            "conversation_authenticated_imperative_is_approval": "true",
            "pilot_scope": "aot_owner_organization_scope",
            "managed_note_update_only": "true",
            "managed_note_title_prefixes": ",".join(_ALLOWED_TITLE_PREFIXES),
            "note_type": "3",
            "publish": "2",
            "ownership_rule": "exact_creator_resource_plus_internal_visibility",
            "activity_update_rule": "append_only",
        }
    )
    evidence = CapabilityEvidence(
        required=True,
        requirements=(
            "authenticated requester identity",
            "provider requester authorization evidence",
            "exact target ticket and ticket note",
            "pre-mutation Jason ownership readback",
            "provider mutation result",
            "post-mutation verification result",
        ),
        verification_requirements=(
            "target note is noteType=3 and publish=2",
            "target note creator is the exact requester or configured Jason autonomy API resource",
            "target note title is an approved Jason-managed title",
            "Jason Activity changes preserve the complete prior body as a prefix",
            "provider-native requester authorization permits TicketNote update",
            "post-mutation readback matches the intended body and preserves ownership",
        ),
    )
    return replace(
        base,
        business_purpose=(
            "Update one existing Jason-owned internal Autotask ticket note while "
            "preserving note ownership, internal visibility, readback verification, "
            "and an auditable before/after revision record."
        ),
        client_isolation_required=False,
        evidence=evidence,
        metadata=metadata,
    )


def _provider(*, now: datetime) -> ExecutionProvider:
    return ExecutionProvider(
        provider_id=AUTOTASK_MANAGED_NOTE_UPDATE_PROVIDER,
        display_name="Autotask PSA Jason-Managed Internal Note Update",
        provider_type=ProviderType.EXTERNAL_CONNECTOR,
        lifecycle_status=ProviderLifecycle.PLANNED,
        health_status=ProviderHealth.UNKNOWN,
        approval_status=ProviderApproval.PILOT,
        execution_modes=frozenset({"deterministic"}),
        capabilities=frozenset({SERVICE_TICKET_NOTE_UPDATE}),
        supported_classifications=frozenset({"internal"}),
        regions=frozenset(),
        limits=ProviderLimits(
            maximum_concurrent_executions=1,
            maximum_requests_per_minute=10,
            maximum_execution_seconds=60,
        ),
        features=ProviderFeatures(structured_output=True),
        pricing_profile_id="zero-cost-foundation",
        stewardship=ProviderStewardship(
            technology_steward="technology-steward",
            business_justification=(
                "Maintain Jason-owned internal ticket notes without modifying "
                "technician, workflow, or client-authored notes."
            ),
            review_interval_days=30,
            last_reviewed_at=now,
            retirement_criteria=(
                "Provider-native requester authorization can no longer be proven.",
                "The Jason-owned note identity boundary cannot be verified.",
            ),
            vendor_change_sources=("Autotask REST API documentation",),
            operational_owner="AOT IT Operations",
            approval_owner="AOT Owner",
        ),
        created_at=now,
        metadata={
            "connector_id": "autotask",
            "resource_authority": "service_management",
            "write_capability": "true",
            "mutation_scope": "jason_owned_internal_ticket_note_update_only",
            "provider_native_impersonation_required": "true",
            "activation_state": "managed_note_update_source_only_not_activated",
        },
    )


def _positive_int(value: Any, *, label: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a positive integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} must be a positive integer") from error
    if parsed < 1:
        raise ValueError(f"{label} must be a positive integer")
    return parsed


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _allowed_title(title: str) -> bool:
    normalized = title.strip()
    return any(
        normalized == prefix or normalized.startswith(prefix + " ")
        for prefix in _ALLOWED_TITLE_PREFIXES
    )


class AutotaskManagedNoteUpdateConnector(AutotaskMutationConnector):
    capabilities = frozenset({"autotask.ticket.note.update"})

    def __init__(self, *, autonomy_api_resource_id: int | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        if autonomy_api_resource_id is None:
            self._autonomy_api_resource_id = None
        else:
            self._autonomy_api_resource_id = _positive_int(
                autonomy_api_resource_id,
                label="autonomy_api_resource_id",
            )

    def _is_autonomous_api_user_request(self, request: ConnectorRequest) -> bool:
        return (
            request.context.principal_id == AUTOTASK_INTERNAL_NOTE_AUTONOMY_PRINCIPAL
            and self._autonomy_api_resource_id is not None
        )

    def prepare_request(
        self,
        request: ConnectorRequest,
        credentials: Mapping[str, str],
    ) -> PreparedRequest:
        if not self._is_autonomous_api_user_request(request):
            return AutotaskMutationConnector.prepare_request(self, request, credentials)

        if request.context.capability not in self.capabilities:
            raise ConnectorAuthorizationError(
                "managed-note connector exposes only TicketNote update"
            )
        prepared = AutotaskConnector.prepare_request(self, request, credentials)
        headers = dict(prepared.headers)
        headers.pop("ImpersonationResourceId", None)
        self._preflight_requester_access(
            prepared=prepared,
            headers=headers,
            operation=request.context.capability,
        )
        return PreparedRequest(
            method=prepared.method,
            url=prepared.url,
            headers=headers,
            params=prepared.params,
            json=prepared.json,
            timeout_seconds=prepared.timeout_seconds,
            audit_operation=prepared.audit_operation,
        )

    @staticmethod
    def validated_payload(request: ConnectorRequest) -> dict[str, Any]:
        raw = request.arguments.get("payload")
        if not isinstance(raw, Mapping):
            raise ValueError("managed note update requires a structured payload")
        payload = dict(raw)
        ticket_id = _positive_int(payload.get("ticketID"), label="ticketID")
        note_id = _positive_int(payload.get("id"), label="id")
        title = str(payload.get("title") or "").strip()
        description = str(payload.get("description") or "").strip()
        if not title or not _allowed_title(title):
            raise PermissionError("AUTOTASK_MANAGED_NOTE_TITLE_NOT_ALLOWED")
        if not description:
            raise ValueError("managed note description must not be empty")
        try:
            note_type = int(payload.get("noteType"))
            publish = int(payload.get("publish"))
        except (TypeError, ValueError) as error:
            raise ValueError("managed note visibility metadata is invalid") from error
        if note_type != 3 or publish != 2:
            raise PermissionError("AUTOTASK_MANAGED_NOTE_MUST_REMAIN_INTERNAL")
        return {
            "ticketID": ticket_id,
            "id": note_id,
            "title": title,
            "description": description,
            "noteType": 3,
            "publish": 2,
        }

    def _read_note(
        self,
        *,
        request: ConnectorRequest,
        ticket_id: int,
        note_id: int,
    ) -> tuple[Mapping[str, Any], int]:
        verify_context = replace(
            request.context,
            capability="autotask.ticket.notes.list",
            mode="observe",
        )
        verify_request = ConnectorRequest(
            context=verify_context,
            arguments={"ticket_id": ticket_id},
        )
        credentials = dict(self._secrets.resolve(self.logical_secret, verify_context))
        try:
            prepared = AutotaskConnector.prepare_request(
                self,
                verify_request,
                credentials,
            )
            headers = dict(prepared.headers)
            if self._is_autonomous_api_user_request(request):
                if self._autonomy_api_resource_id is None:
                    raise AutotaskManagedNoteUpdateVerificationError(
                        "autonomous API-user resource id unavailable"
                    )
                owner_resource_id = self._autonomy_api_resource_id
                headers.pop("ImpersonationResourceId", None)
            else:
                email = self._trusted_email(verify_request)
                if email is None:
                    raise AutotaskManagedNoteUpdateVerificationError(
                        "trusted requester binding unavailable"
                    )
                owner_resource_id = self._resolve_impersonation_resource_id(
                    prepared=prepared,
                    email=email,
                )
                headers["ImpersonationResourceId"] = str(owner_resource_id)
        finally:
            credentials.clear()

        response = self._transport.request(
            method="GET",
            url=prepared.url,
            headers=headers,
            params=prepared.params,
            json=None,
            timeout_seconds=prepared.timeout_seconds,
        )
        items = response.get("items") if isinstance(response, Mapping) else None
        if not isinstance(items, list):
            raise AutotaskManagedNoteUpdateVerificationError(
                "ticket note readback response was invalid"
            )
        matches: list[Mapping[str, Any]] = []
        for item in items:
            if not isinstance(item, Mapping):
                continue
            try:
                observed_id = int(item.get("id"))
            except (TypeError, ValueError):
                continue
            if observed_id == note_id:
                matches.append(dict(item))
        if len(matches) != 1:
            raise AutotaskManagedNoteUpdateVerificationError(
                "managed ticket note was not uniquely observed"
            )
        return matches[0], owner_resource_id

    def _verify_owned_note(
        self,
        *,
        request: ConnectorRequest,
        observed: Mapping[str, Any],
        owner_resource_id: int,
        expected: Mapping[str, Any],
        require_expected_description: bool,
    ) -> None:
        try:
            observed_id = int(observed.get("id"))
            observed_type = int(observed.get("noteType"))
            observed_publish = int(observed.get("publish"))
            observed_creator = int(observed.get("creatorResourceID"))
        except (TypeError, ValueError) as error:
            raise AutotaskManagedNoteUpdateVerificationError(
                "managed note ownership metadata was invalid"
            ) from error

        if observed_id != expected["id"]:
            raise AutotaskManagedNoteUpdateVerificationError("ticket note id failed readback")
        if observed_type != 3 or observed_publish != 2:
            raise AutotaskManagedNoteUpdateVerificationError(
                "managed note is not internal-only"
            )
        if observed_creator != owner_resource_id:
            raise AutotaskManagedNoteUpdateVerificationError(
                "managed note creator does not match Jason execution identity"
            )

        title = str(observed.get("title") or "").strip()
        if title != expected["title"] or not _allowed_title(title):
            raise AutotaskManagedNoteUpdateVerificationError(
                "managed note title/identity failed readback"
            )

        impersonator = observed.get("impersonatorCreatorResourceID")
        if self._is_autonomous_api_user_request(request):
            if impersonator not in (None, "", 0, "0"):
                raise AutotaskManagedNoteUpdateVerificationError(
                    "autonomous Jason note unexpectedly records an impersonator"
                )
        elif impersonator in (None, "", 0, "0"):
            raise AutotaskManagedNoteUpdateVerificationError(
                "interactive Jason note lacks provider impersonator attribution"
            )

        if require_expected_description and (
            str(observed.get("description") or "") != expected["description"]
        ):
            raise AutotaskManagedNoteUpdateVerificationError(
                "managed note description failed readback"
            )

    @staticmethod
    def _enforce_update_semantics(
        *,
        title: str,
        prior_description: str,
        new_description: str,
    ) -> None:
        if title.startswith("Jason Activity"):
            if not (
                new_description.startswith(prior_description + "\n\n")
                and len(new_description) > len(prior_description)
            ):
                raise PermissionError(
                    "AUTOTASK_JASON_ACTIVITY_UPDATE_MUST_BE_APPEND_ONLY"
                )

    def prepare_governed_execution(
        self,
        request: ConnectorRequest,
    ) -> ProviderPreparedExecution:
        if request.context.capability != "autotask.ticket.note.update":
            raise ConnectorAuthorizationError(
                "managed-note connector exposes only TicketNote update"
            )
        expected = self.validated_payload(request)
        prior, owner_resource_id = self._read_note(
            request=request,
            ticket_id=expected["ticketID"],
            note_id=expected["id"],
        )
        self._verify_owned_note(
            request=request,
            observed=prior,
            owner_resource_id=owner_resource_id,
            expected=expected,
            require_expected_description=False,
        )
        prior_description = str(prior.get("description") or "")
        self._enforce_update_semantics(
            title=expected["title"],
            prior_description=prior_description,
            new_description=expected["description"],
        )

        normalized_request = ConnectorRequest(
            context=request.context,
            arguments={**dict(request.arguments), "payload": dict(expected)},
        )
        if normalized_request.context.mode != "execute":
            raise ConnectorAuthorizationError(
                "Autotask mutation requires explicit execute mode."
            )
        if not autotask_mutation_execution_enabled():
            raise PermissionError("AUTOTASK_MUTATION_EXECUTION_DISABLED")
        credentials = self._secrets.resolve(self.logical_secret, normalized_request.context)
        prepared = self.prepare_request(normalized_request, credentials)
        relative_path = prepared.audit_operation or urlsplit(prepared.url).path
        return ProviderPreparedExecution(
            provider_capability=request.context.capability,
            action_method=prepared.method,
            resource_type="service_ticket_note",
            resource_identifier=str(expected["id"]),
            normalized_path=relative_path,
            payload=dict(prepared.json or {}),
            parameters=dict(prepared.params or {}),
            symbolic_resolutions={},
            opaque=_PreparedManagedNoteUpdate(
                request=normalized_request,
                expected=dict(expected),
                prepared=prepared,
                prior_description=prior_description,
                prior_hash=_sha256(prior_description),
                owner_resource_id=owner_resource_id,
            ),
        )

    def execute_governed_execution(
        self,
        prepared_execution: ProviderPreparedExecution,
    ) -> ConnectorResult:
        opaque = prepared_execution.opaque
        if not isinstance(opaque, _PreparedManagedNoteUpdate):
            raise PermissionError("invalid Autotask managed-note prepared execution")
        request = opaque.request
        expected = dict(opaque.expected)
        prepared = opaque.prepared
        if prepared_execution.provider_capability != request.context.capability:
            raise PermissionError("prepared provider capability changed")
        if str(prepared.method).strip().upper() != str(prepared_execution.action_method).strip().upper():
            raise PermissionError("prepared Autotask method changed")
        observed_path = normalize_provider_relative_path(
            prepared.audit_operation or urlsplit(prepared.url).path
        )
        if observed_path != normalize_provider_relative_path(prepared_execution.normalized_path):
            raise PermissionError("prepared Autotask path changed")
        if str(expected["id"]) != str(prepared_execution.resource_identifier):
            raise PermissionError("prepared managed-note target changed")
        if dict(prepared.json or {}) != dict(prepared_execution.payload):
            raise PermissionError("prepared managed-note payload changed")
        if dict(prepared.params or {}) != dict(prepared_execution.parameters):
            raise PermissionError("prepared managed-note parameters changed")

        # Optimistic concurrency gate: the target note may have been edited after
        # the execution plan was prepared. Re-read immediately before PATCH and
        # require the exact previously authorized body/owner to remain current.
        current, current_owner_resource_id = self._read_note(
            request=request,
            ticket_id=expected["ticketID"],
            note_id=expected["id"],
        )
        if current_owner_resource_id != opaque.owner_resource_id:
            raise AutotaskManagedNoteUpdateVerificationError(
                "Jason note owner identity changed before update"
            )
        self._verify_owned_note(
            request=request,
            observed=current,
            owner_resource_id=current_owner_resource_id,
            expected=expected,
            require_expected_description=False,
        )
        current_description = str(current.get("description") or "")
        if (
            current_description != opaque.prior_description
            or _sha256(current_description) != opaque.prior_hash
        ):
            raise AutotaskManagedNoteUpdateVerificationError(
                "managed note changed after execution plan preparation"
            )

        self._audit_mutation_event("connector.mutation.requested", request)
        try:
            if not autotask_mutation_execution_enabled():
                raise PermissionError("AUTOTASK_MUTATION_EXECUTION_DISABLED")
            payload = self._transport.request(
                method=prepared.method,
                url=prepared.url,
                headers=prepared.headers,
                params=prepared.params,
                json=prepared.json,
                timeout_seconds=prepared.timeout_seconds,
            )
        except Exception as error:
            self._audit_mutation_event(
                "connector.mutation.failed",
                request,
                error_type=type(error).__name__,
            )
            raise
        self._audit_mutation_event("connector.mutation.completed", request)

        observed, owner_resource_id = self._read_note(
            request=request,
            ticket_id=expected["ticketID"],
            note_id=expected["id"],
        )
        if owner_resource_id != opaque.owner_resource_id:
            raise AutotaskManagedNoteUpdateVerificationError(
                "Jason note owner identity changed during update"
            )
        self._verify_owned_note(
            request=request,
            observed=observed,
            owner_resource_id=owner_resource_id,
            expected=expected,
            require_expected_description=True,
        )

        new_hash = _sha256(expected["description"])
        self._audit.record(
            "connector.managed_note.revision",
            request.context,
            {
                "provider": "autotask",
                "capability": request.context.capability,
                "ticket_id": expected["ticketID"],
                "ticket_note_id": expected["id"],
                "title": expected["title"],
                "prior_body": opaque.prior_description,
                "prior_sha256": opaque.prior_hash,
                "revised_body": expected["description"],
                "revised_sha256": new_hash,
            },
        )
        self._audit.record(
            "connector.mutation.verified",
            request.context,
            {
                "provider": "autotask",
                "capability": request.context.capability,
                "ticket_note_id": expected["id"],
            },
        )
        result_data = dict(payload) if isinstance(payload, Mapping) else {}
        result_data["jasonVerification"] = {
            "readbackVerified": True,
            "ticketNoteId": expected["id"],
            "ticketId": expected["ticketID"],
            "ownerResourceId": owner_resource_id,
            "priorSha256": opaque.prior_hash,
            "revisedSha256": new_hash,
        }
        return ConnectorResult(
            capability=request.context.capability,
            provider=self.provider_name,
            data=result_data,
            evidence_ids=(f"autotask:ticket-note:{expected['id']}",),
        )

    def execute(self, request: ConnectorRequest) -> ConnectorResult:
        return self.execute_governed_execution(self.prepare_governed_execution(request))


def _validate_pre_activation_contract(
    *,
    capabilities: CapabilityRegistryService,
    providers: ExecutionProviderRegistryService,
) -> None:
    capability = capabilities.get(
        capability_name=SERVICE_TICKET_NOTE_UPDATE,
        version="1.0",
    )
    provider = providers.get(AUTOTASK_MANAGED_NOTE_UPDATE_PROVIDER)
    if capability.lifecycle_status is not CapabilityLifecycle.BUILDING:
        raise AutotaskManagedNoteUpdateActivationError(
            "managed note update capability is not BUILDING"
        )
    if not capability.approval.required or not capability.idempotency_key_required:
        raise AutotaskManagedNoteUpdateActivationError(
            "managed note update governance requirements drifted"
        )
    if capability.maximum_attempts != 1:
        raise AutotaskManagedNoteUpdateActivationError(
            "managed note update permits provider retry"
        )
    if capability.client_isolation_required:
        raise AutotaskManagedNoteUpdateActivationError(
            "Owner organization scope unexpectedly requires client identity"
        )
    if str(capability.metadata.get("mcp_action_enabled", "")).casefold() != "true":
        raise AutotaskManagedNoteUpdateActivationError(
            "managed note update MCP action flag missing"
        )
    if provider.lifecycle_status is not ProviderLifecycle.PLANNED:
        raise AutotaskManagedNoteUpdateActivationError(
            "managed note update provider is not PLANNED"
        )
    if provider.approval_status is not ProviderApproval.PILOT:
        raise AutotaskManagedNoteUpdateActivationError(
            "managed note update provider approval drifted"
        )
    if provider.capabilities != frozenset({SERVICE_TICKET_NOTE_UPDATE}):
        raise AutotaskManagedNoteUpdateActivationError(
            "managed note update provider scope drifted"
        )


def apply_autotask_managed_note_update_activation(
    *,
    capabilities: CapabilityRegistryService,
    providers: ExecutionProviderRegistryService,
    profile: str | None,
) -> AutotaskManagedNoteUpdateActivationState:
    normalized = str(profile or "").strip().casefold()
    if not normalized:
        return AutotaskManagedNoteUpdateActivationState("", False, (), ())
    if normalized != AUTOTASK_INTERNAL_NOTE_PROFILE:
        raise AutotaskManagedNoteUpdateActivationError(
            "unsupported Autotask internal-note MCP profile"
        )
    if not autotask_managed_note_update_surface_enabled():
        raise AutotaskManagedNoteUpdateActivationError(
            "managed note update requires internal-note and mutation execution gates"
        )
    _validate_pre_activation_contract(capabilities=capabilities, providers=providers)
    capabilities.set_lifecycle(
        capability_name=SERVICE_TICKET_NOTE_UPDATE,
        version="1.0",
        lifecycle_status=CapabilityLifecycle.ACTIVE,
    )
    providers.set_approval(
        provider_id=AUTOTASK_MANAGED_NOTE_UPDATE_PROVIDER,
        approval_status=ProviderApproval.APPROVED,
    )
    providers.set_health(
        provider_id=AUTOTASK_MANAGED_NOTE_UPDATE_PROVIDER,
        health_status=ProviderHealth.HEALTHY,
    )
    providers.set_lifecycle(
        provider_id=AUTOTASK_MANAGED_NOTE_UPDATE_PROVIDER,
        lifecycle_status=ProviderLifecycle.AVAILABLE,
    )
    return AutotaskManagedNoteUpdateActivationState(
        normalized,
        True,
        (AUTOTASK_MANAGED_NOTE_UPDATE_PROVIDER,),
        (SERVICE_TICKET_NOTE_UPDATE,),
    )


def register_autotask_managed_note_update_runtime_foundation(
    *,
    capabilities: CapabilityRegistryService,
    providers: ExecutionProviderRegistryService,
    now: datetime,
) -> AutotaskManagedNoteUpdateActivationState:
    capabilities.register(_definition(now=now))
    providers.register(_provider(now=now))
    return apply_autotask_managed_note_update_activation(
        capabilities=capabilities,
        providers=providers,
        profile=os.getenv(AUTOTASK_INTERNAL_NOTE_PROFILE_ENV, ""),
    )


def build_autotask_managed_note_update_invoker(
    *,
    openbao_url: str,
    role_id_path: Path,
    secret_id_path: Path,
    transport: HttpTransport,
    audit: AuditSink,
    bindings: TrustedPrincipalBindingResolver,
) -> CapabilityInvoker:
    secrets = OpenBaoSecretResolver(
        base_url=openbao_url,
        role_id_path=role_id_path,
        secret_id_path=secret_id_path,
    )
    connector = AutotaskManagedNoteUpdateConnector(
        secrets=secrets,
        transport=transport,
        audit=audit,
        bindings=bindings,
        autonomy_api_resource_id=configured_autotask_internal_note_autonomy_resource_id(),
    )
    return GovernedConnectorCapabilityInvoker(
        connectors={AUTOTASK_MANAGED_NOTE_UPDATE_PROVIDER: connector},
        provider_capability_map={
            (
                AUTOTASK_MANAGED_NOTE_UPDATE_PROVIDER,
                SERVICE_TICKET_NOTE_UPDATE,
            ): "autotask.ticket.note.update"
        },
    )


def register_autotask_managed_note_update_invoker(
    *,
    invokers: CapabilityInvokerRegistry,
    invoker: CapabilityInvoker,
) -> None:
    invokers.register(SERVICE_TICKET_NOTE_UPDATE, invoker)
