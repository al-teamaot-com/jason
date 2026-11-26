from __future__ import annotations
import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

SOURCE = Path(__file__).resolve().parents[1] / "signed_owner_release.py"
spec = importlib.util.spec_from_file_location("signed_owner_release", SOURCE)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

NOW = datetime(2026, 11, 10, 19, 45, tzinfo=timezone.utc)
SHA = "a" * 40
PREV = "b" * 40
SCOPE = "c" * 64
MANIFEST = "d" * 64
FREEZE = "e" * 64
RID = "release-" + SHA[:16]
AID = "owner-mcp-" + "f" * 32


def _sign(private_key, **kwargs):
    vals = dict(
        approval_id=AID,
        release_id=RID,
        candidate_sha=SHA,
        rollback_sha=PREV,
        scope_sha256=SCOPE,
        manifest_sha256=MANIFEST,
        freeze_sha256=FREEZE,
        verified_tenant_id=m.TID,
        verified_owner_oid=m.OWNER_OID,
        verified_principal=m.OWNER_PRINCIPAL,
        verified_organization_id="aot",
        confirmed_decision="approve",
        at=NOW,
        private_key=private_key,
    )
    vals.update(kwargs)
    return m.issue_exact_owner_release(**vals)


def _verify(payload, public_key, **kwargs):
    vals = dict(
        public_key=public_key,
        expected_candidate_sha=SHA,
        expected_rollback_sha=PREV,
        expected_release_id=RID,
        expected_scope_sha256=SCOPE,
        expected_manifest_sha256=MANIFEST,
        expected_freeze_sha256=FREEZE,
        at=NOW + timedelta(seconds=45),
    )
    vals.update(kwargs)
    return m.verify_exact_owner_release(payload, **vals)


def test_exact_signed_auth_owner_release_without_any_teams_receipt():
    signer = Ed25519PrivateKey.generate()
    proof = _sign(signer)
    result = _verify(proof, signer.public_key())
    assert result["candidate_sha"] == SHA
    assert result["decision"] == "approve"
    assert result["standing_authority"] is False
    assert result["one_release_only"] is True
    assert result["authentication"] == "verified_entra_oauth_bearer"


@pytest.mark.parametrize("field,value", [
    ("verified_tenant_id", "00000000-0000-0000-0000-000000000000"),
    ("verified_owner_oid", "c848022d-e13b-4457-84b0-e2f5c00dcaf6"),
    ("verified_principal", "person-anyone"),
    ("verified_organization_id", "other"),
    ("approval_id", "not-unique"),
    ("release_id", "release-" + "1" * 16),
    ("scope_sha256", "ab"),
])
def test_signing_rejects_wrong_owner_and_scope(field, value):
    with pytest.raises(m.OwnerReleaseProofDenied):
        _sign(Ed25519PrivateKey.generate(), **{field: value})


def test_ed25519_signature_cannot_be_forged_or_rebound():
    signer = Ed25519PrivateKey.generate()
    proof = _sign(signer)
    proof["payload"]["scope_sha256"] = "f" * 64
    with pytest.raises(m.OwnerReleaseProofDenied, match="SIGNATURE_INVALID"):
        _verify(proof, signer.public_key())


def test_wrong_root_public_key_is_denied():
    signer = Ed25519PrivateKey.generate()
    proof = _sign(signer)
    with pytest.raises(m.OwnerReleaseProofDenied, match="SIGNATURE_INVALID"):
        _verify(proof, Ed25519PrivateKey.generate().public_key())


@pytest.mark.parametrize("change", [
    dict(expected_candidate_sha="f" * 40),
    dict(expected_rollback_sha="f" * 40),
    dict(expected_release_id="release-" + "e" * 16),
    dict(expected_scope_sha256="f" * 64),
    dict(expected_manifest_sha256="f" * 64),
    dict(expected_freeze_sha256="f" * 64),
])
def test_root_rechecks_every_exact_release_and_freeze_binding(change):
    signer = Ed25519PrivateKey.generate()
    proof = _sign(signer)
    with pytest.raises(m.OwnerReleaseProofDenied, match="TRANSACTION_BINDING"):
        _verify(proof, signer.public_key(), **change)


def test_expired_future_or_replayed_decision_rejected():
    signer = Ed25519PrivateKey.generate()
    proof = _sign(signer)
    for changed in (
        {"at": NOW - timedelta(seconds=1)},
        {"at": NOW + timedelta(minutes=15)},
        {"consumed_ids": frozenset({AID})},
    ):
        with pytest.raises(m.OwnerReleaseProofDenied):
            _verify(proof, signer.public_key(), **changed)


def test_signed_deny_never_grants_execution():
    signer = Ed25519PrivateKey.generate()
    proof = _sign(signer, confirmed_decision="deny")
    with pytest.raises(m.OwnerReleaseProofDenied, match="DENIED"):
        _verify(proof, signer.public_key())


def test_raw_chat_and_mutable_flags_cannot_claim_signed_proof():
    signer = Ed25519PrivateKey.generate()
    for bad in (
        {"approved": True, "candidate_sha": SHA},
        "approve this release",
        {"payload": {"approved": True}, "signature_base64url": "a" * 86},
    ):
        with pytest.raises(m.OwnerReleaseProofDenied):
            _verify(bad, signer.public_key())


def test_double_issue_idempotent_payload_but_one_time_ledger_controls_replay():
    signer = Ed25519PrivateKey.generate()
    proof = _sign(signer)
    assert _verify(proof, signer.public_key())["approval_id"] == AID
    with pytest.raises(m.OwnerReleaseProofDenied, match="ONE_USE_REPLAY"):
        _verify(proof, signer.public_key(), consumed_ids=frozenset({AID}))


def test_exact_admin_oauth_owner_subject_is_signed_without_teams():
    signer = Ed25519PrivateKey.generate()
    envelope = _sign(
        signer,
        verified_owner_oid=m.ADMIN_OWNER_OID,
        verified_principal=m.ADMIN_OWNER_PRINCIPAL,
    )
    result = _verify(envelope, signer.public_key())
    assert result["owner_oid"] == m.ADMIN_OWNER_OID
    assert result["owner_principal"] == m.ADMIN_OWNER_PRINCIPAL
