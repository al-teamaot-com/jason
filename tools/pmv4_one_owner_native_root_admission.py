"""Native one-Owner plan read-only admission WITHOUT operator DB (source only).

A future trusted root consumer must independently pin this module, its source
manifest, the root-owned journal and active-Owner attestation issuer BEFORE
enabling production. This module proves the exact cryptographic root admission
with those inputs in isolated /tmp only. It never executes a root operation,
changes release state, or authorizes any production release.
"""
from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping

from kernel.pmv4_plan_child_proof import (
    _parent_validation, verify_derived_step_proof,
)
from kernel.signed_owner_release import canonical, public_key_sha256
from orchestrator.pmv4_objective_scope import BoundedObjective
from tools import pmv4_stage_a_packet as packet
from tools import pmv4_stage_a_admission as admission
from tools.pmv4_bounded_plan_journal import BoundedPlanJournal
from tools.pmv4_current_grant_attestation import (
    verify_current_grant_attestation, _valid_signature,
)


class OneOwnerNativeRootAdmissionDenied(PermissionError):
    pass


def _deny_ok(condition: bool, code: str) -> None:
    if not condition:
        raise OneOwnerNativeRootAdmissionDenied(code)


def verify_sandbox_native_root_action(
    *, repo: Path, candidate_sha: str, reviewed_scope: Mapping[str, Any],
    exact_manifest: Mapping[str, Any], freeze_path: Path, hold_path: Path,
    native_root_health: Mapping[str, Any], objective: BoundedObjective,
    signed_parent: Mapping[str, Any], signed_step: Mapping[str, Any],
    current_signed_grant: Mapping[str, Any],
    root_readonly_journal: BoundedPlanJournal,
    pinned_public_key: Any, action_index: int,
    protected_main_ci_check: Any, at: datetime,
    production: bool = False,
) -> dict[str, Any]:
    """Pure proof and source readback; NO Owner SQL access on ROOT side.

    All trusted/native facts must be independently obtained by the caller
    from the immutable exact source / native root controls. Production
    requests always fail until separate root source+policy deployment.
    """
    if production:
        raise OneOwnerNativeRootAdmissionDenied("ONE_OWNER_NATIVE_ROOT_POLICY_NOT_DEPLOYED")
    if (not isinstance(repo, Path) or not isinstance(objective, BoundedObjective)
            or not isinstance(reviewed_scope, Mapping)
            or not isinstance(exact_manifest, Mapping)
            or not isinstance(native_root_health, Mapping)
            or not isinstance(signed_parent, Mapping)
            or not isinstance(signed_step, Mapping)
            or not isinstance(current_signed_grant, Mapping)
            or not isinstance(root_readonly_journal, BoundedPlanJournal)
            or not isinstance(freeze_path, Path)
            or not isinstance(hold_path, Path)
            or not isinstance(at, datetime) or at.tzinfo is None
            or type(action_index) is not int
            or not 0 <= action_index < len(objective.actions)
            or not callable(protected_main_ci_check)):
        raise OneOwnerNativeRootAdmissionDenied("ONE_OWNER_NATIVE_ROOT_ARGUMENTS_NOT_EXACT")
    _deny_ok(root_readonly_journal.objective == objective
             and root_readonly_journal.signed_parent == signed_parent,
             "ONE_OWNER_NATIVE_ROOT_JOURNAL_OBJECTIVE_CHANGED")
    _deny_ok(candidate_sha == objective.candidate_sha
             and protected_main_ci_check(candidate_sha) is True,
             "ONE_OWNER_NATIVE_ROOT_PROTECTED_SOURCE_OR_CI_CHANGED")

    # Existing exact source and native rollback contract; no operator claim
    # substitutes for code manifest or Git source-hash verification.
    packet.verify_exact_repository_head(repo, candidate_sha)
    actual_scope = packet.build_scope(repo, candidate_sha)
    _deny_ok(dict(reviewed_scope) == actual_scope
             and actual_scope["scope_sha256"]
                 == sha256(packet._canonical({
                     k:v for k,v in actual_scope.items()
                     if k != "scope_sha256"
                 })).hexdigest(),
             "ONE_OWNER_NATIVE_ROOT_SOURCE_SCOPE_CHANGED")
    source_freeze = sha256(freeze_path.read_bytes()).hexdigest()
    source_hold = sha256(hold_path.read_bytes()).hexdigest()
    action = objective.actions[action_index]
    _deny_ok(source_freeze == objective.freeze_sha256
             and source_hold == objective.hold_sha256
             and actual_scope["rollback_sha"]
                 == (action.rollback_sha or objective.rollback_sha)
             and actual_scope["scope_sha256"] == action.scope_sha256
             and exact_manifest == admission.exact_stage_a_manifest(
                 actual_scope, source_freeze)
             and sha256(canonical(exact_manifest)).hexdigest()
                 == action.artifact_sha256,
             "ONE_OWNER_NATIVE_ROOT_EXACT_ARTIFACT_OR_ROLLBACK_CHANGED")

    required_health = {
        "preflight_evidence_satisfied": True,
        "stage_a_empty_baseline_verified": True,
        "root_only_target_parent_verification_needed": False,
        "breaker_state": "closed",
        "installation_ready": False,
        "production_install_authorized": False,
        "runtime_healthy": True, "mcp_running": True,
        "worker_scan_fresh": True,
    }
    _deny_ok(all(native_root_health.get(k) == v for k,v in required_health.items())
             and native_root_health.get("freeze_sha256") == source_freeze
             and native_root_health.get("promotion_hold_sha256") == source_hold,
             "ONE_OWNER_NATIVE_ROOT_INDEPENDENT_HEALTH_NOT_READY")

    # The root verifier does NOT read PlanGrantLedger and does NOT trust
    # an operator-supplied prior_step list. Grant/revocation were signed by
    # the independent issuer within the exact 30-second freshness window.
    verified_attestation = verify_current_grant_attestation(
        objective=objective, signed_parent=signed_parent,
        signed_attestation=current_signed_grant,
        pinned_public_key=pinned_public_key,
        expected_action_index=action_index, at=at,
        production=False,
    )
    _valid_signature(signed_parent, key=pinned_public_key)
    parent = signed_parent["payload"]
    _parent_validation(parent, at=at)
    _deny_ok(parent.get("reviewed_objective") == objective.review_material()
             and parent.get("parent_plan_fingerprint") == objective.fingerprint
             and parent.get("signer_public_key_sha256")
                 == public_key_sha256(pinned_public_key),
             "ONE_OWNER_NATIVE_ROOT_PARENT_SCOPE_CHANGED")
    journal = root_readonly_journal.root_readonly_snapshot(action_index=action_index)
    expected_prior = frozenset(range(action_index))
    _deny_ok(journal["verified_prior_steps"] == expected_prior,
             "ONE_OWNER_NATIVE_ROOT_PRIOR_STAGE_NOT_VERIFIED")
    expected_step = {
        "tenant_id": parent["tenant_id"],
        "owner_oid": parent["owner_oid"],
        "owner_principal": parent["owner_principal"],
        "organization_id": parent["organization_id"],
        "parent_plan_id": objective.plan_id,
        "parent_approval_id": parent["parent_approval_id"],
        "parent_plan_fingerprint": objective.fingerprint,
        "parent_authenticated_decision_sha256":
            sha256(canonical(signed_parent)).hexdigest(),
        "parent_plan_expires_at": objective.expires_at.isoformat(),
        "policy_digest": objective.policy_digest,
        "step_index": action_index,
        "action": action.capability,
        "candidate_sha": candidate_sha,
        "rollback_sha": actual_scope["rollback_sha"],
        "scope_sha256": actual_scope["scope_sha256"],
        "artifact_sha256": sha256(canonical(exact_manifest)).hexdigest(),
        "freeze_sha256": source_freeze,
        "hold_sha256": source_hold,
    }
    verified_step = verify_derived_step_proof(
        signed_step, pinned_public_key=pinned_public_key,
        expected=expected_step, at=at,
        consumed_step_claims=journal["consumed_step_claims"],
    )
    return {
        "status": "read_only_native_exact_one_owner_plan_verified",
        "parent_approval_id": parent["parent_approval_id"],
        "plan_fingerprint": objective.fingerprint,
        "action": action.capability,
        "action_index": action_index,
        "scope_sha256": actual_scope["scope_sha256"],
        "artifact_sha256": action.artifact_sha256,
        "rollback_sha": actual_scope["rollback_sha"],
        "signed_step_claim_id": verified_step["step_claim_id"],
        "current_grant_assertion_sha256": verified_attestation["assertion_sha256"],
        "root_journal_head_sha256": journal["journal_head_sha256"],
        "production_root_authority": False,
        "root_mutation": False,
    }
