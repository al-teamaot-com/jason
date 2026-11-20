"""PMv4 bounded-objective gates over existing approved-plan ledger.

No real owner decision, provider invocation, secret, root write or release occurs.
"""
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from orchestrator.approval_plan_grants import PlanGrantLedger, VerifiedPlanDecision
from orchestrator.approval_plan_scope import ApprovedPlanScope
from orchestrator.pmv4_objective_scope import (
    BoundedObjective, ObjectiveAction, require_objective_step_conformance,
)

NOW = datetime(2026, 11, 14, 16, 0, tzinfo=timezone.utc)

ACTIONS = (
    ObjectiveAction("pmv4-stage-a0-initial-root-trust-v1",
                    "root-trust", "1" * 64, "2" * 64, 3),
    ObjectiveAction("pmv4-stage-a0-sparse-root-source-v1",
                    "source-staging", "3" * 64, "4" * 64, 2),
    ObjectiveAction("pmv4-stage-a0-same-image-owner-issuer-v1",
                    "owner-issuer", "5" * 64, "6" * 64, 3),
    ObjectiveAction("pmv4-stage-a0-native-install-v1",
                    "isolated-stage-a0", "7" * 64, "8" * 64, 3),
)


@pytest.fixture
def approved(tmp_path):
    obj = BoundedObjective(
        plan_id="pmv4-acceptance-fixture-v1", organization_id="AOT",
        policy_digest="9" * 64,
        candidate_sha="a" * 40, rollback_sha="b" * 40,
        freeze_sha256="c" * 64, hold_sha256="d" * 64,
        actions=ACTIONS, expires_at=NOW + timedelta(minutes=30),
    )
    ledger = PlanGrantLedger(tmp_path / "existing-approval-ledger.sqlite3")
    grant = ApprovedPlanScope(
        obj.plan_id, obj.organization_id, obj.policy_digest,
        frozenset(a.capability for a in obj.actions), frozenset(),
        3, True, obj.expires_at,
    )
    # Synthetic already-verified decision; real Entra and approval ingestion
    # remain under the existing universal Teams/Owner authority service.
    decision = VerifiedPlanDecision(
        approval_id="owner-fixture-single-vote",
        approver_identity_id="synthetic-owner-AOT",
        authenticated=True, authorized=True, approved=True,
        plan_fingerprint=obj.fingerprint, decided_at=NOW,
    )
    ledger.record(grant, decision)
    return obj, ledger, decision


def check(approved, index=0, *, observed=None, obj=None, fingerprint=None, now=NOW):
    canonical, ledger, _ = approved
    plan = obj or canonical
    action = canonical.actions[index] if 0 <= index < len(canonical.actions) else canonical.actions[0]
    facts = {
        "observed_candidate_sha": canonical.candidate_sha,
        "observed_rollback_sha": canonical.rollback_sha,
        "observed_freeze_sha256": canonical.freeze_sha256,
        "observed_hold_sha256": canonical.hold_sha256,
        "observed_scope_sha256": action.scope_sha256,
        "observed_artifact_sha256": action.artifact_sha256,
    }
    facts.update(observed or {})
    return require_objective_step_conformance(
        ledger=ledger, objective=plan,
        approved_fingerprint=fingerprint or canonical.fingerprint,
        action_index=index, now=now, **facts,
    )


def test_one_authenticated_plan_decision_covers_four_exact_steps(approved):
    obj, ledger, decision = approved
    for i, action in enumerate(obj.actions):
        assert check(approved, i) == action.capability
    receipt = ledger.decision_receipt(decision.approval_id)
    assert receipt["plan_fingerprint"] == obj.fingerprint
    assert receipt["approver_identity_id"] == decision.approver_identity_id
    # No new human decision or approval record was created by four checks.
    assert ledger.decision_receipt("second-vote") is None


@pytest.mark.parametrize("index", [-1, 4, False])
def test_missing_action_or_invalid_index_denied(approved, index):
    with pytest.raises(PermissionError, match="index"):
        check(approved, index)


@pytest.mark.parametrize("field,altered", [
    ("observed_candidate_sha", "f" * 40),
    ("observed_rollback_sha", "f" * 40),
    ("observed_freeze_sha256", "f" * 64),
    ("observed_hold_sha256", "f" * 64),
    ("observed_scope_sha256", "f" * 64),
    ("observed_artifact_sha256", "f" * 64),
])
def test_material_or_protected_control_drift_denied(approved, field, altered):
    with pytest.raises(PermissionError):
        check(approved, observed={field: altered})


def test_same_steps_in_different_order_denied(approved):
    plan = approved[0]
    other = replace(plan, actions=tuple(reversed(plan.actions)))
    assert other.fingerprint != plan.fingerprint
    with pytest.raises(PermissionError, match="material changed"):
        check(approved, obj=other)


@pytest.mark.parametrize("change", [
    {"policy_digest": "f" * 64},
    {"organization_id": "FOREIGN"},
    {"candidate_sha": "f" * 40},
    {"freeze_sha256": "f" * 64},
    {"rollback_sha": "f" * 40},
])
def test_immutable_objective_drift_denied(approved, change):
    with pytest.raises(PermissionError, match="material changed"):
        check(approved, obj=replace(approved[0], **change))


def test_new_action_cannot_be_added_after_approval(approved):
    extra = ObjectiveAction("unreviewed-dangerous-step", "ticket-core",
                            "e" * 64, "f" * 64, 3)
    with pytest.raises(PermissionError, match="material changed"):
        check(approved, obj=replace(approved[0], actions=approved[0].actions + (extra,)))


def test_expired_objective_denied(approved):
    with pytest.raises(PermissionError, match="expired"):
        check(approved, now=NOW + timedelta(hours=1))


def test_revoked_objective_denied(approved):
    obj, ledger, _ = approved
    ledger.revoke(obj.plan_id, at=NOW + timedelta(minutes=1), reason="Owner revoked")
    with pytest.raises(PermissionError, match="revoked"):
        check(approved, now=NOW + timedelta(minutes=2))


def test_wrong_plan_fingerprint_denied(approved):
    with pytest.raises(PermissionError, match="material changed"):
        check(approved, fingerprint="f" * 64)


def test_duplicate_human_approval_fails_not_a_new_plan_grant(approved):
    obj, ledger, decision = approved
    with pytest.raises(Exception):
        ledger.record(ApprovedPlanScope(
            obj.plan_id, obj.organization_id, obj.policy_digest,
            frozenset(a.capability for a in obj.actions), frozenset(),
            3, True, obj.expires_at,
        ), decision)
    assert check(approved, 2) == obj.actions[2].capability


@pytest.mark.parametrize("kwargs", [
    {"scope_sha256": "not-a-sha"}, {"artifact_sha256": ""},
    {"risk": True}, {"risk": 4}, {"capability": ""}, {"component": ""},
])
def test_malformed_action_is_not_a_reviewable_plan(kwargs):
    with pytest.raises(ValueError):
        replace(ACTIONS[0], **kwargs)


def test_objective_must_be_bounded_and_nonduplicated(approved):
    original = approved[0]
    with pytest.raises(ValueError, match="duplicate"):
        replace(original, actions=(ACTIONS[0], ACTIONS[0]))
    with pytest.raises(ValueError):
        replace(original, actions=())
    with pytest.raises(ValueError):
        replace(original, actions=ACTIONS * 4)


def test_objective_expiry_blocks_even_when_ledger_ttl_is_longer(tmp_path, approved):
    original, _, decision = approved
    short = replace(original, expires_at=NOW + timedelta(minutes=5))
    ledger = PlanGrantLedger(tmp_path / "longer-lived-grant.sqlite3")
    longer_scope = ApprovedPlanScope(
        short.plan_id, short.organization_id, short.policy_digest,
        frozenset(a.capability for a in short.actions), frozenset(),
        3, True, NOW + timedelta(minutes=30),
    )
    ledger.record(longer_scope, replace(decision, plan_fingerprint=short.fingerprint))
    first = short.actions[0]
    with pytest.raises(PermissionError, match="objective authorization expired"):
        require_objective_step_conformance(
            ledger=ledger, objective=short,
            approved_fingerprint=short.fingerprint, action_index=0,
            observed_candidate_sha=short.candidate_sha,
            observed_rollback_sha=short.rollback_sha,
            observed_freeze_sha256=short.freeze_sha256,
            observed_hold_sha256=short.hold_sha256,
            observed_scope_sha256=first.scope_sha256,
            observed_artifact_sha256=first.artifact_sha256,
            now=NOW + timedelta(minutes=6),
        )


def test_no_preexisting_grant_never_allows_a_stage(tmp_path, approved):
    obj, _, _ = approved
    empty = PlanGrantLedger(tmp_path / "no-owner-approval.sqlite3")
    first = obj.actions[0]
    with pytest.raises(PermissionError, match="missing grant"):
        require_objective_step_conformance(
            ledger=empty, objective=obj,
            approved_fingerprint=obj.fingerprint, action_index=0,
            observed_candidate_sha=obj.candidate_sha,
            observed_rollback_sha=obj.rollback_sha,
            observed_freeze_sha256=obj.freeze_sha256,
            observed_hold_sha256=obj.hold_sha256,
            observed_scope_sha256=first.scope_sha256,
            observed_artifact_sha256=first.artifact_sha256,
            now=NOW,
        )


def test_plan_reviewer_not_authorized_for_step_denied(tmp_path, approved):
    obj, _, decision = approved
    limited = PlanGrantLedger(tmp_path / "limited-grant.sqlite3")
    limited.record(ApprovedPlanScope(
        obj.plan_id, obj.organization_id, obj.policy_digest,
        frozenset({obj.actions[0].capability}), frozenset(),
        3, True, obj.expires_at,
    ), decision)
    issuer = obj.actions[2]
    with pytest.raises(PermissionError, match="outside approved plan"):
        require_objective_step_conformance(
            ledger=limited, objective=obj,
            approved_fingerprint=obj.fingerprint, action_index=2,
            observed_candidate_sha=obj.candidate_sha,
            observed_rollback_sha=obj.rollback_sha,
            observed_freeze_sha256=obj.freeze_sha256,
            observed_hold_sha256=obj.hold_sha256,
            observed_scope_sha256=issuer.scope_sha256,
            observed_artifact_sha256=issuer.artifact_sha256,
            now=NOW,
        )
