from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

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


ENDPOINT_SECURITY_SCAN_START = "endpoint.security.scan.start"
DATTO_EDR_SCAN_PROVIDER = "datto_edr_scan_execution"
DATTO_EDR_PROVIDER_CAPABILITY = "datto_edr.scan.start"

DATTO_EDR_SCAN_PROFILE_ENV = "JASON_DATTO_EDR_SCAN_MCP_PROFILE"
DATTO_EDR_SCAN_PROFILE = "owner-av-scan-v1"

DEFAULT_ROLE_ID_PATH = Path("/run/jason-secrets/openbao/datto-edr/role_id")
DEFAULT_SECRET_ID_PATH = Path("/run/jason-secrets/openbao/datto-edr/secret_id")

_PROVIDER_CAPABILITY_MAP = {
    (DATTO_EDR_SCAN_PROVIDER, ENDPOINT_SECURITY_SCAN_START):
        DATTO_EDR_PROVIDER_CAPABILITY,
}

_FORENSIC_FALSE = {
    "process": False,
    "module": False,
    "driver": False,
    "memory": False,
    "account": False,
    "artifact": False,
    "autostart": False,
    "application": False,
    "network": False,
}


class DattoEdrScanActivationError(RuntimeError):
    pass


class DattoEdrScanVerificationError(ConnectorError):
    error_code = "DATTO_EDR_SCAN_VERIFICATION_FAILED"


class DattoEdrScanRateLimitedError(ConnectorError):
    error_code = "DATTO_EDR_SCAN_RATE_LIMITED"


@dataclass(frozen=True, slots=True)
class DattoEdrScanActivationState:
    profile: str
    enabled: bool
    provider_ids: tuple[str, ...]
    capability_names: tuple[str, ...]


def _capability_definition(*, now: datetime) -> CapabilityDefinition:
    return CapabilityDefinition(
        capability_name=ENDPOINT_SECURITY_SCAN_START,
        version="1.0",
        display_name="Start Datto AV Scan",
        lifecycle_status=CapabilityLifecycle.BUILDING,
        business_purpose=(
            "Start one provider-native Datto AV Quick or Full scan on one exact "
            "EDR agent and verify the provider accepted the bounded request."
        ),
        owner_service="Jason Governed Actions",
        architectural_capability_ids=frozenset({"JAC-005", "JAC-006", "JAC-013"}),
        risk_level=CapabilityRisk.MEDIUM,
        data_classifications=frozenset({"internal"}),
        permitted_execution_modes=frozenset({"deterministic"}),
        input_schema_reference="schema://jason/endpoint-security-scan-start/1.0",
        output_schema_reference="schema://jason/endpoint-security-scan-start-result/1.0",
        invoking_roles=frozenset({"orchestrator"}),
        approval=CapabilityApproval(required=True, approver_classes=("owner",)),
        evidence=CapabilityEvidence(
            required=True,
            requirements=(
                "authenticated requester identity",
                "exact endpoint UID",
                "exact EDR agent ID",
                "exact scan type",
                "pre-scan agent status read",
                "provider scan request result",
            ),
            verification_requirements=(
                "agent belongs to exact endpoint UID",
                "Datto AV is licensed and enabled",
                "no AV scan is already in progress",
                "last AV scan is at least one hour old",
                "one provider scan request is issued",
            ),
        ),
        dependencies=frozenset({
            "identity.authorization.resolve",
            "governance.action.evaluate",
            "endpoint.security.status.read",
            "endpoint.security.scan.history.search",
        }),
        idempotency_behavior=IdempotencyBehavior.CONDITIONALLY_IDEMPOTENT,
        idempotency_key_required=True,
        timeout_seconds=30,
        maximum_attempts=1,
        failure_behavior=(
            "Fail closed without agent substitution, endpoint substitution, scan "
            "type substitution, retry, or direct-provider fallback."
        ),
        tenant_isolation_required=True,
        client_isolation_required=False,
        stewardship=CapabilityStewardship(
            steward="technology-steward",
            business_justification=(
                "Allow Jason to verify AV remediation with provider-native scans."
            ),
            review_interval_days=30,
            retirement_criteria=(
                "Exact agent/device identity cannot be verified.",
                "Datto scan route or one-hour provider guard changes.",
            ),
            authoritative_change_sources=(
                "Datto EDR application client contract",
                "Datto AV documentation",
            ),
            last_reviewed_at=now,
            operational_owner="AOT IT Operations",
            approval_owner="AOT Owner",
        ),
        created_at=now,
        metadata={
            "provider_neutral": "true",
            "read_only": "false",
            "write_capability": "true",
            "resource_types": "endpoint_security,endpoint",
            "operation": "scan_start",
            "selector_keys": "resource_id,agent_id,scan_type",
            "mcp_action_enabled": "true",
            "mcp_tool_name": "execute_governed_capability",
            "conversation_authenticated_imperative_is_approval": "true",
            "pilot_scope": "aot_exact_endpoint_exact_agent",
            "activation_state": "datto_edr_scan_source_only_not_activated",
        },
    )


def _provider(*, now: datetime) -> ExecutionProvider:
    return ExecutionProvider(
        provider_id=DATTO_EDR_SCAN_PROVIDER,
        display_name="Datto EDR Governed AV Scan",
        provider_type=ProviderType.EXTERNAL_CONNECTOR,
        lifecycle_status=ProviderLifecycle.PLANNED,
        health_status=ProviderHealth.UNKNOWN,
        approval_status=ProviderApproval.PILOT,
        execution_modes=frozenset({"deterministic"}),
        capabilities=frozenset({ENDPOINT_SECURITY_SCAN_START}),
        supported_classifications=frozenset({"internal"}),
        regions=frozenset(),
        limits=ProviderLimits(
            maximum_concurrent_executions=1,
            maximum_requests_per_minute=2,
            maximum_execution_seconds=30,
        ),
        features=ProviderFeatures(structured_output=True),
        pricing_profile_id="zero-cost-foundation",
        stewardship=ProviderStewardship(
            technology_steward="technology-steward",
            business_justification="Start exact Datto AV scans through governance.",
            review_interval_days=30,
            last_reviewed_at=now,
            retirement_criteria=("Provider scan contract changes.",),
            vendor_change_sources=("Datto EDR application client contract",),
            operational_owner="AOT IT Operations",
            approval_owner="AOT Owner",
        ),
        created_at=now,
        metadata={
            "connector_id": "datto_edr",
            "resource_authority": "endpoint_security",
            "write_capability": "true",
            "mutation_scope": "exact_agent_av_scan_only",
            "activation_state": "datto_edr_scan_source_only_not_activated",
        },
    )


def register_datto_edr_scan_runtime_foundation(
    *,
    capabilities: CapabilityRegistryService,
    providers: ExecutionProviderRegistryService,
    now: datetime,
) -> DattoEdrScanActivationState:
    capabilities.register(_capability_definition(now=now))
    providers.register(_provider(now=now))
    profile = os.getenv(DATTO_EDR_SCAN_PROFILE_ENV, "").strip().casefold()
    if not profile:
        return DattoEdrScanActivationState("", False, (), ())
    if profile != DATTO_EDR_SCAN_PROFILE:
        raise DattoEdrScanActivationError("unsupported Datto EDR scan MCP profile")
    capabilities.set_lifecycle(
        capability_name=ENDPOINT_SECURITY_SCAN_START,
        version="1.0",
        lifecycle_status=CapabilityLifecycle.ACTIVE,
    )
    providers.set_approval(
        provider_id=DATTO_EDR_SCAN_PROVIDER,
        approval_status=ProviderApproval.APPROVED,
    )
    providers.set_health(
        provider_id=DATTO_EDR_SCAN_PROVIDER,
        health_status=ProviderHealth.HEALTHY,
    )
    providers.set_lifecycle(
        provider_id=DATTO_EDR_SCAN_PROVIDER,
        lifecycle_status=ProviderLifecycle.AVAILABLE,
    )
    return DattoEdrScanActivationState(
        profile,
        True,
        (DATTO_EDR_SCAN_PROVIDER,),
        (ENDPOINT_SECURITY_SCAN_START,),
    )


def _parse_utc(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class DattoEdrScanConnector:
    provider_name = "datto_edr"
    capabilities = frozenset({DATTO_EDR_PROVIDER_CAPABILITY})

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

    def execute(self, request: ConnectorRequest) -> ConnectorResult:
        if request.context.capability != DATTO_EDR_PROVIDER_CAPABILITY:
            raise ConnectorAuthorizationError("connector exposes only Datto AV scan start")
        if request.context.mode != "execute":
            raise ConnectorAuthorizationError("Datto AV scan requires execute mode")

        resource_id = str(request.arguments.get("resource_id") or "").strip()
        agent_id = str(request.arguments.get("agent_id") or "").strip()
        scan_type = str(request.arguments.get("scan_type") or "").strip().casefold()
        if not resource_id or not agent_id:
            raise ValueError("resource_id and agent_id are required")
        if scan_type not in {"quick", "full"}:
            raise ValueError("scan_type must be quick or full")
        if set(request.arguments) - {"resource_id", "agent_id", "scan_type"}:
            raise ValueError("unsupported Datto EDR scan arguments")

        credentials = self._secrets.resolve("datto_edr.readonly", request.context)
        api_url = str(credentials.get("api_url") or "").rstrip("/")
        api_token = str(credentials.get("api_token") or "")
        if not api_url or not api_token:
            raise ValueError("Datto EDR credential is incomplete")

        params = {"access_token": api_token}
        filter_json = json.dumps(
            {"where": {"id": agent_id}, "limit": 2},
            separators=(",", ":"),
        )
        before = self._transport.request(
            method="GET",
            url=f"{api_url}/AgentDetails",
            headers={"Accept": "application/json"},
            params={"filter": filter_json, **params},
            json=None,
            timeout_seconds=10.0,
        )
        if not isinstance(before, list) or len(before) != 1 or not isinstance(before[0], Mapping):
            raise DattoEdrScanVerificationError("agent pre-read was not exactly one object")
        agent = before[0]
        if str(agent.get("id") or "") != agent_id:
            raise DattoEdrScanVerificationError("agent pre-read ID mismatch")
        if str(agent.get("deviceId") or "") != resource_id:
            raise DattoEdrScanVerificationError("agent pre-read device UID mismatch")
        if agent.get("hasAvLicense") is not True or agent.get("dattoAvEnabled") is not True:
            raise DattoEdrScanVerificationError("Datto AV is not licensed and enabled")
        if str(agent.get("scanStatus") or "").casefold() == "in-progress":
            raise DattoEdrScanVerificationError("Datto AV scan is already in progress")

        last_scan = _parse_utc(agent.get("lastAvScanTime"))
        if last_scan is not None:
            age_seconds = (datetime.now(timezone.utc) - last_scan).total_seconds()
            if age_seconds < 3600:
                raise DattoEdrScanRateLimitedError(
                    "Datto AV one-hour scan interval has not elapsed"
                )

        options = {
            "diskScan": True,
            "quickScan": scan_type == "quick",
            "fullScan": scan_type == "full",
            "forensicScan": False,
            **_FORENSIC_FALSE,
        }
        task_name = "Scan - AV Quick" if scan_type == "quick" else "Scan - AV Full"
        payload = {
            "where": {"and": [{"id": [agent_id]}]},
            "options": options,
            "taskName": task_name,
        }

        self._audit.record(
            "connector.mutation.requested",
            request.context,
            {
                "provider": self.provider_name,
                "operation": "/agents/scan",
                "scan_type": scan_type,
                "exact_agent": True,
            },
        )
        response = self._transport.request(
            method="POST",
            url=f"{api_url}/agents/scan",
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            params=params,
            json=payload,
            timeout_seconds=20.0,
        )
        self._audit.record(
            "connector.mutation.completed",
            request.context,
            {
                "provider": self.provider_name,
                "operation": "/agents/scan",
                "provider_attempts": 1,
            },
        )

        task_id = ""
        if isinstance(response, Mapping):
            task_id = str(response.get("id") or response.get("taskId") or "").strip()
        return ConnectorResult(
            capability=request.context.capability,
            provider=self.provider_name,
            data={
                "status": "accepted",
                "resource_id": resource_id,
                "agent_id": agent_id,
                "scan_type": scan_type,
                "task_name": task_name,
                "task_id": task_id or None,
                "provider_accepted": True,
                "readback_required": True,
            },
            evidence_ids=(f"datto-edr:agent:{agent_id}:scan:{scan_type}",),
        )


def build_datto_edr_scan_invoker(
    *,
    openbao_url: str,
    transport: HttpTransport,
    audit: AuditSink,
) -> CapabilityInvoker:
    secrets = OpenBaoSecretResolver(
        base_url=openbao_url,
        role_id_path=DEFAULT_ROLE_ID_PATH,
        secret_id_path=DEFAULT_SECRET_ID_PATH,
    )
    connector = DattoEdrScanConnector(
        secrets=secrets,
        transport=transport,
        audit=audit,
    )
    return GovernedConnectorCapabilityInvoker(
        connectors={DATTO_EDR_SCAN_PROVIDER: connector},
        provider_capability_map=_PROVIDER_CAPABILITY_MAP,
        default_maximum_execution_seconds=30.0,
    )


def register_datto_edr_scan_invoker(
    *,
    invokers: CapabilityInvokerRegistry,
    invoker: CapabilityInvoker,
) -> None:
    invokers.register(ENDPOINT_SECURITY_SCAN_START, invoker)
