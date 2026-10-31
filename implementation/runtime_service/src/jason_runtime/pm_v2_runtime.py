from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

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
from orchestrator.contracts import OrchestrationRequest
from orchestrator.service import InvocationResult


PM_V2_STATUS = "operations.productionmanager.status.read"
PM_V2_CONTROL = "operations.productionmanager.work.update"
PM_V2_PROVIDER = "production_manager_v2"
PM_V2_PROFILE = "owner-teams-v1"
ALLOWED_CONTROLS = frozenset({"priority", "pause", "resume", "cancel"})


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(prefix=".pm-v2-runtime-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            os.fchmod(handle.fileno(), 0o600)
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def _status_capability(now: datetime) -> CapabilityDefinition:
    return CapabilityDefinition(
        capability_name=PM_V2_STATUS,
        version="1.0",
        display_name="Read Production Manager V2 Work Status",
        lifecycle_status=CapabilityLifecycle.BUILDING,
        business_purpose=(
            "Read bounded PM V2 queue, component and node status through Jason's "
            "existing governed conversation interface."
        ),
        owner_service="Production Manager V2",
        architectural_capability_ids=frozenset({"JAC-005"}),
        risk_level=CapabilityRisk.LOW,
        data_classifications=frozenset({"internal"}),
        permitted_execution_modes=frozenset({"deterministic"}),
        input_schema_reference="schema://jason/pm-v2-status-read/1.0",
        output_schema_reference="schema://jason/pm-v2-status/1.0",
        invoking_roles=frozenset({"orchestrator"}),
        approval=CapabilityApproval(required=False),
        evidence=CapabilityEvidence(
            required=True,
            requirements=("fresh PM V2 bounded status snapshot",),
            verification_requirements=(
                "status is read-only",
                "no assignment state changes occur",
            ),
        ),
        dependencies=frozenset(),
        idempotency_behavior=IdempotencyBehavior.IDEMPOTENT,
        idempotency_key_required=False,
        timeout_seconds=5,
        maximum_attempts=1,
        failure_behavior="Fail closed when the PM V2 status snapshot is unavailable.",
        tenant_isolation_required=True,
        client_isolation_required=False,
        stewardship=CapabilityStewardship(
            steward="technology-steward",
            business_justification=(
                "Allow authenticated AOT operators to inspect PM V2 without host access."
            ),
            review_interval_days=30,
            retirement_criteria=("PM V2 is retired or replaced.",),
            authoritative_change_sources=("PM V2 canonical agreement",),
            operational_owner="AOT IT Operations",
            approval_owner="AOT Owner",
        ),
        created_at=now,
        metadata={
            "provider_neutral": "true",
            "read_only": "true",
            "resource_types": "engineering_work,production_manager",
            "operation": "read",
            "selector_keys": "assignment_id",
            "selector_required": "false",
            "collection_scope": "authorized PM V2 work state",
            "fact_hints": (
                "production manager pm v2 status queue progress blocker completion "
                "running paused components workers nodes"
            ),
        },
    )


def _control_capability(now: datetime) -> CapabilityDefinition:
    return CapabilityDefinition(
        capability_name=PM_V2_CONTROL,
        version="1.0",
        display_name="Control Production Manager V2 Work",
        lifecycle_status=CapabilityLifecycle.BUILDING,
        business_purpose=(
            "Queue one exact authenticated owner control for PM V2 priority, pause, "
            "resume or cancel without terminal access."
        ),
        owner_service="Production Manager V2",
        architectural_capability_ids=frozenset({"JAC-005", "JAC-006"}),
        risk_level=CapabilityRisk.MEDIUM,
        data_classifications=frozenset({"internal"}),
        permitted_execution_modes=frozenset({"deterministic"}),
        input_schema_reference="schema://jason/pm-v2-work-control/1.0",
        output_schema_reference="schema://jason/pm-v2-control-request/1.0",
        invoking_roles=frozenset({"orchestrator"}),
        approval=CapabilityApproval(required=True, approver_classes=("owner",)),
        evidence=CapabilityEvidence(
            required=True,
            requirements=(
                "authenticated requester identity",
                "exact PM V2 assignment identifier",
                "exact requested control action",
            ),
            verification_requirements=(
                "host PM V2 independently validates current assignment state",
                "request does not grant production deployment authority",
            ),
        ),
        dependencies=frozenset({
            "identity.authorization.resolve",
            "governance.action.evaluate",
        }),
        idempotency_behavior=IdempotencyBehavior.IDEMPOTENT,
        idempotency_key_required=True,
        timeout_seconds=5,
        maximum_attempts=1,
        failure_behavior=(
            "Fail closed without changing PM V2 work when identity, action or target is invalid."
        ),
        tenant_isolation_required=True,
        client_isolation_required=False,
        stewardship=CapabilityStewardship(
            steward="technology-steward",
            business_justification=(
                "Provide the agreed Teams operational-control interface for PM V2."
            ),
            review_interval_days=30,
            retirement_criteria=("PM V2 is retired or replaced.",),
            authoritative_change_sources=("PM V2 canonical agreement",),
            operational_owner="AOT IT Operations",
            approval_owner="AOT Owner",
        ),
        created_at=now,
        metadata={
            "provider_neutral": "true",
            "read_only": "false",
            "write_capability": "true",
            "resource_types": "engineering_work,production_manager",
            "operation": "update",
            "selector_keys": "assignment_id,action,priority,reason",
            "selector_required": "true",
            "fact_hints": (
                "production manager pm v2 pause resume cancel priority work item queue"
            ),
            "conversation_authenticated_imperative_is_approval": "true",
        },
    )


def _provider(now: datetime) -> ExecutionProvider:
    return ExecutionProvider(
        provider_id=PM_V2_PROVIDER,
        display_name="Production Manager V2 Local Control Bridge",
        provider_type=ProviderType.DETERMINISTIC,
        lifecycle_status=ProviderLifecycle.PLANNED,
        health_status=ProviderHealth.UNKNOWN,
        approval_status=ProviderApproval.PILOT,
        execution_modes=frozenset({"deterministic"}),
        capabilities=frozenset({PM_V2_STATUS, PM_V2_CONTROL}),
        supported_classifications=frozenset({"internal"}),
        regions=frozenset(),
        limits=ProviderLimits(
            maximum_concurrent_executions=10,
            maximum_requests_per_minute=60,
            maximum_execution_seconds=5,
        ),
        features=ProviderFeatures(structured_output=True),
        pricing_profile_id="zero-cost-foundation",
        stewardship=ProviderStewardship(
            technology_steward="technology-steward",
            business_justification=(
                "Reuse Jason's existing governed runtime to bridge Teams operations "
                "to PM V2 shared state without a second bot or network control plane."
            ),
            review_interval_days=30,
            last_reviewed_at=now,
            retirement_criteria=("PM V2 is retired or replaced.",),
            vendor_change_sources=("PM V2 canonical agreement",),
            operational_owner="AOT IT Operations",
            approval_owner="AOT Owner",
        ),
        created_at=now,
        metadata={"provider_neutral": "true", "host_bridge": "shared_openclaw_state"},
    )


def register_pm_v2_runtime_foundation(
    *,
    capabilities: CapabilityRegistryService,
    providers: ExecutionProviderRegistryService,
    now: datetime,
) -> None:
    capabilities.register(_status_capability(now))
    capabilities.register(_control_capability(now))
    providers.register(_provider(now))
    if os.getenv("JASON_PM_V2_CONTROL_PROFILE", "").strip().casefold() == PM_V2_PROFILE:
        for capability in (PM_V2_STATUS, PM_V2_CONTROL):
            capabilities.set_lifecycle(
                capability_name=capability,
                version="1.0",
                lifecycle_status=CapabilityLifecycle.ACTIVE,
            )
        providers.set_approval(
            provider_id=PM_V2_PROVIDER,
            approval_status=ProviderApproval.APPROVED,
        )
        providers.set_health(
            provider_id=PM_V2_PROVIDER,
            health_status=ProviderHealth.HEALTHY,
        )
        providers.set_lifecycle(
            provider_id=PM_V2_PROVIDER,
            lifecycle_status=ProviderLifecycle.AVAILABLE,
        )


@dataclass(frozen=True, slots=True)
class PMV2RuntimeInvoker:
    status_path: Path
    control_request_dir: Path

    def invoke(
        self,
        *,
        request: OrchestrationRequest,
        resolution: CapabilityResolutionResult,
    ) -> InvocationResult:
        if resolution.selected_provider_id != PM_V2_PROVIDER:
            raise PermissionError("PM V2 capability resolved to unexpected provider")
        if request.capability_name != resolution.capability_name:
            raise ValueError("PM V2 resolved capability does not match request")
        if request.capability_name == PM_V2_STATUS:
            return self._status(request)
        if request.capability_name == PM_V2_CONTROL:
            return self._control(request)
        raise ValueError("unsupported PM V2 runtime capability")

    def _status(self, request: OrchestrationRequest) -> InvocationResult:
        if request.permission_mode != "observe":
            raise PermissionError("PM V2 status is read-only")
        args = dict(request.arguments or {})
        if set(args) - {"assignment_id"}:
            raise ValueError("unsupported PM V2 status arguments")
        try:
            payload = json.loads(self.status_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError("PM_V2_STATUS_UNAVAILABLE") from exc
        if not isinstance(payload, dict) or payload.get("schema_version") != "1.0":
            raise RuntimeError("PM_V2_STATUS_INVALID")
        assignment_id = str(args.get("assignment_id") or "").strip()
        if assignment_id:
            rows = payload.get("assignments")
            if not isinstance(rows, list):
                raise RuntimeError("PM_V2_STATUS_INVALID")
            matches = [
                row for row in rows
                if isinstance(row, dict) and row.get("assignment_id") == assignment_id
            ]
            if len(matches) != 1:
                raise LookupError("PM_V2_ASSIGNMENT_NOT_FOUND")
            output = {
                "schema_version": "1.0",
                "generated_at": payload.get("generated_at"),
                "assignment": matches[0],
            }
        else:
            output = {
                "schema_version": "1.0",
                "generated_at": payload.get("generated_at"),
                "summary": payload.get("summary"),
                "assignments": payload.get("assignments", [])[:25],
                "components": payload.get("components", [])[:25],
                "nodes": payload.get("nodes", [])[:25],
            }
        return InvocationResult(output=output, attempts=1)

    def _control(self, request: OrchestrationRequest) -> InvocationResult:
        if request.permission_mode != "execute":
            raise PermissionError("PM V2 control requires execute mode")
        args = dict(request.arguments or {})
        allowed = {"assignment_id", "action", "priority", "reason"}
        if set(args) - allowed:
            raise ValueError("unsupported PM V2 control arguments")
        assignment_id = str(args.get("assignment_id") or "").strip()
        action = str(args.get("action") or "").strip().casefold()
        reason = str(args.get("reason") or "").strip()[:500]
        priority = args.get("priority")
        if not assignment_id or len(assignment_id) > 160:
            raise ValueError("PM V2 assignment_id is required")
        if action not in ALLOWED_CONTROLS:
            raise ValueError("unsupported PM V2 control action")
        if action == "priority":
            if type(priority) is not int or not 0 <= priority <= 99:
                raise ValueError("PM V2 priority must be an integer from 0 to 99")
        elif priority is not None:
            raise ValueError("priority is valid only for the priority action")

        idempotency = str(
            request.idempotency_key or ("pm-v2-" + request.execution_id)
        ).strip()
        if not idempotency or len(idempotency) > 240:
            raise ValueError("PM V2 control requires bounded idempotency")
        request_id = "pmv2-" + hashlib.sha256(
            idempotency.encode("utf-8")
        ).hexdigest()[:32]
        path = self.control_request_dir / f"{request_id}.json"
        payload = {
            "schema_version": "1.0",
            "request_id": request_id,
            "principal_id": request.principal_id,
            "organization_id": request.organization_id,
            "assignment_id": assignment_id,
            "action": action,
            "priority": priority,
            "reason": reason,
            "source": "governed_runtime_authenticated_request",
            "correlation_id": request.correlation_id,
        }
        if path.exists():
            current = json.loads(path.read_text(encoding="utf-8"))
            immutable = (
                "principal_id", "organization_id", "assignment_id",
                "action", "priority", "reason",
            )
            if any(current.get(key) != payload.get(key) for key in immutable):
                raise ValueError("PM_V2_CONTROL_IDEMPOTENCY_CONFLICT")
            state = "already_queued"
        else:
            _atomic_json(path, payload)
            state = "queued"
        return InvocationResult(
            output={
                "status": state,
                "request_id": request_id,
                "assignment_id": assignment_id,
                "action": action,
                "host_execution": "separate_pm_v2_service_cycle",
            },
            attempts=1,
        )


def build_pm_v2_runtime_invoker() -> PMV2RuntimeInvoker:
    root = Path(os.getenv("JASON_PM_V2_SHARED_ROOT", "/var/lib/jason/openclaw/pm-v2"))
    return PMV2RuntimeInvoker(
        status_path=root / "status.json",
        control_request_dir=root / "control-requests",
    )
