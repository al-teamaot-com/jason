"""Exact Stage E Entra Owner one-use issuer reuses installed signer format."""
from datetime import datetime,timedelta,timezone
import importlib.util
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pytest

from tools import pmv4_e_exact_owner_offer as offer
from tools import pmv4_e_signed_bootstrap_phase as bootstrap
from tools import pmv4_e_native_release_contract as contract
from tools.tests.test_pmv4_e_signed_native_ledger import (
    CANDIDATE,ROLLBACK,KEY,OID,
)

def signer():
    from implementation.kernel import signed_owner_release
    return signed_owner_release

def plan():
    x=contract.draft(candidate_sha=CANDIDATE,rollback_sha=ROLLBACK)
    return {
        "candidate":CANDIDATE,"rollback":ROLLBACK,
        "scope_sha256":x["scope_sha256"],
        "manifest_sha256":x["manifest_sha256"],
        "freeze_sha256":x["manifest"]["freeze_sha256"],
    }

def test_exact_owner_proof_is_bootstrap_compatible_not_six_unit_authority():
    d=offer.signed_request(plan(),signer=signer(),
                           private=KEY,owner_oid=OID)
    assert set(d)==bootstrap.FIELDS
    assert d["action"]==bootstrap.BOOTSTRAP_ACTION
    assert d["candidate_sha"]==CANDIDATE
    assert d["rollback_sha"]==ROLLBACK
    assert d["scope_sha256"]==plan()["scope_sha256"]
    assert d["signed_owner_proof"]["payload"]["authorization"]==(
        "authenticated_entra_owner_exact_release")
    assert d["signed_owner_proof"]["payload"]["standing_authority"] is False
    assert d["signed_owner_proof"]["payload"]["one_release_only"] is True
    assert d["signed_owner_proof"]["payload"]["approval_id"].startswith(
        "owner-mcp-")

def test_authenticated_non_owner_oid_denied_before_issue():
    with pytest.raises(offer.ExactOwnerOfferDenied,match="AUTHENTICATED_OWNER_NOT_BOUND"):
        offer.signed_request(
            plan(),signer=signer(),private=KEY,
            owner_oid="ffffffff-ffff-ffff-ffff-ffffffffffff")

def test_exact_signature_invalid_for_other_candidate_or_rollback():
    signed=offer.signed_request(plan(),signer=signer(),
                                private=KEY,owner_oid=OID)
    verifier=signer()
    proof=signed["signed_owner_proof"]
    for key,bad in [
        ("expected_candidate_sha","c"*40),
        ("expected_rollback_sha","c"*40),
        ("expected_scope_sha256","0"*64),
        ("expected_manifest_sha256","0"*64),
        ("expected_freeze_sha256","0"*64),
    ]:
        kw={
            "public_key":KEY.public_key(),
            "expected_release_id":"release-"+CANDIDATE[:16],
            "expected_candidate_sha":CANDIDATE,
            "expected_rollback_sha":ROLLBACK,
            "expected_scope_sha256":plan()["scope_sha256"],
            "expected_manifest_sha256":plan()["manifest_sha256"],
            "expected_freeze_sha256":plan()["freeze_sha256"],
            "at":datetime.now(timezone.utc),
        }
        kw[key]=bad
        with pytest.raises(verifier.OwnerReleaseProofDenied):
            verifier.verify_exact_owner_release(proof,**kw)


def test_replay_and_expiry_denied_on_one_exact_owner_proof():
    v=signer()
    request=offer.signed_request(plan(),signer=v,
                                 private=KEY,owner_oid=OID)
    proof=request["signed_owner_proof"]
    kw={
        "public_key":KEY.public_key(),
        "expected_release_id":"release-"+CANDIDATE[:16],
        "expected_candidate_sha":CANDIDATE,
        "expected_rollback_sha":ROLLBACK,
        "expected_scope_sha256":plan()["scope_sha256"],
        "expected_manifest_sha256":plan()["manifest_sha256"],
        "expected_freeze_sha256":plan()["freeze_sha256"],
    }
    used=frozenset({proof["payload"]["approval_id"]})
    with pytest.raises(v.OwnerReleaseProofDenied,match="ONE_USE_REPLAY"):
        v.verify_exact_owner_release(
            proof,at=datetime.now(timezone.utc),consumed_ids=used,**kw)
    with pytest.raises(v.OwnerReleaseProofDenied,match="EXPIRED_OR_FUTURE"):
        v.verify_exact_owner_release(
            proof,at=datetime.now(timezone.utc)+timedelta(minutes=20),**kw)
