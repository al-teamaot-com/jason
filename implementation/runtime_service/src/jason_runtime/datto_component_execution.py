from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping

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
from connectors.datto_rmm.auth import (
    acquire_access_token,
    require_durable_credentials,
)
from connectors.datto_rmm.component_execution import (
    ComponentAllowlistEntry,
    DattoRmmComponentExecutionPolicy,
    StaticComponentAllowlist,
)
from connectors.datto_rmm.execution_identity import (
    DATTO_RMM_EXECUTION_LOGICAL_SECRET,
)
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

from .datto_component_scope import (
    DATTO_EXECUTION_COMPONENT_NAME_ENV,
    DATTO_EXECUTION_COMPONENT_UID_ENV,
    DATTO_EXECUTION_COMPONENTS_JSON_ENV,
    DattoApprovedComponent,
    configured_datto_components,
    resolve_datto_component,
)


AUTOMATION_COMPONENT_EXECUTE = "automation.component.execute"
DATTO_RMM_COMPONENT_EXECUTION_PROVIDER = "datto_rmm_component_execution"

DATTO_COMPONENT_EXECUTION_PROFILE_ENV = (
    "JASON_DATTO_COMPONENT_EXECUTION_MCP_PROFILE"
)
DATTO_COMPONENT_EXECUTION_PROFILE = "owner-diagnostic-v1"

DATTO_EXECUTION_ALLOWLIST_NAME_ENV = (
    "JASON_DATTO_COMPONENT_EXECUTION_ALLOWLIST_NAME"
)
DATTO_EXECUTION_DEVICE_UID_ENV = (
    "JASON_DATTO_COMPONENT_EXECUTION_DEVICE_UID"
)
DATTO_EXECUTION_DEVICE_CLASS_ENV = (
    "JASON_DATTO_COMPONENT_EXECUTION_DEVICE_CLASS"
)

DATTO_EXECUTION_ROLE_ID_PATH_ENV = (
    "JASON_DATTO_EXECUTION_OPENBAO_ROLE_ID_PATH"
)
DATTO_EXECUTION_SECRET_ID_PATH_ENV = (
    "JASON_DATTO_EXECUTION_OPENBAO_SECRET_ID_PATH"
)

DEFAULT_ROLE_ID_PATH = Path(
    "/run/jason-secrets/openbao/datto-rmm-execution/role_id"
)
DEFAULT_SECRET_ID_PATH = Path(
    "/run/jason-secrets/openbao/datto-rmm-execution/secret_id"
)

_SUCCESS_STATUSES = frozenset(
    {
        "complete",
        "completed",
        "success",
        "successful",
        "succeeded",
        "finished",
    }
)

_FAILURE_STATUSES = frozenset(
    {
        "failed",
        "failure",
        "error",
        "cancelled",
        "canceled",
        "aborted",
    }
)

_PROVIDER_CAPABILITY_MAP = {
    (
        DATTO_RMM_COMPONENT_EXECUTION_PROVIDER,
        AUTOMATION_COMPONENT_EXECUTE,
    ): "datto_rmm.component.execute",
}


class DattoRmmComponentExecutionActivationError(RuntimeError):
    pass


class DattoRmmComponentExecutionVerificationError(ConnectorError):
    error_code = "DATTO_RMM_COMPONENT_EXECUTION_VERIFICATION_FAILED"


@dataclass(frozen=True, slots=True)
class DattoComponentExecutionPilot:
    allowlist_name: str
    components: tuple[DattoApprovedComponent, ...]
    device_uid: str
    device_class: str


@dataclass(frozen=True, slots=True)
class DattoComponentExecutionActivationState:
    profile: str
    enabled: bool
    provider_ids: tuple[str, ...]
    capability_names: tuple[str, ...]


def _env(name: str) -> str:
    return os.getenv(name, "").strip()


def configured_pilot() -> DattoComponentExecutionPilot | None:
    allowlist_name = _env(DATTO_EXECUTION_ALLOWLIST_NAME_ENV)
    device_uid = _env(DATTO_EXECUTION_DEVICE_UID_ENV)
    device_class = _env(DATTO_EXECUTION_DEVICE_CLASS_ENV)
    components = configured_datto_components()

    if (
        not allowlist_name
        and not device_uid
        and not device_class
        and not components
    ):
        return None

    if (
        not allowlist_name
        or not device_uid
        or not device_class
        or not components
    ):
        raise DattoRmmComponentExecutionActivationError(
            "Datto execution pilot configuration is incomplete"
        )

    return DattoComponentExecutionPilot(
        allowlist_name=allowlist_name,
        components=components,
        device_uid=device_uid,
        device_class=device_class,
    )


def datto_component_execution_mcp_surface_enabled() -> bool:
    profile = _env(
        DATTO_COMPONENT_EXECUTION_PROFILE_ENV
    ).casefold()

    if profile != DATTO_COMPONENT_EXECUTION_PROFILE:
        return False

    return configured_pilot() is not None


def _capability_definition(
    *,
    now: datetime,
) -> CapabilityDefinition:
    return CapabilityDefinition(
        capability_name=AUTOMATION_COMPONENT_EXECUTE,
        version="1.0",
        display_name="Execute Approved Automation Component",
        lifecycle_status=CapabilityLifecycle.BUILDING,
        business_purpose=(
            "Execute one explicitly approved diagnostic automation "
            "component against one explicitly approved pilot endpoint."
        ),
        owner_service="Jason Governed Actions",
        architectural_capability_ids=frozenset(
            {
                "JAC-005",
                "JAC-006",
                "JAC-013",
            }
        ),
        risk_level=CapabilityRisk.HIGH,
        data_classifications=frozenset({"internal"}),
        permitted_execution_modes=frozenset({"deterministic"}),
        input_schema_reference=(
            "schema://jason/automation-component-execute/1.0"
        ),
        output_schema_reference=(
            "schema://jason/automation-component-execute-result/1.0"
        ),
        invoking_roles=frozenset({"orchestrator"}),
        approval=CapabilityApproval(
            required=True,
            approver_classes=("owner",),
        ),
        evidence=CapabilityEvidence(
            required=True,
            requirements=(
                "authenticated requester identity",
                "exact approved endpoint identity",
                "exact approved component identity",
                "provider quick-job result",
                "post-mutation job identity and status readback",
            ),
            verification_requirements=(
                "execution uses the separate Datto execution identity",
                "endpoint exactly matches the configured pilot endpoint",
                "component exactly matches the configured allowlist",
                "no unapproved component variables are accepted",
                "exactly one provider mutation request is issued",
                "job identity and status are read after creation",
                "terminal completion is verified through automation.job.read when the provider job remains asynchronous",
            ),
        ),
        dependencies=frozenset(
            {
                "identity.authorization.resolve",
                "governance.action.evaluate",
                "automation.job.read",
            }
        ),
        idempotency_behavior=(
            IdempotencyBehavior.NON_IDEMPOTENT
        ),
        idempotency_key_required=True,
        timeout_seconds=30,
        maximum_attempts=1,
        failure_behavior=(
            "Fail closed without retry, arbitrary shell execution, "
            "component substitution, target substitution, or "
            "unverified job identity."
        ),
        tenant_isolation_required=True,
        client_isolation_required=False,
        stewardship=CapabilityStewardship(
            steward="technology-steward",
            business_justification=(
                "Permit narrowly governed execution of existing "
                "approved RMM automation components."
            ),
            review_interval_days=30,
            retirement_criteria=(
                "Execution identity containment can no longer be proven.",
                "Component or endpoint leaves the approved pilot scope.",
                "A safer approved execution mechanism replaces this pilot.",
            ),
            authoritative_change_sources=(
                "Datto RMM API documentation",
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
            "resource_types": (
                "automation_component,automation_job,endpoint"
            ),
            "operation": "execute",
            "mcp_action_enabled": "true",
            "mcp_tool_name": "execute_governed_capability",
            "conversation_authenticated_imperative_is_approval": (
                "false"
            ),
            "component_approval_policy": (
                "server_classified_standing_safe_or_per_run"
            ),
            "pilot_scope": "aot_owner_exact_component_exact_endpoint",
            "provider_native_execution_identity_required": "true",
            "arbitrary_shell_allowed": "false",
            "activation_state": (
                "datto_component_execution_source_only_not_activated"
            ),
        },
    )


def _provider(
    *,
    now: datetime,
) -> ExecutionProvider:
    return ExecutionProvider(
        provider_id=DATTO_RMM_COMPONENT_EXECUTION_PROVIDER,
        display_name="Datto RMM Governed Component Execution",
        provider_type=ProviderType.EXTERNAL_CONNECTOR,
        lifecycle_status=ProviderLifecycle.PLANNED,
        health_status=ProviderHealth.UNKNOWN,
        approval_status=ProviderApproval.PILOT,
        execution_modes=frozenset({"deterministic"}),
        capabilities=frozenset(
            {
                AUTOMATION_COMPONENT_EXECUTE,
            }
        ),
        supported_classifications=frozenset({"internal"}),
        regions=frozenset(),
        limits=ProviderLimits(
            maximum_concurrent_executions=1,
            maximum_requests_per_minute=10,
            maximum_execution_seconds=30,
        ),
        features=ProviderFeatures(
            structured_output=True,
        ),
        pricing_profile_id="zero-cost-foundation",
        stewardship=ProviderStewardship(
            technology_steward="technology-steward",
            business_justification=(
                "Execute one allowlisted Datto quick job through "
                "the separate least-privilege execution identity."
            ),
            review_interval_days=30,
            last_reviewed_at=now,
            retirement_criteria=(
                "Provider execution identity exceeds approved authority.",
                "Component allowlist enforcement cannot be proven.",
            ),
            vendor_change_sources=(
                "Datto RMM API documentation",
            ),
            operational_owner="AOT IT Operations",
            approval_owner="AOT Owner",
        ),
        created_at=now,
        metadata={
            "connector_id": "datto_rmm",
            "resource_authority": "managed_endpoint",
            "write_capability": "true",
            "mutation_scope": "approved_component_quick_job_only",
            "logical_secret": DATTO_RMM_EXECUTION_LOGICAL_SECRET,
            "activation_state": (
                "datto_component_execution_source_only_not_activated"
            ),
        },
    )


def apply_datto_component_execution_activation(
    *,
    capabilities: CapabilityRegistryService,
    providers: ExecutionProviderRegistryService,
    profile: str | None,
) -> DattoComponentExecutionActivationState:
    normalized = str(
        profile or ""
    ).strip().casefold()

    if not normalized:
        return DattoComponentExecutionActivationState(
            profile="",
            enabled=False,
            provider_ids=(),
            capability_names=(),
        )

    if normalized != DATTO_COMPONENT_EXECUTION_PROFILE:
        raise DattoRmmComponentExecutionActivationError(
            "unsupported Datto component-execution MCP profile"
        )

    pilot = configured_pilot()

    if pilot is None:
        raise DattoRmmComponentExecutionActivationError(
            "Datto component-execution pilot configuration is absent"
        )

    capability = capabilities.get(
        capability_name=AUTOMATION_COMPONENT_EXECUTE,
        version="1.0",
    )

    provider = providers.get(
        DATTO_RMM_COMPONENT_EXECUTION_PROVIDER
    )

    if capability.lifecycle_status is not CapabilityLifecycle.BUILDING:
        raise DattoRmmComponentExecutionActivationError(
            "Datto execution capability is not BUILDING"
        )

    if not capability.approval.required:
        raise DattoRmmComponentExecutionActivationError(
            "Datto execution unexpectedly lacks approval"
        )

    if not capability.idempotency_key_required:
        raise DattoRmmComponentExecutionActivationError(
            "Datto execution unexpectedly lacks idempotency"
        )

    if capability.maximum_attempts != 1:
        raise DattoRmmComponentExecutionActivationError(
            "Datto execution permits provider retry"
        )

    if provider.lifecycle_status is not ProviderLifecycle.PLANNED:
        raise DattoRmmComponentExecutionActivationError(
            "Datto execution provider is not PLANNED"
        )

    capabilities.set_lifecycle(
        capability_name=AUTOMATION_COMPONENT_EXECUTE,
        version="1.0",
        lifecycle_status=CapabilityLifecycle.ACTIVE,
    )

    providers.set_approval(
        provider_id=DATTO_RMM_COMPONENT_EXECUTION_PROVIDER,
        approval_status=ProviderApproval.APPROVED,
    )

    providers.set_health(
        provider_id=DATTO_RMM_COMPONENT_EXECUTION_PROVIDER,
        health_status=ProviderHealth.HEALTHY,
    )

    providers.set_lifecycle(
        provider_id=DATTO_RMM_COMPONENT_EXECUTION_PROVIDER,
        lifecycle_status=ProviderLifecycle.AVAILABLE,
    )

    return DattoComponentExecutionActivationState(
        profile=normalized,
        enabled=True,
        provider_ids=(
            DATTO_RMM_COMPONENT_EXECUTION_PROVIDER,
        ),
        capability_names=(
            AUTOMATION_COMPONENT_EXECUTE,
        ),
    )


def register_datto_component_execution_runtime_foundation(
    *,
    capabilities: CapabilityRegistryService,
    providers: ExecutionProviderRegistryService,
    now: datetime,
) -> DattoComponentExecutionActivationState:
    capabilities.register(
        _capability_definition(
            now=now,
        )
    )

    providers.register(
        _provider(
            now=now,
        )
    )

    return apply_datto_component_execution_activation(
        capabilities=capabilities,
        providers=providers,
        profile=os.getenv(
            DATTO_COMPONENT_EXECUTION_PROFILE_ENV,
            "",
        ),
    )


class DattoRmmComponentExecutionConnector:
    provider_name = "datto_rmm"
    capabilities = frozenset(
        {
            "datto_rmm.component.execute",
        }
    )

    def __init__(
        self,
        *,
        secrets: SecretResolver,
        transport: HttpTransport,
        audit: AuditSink,
        pilot: DattoComponentExecutionPilot | None,
        sleeper: Callable[[float], None] = time.sleep,
        maximum_status_reads: int = 1,
        status_interval_seconds: float = 0.0,
    ) -> None:
        self._secrets = secrets
        self._transport = transport
        self._audit = audit
        self._pilot = pilot
        self._sleeper = sleeper
        self._maximum_status_reads = maximum_status_reads
        self._status_interval_seconds = status_interval_seconds

        if maximum_status_reads < 1 or maximum_status_reads > 10:
            raise ValueError(
                "maximum_status_reads must be between 1 and 10"
            )

        if status_interval_seconds < 0 or status_interval_seconds > 5:
            raise ValueError(
                "status_interval_seconds must be between 0 and 5"
            )

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

        raise DattoRmmComponentExecutionVerificationError(
            "quick-job response did not expose a durable job uid"
        )

    @staticmethod
    def _job_record(
        payload: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        nested = payload.get("job")

        if isinstance(nested, Mapping):
            return nested

        return payload

    @classmethod
    def _status(
        cls,
        payload: Mapping[str, Any],
    ) -> str:
        record = cls._job_record(payload)
        status = str(
            record.get("status")
            or record.get("jobStatus")
            or record.get("state")
            or ""
        ).strip()

        if not status:
            raise DattoRmmComponentExecutionVerificationError(
                "job read response did not expose a status"
            )

        return status

    def execute(
        self,
        request: ConnectorRequest,
    ) -> ConnectorResult:
        if (
            request.context.capability
            != "datto_rmm.component.execute"
        ):
            raise ConnectorAuthorizationError(
                "Datto execution connector exposes only "
                "component execution"
            )

        if request.context.mode != "execute":
            raise ConnectorAuthorizationError(
                "Datto component execution requires execute mode"
            )

        pilot = self._pilot

        if pilot is None:
            raise PermissionError(
                "DATTO_COMPONENT_EXECUTION_PILOT_DISABLED"
            )

        requested_allowlist = str(
            request.arguments.get("allowlist_name")
            or ""
        ).strip()

        if requested_allowlist != pilot.allowlist_name:
            raise PermissionError(
                "DATTO_COMPONENT_ALLOWLIST_MISMATCH"
            )

        requested_device = str(
            request.arguments.get("device_uid")
            or request.arguments.get("resource_id")
            or ""
        ).strip()

        if requested_device != pilot.device_uid:
            raise PermissionError(
                "DATTO_COMPONENT_TARGET_NOT_APPROVED"
            )

        requested_class = str(
            request.arguments.get("device_class")
            or ""
        ).strip()

        if requested_class.casefold() != pilot.device_class.casefold():
            raise PermissionError(
                "DATTO_COMPONENT_TARGET_CLASS_NOT_APPROVED"
            )

        selected_component = resolve_datto_component(
            pilot.components,
            component_uid=request.arguments.get("component_uid"),
            component_name=request.arguments.get("component_name"),
            catalog_verified=True,
        )

        variables = request.arguments.get(
            "variables",
            {},
        )

        allowlist = StaticComponentAllowlist(
            entries=(
                ComponentAllowlistEntry(
                    allowlist_name=pilot.allowlist_name,
                    canonical_component_id=(
                        f"datto:{pilot.allowlist_name}:{selected_component.uid}"
                    ),
                    display_name=selected_component.name,
                    provider_component_uid=selected_component.uid,
                    allowed_target_classes=frozenset(
                        {
                            pilot.device_class,
                        }
                    ),
                    # The production pilot deliberately permits no
                    # conversation-supplied component variables.
                    variable_policies=(),
                    requires_per_run_approval=(
                        selected_component.requires_explicit_approval
                    ),
                    status="active",
                ),
            )
        )

        policy = DattoRmmComponentExecutionPolicy(
            allowlist=allowlist
        )

        prepared = policy.prepare(
            allowlist_name=pilot.allowlist_name,
            device_uid=pilot.device_uid,
            device_class=pilot.device_class,
            component_uid=selected_component.uid,
            variables=variables,
            job_name=str(
                request.arguments.get("job_name")
                or f"Jason - {selected_component.name}"
            ),
            observed_component_name=selected_component.name,
        )

        credentials = self._secrets.resolve(
            DATTO_RMM_EXECUTION_LOGICAL_SECRET,
            request.context,
        )

        require_durable_credentials(credentials)

        token = acquire_access_token(
            credentials=credentials
        )

        try:
            headers = {
                "Authorization": (
                    f"{token.token_type} {token.access_token}"
                ),
                "Accept": "application/json",
                "Content-Type": "application/json",
            }

            url = (
                credentials["api_url"].rstrip("/")
                + prepared.provider_request.path
            )

            self._audit.record(
                "connector.mutation.requested",
                request.context,
                {
                    "provider": self.provider_name,
                    "capability": request.context.capability,
                    "operation": "quickjob",
                    "argument_digest": (
                        prepared.provider_request.digest()
                    ),
                },
            )

            created = self._transport.request(
                method=prepared.provider_request.method,
                url=url,
                headers=headers,
                params=None,
                json=prepared.provider_request.body,
                timeout_seconds=20.0,
            )

            if not isinstance(created, Mapping):
                raise DattoRmmComponentExecutionVerificationError(
                    "quick-job response was not an object"
                )

            job_uid = self._job_uid(created)

            self._audit.record(
                "connector.mutation.completed",
                request.context,
                {
                    "provider": self.provider_name,
                    "capability": request.context.capability,
                    "job_uid_present": True,
                },
            )

            last_status = None

            for index in range(
                self._maximum_status_reads
            ):
                status_payload = self._transport.request(
                    method="GET",
                    url=(
                        credentials["api_url"].rstrip("/")
                        + f"/api/v2/job/{job_uid}"
                    ),
                    headers={
                        "Authorization": (
                            f"{token.token_type} "
                            f"{token.access_token}"
                        ),
                        "Accept": "application/json",
                    },
                    params=None,
                    json=None,
                    timeout_seconds=10.0,
                )

                if not isinstance(
                    status_payload,
                    Mapping,
                ):
                    raise DattoRmmComponentExecutionVerificationError(
                        "job read response was not an object"
                    )

                readback_uid = self._job_uid(status_payload)

                if readback_uid != job_uid:
                    raise DattoRmmComponentExecutionVerificationError(
                        "job readback uid did not match the created quick job"
                    )

                status = self._status(
                    status_payload
                )

                last_status = status
                normalized = status.casefold()

                if normalized in _SUCCESS_STATUSES:
                    self._audit.record(
                        "connector.mutation.verified",
                        request.context,
                        {
                            "provider": self.provider_name,
                            "capability": request.context.capability,
                            "job_uid_present": True,
                            "terminal_status": normalized,
                        },
                    )

                    return ConnectorResult(
                        capability=request.context.capability,
                        provider=self.provider_name,
                        data={
                            "status": "verified",
                            "job_uid": job_uid,
                            "job_status": status,
                            "readback_verified": True,
                            "completion_verified": True,
                            "allowlist_name": (
                                pilot.allowlist_name
                            ),
                        },
                        evidence_ids=(
                            f"datto-rmm:job:{job_uid}",
                        ),
                    )

                if normalized in _FAILURE_STATUSES:
                    raise DattoRmmComponentExecutionVerificationError(
                        "Datto quick job reached a failure terminal state"
                    )

                if (
                    index + 1
                    < self._maximum_status_reads
                    and self._status_interval_seconds
                    > 0
                ):
                    self._sleeper(
                        self._status_interval_seconds
                    )

            self._audit.record(
                "connector.mutation.accepted",
                request.context,
                {
                    "provider": self.provider_name,
                    "capability": request.context.capability,
                    "job_uid_present": True,
                    "job_status": str(last_status or "").casefold(),
                    "completion_verified": False,
                },
            )

            return ConnectorResult(
                capability=request.context.capability,
                provider=self.provider_name,
                data={
                    "status": "accepted",
                    "job_uid": job_uid,
                    "job_status": last_status,
                    "readback_verified": True,
                    "completion_verified": False,
                    "allowlist_name": pilot.allowlist_name,
                },
                evidence_ids=(
                    f"datto-rmm:job:{job_uid}",
                ),
                warnings=(
                    "Datto quick job is still asynchronous; verify terminal completion with automation.job.read.",
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
                },
            )
            raise

        finally:
            token = None


def build_datto_component_execution_invoker(
    *,
    openbao_url: str,
    transport: HttpTransport,
    audit: AuditSink,
) -> CapabilityInvoker:
    role_id_path = Path(
        os.getenv(
            DATTO_EXECUTION_ROLE_ID_PATH_ENV,
            str(DEFAULT_ROLE_ID_PATH),
        )
    )

    secret_id_path = Path(
        os.getenv(
            DATTO_EXECUTION_SECRET_ID_PATH_ENV,
            str(DEFAULT_SECRET_ID_PATH),
        )
    )

    secrets = OpenBaoSecretResolver(
        base_url=openbao_url,
        role_id_path=role_id_path,
        secret_id_path=secret_id_path,
    )

    connector = DattoRmmComponentExecutionConnector(
        secrets=secrets,
        transport=transport,
        audit=audit,
        pilot=configured_pilot(),
    )

    return GovernedConnectorCapabilityInvoker(
        connectors={
            DATTO_RMM_COMPONENT_EXECUTION_PROVIDER: connector,
        },
        provider_capability_map=_PROVIDER_CAPABILITY_MAP,
        default_maximum_execution_seconds=30.0,
    )


def register_datto_component_execution_invoker(
    *,
    invokers: CapabilityInvokerRegistry,
    invoker: CapabilityInvoker,
) -> None:
    invokers.register(
        AUTOMATION_COMPONENT_EXECUTE,
        invoker,
    )
