"""One *real cryptographic* Entra claim check and one consent -> 4 steps.

All tests use ephemeral offline signing keys, disposable SQLite, read-only fake
source evidence and NO live root/customer/runtime/provider action. Acceptance is
not a substitute for a separately governed production rollout.
"""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import sqlite3

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric import rsa
import jwt
import pytest

from kernel.pmv4_plan_child_proof import (
    BoundedStepProofDenied, issue_authenticated_owner_objective,
    verify_authenticated_owner_objective,
)
from kernel.signed_owner_release import (
    OWNER_OID, OWNER_PRINCIPAL, ADMIN_OWNER_OID, TID, canonical,
)
from orchestrator.approval_plan_grants import PlanGrantLedger
from orchestrator.pmv4_objective_scope import (
    BoundedObjective, ObjectiveAction, issue_proved_objective_step,
    verify_proved_objective_step,
)

AT = datetime.now(timezone.utc).replace(microsecond=0)
ISSUER = "https://login.microsoftonline.com/" + TID + "/v2.0"
AUDIENCE = "9b9996e9-5c34-48b7-948c-f44f89352f89"
APPROVAL_ID = "planapproval-" + "c" * 32


@pytest.fixture
def enrolled(tmp_path):
    actions = tuple(
        ObjectiveAction("pmv4-stage-a0-step-" + str(i),
                        "stage-a0-component-" + str(i),
                        f"{i+1}" * 64, f"{i+5}" * 64, 3)
        for i in range(4)
    )
    objective = BoundedObjective(
        "pmv4-stage-a0-bound-review", "aot", "9" * 64,
        "a" * 40, "0" * 40, "b" * 64, "c" * 64,
        actions, AT + timedelta(minutes=30),
    )
    owner_signer = Ed25519PrivateKey.generate()
    rsa_signer = rsa.generate_private_key(public_exponent=65537,key_size=2048)
    claims = {
        "tid": TID, "iss": ISSUER, "aud": AUDIENCE, "oid": OWNER_OID,
        "iat": int(AT.timestamp()) - 15,
        "nbf": int(AT.timestamp()) - 15,
        "exp": int(AT.timestamp()) + 300,
    }
    def make_token(updates=None):
        return jwt.encode(
            {**claims, **(updates or {})}, rsa_signer,
            algorithm="RS256", headers={"kid": "offline-only"},
        )
    def verifier(token):
        try:
            return jwt.decode(
                token, rsa_signer.public_key(), algorithms=["RS256"],
                audience=AUDIENCE, issuer=ISSUER,
            )
        except (jwt.PyJWTError, ValueError, TypeError):
            return None
    consents=[]
    ledger=PlanGrantLedger(tmp_path/"existing-universal-plan-ledger.sqlite3")
    return {
        "objective":objective, "owner_key":owner_signer, "rsa_key":rsa_signer,
        "ledger":ledger, "token":make_token(), "make_token":make_token,
        "verifier":verifier,"consents":consents,
    }


def enroll(env, *, token=None, verifier=None, consent=None, at=AT):
    return issue_authenticated_owner_objective(
        objective=env["objective"], ledger=env["ledger"],
        approval_id=APPROVAL_ID,
        bearer_token=token if token is not None else env["token"],
        verify_entra_bearer=verifier or env["verifier"],
        exact_owner_consent=consent or (
            lambda full: env["consents"].append(full) or True
        ),
        protected_main_check=lambda sha: sha==env["objective"].candidate_sha,
        signer_private_key=env["owner_key"], at=at,
    )


def observed(obj, index):
    action=obj.actions[index]
    return {
        "candidate_sha":obj.candidate_sha,"rollback_sha":obj.rollback_sha,
        "freeze_sha256":obj.freeze_sha256,"hold_sha256":obj.hold_sha256,
        "scope_sha256":action.scope_sha256,"artifact_sha256":action.artifact_sha256,
    }


def test_one_verified_owner_enrollment_produces_four_cryptographic_steps(enrolled):
    env=enrolled
    signed_parent=enroll(env)
    obj=env["objective"];ledger=env["ledger"];key=env["owner_key"]
    assert len(env["consents"])==1
    assert env["consents"][0]["plan_fingerprint"]==obj.fingerprint
    assert env["consents"][0]["full_reviewed_objective"]==obj.review_material()
    confirmed=verify_authenticated_owner_objective(
        signed_parent,objective=obj,pinned_public_key=key.public_key(),
        at=AT,ledger=ledger,
    )
    assert confirmed["owner_principal"]==OWNER_PRINCIPAL
    assert confirmed["authentication"]=="verified_entra_oauth_bearer"
    claims=set()
    for i in range(4):
        signed_step=issue_proved_objective_step(
            objective=obj,ledger=ledger,signed_parent=signed_parent,
            signing_key=key,pinned_public_key=key.public_key(),
            action_index=i,observed=observed(obj,i),at=AT,
            verified_prior_steps=frozenset(range(i)),
        )
        root=verify_proved_objective_step(
            objective=obj,ledger=ledger,signed_parent=signed_parent,
            signed_step=signed_step,pinned_public_key=key.public_key(),
            action_index=i,observed=observed(obj,i),at=AT,
            verified_prior_steps=frozenset(range(i)),
        )
        assert root["action"]==obj.actions[i].capability
        assert root["step_index"]==i
        assert root["parent_authenticated_decision_sha256"]==sha256(
            canonical(signed_parent)).hexdigest()
        assert root["standing_authority"] is False
        claims.add(root["step_claim_id"])
    assert len(claims)==4
    assert ledger.authenticated_owner_objective_receipt(
        plan_id=obj.plan_id,approval_id=APPROVAL_ID)==signed_parent
    # One audit decision and one durable signed parent receipt, not four grants.
    with ledger._connection() as db:
        assert db.execute("SELECT COUNT(*) FROM plan_grants").fetchone()[0]==1
        assert db.execute("SELECT COUNT(*) FROM signed_owner_objective_receipts").fetchone()[0]==1


def test_retry_uses_same_signed_decision_without_second_human_consent(enrolled):
    first=enroll(enrolled)
    second=enroll(enrolled,at=AT+timedelta(minutes=1))
    assert second==first
    assert len(enrolled["consents"])==1


def test_duplicate_existing_receipt_mismatch_owner_denied(enrolled):
    enroll(enrolled)
    admin_token=enrolled["make_token"]({"oid":ADMIN_OWNER_OID})
    with pytest.raises(BoundedStepProofDenied,match="RECOVERY_OWNER_IDENTITY_CHANGED"):
        enroll(enrolled,token=admin_token,at=AT+timedelta(minutes=1))
    assert len(enrolled["consents"])==1


@pytest.mark.parametrize("claim_change",[
    {"tid":"wrong-tenant"},
    {"iss":"https://other.invalid/"},
    {"aud":"other-audience"},
    {"oid":"unknown-owner"},
    {"nbf":int(AT.timestamp())+3600},
    {"exp":int(AT.timestamp())-3600},
])
def test_invalid_entra_token_cannot_create_parent(enrolled,claim_change):
    bad=enrolled["make_token"](claim_change)
    with pytest.raises(BoundedStepProofDenied,match="CLAIMS_DENIED"):
        enroll(enrolled,token=bad)
    assert len(enrolled["consents"])==0
    assert enrolled["ledger"].decision_receipt(APPROVAL_ID) is None


def test_token_signed_by_untrusted_rsa_key_cannot_create_parent(enrolled):
    alien=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    claims={
        "tid":TID,"iss":ISSUER,"aud":AUDIENCE,"oid":OWNER_OID,
        "iat":int(AT.timestamp())-10,"nbf":int(AT.timestamp())-10,
        "exp":int(AT.timestamp())+120,
    }
    forged=jwt.encode(claims,alien,algorithm="RS256")
    with pytest.raises(BoundedStepProofDenied,match="CLAIMS_DENIED"):
        enroll(enrolled,token=forged)
    assert len(enrolled["consents"])==0


def test_no_owner_consent_does_not_record_grant(enrolled):
    with pytest.raises(BoundedStepProofDenied,match="CONSENT_DENIED"):
        enroll(enrolled,consent=lambda _:False)
    assert enrolled["ledger"].decision_receipt(APPROVAL_ID) is None


def test_owner_plan_parent_signature_tamper_blocks_all_children(enrolled):
    prior=enroll(enrolled)
    prior["payload"]["reviewed_objective"]["actions"][1]["risk"]=0
    with pytest.raises(BoundedStepProofDenied):
        issue_proved_objective_step(
            objective=enrolled["objective"],ledger=enrolled["ledger"],
            signed_parent=prior,signing_key=enrolled["owner_key"],
            pinned_public_key=enrolled["owner_key"].public_key(),
            action_index=1,observed=observed(enrolled["objective"],1),at=AT,
        )


def test_changed_root_observed_artifact_blocks_unsigned_or_signed_stage(enrolled):
    signed_parent=enroll(enrolled);obj=enrolled["objective"];key=enrolled["owner_key"]
    with pytest.raises(PermissionError,match="reviewed action"):
        issue_proved_objective_step(
            objective=obj,ledger=enrolled["ledger"],signed_parent=signed_parent,
            signing_key=key,pinned_public_key=key.public_key(),
            action_index=2,
            observed={**observed(obj,2),"artifact_sha256":"f"*64},at=AT,
            verified_prior_steps=frozenset({0,1}),
        )


def test_new_step_denied_without_new_human_review(enrolled):
    signed_parent=enroll(enrolled);obj=enrolled["objective"];key=enrolled["owner_key"]
    with pytest.raises(PermissionError,match="sequential completion"):
        issue_proved_objective_step(
            objective=obj,ledger=enrolled["ledger"],signed_parent=signed_parent,
            signing_key=key,pinned_public_key=key.public_key(),
            action_index=4,observed=observed(obj,0),at=AT,
            verified_prior_steps=frozenset({0,1,2,3}),
        )


def test_revoked_parent_grant_disallows_next_root_step(enrolled):
    parent=enroll(enrolled);obj=enrolled["objective"];key=enrolled["owner_key"]
    child=issue_proved_objective_step(
        objective=obj,ledger=enrolled["ledger"],signed_parent=parent,
        signing_key=key,pinned_public_key=key.public_key(),
        action_index=0,observed=observed(obj,0),at=AT,
    )
    assert verify_proved_objective_step(
        objective=obj,ledger=enrolled["ledger"],signed_parent=parent,
        signed_step=child,pinned_public_key=key.public_key(),
        action_index=0,observed=observed(obj,0),at=AT,
    )["step_index"]==0
    enrolled["ledger"].revoke(obj.plan_id,at=AT+timedelta(seconds=1),reason="Owner revoked")
    with pytest.raises(PermissionError,match="revoked"):
        issue_proved_objective_step(
            objective=obj,ledger=enrolled["ledger"],signed_parent=parent,
            signing_key=key,pinned_public_key=key.public_key(),
            action_index=1,observed=observed(obj,1),at=AT+timedelta(seconds=2),
            verified_prior_steps=frozenset({0}),
        )


def test_root_one_use_claim_replay_denied(enrolled):
    parent=enroll(enrolled);obj=enrolled["objective"];key=enrolled["owner_key"]
    child=issue_proved_objective_step(
        objective=obj,ledger=enrolled["ledger"],signed_parent=parent,
        signing_key=key,pinned_public_key=key.public_key(),
        action_index=0,observed=observed(obj,0),at=AT,
    )
    claim=child["payload"]["step_claim_id"]
    with pytest.raises(BoundedStepProofDenied,match="REPLAY"):
        verify_proved_objective_step(
            objective=obj,ledger=enrolled["ledger"],signed_parent=parent,
            signed_step=child,pinned_public_key=key.public_key(),
            action_index=0,observed=observed(obj,0),at=AT,
            consumed_step_claims=frozenset({claim}),
        )


def test_signed_parent_and_grant_are_one_atomic_transaction(enrolled):
    ledger=enrolled["ledger"]
    # Prepare the exact same lazy optional receipt table and inject a
    # deterministic SQLite failure after the grant INSERT but before commit.
    with ledger._connection() as db:
        db.execute("""CREATE TABLE signed_owner_objective_receipts (
            plan_id TEXT PRIMARY KEY,approval_id TEXT UNIQUE,proof_json TEXT,
            proof_sha256 TEXT,decided_at TEXT
        )""")
        db.execute("""CREATE TRIGGER reject_synthetic_receipt
            BEFORE INSERT ON signed_owner_objective_receipts
            BEGIN SELECT RAISE(ABORT, 'synthetic journal write failure'); END;
        """)
    with pytest.raises(sqlite3.IntegrityError,match="synthetic journal"):
        enroll(enrolled)
    assert ledger.decision_receipt(APPROVAL_ID) is None
    assert ledger.authenticated_owner_objective_receipt(
        plan_id=enrolled["objective"].plan_id,approval_id=APPROVAL_ID,
    ) is None


def test_root_cannot_skip_required_prior_stage(enrolled):
    parent=enroll(enrolled);obj=enrolled["objective"];key=enrolled["owner_key"]
    with pytest.raises(PermissionError,match="sequential completion"):
        issue_proved_objective_step(
            objective=obj,ledger=enrolled["ledger"],signed_parent=parent,
            signing_key=key,pinned_public_key=key.public_key(),
            action_index=2,observed=observed(obj,2),at=AT,
            verified_prior_steps=frozenset({0}),
        )


def test_production_root_cannot_assume_prior_stage_receipt(enrolled):
    parent=enroll(enrolled);obj=enrolled["objective"];key=enrolled["owner_key"]
    child=issue_proved_objective_step(
        objective=obj,ledger=enrolled["ledger"],signed_parent=parent,
        signing_key=key,pinned_public_key=key.public_key(),
        action_index=1,observed=observed(obj,1),at=AT,
        verified_prior_steps=frozenset({0}),
    )
    with pytest.raises(PermissionError,match="sequential completion"):
        verify_proved_objective_step(
            objective=obj,ledger=enrolled["ledger"],signed_parent=parent,
            signed_step=child,pinned_public_key=key.public_key(),
            action_index=1,observed=observed(obj,1),at=AT,
            verified_prior_steps=frozenset(),
        )


def test_root_refuses_fabricated_complete_step_indices(enrolled):
    parent=enroll(enrolled);obj=enrolled["objective"];key=enrolled["owner_key"]
    for state in (frozenset({False}),frozenset({0,1}),frozenset({3})):
        with pytest.raises(PermissionError,match="sequential completion"):
            issue_proved_objective_step(
                objective=obj,ledger=enrolled["ledger"],signed_parent=parent,
                signing_key=key,pinned_public_key=key.public_key(),
                action_index=1,observed=observed(obj,1),at=AT,
                verified_prior_steps=state,
            )
