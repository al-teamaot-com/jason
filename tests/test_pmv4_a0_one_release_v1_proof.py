"""One native v1 signed EXACT release covers all 3 A0 actions; no new signer."""
from datetime import timedelta
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pytest

from kernel.signed_owner_release import OWNER_OID
from tools.pmv4_a0_one_release_v1_proof import (
    A0OneReleaseProofDenied, exact_three_action_manifest, exact_v1_release_scopes,
    issue_source_only_existing_v1_proof, verify_existing_v1_whole_transaction,
)
from tools.pmv4_stage_a0_one_owner_review import (
    REVIEWED_ACTIONS, SOURCE, LKG, FREEZE, HOLD,
)
from test_pmv4_owner_objective_end_to_end import AT, enrolled

AUTH_ID = "owner-mcp-" + "d"*32


@pytest.fixture
def signed(enrolled):
    env = enrolled
    claims = env["verifier"](env["token"])
    assert claims["oid"] == OWNER_OID
    env["consents"].append({
        "full_reviewed_three_action_release":True,
        "exact_actions":exact_three_action_manifest()["exact_ordered_actions"],
    })
    signed = issue_source_only_existing_v1_proof(
        approval_id=AUTH_ID, signer_key=env["owner_key"],
        verified_owner_oid=claims["oid"], at=AT,
        independent_entra_owner_was_verified=True,
        confirmed_exact_full_plan=True,
    )
    return env, signed


def test_one_existing_v1_owner_signature_covers_3_exact_operations(signed):
    env, proof = signed
    approved = verify_existing_v1_whole_transaction(
        signed=proof,
        root_pinned_public_key=env["owner_key"].public_key(),
        at=AT + timedelta(seconds=1),
    )
    assert approved["approved_action_count"] == 3
    assert approved["owner_approval_id"] == AUTH_ID
    assert approved["root_mutation_authorized"] is False
    assert approved["production_release_installed"] is False
    assert len(env["consents"]) == 1
    manifest = exact_three_action_manifest()
    assert [a["capability"] for a in manifest["exact_ordered_actions"]] == [
        a[0] for a in REVIEWED_ACTIONS
    ]
    assert manifest["source_sha"] == SOURCE
    assert manifest["rollback_sha"] == LKG
    assert manifest["freeze_sha256"] == FREEZE
    assert manifest["promotion_hold_sha256"] == HOLD
    assert manifest["one_release_only"] is True
    assert manifest["root_lock_shared_by_all_actions"] is True
    scope = exact_v1_release_scopes()
    assert scope["scope_sha256"] == proof["payload"]["scope_sha256"]
    assert scope["manifest_sha256"] == proof["payload"]["manifest_sha256"]
    assert proof["payload"]["standing_authority"] is False


@pytest.mark.parametrize("fault", [
    "foreign_scope", "other_manifest", "other_candidate", "other_rollback",
    "unverified_signature", "foreign_authorization", "expired", "replayed",
])
def test_root_refuses_foreign_or_expired_whole_scope(signed,fault):
    env, original = signed
    proof = {**original, "payload":dict(original["payload"])}
    if fault == "foreign_scope":
        proof["payload"]["scope_sha256"] = "c"*64
    elif fault == "other_manifest":
        proof["payload"]["manifest_sha256"] = "d"*64
    elif fault == "other_candidate":
        proof["payload"]["candidate_sha"] = "d"*40
    elif fault == "other_rollback":
        proof["payload"]["rollback_sha"] = "d"*40
    elif fault == "unverified_signature":
        proof["signature_base64url"] = "A"*86
    elif fault == "foreign_authorization":
        proof["payload"]["one_release_only"] = False
    at = AT+timedelta(seconds=1)
    consumed = frozenset()
    if fault == "expired":
        at = AT+timedelta(minutes=16)
    if fault == "replayed":
        consumed = frozenset({AUTH_ID})
    with pytest.raises((PermissionError,ValueError)):
        verify_existing_v1_whole_transaction(
            signed=proof,
            root_pinned_public_key=env["owner_key"].public_key(),
            at=at,consumed_ids=consumed,
        )


def test_wrong_pinned_root_key_denies_signature(signed):
    _, proof = signed
    with pytest.raises(PermissionError):
        verify_existing_v1_whole_transaction(
            signed=proof, root_pinned_public_key=Ed25519PrivateKey.generate().public_key(),
            at=AT+timedelta(seconds=1),
        )


@pytest.mark.parametrize("override", [
    {"independent_entra_owner_was_verified":False},
    {"confirmed_exact_full_plan":False},
    {"verified_owner_oid":"foreign-owner"},
    {"approval_id":"generic consent"},
    {"production":True},
])
def test_source_issuer_does_not_derive_owner_authority_from_chat(signed,override):
    env, proof = signed
    options = {
        "approval_id":AUTH_ID,"signer_key":env["owner_key"],
        "verified_owner_oid":OWNER_OID,"at":AT,
        "independent_entra_owner_was_verified":True,
        "confirmed_exact_full_plan":True,
    }
    options.update(override)
    with pytest.raises(A0OneReleaseProofDenied):
        issue_source_only_existing_v1_proof(**options)


def test_production_v1_root_integration_still_requires_separate_release(signed):
    env, proof=signed
    with pytest.raises(A0OneReleaseProofDenied,
                       match="ROOT_NOT_INSTALLED"):
        verify_existing_v1_whole_transaction(
            signed=proof,
            root_pinned_public_key=env["owner_key"].public_key(),
            at=AT+timedelta(seconds=1),production=True,
        )
