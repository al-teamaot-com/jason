"""No live signer or root executor: synthetic bounded plan and ephemeral keys."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from kernel.signed_owner_release import (
    OWNER_OID, OWNER_PRINCIPAL, OwnerReleaseProofDenied,
    verify_exact_owner_release,
)
from kernel.pmv4_plan_child_proof import (
    BoundedStepProofDenied, issue_derived_step_proof, verify_derived_step_proof,
)
from orchestrator.approval_plan_grants import PlanGrantLedger, VerifiedPlanDecision
from orchestrator.approval_plan_scope import ApprovedPlanScope
from orchestrator.pmv4_objective_scope import (
    BoundedObjective, ObjectiveAction, require_objective_step_conformance,
)

AT = datetime(2026, 11, 14, 17, 0, tzinfo=timezone.utc)
PARENT_ID = "planapproval-" + ("a" * 32)
OMIT = frozenset({
    "schema_version", "authorization", "authentication",
    "issued_at", "expires_at", "step_claim_id",
    "one_step_only", "standing_authority", "signer_public_key_sha256",
})


@pytest.fixture
def approved(tmp_path):
    key = Ed25519PrivateKey.generate()
    steps = tuple(
        ObjectiveAction("pmv4-stage-a0-action-" + str(i),
                        "component-" + str(i), f"{i+1}" * 64, f"{i+5}" * 64, 3)
        for i in range(4)
    )
    plan = BoundedObjective(
        "pmv4-test-immutable-objective", "aot", "9"*64,
        "a"*40, "b"*40, "c"*64, "d"*64,
        steps, AT + timedelta(minutes=30),
    )
    ledger = PlanGrantLedger(tmp_path / "existing-universal-grants.sqlite3")
    ledger.record(ApprovedPlanScope(
        plan.plan_id, plan.organization_id, plan.policy_digest,
        frozenset(s.capability for s in steps), frozenset(),
        3, True, plan.expires_at,
    ), VerifiedPlanDecision(
        PARENT_ID, OWNER_PRINCIPAL, True, True, True,
        plan.fingerprint, AT,
    ))
    return plan, ledger, key


def make(approved, index=0, *, at=AT):
    plan, ledger, key = approved
    action = plan.actions[index]
    allowed = require_objective_step_conformance(
        ledger=ledger, objective=plan,
        approved_fingerprint=plan.fingerprint, action_index=index,
        observed_candidate_sha=plan.candidate_sha,
        observed_rollback_sha=plan.rollback_sha,
        observed_freeze_sha256=plan.freeze_sha256,
        observed_hold_sha256=plan.hold_sha256,
        observed_scope_sha256=action.scope_sha256,
        observed_artifact_sha256=action.artifact_sha256,
        now=at,
    )
    assert allowed == action.capability
    proof = issue_derived_step_proof(
        private_key=key, verified_owner_oid=OWNER_OID,
        parent_plan_id=plan.plan_id, parent_approval_id=PARENT_ID,
        parent_plan_fingerprint=plan.fingerprint,
        parent_authenticated_decision_sha256="f"*64,
        parent_plan_expires_at=plan.expires_at,
        policy_digest=plan.policy_digest,
        step_index=index, action=action.capability,
        candidate_sha=plan.candidate_sha, rollback_sha=plan.rollback_sha,
        scope_sha256=action.scope_sha256, artifact_sha256=action.artifact_sha256,
        freeze_sha256=plan.freeze_sha256, hold_sha256=plan.hold_sha256, at=at,
    )
    expected = {k:v for k,v in proof["payload"].items() if k not in OMIT}
    return proof, expected, key.public_key()


def test_one_synthetic_human_grant_covers_four_distinct_signed_machine_steps(approved):
    plan, ledger, _ = approved
    claims = set()
    for i in range(4):
        proof, expected, public = make(approved, i)
        result = verify_derived_step_proof(
            proof, pinned_public_key=public, expected=expected, at=AT,
        )
        assert result["parent_approval_id"] == PARENT_ID
        assert result["parent_plan_fingerprint"] == plan.fingerprint
        assert result["authentication"] == "prior_authenticated_owner_plan"
        assert result["standing_authority"] is False
        assert result["one_step_only"] is True
        claims.add(result["step_claim_id"])
    assert len(claims) == 4
    assert ledger.decision_receipt(PARENT_ID)["approver_identity_id"] == OWNER_PRINCIPAL
    assert ledger.decision_receipt("second-human-vote") is None


@pytest.mark.parametrize("field,changed", [
    ("candidate_sha","0"*40), ("rollback_sha","0"*40),
    ("scope_sha256","a"*64), ("artifact_sha256","a"*64),
    ("freeze_sha256","a"*64), ("hold_sha256","a"*64),
    ("parent_plan_fingerprint","a"*64), ("parent_approval_id","planapproval-"+"b"*32),
    ("parent_authenticated_decision_sha256","a"*64),
    ("policy_digest","a"*64), ("step_index",8),
    ("action","pmv4-unreviewed-action"),
    ("owner_oid","c848022d-e13b-4457-84b0-e2f5c00dcaf6"),
    ("parent_plan_id","pmv4-foreign-objective"),
])
def test_verified_root_expected_binding_denies_drift(approved,field,changed):
    proof, expected, public = make(approved, 0)
    expected[field] = changed
    with pytest.raises(BoundedStepProofDenied,match="EXACT_BINDING"):
        verify_derived_step_proof(
            proof,pinned_public_key=public,expected=expected,at=AT,
        )


def test_step_proof_replay_denied(approved):
    proof, expected, public = make(approved)
    claim = proof["payload"]["step_claim_id"]
    with pytest.raises(BoundedStepProofDenied,match="REPLAY"):
        verify_derived_step_proof(
            proof,pinned_public_key=public,expected=expected,at=AT,
            consumed_step_claims=frozenset({claim}),
        )


def test_wrong_signer_key_denied(approved):
    proof, expected, _ = make(approved)
    wrong = Ed25519PrivateKey.generate().public_key()
    with pytest.raises(BoundedStepProofDenied,match="WRONG_ROOT_SIGNER"):
        verify_derived_step_proof(proof,pinned_public_key=wrong,expected=expected,at=AT)


def test_signature_tamper_denied(approved):
    proof, expected, public = make(approved)
    proof = {**proof,"signature_base64url":"a"*86}
    with pytest.raises(BoundedStepProofDenied,match="SIGNATURE_INVALID"):
        verify_derived_step_proof(proof,pinned_public_key=public,expected=expected,at=AT)


def test_signed_payload_mutation_denied(approved):
    proof, _, public = make(approved)
    proof["payload"]["action"]="pmv4-tampered-action"
    expected={k:v for k,v in proof["payload"].items() if k not in OMIT}
    with pytest.raises(BoundedStepProofDenied):
        verify_derived_step_proof(proof,pinned_public_key=public,expected=expected,at=AT)


def test_expiry_and_parent_expiry_fail_closed(approved):
    proof, expected, public = make(approved)
    for when in (AT - timedelta(seconds=1),AT+timedelta(minutes=16),AT+timedelta(minutes=31)):
        with pytest.raises(BoundedStepProofDenied,match="EXPIRED_OR_FUTURE"):
            verify_derived_step_proof(proof,pinned_public_key=public,expected=expected,at=when)


def test_invalid_owner_identity_never_signed(approved):
    plan, _, key = approved
    action=plan.actions[0]
    with pytest.raises(BoundedStepProofDenied):
        issue_derived_step_proof(
            private_key=key,verified_owner_oid="not-a-verified-owner",
            parent_plan_id=plan.plan_id,parent_approval_id=PARENT_ID,
            parent_plan_fingerprint=plan.fingerprint,
            parent_authenticated_decision_sha256="f"*64,
            parent_plan_expires_at=plan.expires_at,policy_digest=plan.policy_digest,
            step_index=0,action=action.capability,candidate_sha=plan.candidate_sha,
            rollback_sha=plan.rollback_sha,scope_sha256=action.scope_sha256,
            artifact_sha256=action.artifact_sha256,
            freeze_sha256=plan.freeze_sha256,hold_sha256=plan.hold_sha256,at=AT,
        )


def test_legacy_current_exact_owner_root_proof_rejects_derived_schema(approved):
    proof, _, public = make(approved)
    p=approved[0]
    a=p.actions[0]
    with pytest.raises(OwnerReleaseProofDenied, match="SCHEMA_INVALID"):
        verify_exact_owner_release(
            proof, public_key=public,
            expected_candidate_sha=p.candidate_sha,
            expected_rollback_sha=p.rollback_sha,
            expected_release_id="release-"+p.candidate_sha[:16],
            expected_scope_sha256=a.scope_sha256,
            expected_manifest_sha256=a.artifact_sha256,
            expected_freeze_sha256=p.freeze_sha256,
            at=AT,
        )


def test_no_signed_step_when_parent_plan_revoked(approved):
    plan, ledger, _ = approved
    ledger.revoke(plan.plan_id, at=AT+timedelta(minutes=1), reason="revoked")
    with pytest.raises(PermissionError, match="revoked"):
        make(approved,0,at=AT+timedelta(minutes=2))


def test_unhashable_or_untrusted_owner_claim_denied_without_crash(approved):
    proof, _, public = make(approved)
    proof["payload"]["owner_oid"] = {"untrusted": "json-object"}
    expected={k:v for k,v in proof["payload"].items() if k not in OMIT}
    with pytest.raises(BoundedStepProofDenied, match="FIELDS_INVALID"):
        verify_derived_step_proof(proof,pinned_public_key=public,expected=expected,at=AT)


def test_missing_or_extra_signed_schema_field_denied(approved):
    proof, expected, public = make(approved)
    proof["payload"]["unreviewed_authority"] = True
    with pytest.raises(BoundedStepProofDenied, match="SCHEMA_INVALID"):
        verify_derived_step_proof(proof,pinned_public_key=public,expected=expected,at=AT)


def test_nonmatching_expected_field_set_denied(approved):
    proof, expected, public = make(approved)
    del expected["hold_sha256"]
    with pytest.raises(BoundedStepProofDenied, match="EXACT_BINDING_CHANGED"):
        verify_derived_step_proof(proof,pinned_public_key=public,expected=expected,at=AT)


def test_same_step_reissuance_uses_same_consumable_claim_id(approved):
    first, expected, public = make(approved)
    second, _, _ = make(approved, 0, at=AT+timedelta(minutes=1))
    assert second["payload"]["step_claim_id"] == first["payload"]["step_claim_id"]
    claim=first["payload"]["step_claim_id"]
    with pytest.raises(BoundedStepProofDenied, match="REPLAY"):
        verify_derived_step_proof(second,pinned_public_key=public,expected=expected,
                                  at=AT+timedelta(minutes=1),
                                  consumed_step_claims=frozenset({claim}))
