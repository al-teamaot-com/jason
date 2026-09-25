from __future__ import annotations

import os
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

from connectors.autotask.connector import AutotaskConnector
from connectors.autotask.impersonating_connector import (
    TrustedPrincipalBindingResolver,
)
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
from kernel.capabilities import (
    CapabilityEvidence,
    CapabilityLifecycle,
    CapabilityRegistryService,
)
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
from orchestrator.connector_invoker import (
    GovernedConnectorCapabilityInvoker,
    ProviderPreparedExecution,
)
from orchestrator.execution_plan import normalize_provider_relative_path
from orchestrator.invokers import CapabilityInvokerRegistry
from orchestrator.provider_mutation_capability_catalog import (
    SERVICE_TICKET_NOTE_CREATE,
    autotask_mutation_capability_definitions,
)
from orchestrator.service import CapabilityInvoker


AUTOTASK_INTERNAL_NOTE_PROVIDER = "autotask_internal_note"

AUTOTASK_INTERNAL_NOTE_PROFILE_ENV = (
    "JASON_AUTOTASK_INTERNAL_NOTE_MCP_PROFILE"
)

AUTOTASK_INTERNAL_NOTE_PROFILE = "owner-internal-note-v1"

AUTOTASK_INTERNAL_NOTE_AUTONOMY_RESOURCE_ID_ENV = (
    "JASON_AUTOTASK_INTERNAL_NOTE_AUTONOMY_RESOURCE_ID"
)
AUTOTASK_INTERNAL_NOTE_AUTONOMY_PRINCIPAL = "jason-autonomy-worker"

_PROVIDER_CAPABILITY_MAP = {
    (
        AUTOTASK_INTERNAL_NOTE_PROVIDER,
        SERVICE_TICKET_NOTE_CREATE,
    ): "autotask.ticket.note.create",
}


class AutotaskInternalNoteActivationError(RuntimeError):
    """Fail-closed internal-note activation error."""


class AutotaskInternalNoteVerificationError(ConnectorError):
    """The provider mutation occurred but durable readback was not proven."""

    error_code = "AUTOTASK_INTERNAL_NOTE_VERIFICATION_FAILED"


@dataclass(frozen=True, slots=True)
class AutotaskInternalNoteActivationState:
    profile: str
    enabled: bool
    provider_ids: tuple[str, ...]
    capability_names: tuple[str, ...]


def configured_autotask_internal_note_autonomy_resource_id() -> int | None:
    """Return the explicitly configured Autotask API-user Resource ID."""

    raw = os.getenv(
        AUTOTASK_INTERNAL_NOTE_AUTONOMY_RESOURCE_ID_ENV,
        "",
    ).strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError) as error:
        raise RuntimeError(
            "AUTOTASK_INTERNAL_NOTE_AUTONOMY_RESOURCE_ID_INVALID"
        ) from error
    if value < 1:
        raise RuntimeError(
            "AUTOTASK_INTERNAL_NOTE_AUTONOMY_RESOURCE_ID_INVALID"
        )
    return value

def autotask_internal_note_mcp_surface_enabled() -> bool:
    """Require all explicit source/runtime mutation gates."""

    profile = os.getenv(
        AUTOTASK_INTERNAL_NOTE_PROFILE_ENV,
        "",
    ).strip().casefold()

    mutation_enabled = os.getenv(
        AUTOTASK_MUTATION_ENABLED_ENV,
        "",
    ).strip().casefold()

    return (
        profile == AUTOTASK_INTERNAL_NOTE_PROFILE
        and mutation_enabled == "true"
    )


def _internal_note_definition(*, now: datetime):
    matches = [
        definition
        for definition
        in autotask_mutation_capability_definitions(
            now=now
        )
        if definition.capability_name
        == SERVICE_TICKET_NOTE_CREATE
    ]

    if len(matches) != 1:
        raise AutotaskInternalNoteActivationError(
            "internal note capability definition is not unique"
        )

    base = matches[0]

    metadata = dict(base.metadata)

    metadata.update(
        {
            "activation_state": (
                "internal_note_mcp_source_only_not_activated"
            ),
            "mcp_action_enabled": "true",
            "mcp_tool_name": (
                "create_autotask_internal_note"
            ),
            "conversation_authenticated_imperative_is_approval": (
                "true"
            ),
            "pilot_scope": (
                "aot_owner_organization_scope"
            ),
            "note_type": "3",
            "publish": "1",
        }
    )

    evidence = CapabilityEvidence(
        required=True,
        requirements=(
            "authenticated requester identity",
            "provider requester authorization evidence",
            "exact resolved target ticket",
            "provider mutation result",
            "post-mutation verification result",
        ),
        verification_requirements=(
            "requester maps to exactly one active Autotask Resource",
            "provider-native requester impersonation is applied",
            "requester Autotask permissions permit TicketNote create",
            "target ticket is within the configured AOT Autotask tenant",
            "post-mutation readback matches the intended internal note",
            "provider attribution identifies the impersonated requester",
        ),
    )

    # The first production pilot is AOT Owner organization scope.
    # We deliberately do NOT alter the generic mutation capability
    # catalog. This specialized surface is exact-principal governed
    # and still tenant-isolated/provider-permission-enforced.
    return replace(
        base,
        business_purpose=(
            "Create one Owner-approved internal note on an exact "
            "Autotask service ticket."
        ),
        client_isolation_required=False,
        evidence=evidence,
        metadata=metadata,
    )


def _internal_note_provider(
    *,
    now: datetime,
) -> ExecutionProvider:
    return ExecutionProvider(
        provider_id=AUTOTASK_INTERNAL_NOTE_PROVIDER,
        display_name=(
            "Autotask PSA Internal Note Mutation"
        ),
        provider_type=ProviderType.EXTERNAL_CONNECTOR,
        lifecycle_status=ProviderLifecycle.PLANNED,
        health_status=ProviderHealth.UNKNOWN,
        approval_status=ProviderApproval.PILOT,
        execution_modes=frozenset(
            {
                "deterministic",
            }
        ),
        capabilities=frozenset(
            {
                SERVICE_TICKET_NOTE_CREATE,
            }
        ),
        supported_classifications=frozenset(
            {
                "internal",
            }
        ),
        regions=frozenset(),
        limits=ProviderLimits(
            maximum_concurrent_executions=1,
            maximum_requests_per_minute=10,
            maximum_execution_seconds=60,
        ),
        features=ProviderFeatures(
            structured_output=True,
        ),
        pricing_profile_id="zero-cost-foundation",
        stewardship=ProviderStewardship(
            technology_steward="technology-steward",
            business_justification=(
                "Permit one narrowly governed Autotask internal "
                "ticket-note mutation through requester "
                "impersonation."
            ),
            review_interval_days=30,
            last_reviewed_at=now,
            retirement_criteria=(
                "Provider-native requester authorization can no "
                "longer be proven.",
                "A safer approved service-note capability replaces "
                "this pilot.",
            ),
            vendor_change_sources=(
                "Autotask REST API documentation",
            ),
            operational_owner="AOT IT Operations",
            approval_owner="AOT Owner",
        ),
        created_at=now,
        metadata={
            "connector_id": "autotask",
            "resource_authority": "service_management",
            "write_capability": "true",
            "mutation_scope": "ticket_note_create_only",
            "provider_native_impersonation_required": "true",
            "activation_state": (
                "internal_note_mcp_source_only_not_activated"
            ),
        },
    )


def _positive_int(
    value: Any,
    *,
    label: str,
) -> int:
    if isinstance(value, bool):
        raise AutotaskInternalNoteVerificationError(
            f"{label} is invalid"
        )

    try:
        result = int(value)
    except (TypeError, ValueError) as error:
        raise AutotaskInternalNoteVerificationError(
            f"{label} is invalid"
        ) from error

    if result < 1:
        raise AutotaskInternalNoteVerificationError(
            f"{label} is invalid"
        )

    return result


@dataclass(frozen=True, slots=True)
class _PreparedAutotaskInternalNote:
    request: ConnectorRequest
    expected: Mapping[str, Any]
    prepared: PreparedRequest


class AutotaskInternalNoteConnector(
    AutotaskMutationConnector
):
    """Exact TicketNote-create connector with mandatory readback."""

    def __init__(
        self,
        *,
        autonomy_api_resource_id: int | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        if autonomy_api_resource_id is not None:
            if isinstance(autonomy_api_resource_id, bool):
                raise ValueError(
                    "AUTOTASK_INTERNAL_NOTE_AUTONOMY_RESOURCE_ID_INVALID"
                )
            try:
                parsed = int(autonomy_api_resource_id)
            except (TypeError, ValueError) as error:
                raise ValueError(
                    "AUTOTASK_INTERNAL_NOTE_AUTONOMY_RESOURCE_ID_INVALID"
                ) from error
            if parsed < 1:
                raise ValueError(
                    "AUTOTASK_INTERNAL_NOTE_AUTONOMY_RESOURCE_ID_INVALID"
                )
            self._autonomy_api_resource_id = parsed
        else:
            self._autonomy_api_resource_id = None

    def _is_autonomous_api_user_request(
        self,
        request: ConnectorRequest,
    ) -> bool:
        return (
            request.context.principal_id
            == AUTOTASK_INTERNAL_NOTE_AUTONOMY_PRINCIPAL
            and self._autonomy_api_resource_id is not None
        )

    def _prepare_autonomous_api_user_request(
        self,
        request: ConnectorRequest,
        credentials: Mapping[str, str],
    ) -> PreparedRequest:
        """Prepare TicketNote creation as the API user itself.

        No ImpersonationResourceId header is added. Provider access preflight
        therefore evaluates the API user's native TicketNote permission.
        """

        prepared = AutotaskConnector.prepare_request(
            self,
            request,
            credentials,
        )
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

    capabilities = frozenset(
        {
            "autotask.ticket.note.create",
        }
    )

    def prepare_request(
        self,
        request: ConnectorRequest,
        credentials: Mapping[str, str],
    ) -> PreparedRequest:
        if self._is_autonomous_api_user_request(request):
            return self._prepare_autonomous_api_user_request(
                request,
                credentials,
            )
        return super().prepare_request(
            request,
            credentials,
        )

    @staticmethod
    def _expected_payload(
        request: ConnectorRequest,
    ) -> dict[str, Any]:
        raw = request.arguments.get("payload")

        if not isinstance(raw, Mapping):
            raise ConnectorAuthorizationError(
                "internal note payload is required"
            )

        payload = dict(raw)

        ticket_id = _positive_int(
            payload.get("ticketID"),
            label="ticketID",
        )

        description = str(
            payload.get("description") or ""
        ).strip()

        if not description:
            raise ConnectorAuthorizationError(
                "internal note description is required"
            )

        try:
            note_type = int(
                payload.get("noteType")
            )
            publish = int(
                payload.get("publish")
            )
        except (TypeError, ValueError) as error:
            raise ConnectorAuthorizationError(
                "internal note visibility metadata is invalid"
            ) from error

        if note_type != 3 or publish != 1:
            raise ConnectorAuthorizationError(
                "internal note visibility must remain "
                "noteType=3,publish=1"
            )

        expected = {
            "ticketID": ticket_id,
            "description": description,
            "noteType": 3,
            "publish": 1,
        }

        title = str(
            payload.get("title") or ""
        ).strip()

        if title:
            expected["title"] = title

        return expected

    @staticmethod
    def _created_note_id(
        data: Mapping[str, Any],
    ) -> int:
        for key in (
            "itemId",
            "itemID",
            "id",
        ):
            if key not in data:
                continue

            try:
                return _positive_int(
                    data.get(key),
                    label="created ticket note id",
                )
            except AutotaskInternalNoteVerificationError:
                continue

        raise AutotaskInternalNoteVerificationError(
            "provider response did not expose a durable "
            "ticket note id"
        )

    def _verify_created_note(
        self,
        *,
        request: ConnectorRequest,
        expected: Mapping[str, Any],
        note_id: int,
    ) -> Mapping[str, Any]:
        verify_context = replace(
            request.context,
            capability="autotask.ticket.notes.list",
            mode="observe",
        )

        verify_request = ConnectorRequest(
            context=verify_context,
            arguments={
                "ticket_id": expected["ticketID"],
            },
        )

        credentials = dict(
            self._secrets.resolve(
                self.logical_secret,
                verify_context,
            )
        )

        try:
            # Bypass mutation prepare_request deliberately. This is
            # a bounded GET used only to verify the just-created note.
            prepared = AutotaskConnector.prepare_request(
                self,
                verify_request,
                credentials,
            )

            if self._is_autonomous_api_user_request(
                verify_request
            ):
                resource_id = self._autonomy_api_resource_id
                if resource_id is None:
                    raise AutotaskInternalNoteVerificationError(
                        "autonomous API-user resource id unavailable "
                        "during readback"
                    )
                headers = dict(prepared.headers)
                headers.pop("ImpersonationResourceId", None)
            else:
                email = self._trusted_email(
                    verify_request
                )
                if email is None:
                    raise AutotaskInternalNoteVerificationError(
                        "trusted requester binding unavailable "
                        "during readback"
                    )
                resource_id = (
                    self._resolve_impersonation_resource_id(
                        prepared=prepared,
                        email=email,
                    )
                )
                headers = dict(prepared.headers)
                headers[
                    "ImpersonationResourceId"
                ] = str(resource_id)
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

        items = (
            response.get("items")
            if isinstance(response, Mapping)
            else None
        )

        if not isinstance(items, list):
            raise AutotaskInternalNoteVerificationError(
                "ticket note readback response was invalid"
            )

        matches = []

        for item in items:
            if not isinstance(item, Mapping):
                continue

            try:
                item_id = int(
                    item.get("id")
                )
            except (TypeError, ValueError):
                continue

            if item_id == note_id:
                matches.append(
                    dict(item)
                )

        if len(matches) != 1:
            raise AutotaskInternalNoteVerificationError(
                "created ticket note was not uniquely observed "
                "during readback"
            )

        observed = matches[0]

        if (
            str(
                observed.get("description")
                or ""
            )
            != str(
                expected["description"]
            )
        ):
            raise AutotaskInternalNoteVerificationError(
                "ticket note description failed readback"
            )

        try:
            observed_note_type = int(
                observed.get("noteType")
            )
            observed_publish = int(
                observed.get("publish")
            )
            observed_creator = int(
                observed.get("creatorResourceID")
            )
        except (TypeError, ValueError) as error:
            raise AutotaskInternalNoteVerificationError(
                "ticket note readback metadata was invalid"
            ) from error

        if observed_note_type != 3:
            raise AutotaskInternalNoteVerificationError(
                "ticket note type failed readback"
            )

        if observed_publish != 1:
            raise AutotaskInternalNoteVerificationError(
                "ticket note publish failed readback"
            )

        expected_title = str(
            expected.get("title")
            or ""
        )

        if expected_title and (
            str(
                observed.get("title")
                or ""
            )
            != expected_title
        ):
            raise AutotaskInternalNoteVerificationError(
                "ticket note title failed readback"
            )

        if observed_creator != resource_id:
            raise AutotaskInternalNoteVerificationError(
                "ticket note requester attribution failed "
                "readback"
            )

        impersonator = observed.get(
            "impersonatorCreatorResourceID"
        )

        if self._is_autonomous_api_user_request(
            request
        ):
            if impersonator not in (
                None,
                "",
                0,
                "0",
            ):
                raise AutotaskInternalNoteVerificationError(
                    "autonomous API-user note unexpectedly "
                    "recorded an impersonator"
                )
            impersonator_recorded = False
        else:
            if impersonator in (
                None,
                "",
                0,
                "0",
            ):
                raise AutotaskInternalNoteVerificationError(
                    "ticket note API impersonator attribution "
                    "was not recorded"
                )
            impersonator_recorded = True

        return {
            "readbackVerified": True,
            "ticketNoteId": note_id,
            "creatorResourceId": resource_id,
            "impersonatorRecorded": impersonator_recorded,
        }

    def prepare_governed_execution(
        self, request: ConnectorRequest
    ) -> ProviderPreparedExecution:
        if request.context.capability != "autotask.ticket.note.create":
            raise ConnectorAuthorizationError(
                "internal-note connector exposes only TicketNote create"
            )
        expected = self._expected_payload(request)
        normalized_request = ConnectorRequest(
            context=request.context,
            arguments={**dict(request.arguments), "payload": dict(expected)},
        )
        if normalized_request.context.mode != "execute":
            raise ConnectorAuthorizationError("Autotask mutation requires explicit execute mode.")
        if not autotask_mutation_execution_enabled():
            raise PermissionError("AUTOTASK_MUTATION_EXECUTION_DISABLED")
        credentials = self._secrets.resolve(self.logical_secret, normalized_request.context)
        prepared = self.prepare_request(
            normalized_request,
            credentials,
        )
        relative_path = prepared.audit_operation or urlsplit(prepared.url).path
        return ProviderPreparedExecution(
            provider_capability=request.context.capability,
            action_method=prepared.method,
            resource_type="service_ticket_note",
            resource_identifier=str(expected["ticketID"]),
            normalized_path=relative_path,
            payload=dict(prepared.json or {}),
            parameters=dict(prepared.params or {}),
            symbolic_resolutions={},
            opaque=_PreparedAutotaskInternalNote(
                request=normalized_request, expected=dict(expected), prepared=prepared
            ),
        )

    def execute_governed_execution(
        self, prepared_execution: ProviderPreparedExecution
    ) -> ConnectorResult:
        opaque = prepared_execution.opaque
        if not isinstance(opaque, _PreparedAutotaskInternalNote):
            raise PermissionError("invalid Autotask internal-note prepared execution")
        request = opaque.request
        expected = dict(opaque.expected)
        prepared = opaque.prepared
        if prepared_execution.provider_capability != request.context.capability:
            raise PermissionError("prepared Autotask provider capability no longer matches authorized execution plan")
        if str(prepared.method).strip().upper() != str(prepared_execution.action_method).strip().upper():
            raise PermissionError("prepared Autotask method no longer matches authorized execution plan")
        observed_path = normalize_provider_relative_path(prepared.audit_operation or urlsplit(prepared.url).path)
        if observed_path != normalize_provider_relative_path(prepared_execution.normalized_path):
            raise PermissionError("prepared Autotask path no longer matches authorized execution plan")
        if str(expected["ticketID"]) != str(prepared_execution.resource_identifier):
            raise PermissionError("prepared Autotask ticket-note target no longer matches authorized execution plan")
        if dict(prepared.json or {}) != dict(prepared_execution.payload):
            raise PermissionError("prepared Autotask payload no longer matches authorized execution plan")
        if dict(prepared.params or {}) != dict(prepared_execution.parameters):
            raise PermissionError("prepared Autotask parameters no longer match authorized execution plan")
        self._audit_mutation_event("connector.mutation.requested", request)
        try:
            if not autotask_mutation_execution_enabled():
                raise PermissionError("AUTOTASK_MUTATION_EXECUTION_DISABLED")
            payload = self._transport.request(
                method=prepared.method, url=prepared.url, headers=prepared.headers,
                params=prepared.params, json=prepared.json, timeout_seconds=prepared.timeout_seconds,
            )
        except Exception as error:
            self._audit_mutation_event("connector.mutation.failed", request, error_type=type(error).__name__)
            raise
        self._audit_mutation_event("connector.mutation.completed", request)
        result = ConnectorResult(capability=request.context.capability, provider=self.provider_name, data=payload)
        note_id = self._created_note_id(result.data)
        try:
            verification = self._verify_created_note(
                request=request, expected=expected, note_id=note_id
            )
        except Exception as error:
            self._audit.record(
                "connector.mutation.verification_failed", request.context,
                {"provider": self.provider_name, "capability": request.context.capability, "error_type": type(error).__name__},
            )
            if isinstance(error, AutotaskInternalNoteVerificationError):
                raise
            raise AutotaskInternalNoteVerificationError(
                "internal note post-mutation verification failed"
            ) from error
        self._audit.record(
            "connector.mutation.verified", request.context,
            {"provider": self.provider_name, "capability": request.context.capability, "ticket_note_id": note_id},
        )
        data = dict(result.data)
        data["jasonVerification"] = dict(verification)
        return ConnectorResult(
            capability=result.capability, provider=result.provider, data=data,
            evidence_ids=(*result.evidence_ids, f"autotask:ticket-note:{note_id}"),
            warnings=result.warnings,
        )

    def execute(
        self,
        request: ConnectorRequest,
    ) -> ConnectorResult:
        if (
            request.context.capability
            != "autotask.ticket.note.create"
        ):
            raise ConnectorAuthorizationError(
                "internal-note connector exposes only "
                "TicketNote create"
            )

        expected = self._expected_payload(
            request
        )

        # The parent performs all existing mutation gates,
        # write-secret resolution, requester lookup, provider
        # entityInformation preflight, one POST, and mutation audit.
        result = super().execute(
            request
        )

        note_id = self._created_note_id(
            result.data
        )

        try:
            verification = self._verify_created_note(
                request=request,
                expected=expected,
                note_id=note_id,
            )
        except Exception as error:
            self._audit.record(
                "connector.mutation.verification_failed",
                request.context,
                {
                    "provider": self.provider_name,
                    "capability": request.context.capability,
                    "error_type": type(error).__name__,
                },
            )

            if isinstance(
                error,
                AutotaskInternalNoteVerificationError,
            ):
                raise

            raise AutotaskInternalNoteVerificationError(
                "internal note post-mutation verification failed"
            ) from error

        self._audit.record(
            "connector.mutation.verified",
            request.context,
            {
                "provider": self.provider_name,
                "capability": request.context.capability,
                "ticket_note_id": note_id,
            },
        )

        data = dict(
            result.data
        )

        data[
            "jasonVerification"
        ] = dict(
            verification
        )

        return ConnectorResult(
            capability=result.capability,
            provider=result.provider,
            data=data,
            evidence_ids=(
                *result.evidence_ids,
                f"autotask:ticket-note:{note_id}",
            ),
            warnings=result.warnings,
        )


def _validate_pre_activation_contract(
    *,
    capabilities: CapabilityRegistryService,
    providers: ExecutionProviderRegistryService,
) -> None:
    capability = capabilities.get(
        capability_name=SERVICE_TICKET_NOTE_CREATE,
        version="1.0",
    )

    provider = providers.get(
        AUTOTASK_INTERNAL_NOTE_PROVIDER
    )

    metadata = capability.metadata

    if (
        capability.lifecycle_status
        is not CapabilityLifecycle.BUILDING
    ):
        raise AutotaskInternalNoteActivationError(
            "internal note capability is not BUILDING"
        )

    if (
        str(
            metadata.get(
                "provider_neutral",
                "",
            )
        ).casefold()
        != "true"
    ):
        raise AutotaskInternalNoteActivationError(
            "internal note capability is not provider-neutral"
        )

    if (
        str(
            metadata.get(
                "write_capability",
                "",
            )
        ).casefold()
        != "true"
    ):
        raise AutotaskInternalNoteActivationError(
            "internal note capability is not marked writable"
        )

    if (
        str(
            metadata.get(
                "provider_native_impersonation_required",
                "",
            )
        ).casefold()
        != "true"
    ):
        raise AutotaskInternalNoteActivationError(
            "requester impersonation requirement drifted"
        )

    if not capability.approval.required:
        raise AutotaskInternalNoteActivationError(
            "internal note capability unexpectedly lacks approval"
        )

    if not capability.idempotency_key_required:
        raise AutotaskInternalNoteActivationError(
            "internal note capability unexpectedly lacks "
            "idempotency requirement"
        )

    if capability.maximum_attempts != 1:
        raise AutotaskInternalNoteActivationError(
            "internal note capability permits provider retry"
        )

    if capability.client_isolation_required:
        raise AutotaskInternalNoteActivationError(
            "Owner pilot unexpectedly requires a single "
            "client-bound identity"
        )

    if (
        provider.lifecycle_status
        is not ProviderLifecycle.PLANNED
    ):
        raise AutotaskInternalNoteActivationError(
            "internal note provider is not PLANNED"
        )

    if (
        provider.health_status
        is not ProviderHealth.UNKNOWN
    ):
        raise AutotaskInternalNoteActivationError(
            "internal note provider health drifted"
        )

    if (
        provider.approval_status
        is not ProviderApproval.PILOT
    ):
        raise AutotaskInternalNoteActivationError(
            "internal note provider approval drifted"
        )

    if provider.capabilities != frozenset(
        {
            SERVICE_TICKET_NOTE_CREATE,
        }
    ):
        raise AutotaskInternalNoteActivationError(
            "internal note provider capability scope drifted"
        )


def apply_autotask_internal_note_activation(
    *,
    capabilities: CapabilityRegistryService,
    providers: ExecutionProviderRegistryService,
    profile: str | None,
) -> AutotaskInternalNoteActivationState:
    normalized = str(
        profile or ""
    ).strip().casefold()

    if not normalized:
        return AutotaskInternalNoteActivationState(
            profile="",
            enabled=False,
            provider_ids=(),
            capability_names=(),
        )

    if (
        normalized
        != AUTOTASK_INTERNAL_NOTE_PROFILE
    ):
        raise AutotaskInternalNoteActivationError(
            "unsupported Autotask internal-note MCP profile"
        )

    if not autotask_internal_note_mcp_surface_enabled():
        raise AutotaskInternalNoteActivationError(
            "internal-note MCP profile requires mutation "
            "execution gate"
        )

    _validate_pre_activation_contract(
        capabilities=capabilities,
        providers=providers,
    )

    capabilities.set_lifecycle(
        capability_name=SERVICE_TICKET_NOTE_CREATE,
        version="1.0",
        lifecycle_status=CapabilityLifecycle.ACTIVE,
    )

    providers.set_approval(
        provider_id=AUTOTASK_INTERNAL_NOTE_PROVIDER,
        approval_status=ProviderApproval.APPROVED,
    )

    providers.set_health(
        provider_id=AUTOTASK_INTERNAL_NOTE_PROVIDER,
        health_status=ProviderHealth.HEALTHY,
    )

    providers.set_lifecycle(
        provider_id=AUTOTASK_INTERNAL_NOTE_PROVIDER,
        lifecycle_status=ProviderLifecycle.AVAILABLE,
    )

    return AutotaskInternalNoteActivationState(
        profile=normalized,
        enabled=True,
        provider_ids=(
            AUTOTASK_INTERNAL_NOTE_PROVIDER,
        ),
        capability_names=(
            SERVICE_TICKET_NOTE_CREATE,
        ),
    )


def register_autotask_internal_note_runtime_foundation(
    *,
    capabilities: CapabilityRegistryService,
    providers: ExecutionProviderRegistryService,
    now: datetime,
) -> AutotaskInternalNoteActivationState:
    capabilities.register(
        _internal_note_definition(
            now=now,
        )
    )

    providers.register(
        _internal_note_provider(
            now=now,
        )
    )

    return apply_autotask_internal_note_activation(
        capabilities=capabilities,
        providers=providers,
        profile=os.getenv(
            AUTOTASK_INTERNAL_NOTE_PROFILE_ENV,
            "",
        ),
    )


def build_autotask_internal_note_invoker(
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

    connector = AutotaskInternalNoteConnector(
        secrets=secrets,
        transport=transport,
        audit=audit,
        bindings=bindings,
        autonomy_api_resource_id=(
            configured_autotask_internal_note_autonomy_resource_id()
        ),
    )

    return GovernedConnectorCapabilityInvoker(
        connectors={
            AUTOTASK_INTERNAL_NOTE_PROVIDER: connector,
        },
        provider_capability_map=_PROVIDER_CAPABILITY_MAP,
    )


def register_autotask_internal_note_invoker(
    *,
    invokers: CapabilityInvokerRegistry,
    invoker: CapabilityInvoker,
) -> None:
    invokers.register(
        SERVICE_TICKET_NOTE_CREATE,
        invoker,
    )
