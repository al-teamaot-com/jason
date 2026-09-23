from __future__ import annotations

import os
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

from connectors.autotask.mutation_connector import (
    AUTOTASK_MUTATION_ENABLED_ENV,
    AutotaskMutationConnector,
    autotask_mutation_execution_enabled,
)
from connectors.autotask.impersonating_connector import TrustedPrincipalBindingResolver
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
    SERVICE_TICKET_CREATE,
    autotask_mutation_capability_definitions,
)
from orchestrator.service import CapabilityInvoker

from .autotask_ticket_update import AutotaskTicketUpdateConnector, _positive_int


AUTOTASK_TICKET_CREATE_PROVIDER = "autotask_ticket_create"
AUTOTASK_TICKET_CREATE_PROFILE_ENV = "JASON_AUTOTASK_TICKET_CREATE_MCP_PROFILE"
AUTOTASK_TICKET_CREATE_PROFILE = "owner-ticket-create-v1"

SAFE_TICKET_CREATE_FIELDS = frozenset(
    {
        "companyID",
        "title",
        "description",
        "status",
        "priority",
        "queueID",
        "assignedResourceID",
        "dueDateTime",
        "configurationItemID",
        "billingCodeID",
        "issueType",
        "subIssueType",
        "ticketType",
        "contactID",
        "source",
    }
)
INTEGER_CREATE_FIELDS = frozenset(
    {
        "companyID",
        "status",
        "priority",
        "queueID",
        "assignedResourceID",
        "configurationItemID",
        "billingCodeID",
        "issueType",
        "subIssueType",
        "ticketType",
        "contactID",
        "source",
    }
)
_PROVIDER_CAPABILITY_MAP = {
    (AUTOTASK_TICKET_CREATE_PROVIDER, SERVICE_TICKET_CREATE): "autotask.ticket.create",
}


class AutotaskTicketCreateActivationError(RuntimeError):
    pass


class AutotaskTicketCreateVerificationError(ConnectorError):
    error_code = "AUTOTASK_TICKET_CREATE_VERIFICATION_FAILED"


@dataclass(frozen=True, slots=True)
class AutotaskTicketCreateActivationState:
    profile: str
    enabled: bool
    provider_ids: tuple[str, ...]
    capability_names: tuple[str, ...]


def autotask_ticket_create_mcp_surface_enabled() -> bool:
    profile = os.getenv(AUTOTASK_TICKET_CREATE_PROFILE_ENV, "").strip().casefold()
    mutation_enabled = os.getenv(AUTOTASK_MUTATION_ENABLED_ENV, "").strip().casefold()
    return profile == AUTOTASK_TICKET_CREATE_PROFILE and mutation_enabled == "true"


def _ticket_create_definition(*, now: datetime):
    matches = [
        definition
        for definition in autotask_mutation_capability_definitions(now=now)
        if definition.capability_name == SERVICE_TICKET_CREATE
    ]
    if len(matches) != 1:
        raise AutotaskTicketCreateActivationError("ticket create capability definition is not unique")
    base = matches[0]
    metadata = dict(base.metadata)
    metadata.update(
        {
            "activation_state": "ticket_create_mcp_source_only_not_activated",
            "mcp_action_enabled": "true",
            "mcp_tool_name": "execute_governed_capability",
            "conversation_authenticated_imperative_is_approval": "true",
            "pilot_scope": "aot_owner_organization_scope",
            "safe_create_fields": ",".join(sorted(SAFE_TICKET_CREATE_FIELDS)),
        }
    )
    evidence = CapabilityEvidence(
        required=True,
        requirements=(
            "authenticated requester identity",
            "provider requester authorization evidence",
            "bounded validated ticket payload",
            "provider mutation result",
            "post-create ticket readback",
        ),
        verification_requirements=(
            "requester maps to exactly one active Autotask Resource",
            "provider-native requester impersonation is applied",
            "requester Autotask permissions permit Ticket create",
            "only explicitly allowed ticket fields are supplied",
            "provider returns one durable ticket id",
            "post-create readback matches the created ticket",
        ),
    )
    return replace(
        base,
        business_purpose="Create one bounded Autotask service ticket and verify its durable readback.",
        client_isolation_required=False,
        evidence=evidence,
        metadata=metadata,
    )


def _ticket_create_provider(*, now: datetime) -> ExecutionProvider:
    return ExecutionProvider(
        provider_id=AUTOTASK_TICKET_CREATE_PROVIDER,
        display_name="Autotask PSA Governed Ticket Create",
        provider_type=ProviderType.EXTERNAL_CONNECTOR,
        lifecycle_status=ProviderLifecycle.PLANNED,
        health_status=ProviderHealth.UNKNOWN,
        approval_status=ProviderApproval.PILOT,
        execution_modes=frozenset({"deterministic"}),
        capabilities=frozenset({SERVICE_TICKET_CREATE}),
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
            business_justification="Permit one narrowly governed Autotask ticket create through requester impersonation.",
            review_interval_days=30,
            last_reviewed_at=now,
            retirement_criteria=(
                "Provider-native requester authorization cannot be proven.",
                "A safer approved mutation capability replaces this pilot.",
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
            "mutation_scope": "ticket_create_safe_fields_only",
            "provider_native_impersonation_required": "true",
            "activation_state": "ticket_create_mcp_source_only_not_activated",
        },
    )


@dataclass(frozen=True, slots=True)
class _PreparedAutotaskTicketCreate:
    request: ConnectorRequest
    expected: Mapping[str, Any]
    prepared: PreparedRequest


class AutotaskTicketCreateConnector(AutotaskTicketUpdateConnector):
    capabilities = frozenset({"autotask.ticket.create"})

    @staticmethod
    def validated_payload(request: ConnectorRequest) -> dict[str, Any]:
        raw = request.arguments.get("payload")
        if not isinstance(raw, Mapping):
            raise ValueError("ticket create requires a structured payload")
        payload = dict(raw)
        unknown = set(payload) - SAFE_TICKET_CREATE_FIELDS
        if unknown:
            raise PermissionError("AUTOTASK_TICKET_CREATE_FIELD_NOT_ALLOWED")
        raw_company_id = payload.get("companyID")
        if isinstance(raw_company_id, bool):
            raise ValueError("companyID must be a non-negative integer")
        try:
            company_id = int(raw_company_id)
        except (TypeError, ValueError) as error:
            raise ValueError("companyID must be a non-negative integer") from error
        if company_id < 0:
            raise ValueError("companyID must be a non-negative integer")
        title = str(payload.get("title") or "").strip()
        if not title or len(title) > 512:
            raise ValueError("title must be a bounded non-empty string")
        normalized: dict[str, Any] = {"companyID": company_id, "title": title}
        if "description" in payload:
            description = str(payload.get("description") or "").strip()
            if len(description) > 20000:
                raise ValueError("description exceeds bounded create limit")
            normalized["description"] = description
        for field in set(payload) - {"companyID", "title", "description"}:
            value = payload[field]
            if field in INTEGER_CREATE_FIELDS:
                normalized[field] = _positive_int(value, field=field)
            elif field == "dueDateTime":
                text = str(value or "").strip()
                if not text or len(text) > 128:
                    raise ValueError("dueDateTime must be a bounded non-empty datetime string")
                normalized[field] = text
        return normalized

    @staticmethod
    def _created_ticket_id(data: Mapping[str, Any]) -> int:
        for key in ("itemId", "itemID", "id"):
            if key in data:
                return _positive_int(data.get(key), field="created ticket id")
        item = data.get("item")
        if isinstance(item, Mapping) and "id" in item:
            return _positive_int(item.get("id"), field="created ticket id")
        raise AutotaskTicketCreateVerificationError("provider create response did not contain a durable ticket id")

    def prepare_governed_execution(
        self, request: ConnectorRequest
    ) -> ProviderPreparedExecution:
        if request.context.capability != "autotask.ticket.create":
            raise ConnectorAuthorizationError("ticket-create connector exposes only Ticket create")
        raw = request.arguments.get("payload")
        if not isinstance(raw, Mapping):
            raise ValueError("ticket create requires a structured payload")
        raw_payload = dict(raw)
        resolved_payload = self._resolve_symbolic_payload(request)
        normalized_input = ConnectorRequest(
            context=request.context,
            arguments={**dict(request.arguments), "payload": resolved_payload},
        )
        expected = self.validated_payload(normalized_input)
        normalized_request = ConnectorRequest(
            context=request.context,
            arguments={**dict(request.arguments), "payload": expected},
        )
        symbolic_resolutions: dict[str, Any] = {}
        for field in ("status", "queueID", "ticketType", "issueType", "subIssueType", "billingCodeID"):
            if field not in raw_payload or not self._label_requires_resolution(raw_payload[field]):
                continue
            symbolic_resolutions[field] = {
                "symbolic": str(raw_payload[field]).strip(),
                "resolved": expected[field],
            }
        if normalized_request.context.mode != "execute":
            raise ConnectorAuthorizationError("Autotask mutation requires explicit execute mode.")
        if not autotask_mutation_execution_enabled():
            raise PermissionError("AUTOTASK_MUTATION_EXECUTION_DISABLED")
        credentials = self._secrets.resolve(self.logical_secret, normalized_request.context)
        prepared = AutotaskMutationConnector.prepare_request(self, normalized_request, credentials)
        relative_path = prepared.audit_operation or urlsplit(prepared.url).path
        return ProviderPreparedExecution(
            provider_capability=request.context.capability,
            action_method=prepared.method,
            resource_type="service_ticket",
            resource_identifier=None,
            normalized_path=relative_path,
            payload=dict(prepared.json or {}),
            parameters=dict(prepared.params or {}),
            symbolic_resolutions=symbolic_resolutions,
            opaque=_PreparedAutotaskTicketCreate(
                request=normalized_request, expected=dict(expected), prepared=prepared
            ),
        )

    def execute_governed_execution(
        self, prepared_execution: ProviderPreparedExecution
    ) -> ConnectorResult:
        opaque = prepared_execution.opaque
        if not isinstance(opaque, _PreparedAutotaskTicketCreate):
            raise PermissionError("invalid Autotask ticket-create prepared execution")
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
        if prepared_execution.resource_identifier is not None:
            raise PermissionError("ticket-create execution plan must not pre-authorize a provider-created ticket id")
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
        ticket_id = self._created_ticket_id(result.data)
        try:
            observed = self._readback(request=request, ticket_id=ticket_id)
            observed_id = _positive_int(observed.get("id"), field="observed id")
            if observed_id != ticket_id:
                raise AutotaskTicketCreateVerificationError("ticket id failed readback")
            if int(observed.get("companyID")) != expected["companyID"]:
                raise AutotaskTicketCreateVerificationError("companyID failed readback")
            if str(observed.get("title") or "").strip() != expected["title"]:
                raise AutotaskTicketCreateVerificationError("title failed readback")
        except Exception as error:
            self._audit.record(
                "connector.mutation.verification_failed", request.context,
                {"provider": self.provider_name, "capability": request.context.capability, "error_type": type(error).__name__},
            )
            if isinstance(error, AutotaskTicketCreateVerificationError):
                raise
            raise AutotaskTicketCreateVerificationError("ticket create post-mutation verification failed") from error
        self._audit.record(
            "connector.mutation.verified", request.context,
            {"provider": self.provider_name, "capability": request.context.capability, "ticket_id": ticket_id},
        )
        data = dict(result.data)
        data["jasonVerification"] = {
            "readbackVerified": True, "ticketId": ticket_id, "verifiedFields": ["companyID", "title"]
        }
        return ConnectorResult(
            capability=result.capability, provider=result.provider, data=data,
            evidence_ids=(*result.evidence_ids, f"autotask:ticket:{ticket_id}"), warnings=result.warnings,
        )

    def execute(self, request: ConnectorRequest) -> ConnectorResult:
        if request.context.capability != "autotask.ticket.create":
            raise ConnectorAuthorizationError("ticket-create connector exposes only Ticket create")
        resolved_payload = self._resolve_symbolic_payload(request)
        normalized_input = ConnectorRequest(
            context=request.context,
            arguments={**dict(request.arguments), "payload": resolved_payload},
        )
        expected = self.validated_payload(normalized_input)
        normalized_request = ConnectorRequest(
            context=request.context,
            arguments={**dict(request.arguments), "payload": expected},
        )
        result = AutotaskMutationConnector.execute(self, normalized_request)
        ticket_id = self._created_ticket_id(result.data)
        try:
            observed = self._readback(request=request, ticket_id=ticket_id)
            observed_id = _positive_int(observed.get("id"), field="observed id")
            if observed_id != ticket_id:
                raise AutotaskTicketCreateVerificationError("ticket id failed readback")
            if int(observed.get("companyID")) != expected["companyID"]:
                raise AutotaskTicketCreateVerificationError("companyID failed readback")
            if str(observed.get("title") or "").strip() != expected["title"]:
                raise AutotaskTicketCreateVerificationError("title failed readback")
        except Exception as error:
            self._audit.record(
                "connector.mutation.verification_failed",
                request.context,
                {"provider": self.provider_name, "capability": request.context.capability, "error_type": type(error).__name__},
            )
            if isinstance(error, AutotaskTicketCreateVerificationError):
                raise
            raise AutotaskTicketCreateVerificationError("ticket create post-mutation verification failed") from error
        self._audit.record(
            "connector.mutation.verified",
            request.context,
            {"provider": self.provider_name, "capability": request.context.capability, "ticket_id": ticket_id},
        )
        data = dict(result.data)
        data["jasonVerification"] = {
            "readbackVerified": True,
            "ticketId": ticket_id,
            "verifiedFields": ["companyID", "title"],
        }
        return ConnectorResult(
            capability=result.capability,
            provider=result.provider,
            data=data,
            evidence_ids=(*result.evidence_ids, f"autotask:ticket:{ticket_id}"),
            warnings=result.warnings,
        )


def _validate_pre_activation_contract(*, capabilities: CapabilityRegistryService, providers: ExecutionProviderRegistryService) -> None:
    capability = capabilities.get(capability_name=SERVICE_TICKET_CREATE, version="1.0")
    provider = providers.get(AUTOTASK_TICKET_CREATE_PROVIDER)
    if capability.lifecycle_status is not CapabilityLifecycle.BUILDING:
        raise AutotaskTicketCreateActivationError("ticket create capability is not BUILDING")
    if capability.approval.required is not True or capability.idempotency_key_required is not True:
        raise AutotaskTicketCreateActivationError("ticket create governance contract drifted")
    if capability.maximum_attempts != 1:
        raise AutotaskTicketCreateActivationError("ticket create permits provider retry")
    if capability.client_isolation_required:
        raise AutotaskTicketCreateActivationError("Owner pilot unexpectedly requires client-bound identity")
    if str(capability.metadata.get("mcp_action_enabled", "")).casefold() != "true":
        raise AutotaskTicketCreateActivationError("ticket create MCP action flag missing")
    if provider.lifecycle_status is not ProviderLifecycle.PLANNED or provider.approval_status is not ProviderApproval.PILOT:
        raise AutotaskTicketCreateActivationError("ticket create provider activation contract drifted")
    if provider.capabilities != frozenset({SERVICE_TICKET_CREATE}):
        raise AutotaskTicketCreateActivationError("ticket create provider capability scope drifted")


def apply_autotask_ticket_create_activation(*, capabilities: CapabilityRegistryService, providers: ExecutionProviderRegistryService, profile: str | None) -> AutotaskTicketCreateActivationState:
    normalized = str(profile or "").strip().casefold()
    if not normalized:
        return AutotaskTicketCreateActivationState(profile="", enabled=False, provider_ids=(), capability_names=())
    if normalized != AUTOTASK_TICKET_CREATE_PROFILE:
        raise AutotaskTicketCreateActivationError("unsupported Autotask ticket-create MCP profile")
    if not autotask_ticket_create_mcp_surface_enabled():
        raise AutotaskTicketCreateActivationError("ticket-create MCP profile requires mutation execution gate")
    _validate_pre_activation_contract(capabilities=capabilities, providers=providers)
    capabilities.set_lifecycle(capability_name=SERVICE_TICKET_CREATE, version="1.0", lifecycle_status=CapabilityLifecycle.ACTIVE)
    providers.set_approval(provider_id=AUTOTASK_TICKET_CREATE_PROVIDER, approval_status=ProviderApproval.APPROVED)
    providers.set_health(provider_id=AUTOTASK_TICKET_CREATE_PROVIDER, health_status=ProviderHealth.HEALTHY)
    providers.set_lifecycle(provider_id=AUTOTASK_TICKET_CREATE_PROVIDER, lifecycle_status=ProviderLifecycle.AVAILABLE)
    return AutotaskTicketCreateActivationState(
        profile=normalized,
        enabled=True,
        provider_ids=(AUTOTASK_TICKET_CREATE_PROVIDER,),
        capability_names=(SERVICE_TICKET_CREATE,),
    )


def register_autotask_ticket_create_runtime_foundation(*, capabilities: CapabilityRegistryService, providers: ExecutionProviderRegistryService, now: datetime) -> AutotaskTicketCreateActivationState:
    capabilities.register(_ticket_create_definition(now=now))
    providers.register(_ticket_create_provider(now=now))
    return apply_autotask_ticket_create_activation(
        capabilities=capabilities,
        providers=providers,
        profile=os.getenv(AUTOTASK_TICKET_CREATE_PROFILE_ENV, ""),
    )


def build_autotask_ticket_create_invoker(*, openbao_url: str, role_id_path: Path, secret_id_path: Path, transport: HttpTransport, audit: AuditSink, bindings: TrustedPrincipalBindingResolver) -> CapabilityInvoker:
    secrets = OpenBaoSecretResolver(base_url=openbao_url, role_id_path=role_id_path, secret_id_path=secret_id_path)
    connector = AutotaskTicketCreateConnector(secrets=secrets, transport=transport, audit=audit, bindings=bindings)
    return GovernedConnectorCapabilityInvoker(
        connectors={AUTOTASK_TICKET_CREATE_PROVIDER: connector},
        provider_capability_map=_PROVIDER_CAPABILITY_MAP,
    )


def register_autotask_ticket_create_invoker(*, invokers: CapabilityInvokerRegistry, invoker: CapabilityInvoker) -> None:
    invokers.register(SERVICE_TICKET_CREATE, invoker)
