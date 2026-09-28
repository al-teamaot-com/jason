from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

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
from kernel.resolution import CapabilityResolutionResult
from kernel.identity_authority import AuthorityGrant, IdentityRecord, PermissionMode
from orchestrator.contracts import OrchestrationRequest
from orchestrator.invokers import CapabilityInvokerRegistry
from orchestrator.service import InvocationResult


DEPLOYMENT_REPAIR_APPLY = "deployment.repair.apply"
DEPLOYMENT_REPAIR_STATUS = "deployment.repair.status"
AUTONOMOUS_REPAIR_DEPLOYMENT_PROVIDER = "jason_host_repair_runner"
AUTONOMOUS_REPAIR_PROFILE_ENV = "JASON_AUTONOMOUS_REPAIR_DEPLOYMENT_PROFILE"
AUTONOMOUS_REPAIR_PROFILE = "autonomous-repair-v1"
AUTONOMOUS_REPAIR_SPOOL_ENV = "JASON_AUTONOMOUS_REPAIR_SPOOL"
DEFAULT_SPOOL = Path("/var/lib/jason/openclaw/autonomous-repair")

_SHA = re.compile(r"^[0-9a-f]{40}$")
_SUPPORT = re.compile(r"^SUPPORT-[A-Z]+-[0-9]+$")
_REQUEST_ID = re.compile(r"^[0-9a-f]{64}$")


class AutonomousRepairDeploymentActivationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class AutonomousRepairDeploymentActivationState:
    profile: str
    enabled: bool
    provider_ids: tuple[str, ...]
    capability_names: tuple[str, ...]


def autonomous_repair_deployment_enabled() -> bool:
    return (
        os.getenv(AUTONOMOUS_REPAIR_PROFILE_ENV, "").strip().casefold()
        == AUTONOMOUS_REPAIR_PROFILE
    )


def _apply_capability(now: datetime) -> CapabilityDefinition:
    return CapabilityDefinition(
        capability_name=DEPLOYMENT_REPAIR_APPLY,
        version="1.0",
        display_name="Queue Autonomous Repair Deployment",
        lifecycle_status=CapabilityLifecycle.BUILDING,
        business_purpose=(
            "Queue one exact J-CHANGE-002-authorized Jason software repair for "
            "the dedicated host deployment runner without exposing Docker or host shell "
            "authority to the runtime."
        ),
        owner_service="Jason Deployment System",
        architectural_capability_ids=frozenset({"JAC-005", "JAC-006", "JAC-013"}),
        risk_level=CapabilityRisk.HIGH,
        data_classifications=frozenset({"internal"}),
        permitted_execution_modes=frozenset({"deterministic"}),
        input_schema_reference="schema://jason/deployment-repair-apply/1.0",
        output_schema_reference="schema://jason/deployment-repair-queued/1.0",
        invoking_roles=frozenset({"orchestrator"}),
        approval=CapabilityApproval(required=False),
        evidence=CapabilityEvidence(
            required=True,
            requirements=(
                "exact merged candidate SHA",
                "exact observed production rollback SHA",
                "open SUPPORT item",
                "merged PR number",
                "J-CHANGE-002 repair classification",
                "post-deploy verification declaration",
            ),
            verification_requirements=(
                "request principal is Jason autonomous workload identity",
                "candidate and rollback SHAs are exact immutable commit identifiers",
                "host runner independently revalidates J-CHANGE-002 eligibility",
                "host runner observes rollback SHA directly from live runtime",
                "host runner verifies live source revision after deployment",
            ),
        ),
        dependencies=frozenset(),
        idempotency_behavior=IdempotencyBehavior.IDEMPOTENT,
        idempotency_key_required=False,
        timeout_seconds=5,
        maximum_attempts=1,
        failure_behavior=(
            "Fail closed without host mutation when request identity, repair metadata, "
            "spool integrity, live rollback revision, or independent repair eligibility "
            "cannot be proven."
        ),
        tenant_isolation_required=True,
        client_isolation_required=False,
        stewardship=CapabilityStewardship(
            steward="technology-steward",
            business_justification=(
                "Permit Jason to restore already-approved software behavior through a "
                "bounded repair-only release lane without giving the runtime host privileges."
            ),
            review_interval_days=30,
            retirement_criteria=(
                "A safer governed deployment transport replaces the spool runner.",
                "J-CHANGE-002 autonomous repair authority is retired.",
            ),
            authoritative_change_sources=(
                "J-CHANGE-002",
                "Jason Deployment System",
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
            "resource_types": "jason_deployment,repair_release",
            "operation": "apply",
            "selector_keys": (
                "candidate_sha,rollback_sha,support_item,pr_number,"
                "post_deploy_verification"
            ),
            "mcp_action_enabled": "false",
            "autonomous_repair_only": "true",
            "standing_authority_source": "J-CHANGE-002",
            "host_privilege_exposed_to_runtime": "false",
            "activation_state": "source_only_not_activated",
        },
    )


def _status_capability(now: datetime) -> CapabilityDefinition:
    return CapabilityDefinition(
        capability_name=DEPLOYMENT_REPAIR_STATUS,
        version="1.0",
        display_name="Read Autonomous Repair Deployment Status",
        lifecycle_status=CapabilityLifecycle.BUILDING,
        business_purpose=(
            "Read bounded durable status for one exact autonomous repair deployment request."
        ),
        owner_service="Jason Deployment System",
        architectural_capability_ids=frozenset({"JAC-005", "JAC-013"}),
        risk_level=CapabilityRisk.LOW,
        data_classifications=frozenset({"internal"}),
        permitted_execution_modes=frozenset({"deterministic"}),
        input_schema_reference="schema://jason/deployment-repair-status/1.0",
        output_schema_reference="schema://jason/deployment-repair-status-result/1.0",
        invoking_roles=frozenset({"orchestrator"}),
        approval=CapabilityApproval(required=False),
        evidence=CapabilityEvidence(
            required=True,
            requirements=("exact repair request ID",),
            verification_requirements=(
                "status is read only from the bounded repair spool",
                "raw build or secret output is not returned",
            ),
        ),
        dependencies=frozenset(),
        idempotency_behavior=IdempotencyBehavior.IDEMPOTENT,
        idempotency_key_required=False,
        timeout_seconds=5,
        maximum_attempts=1,
        failure_behavior="Fail closed without directory traversal or broad spool enumeration.",
        tenant_isolation_required=True,
        client_isolation_required=False,
        stewardship=CapabilityStewardship(
            steward="technology-steward",
            business_justification="Expose bounded post-restart repair deployment evidence.",
            review_interval_days=30,
            retirement_criteria=(
                "A replacement deployment evidence capability provides equal or stronger controls.",
            ),
            authoritative_change_sources=("J-CHANGE-002",),
            last_reviewed_at=now,
            operational_owner="AOT IT Operations",
            approval_owner="AOT Owner",
        ),
        created_at=now,
        metadata={
            "provider_neutral": "true",
            "read_only": "true",
            "resource_types": "jason_deployment,repair_release",
            "operation": "status",
            "selector_keys": "request_id",
            "fact_hints": "repair deployment status result rollback verification",
            "activation_state": "source_only_not_activated",
        },
    )


def _provider(now: datetime) -> ExecutionProvider:
    return ExecutionProvider(
        provider_id=AUTONOMOUS_REPAIR_DEPLOYMENT_PROVIDER,
        display_name="Jason Host Autonomous Repair Runner",
        provider_type=ProviderType.WORKFLOW,
        lifecycle_status=ProviderLifecycle.PLANNED,
        health_status=ProviderHealth.UNKNOWN,
        approval_status=ProviderApproval.PILOT,
        execution_modes=frozenset({"deterministic"}),
        capabilities=frozenset({DEPLOYMENT_REPAIR_APPLY, DEPLOYMENT_REPAIR_STATUS}),
        supported_classifications=frozenset({"internal"}),
        regions=frozenset(),
        limits=ProviderLimits(
            maximum_concurrent_executions=1,
            maximum_requests_per_minute=6,
            maximum_execution_seconds=5,
        ),
        features=ProviderFeatures(structured_output=True),
        pricing_profile_id="zero-cost-foundation",
        stewardship=ProviderStewardship(
            technology_steward="technology-steward",
            business_justification=(
                "Separate host-level deployment privilege from Jason runtime while preserving "
                "a named governed deployment capability and durable evidence."
            ),
            review_interval_days=30,
            last_reviewed_at=now,
            retirement_criteria=(
                "A stronger deployment runner with equal privilege separation replaces it.",
            ),
            vendor_change_sources=("J-CHANGE-002", "Jason Deployment System"),
            operational_owner="AOT IT Operations",
            approval_owner="AOT Owner",
        ),
        created_at=now,
        metadata={
            "authoritative": "true",
            "host_runner": "true",
            "docker_socket_exposed_to_runtime": "false",
            "spool_transport": "true",
        },
    )


def register_autonomous_repair_deployment_foundation(
    *,
    capabilities: CapabilityRegistryService,
    providers: ExecutionProviderRegistryService,
    now: datetime,
) -> AutonomousRepairDeploymentActivationState:
    capabilities.register(_apply_capability(now))
    capabilities.register(_status_capability(now))
    providers.register(_provider(now))

    profile = os.getenv(AUTONOMOUS_REPAIR_PROFILE_ENV, "").strip().casefold()
    if not profile:
        return AutonomousRepairDeploymentActivationState("", False, (), ())
    if profile != AUTONOMOUS_REPAIR_PROFILE:
        raise AutonomousRepairDeploymentActivationError(
            "unsupported autonomous repair deployment profile"
        )

    for capability_name in (DEPLOYMENT_REPAIR_APPLY, DEPLOYMENT_REPAIR_STATUS):
        capabilities.set_lifecycle(
            capability_name=capability_name,
            version="1.0",
            lifecycle_status=CapabilityLifecycle.ACTIVE,
        )
    providers.set_approval(
        provider_id=AUTONOMOUS_REPAIR_DEPLOYMENT_PROVIDER,
        approval_status=ProviderApproval.APPROVED,
    )
    providers.set_health(
        provider_id=AUTONOMOUS_REPAIR_DEPLOYMENT_PROVIDER,
        health_status=ProviderHealth.HEALTHY,
    )
    providers.set_lifecycle(
        provider_id=AUTONOMOUS_REPAIR_DEPLOYMENT_PROVIDER,
        lifecycle_status=ProviderLifecycle.AVAILABLE,
    )
    return AutonomousRepairDeploymentActivationState(
        profile,
        True,
        (AUTONOMOUS_REPAIR_DEPLOYMENT_PROVIDER,),
        (DEPLOYMENT_REPAIR_APPLY, DEPLOYMENT_REPAIR_STATUS),
    )


def _exact_sha(value: Any, field: str) -> str:
    text = str(value or "").strip().casefold()
    if not _SHA.fullmatch(text):
        raise ValueError(f"{field} must be an exact 40-character lowercase git SHA")
    return text


def _support_item(value: Any) -> str:
    text = str(value or "").strip().upper()
    if not _SUPPORT.fullmatch(text):
        raise ValueError("support_item must be an exact SUPPORT-<AREA>-<NUMBER> identifier")
    return text


def _positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a positive integer")
    try:
        number = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} must be a positive integer") from error
    if number < 1:
        raise ValueError(f"{field} must be a positive integer")
    return number


def _bounded_text(value: Any, field: str, maximum: int = 512) -> str:
    text = str(value or "").strip()
    if not text or len(text) > maximum:
        raise ValueError(f"{field} must be non-empty and at most {maximum} characters")
    return text


def _canonical_request(arguments: Mapping[str, Any]) -> dict[str, Any]:
    allowed = {
        "candidate_sha",
        "rollback_sha",
        "support_item",
        "pr_number",
        "post_deploy_verification",
    }
    unknown = set(arguments) - allowed
    if unknown:
        raise ValueError(
            "unsupported autonomous repair deployment arguments: "
            + ", ".join(sorted(str(value) for value in unknown))
        )
    candidate = _exact_sha(arguments.get("candidate_sha"), "candidate_sha")
    rollback = _exact_sha(arguments.get("rollback_sha"), "rollback_sha")
    if candidate == rollback:
        raise ValueError("candidate_sha must differ from rollback_sha")
    return {
        "candidate_sha": candidate,
        "rollback_sha": rollback,
        "support_item": _support_item(arguments.get("support_item")),
        "pr_number": _positive_int(arguments.get("pr_number"), "pr_number"),
        "post_deploy_verification": _bounded_text(
            arguments.get("post_deploy_verification"),
            "post_deploy_verification",
        ),
    }


def _request_fingerprint(payload: Mapping[str, Any]) -> str:
    authority_material = {
        key: payload[key]
        for key in (
            "capability",
            "provider",
            "principal_id",
            "organization_id",
            "candidate_sha",
            "rollback_sha",
            "support_item",
            "pr_number",
            "post_deploy_verification",
        )
    }
    encoded = json.dumps(
        authority_material,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _atomic_write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    data = json.dumps(dict(payload), indent=2, sort_keys=True) + "\n"
    with temp.open("x", encoding="utf-8") as handle:
        os.chmod(temp, 0o600)
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)


@dataclass(slots=True)
class AutonomousRepairDeploymentInvoker:
    spool_root: Path = DEFAULT_SPOOL

    def invoke(
        self,
        *,
        request: OrchestrationRequest,
        resolution: CapabilityResolutionResult,
    ) -> InvocationResult:
        if resolution.selected_provider_id != AUTONOMOUS_REPAIR_DEPLOYMENT_PROVIDER:
            raise PermissionError("autonomous repair resolved to an unexpected provider")
        if request.capability_name != resolution.capability_name:
            raise ValueError("resolved autonomous repair capability does not match request")

        if resolution.capability_name == DEPLOYMENT_REPAIR_APPLY:
            return self._apply(request)
        if resolution.capability_name == DEPLOYMENT_REPAIR_STATUS:
            return self._status(request)
        raise LookupError(f"unsupported autonomous repair capability: {resolution.capability_name}")

    def _apply(self, request: OrchestrationRequest) -> InvocationResult:
        if request.permission_mode != "execute":
            raise PermissionError("repair deployment apply requires execute permission")
        if request.principal_id != "jason-autonomy-worker":
            raise PermissionError("repair deployment apply is restricted to Jason autonomy workload")

        canonical = _canonical_request(request.arguments)
        material = {
            "schema_version": "1.0",
            "capability": DEPLOYMENT_REPAIR_APPLY,
            "provider": AUTONOMOUS_REPAIR_DEPLOYMENT_PROVIDER,
            "principal_id": request.principal_id,
            "organization_id": request.organization_id,
            "execution_id": request.execution_id,
            "correlation_id": request.correlation_id,
            **canonical,
        }
        request_id = _request_fingerprint(material)
        payload = {
            **material,
            "request_id": request_id,
            "request_fingerprint": request_id,
            "requested_at": datetime.now(timezone.utc).isoformat(),
            "state": "queued",
        }

        requests = self.spool_root / "requests"
        results = self.spool_root / "results"
        result_path = results / f"{request_id}.json"
        request_path = requests / f"{request_id}.json"

        if result_path.exists():
            existing = json.loads(result_path.read_text(encoding="utf-8"))
            return InvocationResult(
                output={
                    "provider": AUTONOMOUS_REPAIR_DEPLOYMENT_PROVIDER,
                    "provider_capability": DEPLOYMENT_REPAIR_APPLY,
                    "data": {
                        "status": "completed",
                        "request_id": request_id,
                        "candidate_sha": canonical["candidate_sha"],
                        "result_state": existing.get("state", "unknown"),
                    },
                    "evidence_ids": (f"repair-deployment:{request_id}",),
                    "warnings": (),
                },
                attempts=1,
            )

        if not request_path.exists():
            _atomic_write(request_path, payload)

        return InvocationResult(
            output={
                "provider": AUTONOMOUS_REPAIR_DEPLOYMENT_PROVIDER,
                "provider_capability": DEPLOYMENT_REPAIR_APPLY,
                "data": {
                    "status": "queued",
                    "request_id": request_id,
                    "candidate_sha": canonical["candidate_sha"],
                    "rollback_sha": canonical["rollback_sha"],
                    "support_item": canonical["support_item"],
                    "host_mutation_performed": False,
                },
                "evidence_ids": (f"repair-deployment:{request_id}",),
                "warnings": (),
            },
            attempts=1,
        )

    def _status(self, request: OrchestrationRequest) -> InvocationResult:
        if request.permission_mode != "observe":
            raise PermissionError("repair deployment status is read-only")
        request_id = str(request.arguments.get("request_id") or "").strip().casefold()
        if not _REQUEST_ID.fullmatch(request_id):
            raise ValueError("request_id must be an exact repair deployment request identifier")

        result_path = self.spool_root / "results" / f"{request_id}.json"
        processing_path = self.spool_root / "processing" / f"{request_id}.json"
        request_path = self.spool_root / "requests" / f"{request_id}.json"

        state = "unknown"
        data: dict[str, Any] = {"request_id": request_id}
        if result_path.exists():
            raw = json.loads(result_path.read_text(encoding="utf-8"))
            state = str(raw.get("state") or "unknown")
            for key in (
                "candidate_sha",
                "rollback_sha",
                "support_item",
                "started_at",
                "completed_at",
                "live_revision",
                "rollback_performed",
                "verification_passed",
                "error_code",
            ):
                if key in raw:
                    data[key] = raw[key]
        elif processing_path.exists():
            state = "processing"
        elif request_path.exists():
            state = "queued"

        data["state"] = state
        return InvocationResult(
            output={
                "provider": AUTONOMOUS_REPAIR_DEPLOYMENT_PROVIDER,
                "provider_capability": DEPLOYMENT_REPAIR_STATUS,
                "data": data,
                "evidence_ids": (f"repair-deployment:{request_id}",),
                "warnings": (),
            },
            attempts=1,
        )


AUTONOMOUS_REPAIR_EXECUTE_GRANT_ID = "grant-jason-autonomy-worker-deployment-repair-apply-v1"
AUTONOMOUS_REPAIR_STATUS_GRANT_ID = "grant-jason-autonomy-worker-deployment-repair-status-v1"


def ensure_autonomous_repair_authority(identity_authority) -> tuple[str, ...]:
    """Persist only the exact J-CHANGE-002 workload grants when profile is active."""

    if not autonomous_repair_deployment_enabled():
        return ()

    identity = identity_authority.identities.get("jason-autonomy-worker")
    expected_identity = IdentityRecord(
        identity_id="jason-autonomy-worker",
        identity_type="service",
        organization_id="aot",
        status="active",
    )
    if identity is None:
        identity_authority.identities.put(expected_identity)
    elif identity != expected_identity:
        raise AutonomousRepairDeploymentActivationError(
            "autonomous repair worker identity conflicts with existing JKD-001 identity"
        )

    expected = (
        AuthorityGrant(
            grant_id=AUTONOMOUS_REPAIR_EXECUTE_GRANT_ID,
            subject_id="jason-autonomy-worker",
            capability=DEPLOYMENT_REPAIR_APPLY,
            organization_id="aot",
            client_id=None,
            permission=PermissionMode.EXECUTE,
            approval_required=False,
            status="active",
        ),
        AuthorityGrant(
            grant_id=AUTONOMOUS_REPAIR_STATUS_GRANT_ID,
            subject_id="jason-autonomy-worker",
            capability=DEPLOYMENT_REPAIR_STATUS,
            organization_id="aot",
            client_id=None,
            permission=PermissionMode.OBSERVE,
            approval_required=False,
            status="active",
        ),
    )
    created: list[str] = []
    for grant in expected:
        existing = identity_authority.grants.get(grant.grant_id)
        if existing is None:
            identity_authority.grants.put(grant)
            created.append(grant.grant_id)
        elif existing != grant:
            raise AutonomousRepairDeploymentActivationError(
                f"autonomous repair authority grant conflicts: {grant.grant_id}"
            )
    return tuple(created)


def build_autonomous_repair_deployment_invoker() -> AutonomousRepairDeploymentInvoker:
    spool = Path(os.getenv(AUTONOMOUS_REPAIR_SPOOL_ENV, str(DEFAULT_SPOOL))).expanduser()
    return AutonomousRepairDeploymentInvoker(spool_root=spool)


def register_autonomous_repair_deployment_invokers(
    *,
    invokers: CapabilityInvokerRegistry,
    invoker: AutonomousRepairDeploymentInvoker,
) -> None:
    invokers.register(DEPLOYMENT_REPAIR_APPLY, invoker)
    invokers.register(DEPLOYMENT_REPAIR_STATUS, invoker)
