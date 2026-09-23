from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping
from uuid import UUID

from connectors.core.contracts import (
    AuditSink,
    ConnectorAuthorizationError,
    ConnectorContext,
    ConnectorError,
    ConnectorRequest,
    ConnectorResult,
    HttpTransport,
    SecretResolver,
)
from connectors.core.openbao_secrets import OpenBaoSecretResolver
from connectors.datto_rmm.auth import acquire_access_token, require_durable_credentials
from connectors.datto_rmm.execution_identity import DATTO_RMM_EXECUTION_LOGICAL_SECRET
from kernel.capabilities import (
    CapabilityApproval,
    CapabilityDefinition,
    CapabilityEvidence,
    CapabilityLifecycle,
    CapabilityRegistryService,
    CapabilityRisk,
    CapabilityStewardship,
    IdempotencyBehavior,
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
from orchestrator.connector_invoker import GovernedConnectorCapabilityInvoker, ProviderPreparedExecution
from orchestrator.execution_plan import normalize_provider_relative_path
from orchestrator.invokers import CapabilityInvokerRegistry
from orchestrator.service import CapabilityInvoker


ENDPOINT_ALERT_RESOLVE = "endpoint.alert.resolve"
DATTO_RMM_ALERT_RESOLUTION_PROVIDER = "datto_rmm_alert_resolution"
DATTO_RMM_PROVIDER_CAPABILITY = "datto_rmm.alert.resolve"

DATTO_ALERT_RESOLUTION_PROFILE_ENV = "JASON_DATTO_ALERT_RESOLUTION_MCP_PROFILE"
DATTO_ALERT_RESOLUTION_PROFILE = "owner-alert-resolution-v1"
DATTO_EXECUTION_ROLE_ID_PATH_ENV = "JASON_DATTO_EXECUTION_OPENBAO_ROLE_ID_PATH"
DATTO_EXECUTION_SECRET_ID_PATH_ENV = "JASON_DATTO_EXECUTION_OPENBAO_SECRET_ID_PATH"

DEFAULT_ROLE_ID_PATH = Path("/run/jason-secrets/openbao/datto-rmm-execution/role_id")
DEFAULT_SECRET_ID_PATH = Path("/run/jason-secrets/openbao/datto-rmm-execution/secret_id")

_PROVIDER_CAPABILITY_MAP = {
    (DATTO_RMM_ALERT_RESOLUTION_PROVIDER, ENDPOINT_ALERT_RESOLVE):
        DATTO_RMM_PROVIDER_CAPABILITY,
}


class DattoRmmAlertResolutionActivationError(RuntimeError):
    pass


class DattoRmmAlertResolutionVerificationError(ConnectorError):
    error_code = "DATTO_RMM_ALERT_RESOLUTION_VERIFICATION_FAILED"


@dataclass(frozen=True, slots=True)
class DattoAlertResolutionActivationState:
    profile: str
    enabled: bool
    provider_ids: tuple[str, ...]
    capability_names: tuple[str, ...]


def _canonical_uuid(value: object, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} is required")
    try:
        parsed = UUID(text)
    except ValueError as exc:
        raise ValueError(f"{field} must be a UUID") from exc
    canonical = str(parsed)
    if text.casefold() != canonical:
        raise ValueError(f"{field} must use canonical UUID form")
    return canonical


def datto_alert_resolution_mcp_surface_enabled() -> bool:
    return (
        os.getenv(DATTO_ALERT_RESOLUTION_PROFILE_ENV, "").strip().casefold()
        == DATTO_ALERT_RESOLUTION_PROFILE
    )


def _capability_definition(*, now: datetime) -> CapabilityDefinition:
    return CapabilityDefinition(
        capability_name=ENDPOINT_ALERT_RESOLVE,
        version="1.0",
        display_name="Resolve Endpoint Alert",
        lifecycle_status=CapabilityLifecycle.BUILDING,
        business_purpose=(
            "Resolve one exact Datto RMM endpoint alert after the underlying "
            "issue has been remediated and verify provider readback."
        ),
        owner_service="Jason Governed Actions",
        architectural_capability_ids=frozenset({"JAC-005", "JAC-006", "JAC-013"}),
        risk_level=CapabilityRisk.MEDIUM,
        data_classifications=frozenset({"internal"}),
        permitted_execution_modes=frozenset({"deterministic"}),
        input_schema_reference="schema://jason/endpoint-alert-resolve/1.0",
        output_schema_reference="schema://jason/endpoint-alert-resolve-result/1.0",
        invoking_roles=frozenset({"orchestrator"}),
        approval=CapabilityApproval(required=True, approver_classes=("owner",)),
        evidence=CapabilityEvidence(
            required=True,
            requirements=(
                "authenticated requester identity",
                "exact alert UID",
                "exact endpoint UID",
                "pre-mutation alert read",
                "provider mutation result",
                "post-mutation alert readback",
            ),
            verification_requirements=(
                "alert UID is canonical and exact",
                "pre-read alert belongs to the exact endpoint UID",
                "at most one provider resolve request is issued",
                "post-read alert UID matches the requested alert",
                "post-read reports resolved=true",
            ),
        ),
        dependencies=frozenset({
            "identity.authorization.resolve",
            "governance.action.evaluate",
            "endpoint.alert.search",
            "endpoint.alert.history.search",
        }),
        idempotency_behavior=IdempotencyBehavior.CONDITIONALLY_IDEMPOTENT,
        idempotency_key_required=True,
        timeout_seconds=30,
        maximum_attempts=1,
        failure_behavior=(
            "Fail closed without alert substitution, device substitution, retry, "
            "direct-provider fallback, or unverified success."
        ),
        tenant_isolation_required=True,
        client_isolation_required=False,
        stewardship=CapabilityStewardship(
            steward="technology-steward",
            business_justification=(
                "Allow Jason to complete remediated Datto monitoring workflows "
                "without leaving stale alerts open."
            ),
            review_interval_days=30,
            retirement_criteria=(
                "Exact alert/device precondition verification cannot be proven.",
                "Provider no longer supports bounded alert resolution.",
            ),
            authoritative_change_sources=("Datto RMM API documentation",),
            last_reviewed_at=now,
            operational_owner="AOT IT Operations",
            approval_owner="AOT Owner",
        ),
        created_at=now,
        metadata={
            "provider_neutral": "true",
            "read_only": "false",
            "write_capability": "true",
            "resource_types": "endpoint_alert,endpoint",
            "operation": "resolve",
            "selector_keys": "alert_uid,device_uid",
            "mcp_action_enabled": "true",
            "mcp_tool_name": "execute_governed_capability",
            "conversation_authenticated_imperative_is_approval": "true",
            "pilot_scope": "aot_exact_alert_exact_endpoint",
            "provider_native_execution_identity_required": "true",
            "activation_state": "datto_alert_resolution_source_only_not_activated",
        },
    )


def _provider(*, now: datetime) -> ExecutionProvider:
    return ExecutionProvider(
        provider_id=DATTO_RMM_ALERT_RESOLUTION_PROVIDER,
        display_name="Datto RMM Governed Alert Resolution",
        provider_type=ProviderType.EXTERNAL_CONNECTOR,
        lifecycle_status=ProviderLifecycle.PLANNED,
        health_status=ProviderHealth.UNKNOWN,
        approval_status=ProviderApproval.PILOT,
        execution_modes=frozenset({"deterministic"}),
        capabilities=frozenset({ENDPOINT_ALERT_RESOLVE}),
        supported_classifications=frozenset({"internal"}),
        regions=frozenset(),
        limits=ProviderLimits(
            maximum_concurrent_executions=1,
            maximum_requests_per_minute=10,
            maximum_execution_seconds=30,
        ),
        features=ProviderFeatures(structured_output=True),
        pricing_profile_id="zero-cost-foundation",
        stewardship=ProviderStewardship(
            technology_steward="technology-steward",
            business_justification=(
                "Resolve one exact Datto RMM alert through the separate "
                "least-privilege execution identity."
            ),
            review_interval_days=30,
            last_reviewed_at=now,
            retirement_criteria=(
                "Execution identity exceeds approved authority.",
                "Exact alert readback cannot be verified.",
            ),
            vendor_change_sources=("Datto RMM API documentation",),
            operational_owner="AOT IT Operations",
            approval_owner="AOT Owner",
        ),
        created_at=now,
        metadata={
            "connector_id": "datto_rmm",
            "resource_authority": "endpoint_alert",
            "write_capability": "true",
            "mutation_scope": "exact_alert_resolve_only",
            "logical_secret": DATTO_RMM_EXECUTION_LOGICAL_SECRET,
            "activation_state": "datto_alert_resolution_source_only_not_activated",
        },
    )


def apply_datto_alert_resolution_activation(
    *,
    capabilities: CapabilityRegistryService,
    providers: ExecutionProviderRegistryService,
    profile: str | None,
) -> DattoAlertResolutionActivationState:
    normalized = str(profile or "").strip().casefold()
    if not normalized:
        return DattoAlertResolutionActivationState("", False, (), ())
    if normalized != DATTO_ALERT_RESOLUTION_PROFILE:
        raise DattoRmmAlertResolutionActivationError(
            "unsupported Datto alert-resolution MCP profile"
        )

    capability = capabilities.get(
        capability_name=ENDPOINT_ALERT_RESOLVE,
        version="1.0",
    )
    provider = providers.get(DATTO_RMM_ALERT_RESOLUTION_PROVIDER)

    if capability.lifecycle_status is not CapabilityLifecycle.BUILDING:
        raise DattoRmmAlertResolutionActivationError(
            "Datto alert-resolution capability is not BUILDING"
        )
    if not capability.approval.required or capability.maximum_attempts != 1:
        raise DattoRmmAlertResolutionActivationError(
            "Datto alert-resolution governance contract is invalid"
        )
    if provider.lifecycle_status is not ProviderLifecycle.PLANNED:
        raise DattoRmmAlertResolutionActivationError(
            "Datto alert-resolution provider is not PLANNED"
        )

    capabilities.set_lifecycle(
        capability_name=ENDPOINT_ALERT_RESOLVE,
        version="1.0",
        lifecycle_status=CapabilityLifecycle.ACTIVE,
    )
    providers.set_approval(
        provider_id=DATTO_RMM_ALERT_RESOLUTION_PROVIDER,
        approval_status=ProviderApproval.APPROVED,
    )
    providers.set_health(
        provider_id=DATTO_RMM_ALERT_RESOLUTION_PROVIDER,
        health_status=ProviderHealth.HEALTHY,
    )
    providers.set_lifecycle(
        provider_id=DATTO_RMM_ALERT_RESOLUTION_PROVIDER,
        lifecycle_status=ProviderLifecycle.AVAILABLE,
    )

    return DattoAlertResolutionActivationState(
        normalized,
        True,
        (DATTO_RMM_ALERT_RESOLUTION_PROVIDER,),
        (ENDPOINT_ALERT_RESOLVE,),
    )


def register_datto_alert_resolution_runtime_foundation(
    *,
    capabilities: CapabilityRegistryService,
    providers: ExecutionProviderRegistryService,
    now: datetime,
) -> DattoAlertResolutionActivationState:
    capabilities.register(_capability_definition(now=now))
    providers.register(_provider(now=now))
    return apply_datto_alert_resolution_activation(
        capabilities=capabilities,
        providers=providers,
        profile=os.getenv(DATTO_ALERT_RESOLUTION_PROFILE_ENV, ""),
    )


@dataclass(frozen=True, slots=True)
class _PreparedDattoAlertResolution:
    request: ConnectorRequest
    alert_uid: str
    device_uid: str
    already_resolved: bool
    method: str
    path: str
    credentials: Mapping[str, str]
    token: Any


class DattoRmmAlertResolutionConnector:
    provider_name = "datto_rmm"
    capabilities = frozenset({DATTO_RMM_PROVIDER_CAPABILITY})

    def __init__(
        self,
        *,
        secrets: SecretResolver,
        transport: HttpTransport,
        audit: AuditSink,
    ) -> None:
        self._secrets = secrets
        self._transport = transport
        self._audit = audit

    @staticmethod
    def _alert_device_uid(payload: Mapping[str, Any]) -> str:
        source = payload.get("alertSourceInfo")
        if not isinstance(source, Mapping):
            return ""
        return str(source.get("deviceUid") or "").strip()

    @staticmethod
    def _alert_uid(payload: Mapping[str, Any]) -> str:
        return str(payload.get("alertUid") or payload.get("uid") or "").strip()

    def prepare_governed_execution(
        self, request: ConnectorRequest
    ) -> ProviderPreparedExecution:
        if request.context.capability != DATTO_RMM_PROVIDER_CAPABILITY:
            raise ConnectorAuthorizationError(
                "Datto alert-resolution connector exposes only alert resolution"
            )
        if request.context.mode != "execute":
            raise ConnectorAuthorizationError(
                "Datto alert resolution requires execute mode"
            )

        alert_uid = _canonical_uuid(request.arguments.get("alert_uid"), "alert_uid")
        device_uid = _canonical_uuid(request.arguments.get("device_uid"), "device_uid")
        unknown = set(request.arguments) - {"alert_uid", "device_uid"}
        if unknown:
            raise ValueError(
                "unsupported alert-resolution arguments: " + ", ".join(sorted(unknown))
            )

        credentials = dict(
            self._secrets.resolve(DATTO_RMM_EXECUTION_LOGICAL_SECRET, request.context)
        )
        require_durable_credentials(credentials)
        token = acquire_access_token(credentials=credentials)
        headers = {
            "Authorization": f"{token.token_type} {token.access_token}",
            "Accept": "application/json",
        }
        base = credentials["api_url"].rstrip("/")
        alert_path = f"/api/v2/alert/{alert_uid}"
        before = self._transport.request(
            method="GET",
            url=base + alert_path,
            headers=headers,
            params=None,
            json=None,
            timeout_seconds=10.0,
        )
        if not isinstance(before, Mapping):
            raise DattoRmmAlertResolutionVerificationError(
                "alert pre-read was not an object"
            )
        if self._alert_uid(before) != alert_uid:
            raise DattoRmmAlertResolutionVerificationError(
                "alert pre-read UID did not match requested alert"
            )
        if self._alert_device_uid(before) != device_uid:
            raise DattoRmmAlertResolutionVerificationError(
                "alert pre-read device UID did not match requested endpoint"
            )

        already_resolved = before.get("resolved") is True
        method = "NOOP" if already_resolved else "POST"
        path = f"{alert_path}/resolve"
        return ProviderPreparedExecution(
            provider_capability=request.context.capability,
            action_method=method,
            resource_type="endpoint_alert",
            resource_identifier=alert_uid,
            normalized_path=path,
            payload={},
            parameters={
                "alert_uid": alert_uid,
                "device_uid": device_uid,
                "already_resolved": already_resolved,
            },
            symbolic_resolutions={},
            opaque=_PreparedDattoAlertResolution(
                request=request,
                alert_uid=alert_uid,
                device_uid=device_uid,
                already_resolved=already_resolved,
                method=method,
                path=path,
                credentials=credentials,
                token=token,
            ),
        )

    def execute_governed_execution(
        self, prepared_execution: ProviderPreparedExecution
    ) -> ConnectorResult:
        opaque = prepared_execution.opaque
        if not isinstance(opaque, _PreparedDattoAlertResolution):
            raise PermissionError("invalid Datto alert-resolution prepared execution")
        request = opaque.request
        if prepared_execution.provider_capability != request.context.capability:
            raise PermissionError("prepared Datto alert capability changed")
        if opaque.method != str(prepared_execution.action_method).strip().upper():
            raise PermissionError("prepared Datto alert action changed")
        if normalize_provider_relative_path(opaque.path) != normalize_provider_relative_path(prepared_execution.normalized_path):
            raise PermissionError("prepared Datto alert path changed")
        if opaque.alert_uid != str(prepared_execution.resource_identifier or ""):
            raise PermissionError("prepared Datto alert target changed")
        if dict(prepared_execution.payload):
            raise PermissionError("Datto alert resolution plan must not contain a provider body")
        expected_parameters = {
            "alert_uid": opaque.alert_uid,
            "device_uid": opaque.device_uid,
            "already_resolved": opaque.already_resolved,
        }
        if expected_parameters != dict(prepared_execution.parameters):
            raise PermissionError("prepared Datto alert parameters changed")

        if opaque.already_resolved:
            return ConnectorResult(
                capability=request.context.capability,
                provider=self.provider_name,
                data={
                    "status": "verified",
                    "alert_uid": opaque.alert_uid,
                    "device_uid": opaque.device_uid,
                    "resolved": True,
                    "already_resolved": True,
                    "mutation_performed": False,
                    "readback_verified": True,
                },
                evidence_ids=(f"datto-rmm:alert:{opaque.alert_uid}",),
            )

        credentials = opaque.credentials
        token = opaque.token
        headers = {
            "Authorization": f"{token.token_type} {token.access_token}",
            "Accept": "application/json",
        }
        base = credentials["api_url"].rstrip("/")
        alert_path = f"/api/v2/alert/{opaque.alert_uid}"
        try:
            self._audit.record(
                "connector.mutation.requested",
                request.context,
                {
                    "provider": self.provider_name,
                    "capability": request.context.capability,
                    "operation": "alert.resolve",
                    "alert_uid_present": True,
                    "device_uid_present": True,
                },
            )
            self._transport.request(
                method="POST",
                url=base + opaque.path,
                headers=headers,
                params=None,
                json=None,
                timeout_seconds=20.0,
            )
            self._audit.record(
                "connector.mutation.completed",
                request.context,
                {
                    "provider": self.provider_name,
                    "capability": request.context.capability,
                    "provider_attempts": 1,
                },
            )
            after = self._transport.request(
                method="GET",
                url=base + alert_path,
                headers=headers,
                params=None,
                json=None,
                timeout_seconds=10.0,
            )
            if not isinstance(after, Mapping):
                raise DattoRmmAlertResolutionVerificationError(
                    "alert post-read was not an object"
                )
            if self._alert_uid(after) != opaque.alert_uid:
                raise DattoRmmAlertResolutionVerificationError(
                    "alert post-read UID did not match requested alert"
                )
            if self._alert_device_uid(after) != opaque.device_uid:
                raise DattoRmmAlertResolutionVerificationError(
                    "alert post-read device UID did not match requested endpoint"
                )
            if after.get("resolved") is not True:
                raise DattoRmmAlertResolutionVerificationError(
                    "alert post-read did not verify resolved=true"
                )
            self._audit.record(
                "connector.mutation.verified",
                request.context,
                {
                    "provider": self.provider_name,
                    "capability": request.context.capability,
                    "resolved": True,
                    "readback_verified": True,
                },
            )
            return ConnectorResult(
                capability=request.context.capability,
                provider=self.provider_name,
                data={
                    "status": "verified",
                    "alert_uid": opaque.alert_uid,
                    "device_uid": opaque.device_uid,
                    "resolved": True,
                    "already_resolved": False,
                    "mutation_performed": True,
                    "readback_verified": True,
                },
                evidence_ids=(f"datto-rmm:alert:{opaque.alert_uid}",),
            )
        except Exception as error:
            self._audit.record(
                "connector.mutation.failed",
                request.context,
                {
                    "provider": self.provider_name,
                    "capability": request.context.capability,
                    "error_type": type(error).__name__,
                },
            )
            raise
        finally:
            token = None

    def execute(self, request: ConnectorRequest) -> ConnectorResult:
        return self.execute_governed_execution(self.prepare_governed_execution(request))


def build_datto_alert_resolution_invoker(
    *,
    openbao_url: str,
    transport: HttpTransport,
    audit: AuditSink,
) -> CapabilityInvoker:
    secrets = OpenBaoSecretResolver(
        base_url=openbao_url,
        role_id_path=Path(
            os.getenv(
                DATTO_EXECUTION_ROLE_ID_PATH_ENV,
                str(DEFAULT_ROLE_ID_PATH),
            )
        ),
        secret_id_path=Path(
            os.getenv(
                DATTO_EXECUTION_SECRET_ID_PATH_ENV,
                str(DEFAULT_SECRET_ID_PATH),
            )
        ),
    )
    connector = DattoRmmAlertResolutionConnector(
        secrets=secrets,
        transport=transport,
        audit=audit,
    )
    return GovernedConnectorCapabilityInvoker(
        connectors={DATTO_RMM_ALERT_RESOLUTION_PROVIDER: connector},
        provider_capability_map=_PROVIDER_CAPABILITY_MAP,
        default_maximum_execution_seconds=30.0,
    )


def register_datto_alert_resolution_invoker(
    *,
    invokers: CapabilityInvokerRegistry,
    invoker: CapabilityInvoker,
) -> None:
    invokers.register(ENDPOINT_ALERT_RESOLVE, invoker)
