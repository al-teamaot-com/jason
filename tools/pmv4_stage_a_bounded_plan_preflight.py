"""PMv4 Stage A0 bounded-plan adapter over existing read-only native gates.

SOURCE-ONLY. This module cannot issue Owner approvals, acquire privileged
authority, consume a claim, modify root, or install Stage A0. The currently
installed root worker continues to accept ONLY its legacy authenticated v1
exact-action Owner proof. This adapter fails closed in production until a
reviewed, explicitly deployed root-owned policy/handler accepts plan proofs.
"""
from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable, Mapping

from kernel.signed_owner_release import canonical
from orchestrator.pmv4_objective_scope import (
    BoundedObjective, verify_proved_objective_step,
)
from tools import pmv4_stage_a_admission as admission
from tools import pmv4_stage_a_packet as packet


class StageABoundedPlanDenied(PermissionError):
    pass


def verify_bounded_plan_stage_a0_readonly(
    *, repo: Path, candidate_sha: str, scope: Mapping[str, Any],
    exact_manifest: Mapping[str, Any],
    objective: BoundedObjective, action_index: int,
    signed_parent: Mapping[str, Any], signed_step: Mapping[str, Any],
    owner_plan_ledger: Any, pinned_public_key: Any,
    freeze_path: Path, hold_path: Path,
    native_root_health: Mapping[str, Any],
    verified_prior_steps: frozenset[int],
    consumed_step_claims: frozenset[str],
    protected_main_ci_check: Callable[[str], bool],
    at: datetime, production: bool = False,
) -> dict[str, Any]:
    """Dry-readback only; only the existing root controller could execute later.

    All inputs must come from a root-trusted, immutable snapshot in the future
    privileged adapter. In this source-only phase the function rejects any
    production-mode call unconditionally. No status string is an executable
    release permit and no caller-provided file path is accepted in production.
    """
    if production:
        raise StageABoundedPlanDenied("STAGE_A_BOUNDED_PLAN_ROOT_POLICY_NOT_DEPLOYED")
    if (not isinstance(objective, BoundedObjective)
            or not isinstance(scope, Mapping)
            or not isinstance(exact_manifest, Mapping)
            or not isinstance(native_root_health, Mapping)
            or not callable(protected_main_ci_check)
            or not isinstance(at, datetime) or at.tzinfo is None):
        raise StageABoundedPlanDenied("STAGE_A_BOUNDED_PLAN_INVALID_REQUEST")
    if candidate_sha != objective.candidate_sha:
        raise StageABoundedPlanDenied("STAGE_A_BOUNDED_PLAN_CANDIDATE_DRIFT")
    if protected_main_ci_check(candidate_sha) is not True:
        raise StageABoundedPlanDenied("STAGE_A_BOUNDED_PLAN_CI_DENIED")
    # Same protected source/scope analyzer as the trusted native Stage A0
    # installer. Neither a chat request nor a fake body may replace these.
    packet.verify_exact_repository_head(repo, candidate_sha)
    actual_scope = packet.build_scope(repo, candidate_sha)
    if dict(scope) != actual_scope:
        raise StageABoundedPlanDenied("STAGE_A_BOUNDED_PLAN_SCOPE_CHANGED")
    if actual_scope.get("scope_sha256") != packet._digest(packet._canonical({
            key: value for key, value in actual_scope.items()
            if key != "scope_sha256"
    })):
        raise StageABoundedPlanDenied("STAGE_A_BOUNDED_PLAN_SCOPE_HASH_CHANGED")
    if actual_scope.get("rollback_sha") != objective.rollback_sha:
        raise StageABoundedPlanDenied("STAGE_A_BOUNDED_PLAN_ROLLBACK_CHANGED")
    try:
        freeze_sha256 = sha256(Path(freeze_path).read_bytes()).hexdigest()
        hold_sha256 = sha256(Path(hold_path).read_bytes()).hexdigest()
    except OSError as exc:
        raise StageABoundedPlanDenied("STAGE_A_BOUNDED_PLAN_CONTROL_UNAVAILABLE") from exc
    if (freeze_sha256 != objective.freeze_sha256
            or hold_sha256 != objective.hold_sha256):
        raise StageABoundedPlanDenied("STAGE_A_BOUNDED_PLAN_PROTECTED_CONTROL_DRIFT")
    if exact_manifest != admission.exact_stage_a_manifest(actual_scope, freeze_sha256):
        raise StageABoundedPlanDenied("STAGE_A_BOUNDED_PLAN_MANIFEST_CHANGED")
    health = native_root_health
    required = {
        "preflight_evidence_satisfied": True,
        "stage_a_empty_baseline_verified": True,
        "root_only_target_parent_verification_needed": False,
        "breaker_state": "closed",
        "installation_ready": False,
        "production_install_authorized": False,
        "runtime_healthy": True,
        "mcp_running": True,
        "worker_scan_fresh": True,
    }
    if any(health.get(k) != v for k, v in required.items()):
        raise StageABoundedPlanDenied("STAGE_A_BOUNDED_PLAN_NATIVE_ROOT_HEALTH_DENIED")
    if (health.get("freeze_sha256") != freeze_sha256
            or health.get("promotion_hold_sha256") != hold_sha256):
        raise StageABoundedPlanDenied("STAGE_A_BOUNDED_PLAN_HEALTH_CONTROL_DRIFT")
    observed = {
        "candidate_sha": candidate_sha,
        "rollback_sha": actual_scope["rollback_sha"],
        "freeze_sha256": freeze_sha256,
        "hold_sha256": hold_sha256,
        "scope_sha256": actual_scope["scope_sha256"],
        "artifact_sha256": sha256(canonical(exact_manifest)).hexdigest(),
    }
    verified = verify_proved_objective_step(
        objective=objective, ledger=owner_plan_ledger,
        signed_parent=dict(signed_parent), signed_step=dict(signed_step),
        pinned_public_key=pinned_public_key,
        action_index=action_index, observed=observed, at=at,
        verified_prior_steps=verified_prior_steps,
        consumed_step_claims=consumed_step_claims,
    )
    return {
        "status": "source_only_bounded_plan_preflight_verified",
        "candidate_sha": candidate_sha,
        "action": verified["action"],
        "parent_approval_id": verified["parent_approval_id"],
        "plan_fingerprint": verified["parent_plan_fingerprint"],
        "step_claim_id": verified["step_claim_id"],
        "no_production_authority": True,
        "root_mutation": False,
    }
