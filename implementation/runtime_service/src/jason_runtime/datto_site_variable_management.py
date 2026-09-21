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
    ConnectorError,
    ConnectorRequest,
    ConnectorResult,
    HttpTransport,
)
from connectors.core.openbao_secrets import OpenBaoSecretResolver
from connectors.datto_rmm.auth import acquire_access_token, require_durable_credentials
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
from orchestrator.connector_invoker import GovernedConnectorCapabilityInvoker
from orchestrator.invokers import CapabilityInvokerRegistry
from orchestrator.service import CapabilityInvoker

SITE_VARIABLE_CREATE = "management.site.variable.create"
SITE_VARIABLE_UPDATE = "management.site.variable.update"
DATTO_SITE_VARIABLE_PROVIDER = "datto_rmm_site_variable_management"
DATTO_SITE_VARIABLE_CREATE = "datto_rmm.site.variable.create"
DATTO_SITE_VARIABLE_UPDATE = "datto_rmm.site.variable.update"
DATTO_SITE_VARIABLE_LOGICAL_SECRET = "datto_rmm.site_variables"

SITE_VARIABLE_PROFILE_ENV = "JASON_DATTO_SITE_VARIABLE_MCP_PROFILE"
SITE_VARIABLE_PROFILE = "owner-site-variable-v1"
SITE_VARIABLE_ROLE_ID_ENV = "JASON_DATTO_SITE_VARIABLE_OPENBAO_ROLE_ID_PATH"
SITE_VARIABLE_SECRET_ID_ENV = "JASON_DATTO_SITE_VARIABLE_OPENBAO_SECRET_ID_PATH"
DEFAULT_ROLE_ID_PATH = Path("/run/jason-secrets/openbao/datto-rmm-site-variables/role_id")
DEFAULT_SECRET_ID_PATH = Path("/run/jason-secrets/openbao/datto-rmm-site-variables/secret_id")

_PROVIDER_CAPABILITY_MAP = {
    (DATTO_SITE_VARIABLE_PROVIDER, SITE_VARIABLE_CREATE): DATTO_SITE_VARIABLE_CREATE,
    (DATTO_SITE_VARIABLE_PROVIDER, SITE_VARIABLE_UPDATE): DATTO_SITE_VARIABLE_UPDATE,
}


class DattoSiteVariableActivationError(RuntimeError):
    pass


class DattoSiteVariableVerificationError(ConnectorError):
    error_code = "DATTO_RMM_SITE_VARIABLE_VERIFICATION_FAILED"


@dataclass(frozen=True, slots=True)
class SiteVariableActivationState:
    profile: str
    enabled: bool
    provider_ids: tuple[str, ...]
    capability_names: tuple[str, ...]
def _action_capability(
    *,
    now: datetime,
    capability_name: str,
    display_name: str,
    operation: str,
) -> CapabilityDefinition:
    return CapabilityDefinition(
        capability_name=capability_name,
        version="1.0",
        display_name=display_name,
        lifecycle_status=CapabilityLifecycle.BUILDING,
        business_purpose=(
            "Manage one Datto RMM site variable through a separate least-privilege "
            "site-management identity without exposing the variable value."
        ),
        owner_service="Jason Governed Actions",
        architectural_capability_ids=frozenset({"JAC-005", "JAC-006", "JAC-013"}),
        risk_level=CapabilityRisk.MEDIUM,
        data_classifications=frozenset({"internal", "secret"}),
        permitted_execution_modes=frozenset({"deterministic"}),
        input_schema_reference=f"schema://jason/{capability_name.replace('.', '-')}/1.0",
        output_schema_reference=f"schema://jason/{capability_name.replace('.', '-')}-result/1.0",
        invoking_roles=frozenset({"orchestrator"}),
        approval=CapabilityApproval(required=True, approver_classes=("owner", "administrator")),
        evidence=CapabilityEvidence(
            required=True,
            requirements=(
                "authenticated requester identity",
                "exact site UID",
                "pre-mutation variable list",
                "provider mutation result",
                "post-mutation variable list",
            ),
            verification_requirements=(
                "at most one provider mutation request is issued",
                "secret values are never returned or audited",
                "post-mutation site-variable state matches the requested identity",
            ),
        ),
        dependencies=frozenset({"identity.authorization.resolve", "governance.action.evaluate"}),
        idempotency_behavior=IdempotencyBehavior.CONDITIONALLY_IDEMPOTENT,
        idempotency_key_required=True,
        timeout_seconds=30,
        maximum_attempts=1,
        failure_behavior=(
            "Fail closed without delete fallback, secret disclosure, retry, "
            "direct-provider fallback, or unverified success."
        ),
        tenant_isolation_required=True,
        client_isolation_required=False,
        stewardship=CapabilityStewardship(
            steward="technology-steward",
            business_justification=(
                "Allow governed playbooks and administrators to maintain required "
                "site configuration without exposing secret values."
            ),
            review_interval_days=30,
            retirement_criteria=(
                "Datto RMM is no longer the site-variable authority.",
                "Least-privilege site-management identity cannot be maintained.",
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
            "resource_types": "management_site_variable",
            "operation": operation,
            "selector_keys": "site_uid,variable_id,name",
            "mcp_action_enabled": "true",
            "mcp_tool_name": "execute_governed_capability",
            "conversation_authenticated_imperative_is_approval": "true",
            "secret_logging": "forbidden",
            "delete_enabled": "false",
            "activation_state": "datto_site_variable_source_only_not_activated",
        },
    )


def _provider(*, now: datetime) -> ExecutionProvider:
    return ExecutionProvider(
        provider_id=DATTO_SITE_VARIABLE_PROVIDER,
        display_name="Datto RMM Governed Site Variable Management",
        provider_type=ProviderType.EXTERNAL_CONNECTOR,
        lifecycle_status=ProviderLifecycle.PLANNED,
        health_status=ProviderHealth.UNKNOWN,
        approval_status=ProviderApproval.PILOT,
        execution_modes=frozenset({"deterministic"}),
        capabilities=frozenset({SITE_VARIABLE_CREATE, SITE_VARIABLE_UPDATE}),
        supported_classifications=frozenset({"internal", "secret"}),
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
                "Use a Datto identity restricted to the site-management permission "
                "required by the site-variable API."
            ),
            review_interval_days=30,
            last_reviewed_at=now,
            retirement_criteria=("Site-management identity exceeds approved authority.",),
            vendor_change_sources=("Datto RMM API documentation",),
            operational_owner="AOT IT Operations",
            approval_owner="AOT Owner",
        ),
        created_at=now,
        metadata={
            "connector_id": "datto_rmm",
            "resource_authority": "management_site_variable",
            "write_capability": "true",
            "mutation_scope": "site_variable_create_update_only",
            "logical_secret": DATTO_SITE_VARIABLE_LOGICAL_SECRET,
            "delete_enabled": "false",
            "activation_state": "datto_site_variable_source_only_not_activated",
        },
    )
def apply_site_variable_activation(
    *,
    capabilities: CapabilityRegistryService,
    providers: ExecutionProviderRegistryService,
    profile: str | None,
) -> SiteVariableActivationState:
    normalized = str(profile or "").strip().casefold()
    if not normalized:
        return SiteVariableActivationState("", False, (), ())
    if normalized != SITE_VARIABLE_PROFILE:
        raise DattoSiteVariableActivationError("unsupported Datto site-variable MCP profile")

    for capability_name in (SITE_VARIABLE_CREATE, SITE_VARIABLE_UPDATE):
        capability = capabilities.get(capability_name=capability_name, version="1.0")
        if capability.lifecycle_status is not CapabilityLifecycle.BUILDING:
            raise DattoSiteVariableActivationError(
                "Datto site-variable capability is not BUILDING"
            )
        if not capability.approval.required or capability.maximum_attempts != 1:
            raise DattoSiteVariableActivationError(
                "Datto site-variable governance contract is invalid"
            )
        capabilities.set_lifecycle(
            capability_name=capability_name,
            version="1.0",
            lifecycle_status=CapabilityLifecycle.ACTIVE,
        )

    provider = providers.get(DATTO_SITE_VARIABLE_PROVIDER)
    if provider.lifecycle_status is not ProviderLifecycle.PLANNED:
        raise DattoSiteVariableActivationError(
            "Datto site-variable provider is not PLANNED"
        )
    providers.set_approval(
        provider_id=DATTO_SITE_VARIABLE_PROVIDER,
        approval_status=ProviderApproval.APPROVED,
    )
    providers.set_health(
        provider_id=DATTO_SITE_VARIABLE_PROVIDER,
        health_status=ProviderHealth.HEALTHY,
    )
    providers.set_lifecycle(
        provider_id=DATTO_SITE_VARIABLE_PROVIDER,
        lifecycle_status=ProviderLifecycle.AVAILABLE,
    )
    return SiteVariableActivationState(
        normalized,
        True,
        (DATTO_SITE_VARIABLE_PROVIDER,),
        (SITE_VARIABLE_CREATE, SITE_VARIABLE_UPDATE),
    )


def register_site_variable_runtime_foundation(
    *,
    capabilities: CapabilityRegistryService,
    providers: ExecutionProviderRegistryService,
    now: datetime,
) -> SiteVariableActivationState:
    capabilities.register(
        _action_capability(
            now=now,
            capability_name=SITE_VARIABLE_CREATE,
            display_name="Create Managed Site Variable",
            operation="create",
        )
    )
    capabilities.register(
        _action_capability(
            now=now,
            capability_name=SITE_VARIABLE_UPDATE,
            display_name="Update Managed Site Variable",
            operation="update",
        )
    )
    providers.register(_provider(now=now))
    return apply_site_variable_activation(
        capabilities=capabilities,
        providers=providers,
        profile=os.getenv(SITE_VARIABLE_PROFILE_ENV, ""),
    )


def _canonical_uuid(value: object, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} is required")
    try:
        canonical = str(UUID(text))
    except ValueError as error:
        raise ValueError(f"{field} must be a UUID") from error
    if canonical != text.casefold():
        raise ValueError(f"{field} must use canonical UUID form")
    return canonical


def _variable_rows(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    for key in ("variables", "items"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, Mapping)]
    data = payload.get("data")
    if isinstance(data, Mapping):
        return _variable_rows(data)
    raise DattoSiteVariableVerificationError(
        "site-variable readback did not contain a variable collection"
    )


def _variable_id(row: Mapping[str, Any]) -> str:
    return str(row.get("id") or row.get("uid") or row.get("variableId") or "").strip()


def _variable_name(row: Mapping[str, Any]) -> str:
    return str(row.get("name") or row.get("variableName") or "").strip()
class DattoSiteVariableManagementConnector:
    provider_name = "datto_rmm"
    capabilities = frozenset({DATTO_SITE_VARIABLE_CREATE, DATTO_SITE_VARIABLE_UPDATE})

    def __init__(self, *, secrets, transport: HttpTransport, audit: AuditSink) -> None:
        self._secrets = secrets
        self._transport = transport
        self._audit = audit

    def _list(self, *, base: str, site_uid: str, headers: Mapping[str, str]):
        payload = self._transport.request(
            method="GET",
            url=f"{base}/api/v2/site/{site_uid}/variables",
            headers=headers,
            params={"max": 250, "page": 0},
            json=None,
            timeout_seconds=10.0,
        )
        if not isinstance(payload, Mapping):
            raise DattoSiteVariableVerificationError(
                "site-variable readback was not an object"
            )
        return _variable_rows(payload)

    def execute(self, request: ConnectorRequest) -> ConnectorResult:
        if request.context.capability not in self.capabilities:
            raise ConnectorAuthorizationError(
                "Datto site-variable connector exposes create and update only"
            )
        if request.context.mode != "execute":
            raise ConnectorAuthorizationError(
                "Datto site-variable mutation requires execute mode"
            )

        site_uid = _canonical_uuid(request.arguments.get("site_uid"), "site_uid")
        name = str(request.arguments.get("name") or "").strip()
        value = request.arguments.get("value")
        if not name or " " in name:
            raise ValueError("name is required and cannot contain spaces")
        if not isinstance(value, str):
            raise ValueError("value must be a string")
        if len(value) > 20000:
            raise ValueError("value exceeds the Datto site-variable limit")

        unknown_allowed = {"site_uid", "name", "value", "masked", "variable_id"}
        unknown = set(request.arguments) - unknown_allowed
        if unknown:
            raise ValueError(
                "unsupported site-variable arguments: " + ", ".join(sorted(unknown))
            )

        credentials = self._secrets.resolve(
            DATTO_SITE_VARIABLE_LOGICAL_SECRET,
            request.context,
        )
        require_durable_credentials(credentials)
        token = acquire_access_token(credentials=credentials)
        headers = {
            "Authorization": f"{token.token_type} {token.access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        base = credentials["api_url"].rstrip("/")

        try:
            before = self._list(base=base, site_uid=site_uid, headers=headers)
            if request.context.capability == DATTO_SITE_VARIABLE_CREATE:
                if any(_variable_name(row).casefold() == name.casefold() for row in before):
                    raise DattoSiteVariableVerificationError(
                        "a site variable with that name already exists"
                    )
                masked = bool(request.arguments.get("masked", True))
                mutation_url = f"{base}/api/v2/site/{site_uid}/variable"
                method = "PUT"
                body = {"name": name, "value": value, "masked": masked}
                target_variable_id = ""
            else:
                variable_id = _canonical_uuid(
                    request.arguments.get("variable_id"),
                    "variable_id",
                )
                current = next(
                    (row for row in before if _variable_id(row) == variable_id),
                    None,
                )
                if current is None:
                    raise DattoSiteVariableVerificationError(
                        "the requested site variable was not found in the site"
                    )
                mutation_url = (
                    f"{base}/api/v2/site/{site_uid}/variables/{variable_id}"
                )
                method = "POST"
                body = {"name": name, "value": value}
                masked = bool(current.get("masked", False))
                target_variable_id = variable_id

            self._audit.record(
                "connector.mutation.requested",
                request.context,
                {
                    "provider": self.provider_name,
                    "capability": request.context.capability,
                    "site_uid_present": True,
                    "variable_id_present": bool(target_variable_id),
                    "variable_name_present": True,
                    "secret_value_logged": False,
                },
            )
            self._transport.request(
                method=method,
                url=mutation_url,
                headers=headers,
                params=None,
                json=body,
                timeout_seconds=20.0,
            )
            after = self._list(base=base, site_uid=site_uid, headers=headers)

            if request.context.capability == DATTO_SITE_VARIABLE_CREATE:
                match = next(
                    (
                        row
                        for row in after
                        if _variable_name(row).casefold() == name.casefold()
                    ),
                    None,
                )
            else:
                match = next(
                    (row for row in after if _variable_id(row) == target_variable_id),
                    None,
                )
            if match is None or _variable_name(match) != name:
                raise DattoSiteVariableVerificationError(
                    "post-mutation readback did not verify the site variable"
                )

            resolved_id = _variable_id(match) or target_variable_id
            self._audit.record(
                "connector.mutation.verified",
                request.context,
                {
                    "provider": self.provider_name,
                    "capability": request.context.capability,
                    "readback_verified": True,
                    "secret_value_logged": False,
                },
            )
            return ConnectorResult(
                capability=request.context.capability,
                provider=self.provider_name,
                data={
                    "status": "verified",
                    "site_uid": site_uid,
                    "variable_id": resolved_id,
                    "name": name,
                    "masked": masked,
                    "mutation_performed": True,
                    "readback_verified": True,
                    "value_disclosed": False,
                },
                evidence_ids=(
                    f"datto-rmm:site:{site_uid}:variable:{resolved_id or name}",
                ),
            )
        except Exception as error:
            self._audit.record(
                "connector.mutation.failed",
                request.context,
                {
                    "provider": self.provider_name,
                    "capability": request.context.capability,
                    "error_type": type(error).__name__,
                    "secret_value_logged": False,
                },
            )
            raise
        finally:
            token = None
def build_site_variable_invoker(
    *,
    openbao_url: str,
    transport: HttpTransport,
    audit: AuditSink,
) -> CapabilityInvoker:
    secrets = OpenBaoSecretResolver(
        base_url=openbao_url,
        role_id_path=Path(
            os.getenv(SITE_VARIABLE_ROLE_ID_ENV, str(DEFAULT_ROLE_ID_PATH))
        ),
        secret_id_path=Path(
            os.getenv(SITE_VARIABLE_SECRET_ID_ENV, str(DEFAULT_SECRET_ID_PATH))
        ),
    )
    connector = DattoSiteVariableManagementConnector(
        secrets=secrets,
        transport=transport,
        audit=audit,
    )
    return GovernedConnectorCapabilityInvoker(
        connectors={DATTO_SITE_VARIABLE_PROVIDER: connector},
        provider_capability_map=_PROVIDER_CAPABILITY_MAP,
        default_maximum_execution_seconds=30.0,
    )


def register_site_variable_invokers(
    *,
    invokers: CapabilityInvokerRegistry,
    invoker: CapabilityInvoker,
) -> None:
    invokers.register(SITE_VARIABLE_CREATE, invoker)
    invokers.register(SITE_VARIABLE_UPDATE, invoker)
