from __future__ import annotations

import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping

from connectors.core.contracts import (
    AuditSink,
    ConnectorAuthorizationError,
    ConnectorContext,
    ConnectorRequest,
    ConnectorResult,
    HttpTransport,
    SecretResolver,
    require_capability,
)
from connectors.core.openbao_secrets import OpenBaoSecretResolver
from connectors.datto_rmm.auth import acquire_access_token, require_durable_credentials
from connectors.datto_rmm.execution_identity import DATTO_RMM_EXECUTION_LOGICAL_SECRET
from connectors.datto_rmm.readonly_powershell import DattoRmmReadOnlyPowerShellPolicy
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

from .datto_component_execution import (
    DATTO_COMPONENT_EXECUTION_PROFILE,
    DATTO_COMPONENT_EXECUTION_PROFILE_ENV,
    DATTO_EXECUTION_ROLE_ID_PATH_ENV,
    DATTO_EXECUTION_SECRET_ID_PATH_ENV,
    DEFAULT_ROLE_ID_PATH,
    DEFAULT_SECRET_ID_PATH,
)
from .datto_component_scope import (
    DATTO_AD_HOC_POWERSHELL_NAME,
    DATTO_AD_HOC_POWERSHELL_UID,
    configured_datto_components,
)


ENDPOINT_POWERSHELL_READ = "endpoint.powershell.read"
DATTO_RMM_POWERSHELL_READ_PROVIDER = "datto_rmm_powershell_read"
DATTO_RMM_POWERSHELL_READ_PROVIDER_CAPABILITY = "datto_rmm.powershell.read"

_SUCCESS_STATUSES = frozenset(
    {"complete", "completed", "success", "successful", "succeeded", "finished"}
)
_FAILURE_STATUSES = frozenset(
    {"failed", "failure", "error", "cancelled", "canceled", "aborted"}
)


class DattoPowerShellReadActivationError(RuntimeError):
    pass


class DattoPowerShellReadVerificationError(RuntimeError):
    pass


def _capability_definition(*, now: datetime) -> CapabilityDefinition:
    return CapabilityDefinition(
        capability_name=ENDPOINT_POWERSHELL_READ,
        version="1.0",
        display_name="Read Endpoint State with PowerShell",
        lifecycle_status=CapabilityLifecycle.BUILDING,
        business_purpose=(
            "Run classifier-approved read-only PowerShell against one managed "
            "Windows endpoint through Datto RMM and return bounded diagnostic output."
        ),
        owner_service="Jason Resource Intelligence",
        architectural_capability_ids=frozenset({"JAC-005", "JAC-013"}),
        risk_level=CapabilityRisk.MEDIUM,
        data_classifications=frozenset({"internal"}),
        permitted_execution_modes=frozenset({"deterministic"}),
        input_schema_reference="schema://jason/endpoint-powershell-read/1.0",
        output_schema_reference="schema://jason/endpoint-powershell-read-result/1.0",
        invoking_roles=frozenset({"orchestrator"}),
        approval=CapabilityApproval(required=False),
        evidence=CapabilityEvidence(
            required=True,
            requirements=(
                "authenticated requester identity",
                "exact Datto device uid",
                "classifier-approved read-only PowerShell",
                "exact AOT ad-hoc PowerShell component identity",
                "Datto quick-job identity and status",
                "bounded provider StdOut and StdErr",
            ),
            verification_requirements=(
                "command is reclassified immediately before provider submission",
                "sensitive, mutating, and uncertain commands fail closed",
                "exactly one Datto quick-job PUT is issued",
                "target device uid is verified before job creation",
                "component uid is fixed server-side and cannot be caller-selected",
                "provider output is bounded before return",
            ),
        ),
        dependencies=frozenset({"identity.authorization.resolve"}),
        idempotency_behavior=IdempotencyBehavior.NON_IDEMPOTENT,
        idempotency_key_required=False,
        timeout_seconds=30,
        maximum_attempts=1,
        failure_behavior=(
            "Fail closed without command substitution, component substitution, "
            "target substitution, provider retry, or write-capable PowerShell."
        ),
        tenant_isolation_required=True,
        client_isolation_required=False,
        stewardship=CapabilityStewardship(
            steward="technology-steward",
            business_justification=(
                "Permit fast endpoint discovery and troubleshooting while keeping "
                "all endpoint-state mutation behind governed action authority."
            ),
            review_interval_days=30,
            retirement_criteria=(
                "The exact diagnostic component identity changes without review.",
                "The read-only classifier can no longer prove the safety boundary.",
                "A supported lower-latency Datto shell API replaces Quick Jobs.",
            ),
            authoritative_change_sources=("Datto RMM API documentation",),
            last_reviewed_at=now,
            operational_owner="AOT IT Operations",
            approval_owner="AOT Owner",
        ),
        created_at=now,
        metadata={
            "provider_neutral": "true",
            "read_only": "true",
            "resource_types": "endpoint,managed_endpoint,powershell_diagnostic",
            "operation": "read",
            "selector_keys": "device_uid,command,timeout_seconds",
            "fact_hints": (
                "PowerShell,endpoint diagnostics,service,process,event log,disk,"
                "network,registry,patch,scheduled task,troubleshooting"
            ),
            "provider_native_execution_identity_required": "true",
            "endpoint_state_mutation_allowed": "false",
            "provider_side_effect": "one Datto diagnostic job record",
            "component_uid_fixed_server_side": DATTO_AD_HOC_POWERSHELL_UID,
            "activation_state": "requires_existing_datto_execution_profile",
        },
    )


def _provider(*, now: datetime) -> ExecutionProvider:
    return ExecutionProvider(
        provider_id=DATTO_RMM_POWERSHELL_READ_PROVIDER,
        display_name="Datto RMM Read-Only PowerShell",
        provider_type=ProviderType.EXTERNAL_CONNECTOR,
        lifecycle_status=ProviderLifecycle.PLANNED,
        health_status=ProviderHealth.UNKNOWN,
        approval_status=ProviderApproval.PILOT,
        execution_modes=frozenset({"deterministic"}),
        capabilities=frozenset({ENDPOINT_POWERSHELL_READ}),
        supported_classifications=frozenset({"internal"}),
        regions=frozenset(),
        limits=ProviderLimits(
            maximum_concurrent_executions=3,
            maximum_requests_per_minute=30,
            maximum_execution_seconds=30,
        ),
        features=ProviderFeatures(structured_output=True),
        pricing_profile_id="zero-cost-foundation",
        stewardship=ProviderStewardship(
            technology_steward="technology-steward",
            business_justification=(
                "Use Datto's supported Quick Job API as the transport for "
                "classifier-approved read-only endpoint diagnostics."
            ),
            review_interval_days=30,
            last_reviewed_at=now,
            retirement_criteria=(
                "Datto removes the Quick Job or job-output API.",
                "Execution identity containment cannot be proven.",
            ),
            vendor_change_sources=("Datto RMM API documentation",),
            operational_owner="AOT IT Operations",
            approval_owner="AOT Owner",
        ),
        created_at=now,
        metadata={
            "connector_id": "datto_rmm",
            "resource_authority": "managed_endpoint",
            "logical_secret": DATTO_RMM_EXECUTION_LOGICAL_SECRET,
            "transport": "api_v2_quickjob",
            "endpoint_state_read_only": "true",
        },
    )


def _component_is_configured() -> bool:
    for component in configured_datto_components():
        if (
            component.uid == DATTO_AD_HOC_POWERSHELL_UID
            and component.name.casefold() == DATTO_AD_HOC_POWERSHELL_NAME.casefold()
        ):
            return True
    return False


def register_datto_powershell_read_runtime_foundation(
    *,
    capabilities: CapabilityRegistryService,
    providers: ExecutionProviderRegistryService,
    now: datetime,
) -> None:
    capabilities.register(_capability_definition(now=now))
    providers.register(_provider(now=now))

    profile = os.getenv(DATTO_COMPONENT_EXECUTION_PROFILE_ENV, "").strip().casefold()
    if not profile:
        return
    if profile != DATTO_COMPONENT_EXECUTION_PROFILE:
        raise DattoPowerShellReadActivationError(
            "unsupported Datto component execution profile for PowerShell read"
        )
    if not _component_is_configured():
        raise DattoPowerShellReadActivationError(
            "exact AOT ad-hoc PowerShell component is not configured"
        )

    capability = capabilities.get(
        capability_name=ENDPOINT_POWERSHELL_READ,
        version="1.0",
    )
    provider = providers.get(DATTO_RMM_POWERSHELL_READ_PROVIDER)

    if capability.lifecycle_status is not CapabilityLifecycle.BUILDING:
        raise DattoPowerShellReadActivationError(
            "PowerShell read capability is not in BUILDING state"
        )
    if capability.approval.required:
        raise DattoPowerShellReadActivationError(
            "PowerShell read unexpectedly requires per-call approval"
        )
    if capability.maximum_attempts != 1:
        raise DattoPowerShellReadActivationError(
            "PowerShell read unexpectedly permits provider retries"
        )
    if provider.lifecycle_status is not ProviderLifecycle.PLANNED:
        raise DattoPowerShellReadActivationError(
            "PowerShell read provider is not PLANNED"
        )

    capabilities.set_lifecycle(
        capability_name=ENDPOINT_POWERSHELL_READ,
        version="1.0",
        lifecycle_status=CapabilityLifecycle.ACTIVE,
    )
    providers.set_approval(
        provider_id=DATTO_RMM_POWERSHELL_READ_PROVIDER,
        approval_status=ProviderApproval.APPROVED,
    )
    providers.set_health(
        provider_id=DATTO_RMM_POWERSHELL_READ_PROVIDER,
        health_status=ProviderHealth.HEALTHY,
    )
    providers.set_lifecycle(
        provider_id=DATTO_RMM_POWERSHELL_READ_PROVIDER,
        lifecycle_status=ProviderLifecycle.AVAILABLE,
    )


class DattoRmmPowerShellReadConnector:
    provider_name = DATTO_RMM_POWERSHELL_READ_PROVIDER
    capabilities = frozenset({DATTO_RMM_POWERSHELL_READ_PROVIDER_CAPABILITY})
    maximum_output_chars = 50_000
    maximum_output_records = 20

    def __init__(
        self,
        *,
        secrets: SecretResolver,
        transport: HttpTransport,
        audit: AuditSink,
        sleeper: Callable[[float], None] = time.sleep,
        maximum_status_reads: int = 10,
        status_interval_seconds: float = 1.5,
    ) -> None:
        self._secrets = secrets
        self._transport = transport
        self._audit = audit
        self._sleeper = sleeper
        self._maximum_status_reads = maximum_status_reads
        self._status_interval_seconds = status_interval_seconds
        self._policy = DattoRmmReadOnlyPowerShellPolicy()
        if maximum_status_reads < 1 or maximum_status_reads > 12:
            raise ValueError("maximum_status_reads must be between 1 and 12")
        if status_interval_seconds < 0 or status_interval_seconds > 2:
            raise ValueError("status_interval_seconds must be between 0 and 2")

    @staticmethod
    def _job_uid(payload: Mapping[str, Any]) -> str:
        candidates = (
            payload.get("uid"),
            payload.get("jobUid"),
            payload.get("jobUID"),
            payload.get("resource_id"),
        )
        nested = payload.get("job")
        if isinstance(nested, Mapping):
            candidates = (
                *candidates,
                nested.get("uid"),
                nested.get("jobUid"),
                nested.get("jobUID"),
                nested.get("resource_id"),
            )
        for value in candidates:
            text = str(value or "").strip()
            if text:
                return text
        raise DattoPowerShellReadVerificationError(
            "Datto quick-job response did not expose a durable job uid"
        )

    @classmethod
    def _job_status(cls, payload: Mapping[str, Any]) -> str:
        record = payload.get("job") if isinstance(payload.get("job"), Mapping) else payload
        status = str(
            record.get("status")
            or record.get("jobStatus")
            or record.get("state")
            or ""
        ).strip()
        if not status:
            raise DattoPowerShellReadVerificationError(
                "Datto job read response did not expose a status"
            )
        return status

    @classmethod
    def _bounded_stream(
        cls,
        payload: Any,
        *,
        stream: str,
    ) -> tuple[str, bool, int]:
        if not isinstance(payload, (list, tuple)):
            raise DattoPowerShellReadVerificationError(
                f"Datto {stream} response was not a collection"
            )
        parts: list[str] = []
        remaining = cls.maximum_output_chars
        bounded = False
        matches = 0
        for record in payload:
            if not isinstance(record, Mapping):
                raise DattoPowerShellReadVerificationError(
                    f"Datto {stream} returned a non-object record"
                )
            component_uid = str(record.get("componentUid") or "").strip()
            if not component_uid:
                raise DattoPowerShellReadVerificationError(
                    f"Datto {stream} record lacked componentUid"
                )
            if component_uid != DATTO_AD_HOC_POWERSHELL_UID:
                continue
            matches += 1
            if len(parts) >= cls.maximum_output_records:
                bounded = True
                continue
            raw = record.get("stdData")
            if raw is None:
                value = ""
            elif isinstance(raw, str):
                value = raw
            else:
                raise DattoPowerShellReadVerificationError(
                    f"Datto {stream} stdData was not text"
                )
            if remaining <= 0:
                bounded = True
                continue
            if len(value) > remaining:
                value = value[:remaining]
                bounded = True
            remaining -= len(value)
            parts.append(value)
        return "\n".join(parts), bounded, matches

    def execute(self, request: ConnectorRequest) -> ConnectorResult:
        require_capability(request, self.capabilities)
        device_uid = str(
            request.arguments.get("device_uid")
            or request.arguments.get("resource_id")
            or ""
        ).strip()
        command = str(request.arguments.get("command") or "").strip()
        if not device_uid:
            raise ConnectorAuthorizationError("device_uid is required")
        if not command:
            raise ConnectorAuthorizationError("command is required")

        requested_timeout = request.arguments.get("timeout_seconds", 30)
        prepared = self._policy.prepare_command(
            device_uid=device_uid,
            command=command,
            timeout_seconds=requested_timeout,
        )

        credentials = dict(
            self._secrets.resolve(DATTO_RMM_EXECUTION_LOGICAL_SECRET, request.context)
        )
        require_durable_credentials(credentials)
        token = acquire_access_token(credentials=credentials)
        base_url = credentials["api_url"].rstrip("/")
        headers = {
            "Authorization": f"{token.token_type} {token.access_token}",
            "Accept": "application/json",
        }

        try:
            target = self._transport.request(
                method="GET",
                url=f"{base_url}/api/v2/device/{device_uid}",
                headers=headers,
                params=None,
                json=None,
                timeout_seconds=10.0,
            )
            if not isinstance(target, Mapping):
                raise DattoPowerShellReadVerificationError(
                    "Datto target pre-read was not an object"
                )
            observed_uid = str(
                target.get("uid")
                or target.get("deviceUid")
                or target.get("resource_id")
                or ""
            ).strip()
            if observed_uid != device_uid:
                raise DattoPowerShellReadVerificationError(
                    "Datto target pre-read uid did not match requested endpoint"
                )
            if target.get("deleted") is True or target.get("suspended") is True:
                raise ConnectorAuthorizationError("Datto target is not active")

            body = {
                "jobName": "Jason - Read Only PowerShell",
                "jobComponent": {
                    "componentUid": DATTO_AD_HOC_POWERSHELL_UID,
                    "variables": [
                        {"name": "usrInput", "value": prepared.command},
                    ],
                },
            }
            self._audit.record(
                "connector.readonly_powershell.requested",
                request.context,
                {
                    "provider": self.provider_name,
                    "device_uid_present": True,
                    "component_uid": DATTO_AD_HOC_POWERSHELL_UID,
                    "command_digest": prepared.digest(),
                    "active_probe": prepared.active_probe,
                },
            )
            created = self._transport.request(
                method="PUT",
                url=f"{base_url}/api/v2/device/{device_uid}/quickjob",
                headers={**headers, "Content-Type": "application/json"},
                params=None,
                json=body,
                timeout_seconds=20.0,
            )
            if not isinstance(created, Mapping):
                raise DattoPowerShellReadVerificationError(
                    "Datto quick-job response was not an object"
                )
            job_uid = self._job_uid(created)

            final_status = ""
            for index in range(self._maximum_status_reads):
                job_payload = self._transport.request(
                    method="GET",
                    url=f"{base_url}/api/v2/job/{job_uid}",
                    headers=headers,
                    params=None,
                    json=None,
                    timeout_seconds=10.0,
                )
                if not isinstance(job_payload, Mapping):
                    raise DattoPowerShellReadVerificationError(
                        "Datto job read response was not an object"
                    )
                if self._job_uid(job_payload) != job_uid:
                    raise DattoPowerShellReadVerificationError(
                        "Datto job readback uid did not match created job"
                    )
                final_status = self._job_status(job_payload)
                normalized = final_status.casefold()
                if normalized in _FAILURE_STATUSES:
                    raise DattoPowerShellReadVerificationError(
                        f"Datto read-only PowerShell job failed: {normalized}"
                    )
                if normalized in _SUCCESS_STATUSES:
                    break
                if index + 1 < self._maximum_status_reads:
                    self._sleeper(self._status_interval_seconds)

            if final_status.casefold() not in _SUCCESS_STATUSES:
                return ConnectorResult(
                    capability=request.context.capability,
                    provider=self.provider_name,
                    data={
                        "status": "accepted",
                        "job_uid": job_uid,
                        "job_status": final_status,
                        "device_uid": device_uid,
                        "component_uid": DATTO_AD_HOC_POWERSHELL_UID,
                        "component_name": DATTO_AD_HOC_POWERSHELL_NAME,
                        "classification": "read_only",
                        "active_probe": prepared.active_probe,
                        "completion_verified": False,
                    },
                    evidence_ids=(f"datto-rmm:job:{job_uid}",),
                    warnings=(
                        "Datto job is still asynchronous; use automation.job.read "
                        "and automation.job.output.read with the returned selectors.",
                    ),
                )

            stdout_payload = self._transport.request(
                method="GET",
                url=f"{base_url}/api/v2/job/{job_uid}/results/{device_uid}/stdout",
                headers=headers,
                params=None,
                json=None,
                timeout_seconds=10.0,
            )
            stderr_payload = self._transport.request(
                method="GET",
                url=f"{base_url}/api/v2/job/{job_uid}/results/{device_uid}/stderr",
                headers=headers,
                params=None,
                json=None,
                timeout_seconds=10.0,
            )
            stdout, stdout_bounded, stdout_matches = self._bounded_stream(
                stdout_payload, stream="stdout"
            )
            stderr, stderr_bounded, stderr_matches = self._bounded_stream(
                stderr_payload, stream="stderr"
            )
            self._audit.record(
                "connector.readonly_powershell.completed",
                request.context,
                {
                    "provider": self.provider_name,
                    "device_uid_present": True,
                    "job_uid_present": True,
                    "job_status": final_status.casefold(),
                    "stdout_bounded": stdout_bounded,
                    "stderr_bounded": stderr_bounded,
                },
            )
            return ConnectorResult(
                capability=request.context.capability,
                provider=self.provider_name,
                data={
                    "status": "succeeded",
                    "job_uid": job_uid,
                    "job_status": final_status,
                    "device_uid": device_uid,
                    "component_uid": DATTO_AD_HOC_POWERSHELL_UID,
                    "component_name": DATTO_AD_HOC_POWERSHELL_NAME,
                    "classification": "read_only",
                    "active_probe": prepared.active_probe,
                    "stdout": stdout,
                    "stderr": stderr,
                    "stdout_match_count": stdout_matches,
                    "stderr_match_count": stderr_matches,
                    "output_bounded": stdout_bounded or stderr_bounded,
                    "completion_verified": True,
                    "output_read_arguments": {
                        "resource_id": job_uid,
                        "device_uid": device_uid,
                        "component_uid": DATTO_AD_HOC_POWERSHELL_UID,
                        "stream": "stdout",
                    },
                },
                evidence_ids=(f"datto-rmm:job:{job_uid}",),
            )
        finally:
            token = None


def build_datto_powershell_read_invoker(
    *,
    openbao_url: str,
    transport: HttpTransport,
    audit: AuditSink,
) -> CapabilityInvoker:
    role_id_path = Path(
        os.getenv(DATTO_EXECUTION_ROLE_ID_PATH_ENV, str(DEFAULT_ROLE_ID_PATH))
    )
    secret_id_path = Path(
        os.getenv(DATTO_EXECUTION_SECRET_ID_PATH_ENV, str(DEFAULT_SECRET_ID_PATH))
    )
    secrets = OpenBaoSecretResolver(
        base_url=openbao_url,
        role_id_path=role_id_path,
        secret_id_path=secret_id_path,
    )
    connector = DattoRmmPowerShellReadConnector(
        secrets=secrets,
        transport=transport,
        audit=audit,
    )
    return GovernedConnectorCapabilityInvoker(
        connectors={DATTO_RMM_POWERSHELL_READ_PROVIDER: connector},
        provider_capability_map={
            (
                DATTO_RMM_POWERSHELL_READ_PROVIDER,
                ENDPOINT_POWERSHELL_READ,
            ): DATTO_RMM_POWERSHELL_READ_PROVIDER_CAPABILITY,
        },
        default_maximum_execution_seconds=30.0,
    )


def register_datto_powershell_read_invoker(
    *,
    invokers: CapabilityInvokerRegistry,
    invoker: CapabilityInvoker,
) -> None:
    invokers.register(ENDPOINT_POWERSHELL_READ, invoker)
