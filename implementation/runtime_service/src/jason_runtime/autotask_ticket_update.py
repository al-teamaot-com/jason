from __future__ import annotations

import os
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from connectors.autotask.connector import AutotaskConnector
from connectors.autotask.impersonating_connector import (
    AUTOTASK_AUTH_MODE_IMPERSONATED,
    AUTOTASK_REQUESTER_AUTH_MODE_ENV,
    TrustedPrincipalBindingResolver,
)
from connectors.autotask.mutation_connector import (
    AUTOTASK_MUTATION_ENABLED_ENV,
    AutotaskMutationConnector,
)
from connectors.core.contracts import (
    AuditSink,
    ConnectorAuthorizationError,
    ConnectorContext,
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
from orchestrator.connector_invoker import GovernedConnectorCapabilityInvoker
from orchestrator.invokers import CapabilityInvokerRegistry
from orchestrator.provider_mutation_capability_catalog import (
    SERVICE_TICKET_UPDATE,
    autotask_mutation_capability_definitions,
)
from orchestrator.service import CapabilityInvoker


AUTOTASK_TICKET_UPDATE_PROVIDER = "autotask_ticket_update"

AUTOTASK_TICKET_UPDATE_PROFILE_ENV = (
    "JASON_AUTOTASK_TICKET_UPDATE_MCP_PROFILE"
)

AUTOTASK_TICKET_UPDATE_PROFILE = "owner-ticket-update-v1"

SAFE_TICKET_UPDATE_FIELDS = frozenset(
    {
        "status",
        "priority",
        "queueID",
        "assignedResourceID",
        "dueDateTime",
    }
)

_INTEGER_FIELDS = frozenset(
    {
        "status",
        "priority",
        "queueID",
        "assignedResourceID",
    }
)

_PROVIDER_CAPABILITY_MAP = {
    (
        AUTOTASK_TICKET_UPDATE_PROVIDER,
        SERVICE_TICKET_UPDATE,
    ): "autotask.ticket.update",
}


class AutotaskTicketUpdateActivationError(RuntimeError):
    pass


class AutotaskTicketUpdateVerificationError(ConnectorError):
    error_code = "AUTOTASK_TICKET_UPDATE_VERIFICATION_FAILED"


@dataclass(frozen=True, slots=True)
class AutotaskTicketUpdateActivationState:
    profile: str
    enabled: bool
    provider_ids: tuple[str, ...]
    capability_names: tuple[str, ...]


def autotask_ticket_update_mcp_surface_enabled() -> bool:
    profile = os.getenv(
        AUTOTASK_TICKET_UPDATE_PROFILE_ENV,
        "",
    ).strip().casefold()

    mutation_enabled = os.getenv(
        AUTOTASK_MUTATION_ENABLED_ENV,
        "",
    ).strip().casefold()

    requester_mode = os.getenv(
        AUTOTASK_REQUESTER_AUTH_MODE_ENV,
        "",
    ).strip().casefold()

    return (
        profile == AUTOTASK_TICKET_UPDATE_PROFILE
        and mutation_enabled == "true"
        and requester_mode == AUTOTASK_AUTH_MODE_IMPERSONATED
    )


def _ticket_update_definition(*, now: datetime):
    matches = [
        definition
        for definition in autotask_mutation_capability_definitions(
            now=now
        )
        if definition.capability_name == SERVICE_TICKET_UPDATE
    ]

    if len(matches) != 1:
        raise AutotaskTicketUpdateActivationError(
            "ticket update capability definition is not unique"
        )

    base = matches[0]
    metadata = dict(base.metadata)

    metadata.update(
        {
            "activation_state": (
                "ticket_update_mcp_source_only_not_activated"
            ),
            "mcp_action_enabled": "true",
            "mcp_tool_name": "execute_governed_capability",
            "conversation_authenticated_imperative_is_approval": (
                "true"
            ),
            "pilot_scope": "aot_owner_organization_scope",
            "safe_update_fields": ",".join(
                sorted(SAFE_TICKET_UPDATE_FIELDS)
            ),
        }
    )

    evidence = CapabilityEvidence(
        required=True,
        requirements=(
            "authenticated requester identity",
            "provider requester authorization evidence",
            "exact resolved target ticket",
            "provider mutation result",
            "post-mutation ticket readback",
        ),
        verification_requirements=(
            "requester maps to exactly one active Autotask Resource",
            "provider-native requester impersonation is applied",
            "requester Autotask permissions permit Ticket update",
            "only explicitly allowed ticket fields are mutated",
            "post-mutation readback matches every intended field",
        ),
    )

    return replace(
        base,
        business_purpose=(
            "Apply one Owner-approved bounded update to an exact "
            "Autotask service ticket."
        ),
        client_isolation_required=False,
        evidence=evidence,
        metadata=metadata,
    )


def _ticket_update_provider(*, now: datetime) -> ExecutionProvider:
    return ExecutionProvider(
        provider_id=AUTOTASK_TICKET_UPDATE_PROVIDER,
        display_name="Autotask PSA Governed Ticket Update",
        provider_type=ProviderType.EXTERNAL_CONNECTOR,
        lifecycle_status=ProviderLifecycle.PLANNED,
        health_status=ProviderHealth.UNKNOWN,
        approval_status=ProviderApproval.PILOT,
        execution_modes=frozenset({"deterministic"}),
        capabilities=frozenset({SERVICE_TICKET_UPDATE}),
        supported_classifications=frozenset({"internal"}),
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
                "Permit one narrowly governed Autotask ticket "
                "update through requester impersonation."
            ),
            review_interval_days=30,
            last_reviewed_at=now,
            retirement_criteria=(
                "Provider-native requester authorization cannot be proven.",
                "A safer approved mutation capability replaces this pilot.",
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
            "mutation_scope": "ticket_update_safe_fields_only",
            "provider_native_impersonation_required": "true",
            "activation_state": (
                "ticket_update_mcp_source_only_not_activated"
            ),
        },
    )


def _positive_int(value: Any, *, field: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a positive integer")

    try:
        result = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(
            f"{field} must be a positive integer"
        ) from error

    if result < 1:
        raise ValueError(f"{field} must be a positive integer")

    return result


def _normalized_due(value: Any) -> str:
    text = str(value or "").strip()

    if not text or len(text) > 128:
        raise ValueError(
            "dueDateTime must be a bounded non-empty datetime string"
        )

    return text


class AutotaskTicketUpdateConnector(AutotaskMutationConnector):
    capabilities = frozenset(
        {
            "autotask.ticket.update",
        }
    )

    @staticmethod
    def validated_payload(
        request: ConnectorRequest,
    ) -> dict[str, Any]:
        raw = request.arguments.get("payload")

        if not isinstance(raw, Mapping):
            raise ValueError(
                "ticket update requires a structured payload"
            )

        payload = dict(raw)

        ticket_id = _positive_int(
            payload.get("id"),
            field="id",
        )

        supplied = set(payload) - {"id"}

        if not supplied:
            raise ValueError(
                "ticket update requires at least one mutable field"
            )

        disallowed = supplied - SAFE_TICKET_UPDATE_FIELDS

        if disallowed:
            raise PermissionError(
                "AUTOTASK_TICKET_UPDATE_FIELD_NOT_ALLOWED"
            )

        normalized: dict[str, Any] = {
            "id": ticket_id,
        }

        for field in supplied:
            value = payload[field]

            if field in _INTEGER_FIELDS:
                normalized[field] = _positive_int(
                    value,
                    field=field,
                )
            elif field == "dueDateTime":
                normalized[field] = _normalized_due(value)

        return normalized

    def _readback(
        self,
        *,
        request: ConnectorRequest,
        ticket_id: int,
    ) -> Mapping[str, Any]:
        credentials = self._secrets.resolve(
            self.logical_secret,
            request.context,
        )

        read_request = ConnectorRequest(
            context=ConnectorContext(
                correlation_id=request.context.correlation_id,
                principal_id=request.context.principal_id,
                organization_id=request.context.organization_id,
                client_id=request.context.client_id,
                capability="autotask.ticket.get",
                mode="observe",
            ),
            arguments={
                "ticket_id": ticket_id,
            },
        )

        prepared = AutotaskConnector.prepare_request(
            self,
            read_request,
            credentials,
        )

        email = self._trusted_email(request)

        if email is None:
            raise AutotaskTicketUpdateVerificationError(
                "trusted requester binding unavailable for readback"
            )

        resource_id = self._resolve_impersonation_resource_id(
            prepared=prepared,
            email=email,
        )

        headers = dict(prepared.headers)
        headers["ImpersonationResourceId"] = str(resource_id)

        payload = self._transport.request(
            method=prepared.method,
            url=prepared.url,
            headers=headers,
            params=prepared.params,
            json=prepared.json,
            timeout_seconds=prepared.timeout_seconds,
        )

        if not isinstance(payload, Mapping):
            raise AutotaskTicketUpdateVerificationError(
                "ticket readback was not a mapping"
            )

        item = payload.get("item")

        if isinstance(item, Mapping):
            return item

        return payload

    @staticmethod
    def _verify(
        *,
        expected: Mapping[str, Any],
        observed: Mapping[str, Any],
    ) -> None:
        observed_id = _positive_int(
            observed.get("id"),
            field="observed id",
        )

        if observed_id != expected["id"]:
            raise AutotaskTicketUpdateVerificationError(
                "ticket id failed readback"
            )

        for field, expected_value in expected.items():
            if field == "id":
                continue

            observed_value = observed.get(field)

            if field in _INTEGER_FIELDS:
                try:
                    observed_value = int(observed_value)
                except (TypeError, ValueError) as error:
                    raise AutotaskTicketUpdateVerificationError(
                        f"{field} readback was invalid"
                    ) from error

            if field == "dueDateTime":
                observed_value = str(
                    observed_value or ""
                ).strip()

            if observed_value != expected_value:
                raise AutotaskTicketUpdateVerificationError(
                    f"{field} failed readback"
                )

    def execute(
        self,
        request: ConnectorRequest,
    ) -> ConnectorResult:
        if request.context.capability != "autotask.ticket.update":
            raise ConnectorAuthorizationError(
                "ticket-update connector exposes only Ticket update"
            )

        expected = self.validated_payload(request)

        normalized_request = ConnectorRequest(
            context=request.context,
            arguments={
                **dict(request.arguments),
                "payload": expected,
            },
        )

        result = super().execute(
            normalized_request
        )

        try:
            observed = self._readback(
                request=request,
                ticket_id=expected["id"],
            )

            self._verify(
                expected=expected,
                observed=observed,
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
                AutotaskTicketUpdateVerificationError,
            ):
                raise

            raise AutotaskTicketUpdateVerificationError(
                "ticket update post-mutation verification failed"
            ) from error

        self._audit.record(
            "connector.mutation.verified",
            request.context,
            {
                "provider": self.provider_name,
                "capability": request.context.capability,
                "ticket_id": expected["id"],
            },
        )

        data = dict(result.data)

        data["jasonVerification"] = {
            "readbackVerified": True,
            "ticketId": expected["id"],
            "verifiedFields": sorted(
                key
                for key in expected
                if key != "id"
            ),
        }

        return ConnectorResult(
            capability=result.capability,
            provider=result.provider,
            data=data,
            evidence_ids=(
                *result.evidence_ids,
                f"autotask:ticket:{expected['id']}",
            ),
            warnings=result.warnings,
        )


def _validate_pre_activation_contract(
    *,
    capabilities: CapabilityRegistryService,
    providers: ExecutionProviderRegistryService,
) -> None:
    capability = capabilities.get(
        capability_name=SERVICE_TICKET_UPDATE,
        version="1.0",
    )

    provider = providers.get(
        AUTOTASK_TICKET_UPDATE_PROVIDER
    )

    if capability.lifecycle_status is not CapabilityLifecycle.BUILDING:
        raise AutotaskTicketUpdateActivationError(
            "ticket update capability is not BUILDING"
        )

    if capability.approval.required is not True:
        raise AutotaskTicketUpdateActivationError(
            "ticket update unexpectedly lacks approval"
        )

    if capability.idempotency_key_required is not True:
        raise AutotaskTicketUpdateActivationError(
            "ticket update unexpectedly lacks idempotency"
        )

    if capability.maximum_attempts != 1:
        raise AutotaskTicketUpdateActivationError(
            "ticket update permits provider retry"
        )

    if capability.client_isolation_required:
        raise AutotaskTicketUpdateActivationError(
            "Owner pilot unexpectedly requires client-bound identity"
        )

    if (
        str(
            capability.metadata.get(
                "mcp_action_enabled",
                "",
            )
        ).casefold()
        != "true"
    ):
        raise AutotaskTicketUpdateActivationError(
            "ticket update MCP action flag missing"
        )

    if provider.lifecycle_status is not ProviderLifecycle.PLANNED:
        raise AutotaskTicketUpdateActivationError(
            "ticket update provider is not PLANNED"
        )

    if provider.approval_status is not ProviderApproval.PILOT:
        raise AutotaskTicketUpdateActivationError(
            "ticket update provider approval drifted"
        )

    if provider.capabilities != frozenset(
        {
            SERVICE_TICKET_UPDATE,
        }
    ):
        raise AutotaskTicketUpdateActivationError(
            "ticket update provider capability scope drifted"
        )


def apply_autotask_ticket_update_activation(
    *,
    capabilities: CapabilityRegistryService,
    providers: ExecutionProviderRegistryService,
    profile: str | None,
) -> AutotaskTicketUpdateActivationState:
    normalized = str(
        profile or ""
    ).strip().casefold()

    if not normalized:
        return AutotaskTicketUpdateActivationState(
            profile="",
            enabled=False,
            provider_ids=(),
            capability_names=(),
        )

    if normalized != AUTOTASK_TICKET_UPDATE_PROFILE:
        raise AutotaskTicketUpdateActivationError(
            "unsupported Autotask ticket-update MCP profile"
        )

    if not autotask_ticket_update_mcp_surface_enabled():
        raise AutotaskTicketUpdateActivationError(
            "ticket-update MCP profile requires mutation "
            "execution and requester impersonation gates"
        )

    _validate_pre_activation_contract(
        capabilities=capabilities,
        providers=providers,
    )

    capabilities.set_lifecycle(
        capability_name=SERVICE_TICKET_UPDATE,
        version="1.0",
        lifecycle_status=CapabilityLifecycle.ACTIVE,
    )

    providers.set_approval(
        provider_id=AUTOTASK_TICKET_UPDATE_PROVIDER,
        approval_status=ProviderApproval.APPROVED,
    )

    providers.set_health(
        provider_id=AUTOTASK_TICKET_UPDATE_PROVIDER,
        health_status=ProviderHealth.HEALTHY,
    )

    providers.set_lifecycle(
        provider_id=AUTOTASK_TICKET_UPDATE_PROVIDER,
        lifecycle_status=ProviderLifecycle.AVAILABLE,
    )

    return AutotaskTicketUpdateActivationState(
        profile=normalized,
        enabled=True,
        provider_ids=(
            AUTOTASK_TICKET_UPDATE_PROVIDER,
        ),
        capability_names=(
            SERVICE_TICKET_UPDATE,
        ),
    )


def register_autotask_ticket_update_runtime_foundation(
    *,
    capabilities: CapabilityRegistryService,
    providers: ExecutionProviderRegistryService,
    now: datetime,
) -> AutotaskTicketUpdateActivationState:
    capabilities.register(
        _ticket_update_definition(
            now=now,
        )
    )

    providers.register(
        _ticket_update_provider(
            now=now,
        )
    )

    return apply_autotask_ticket_update_activation(
        capabilities=capabilities,
        providers=providers,
        profile=os.getenv(
            AUTOTASK_TICKET_UPDATE_PROFILE_ENV,
            "",
        ),
    )


def build_autotask_ticket_update_invoker(
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

    connector = AutotaskTicketUpdateConnector(
        secrets=secrets,
        transport=transport,
        audit=audit,
        bindings=bindings,
    )

    return GovernedConnectorCapabilityInvoker(
        connectors={
            AUTOTASK_TICKET_UPDATE_PROVIDER: connector,
        },
        provider_capability_map=_PROVIDER_CAPABILITY_MAP,
    )


def register_autotask_ticket_update_invoker(
    *,
    invokers: CapabilityInvokerRegistry,
    invoker: CapabilityInvoker,
) -> None:
    invokers.register(
        SERVICE_TICKET_UPDATE,
        invoker,
    )
