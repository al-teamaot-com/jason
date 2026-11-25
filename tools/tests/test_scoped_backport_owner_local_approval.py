"""One-use signed Owner decision requires source eligibility and fresh identity."""
from pathlib import Path
import json

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pytest

from implementation.kernel.signed_owner_release import (
    EXACT_OWNER_OAUTH_SUBJECTS,
)
from tools import scoped_backport_owner_local_approval as auth
from tools import scoped_backport_release as sb

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = json.loads((ROOT / sb.RELEASE_MANIFEST).read_text())
OFFER = sb.make_offer(MANIFEST, main_sha="510243494efcd592a1585c681a3fa28a29296e17")


def test_local_owner_approval_not_callable_from_uninstalled_source():
    with pytest.raises(sb.ScopedBackportDenied, match="OWNER_AUTHENTICATION_INSTALLED_OPERATOR_REQUIRED"):
        auth.installed()


def test_exact_signed_owner_proof_is_one_use_and_bound(monkeypatch, tmp_path):
    release_id = OFFER["release_id"]
    eligible = {
        "release_id": release_id,
        "status": "native_scoped_preproduction_eligible_not_approved",
        "candidate_sha": OFFER["candidate_sha"],
        "scope_sha256": OFFER["scope_sha256"],
        "manifest_sha256": OFFER["manifest_sha256"],
        "freeze_sha256": OFFER["freeze_sha256"],
    }
    folder = tmp_path / "owner-approvals"
    folder.mkdir(mode=0o700)
    key = Ed25519PrivateKey.generate()
    owner_oid = next(iter(EXACT_OWNER_OAUTH_SUBJECTS))
    monkeypatch.setattr(auth, "installed", lambda: None)
    monkeypatch.setattr(auth, "_safe_public",
                        lambda name, release: OFFER if name == "offers" else eligible)
    monkeypatch.setattr(auth, "authenticated_owner", lambda: owner_oid)
    monkeypatch.setattr(auth, "input", lambda prompt: auth.DECISION, raising=False)
    monkeypatch.setattr(auth, "AUTH", tmp_path)
    monkeypatch.setattr(auth, "read_pinned_root_owner_public_key",
                        lambda trust: key.public_key())
    monkeypatch.setattr(auth, "read_service_owner_signing_key",
                        lambda path: key)
    result = auth.approve(release_id)
    assert result["status"] == "owner_exact_signed_release_proof_queued_not_deployed"
    assert result["production_deployment"] is False
    doc = json.loads((folder / (release_id + ".json")).read_text())
    assert doc["standing_authority"] is False
    assert doc["provider_mutations_approved"] is False
    assert doc["candidate_sha"] == OFFER["candidate_sha"]
    assert doc["signed_owner_proof"]["payload"]["release_id"] == release_id
    with pytest.raises(sb.ScopedBackportDenied, match="OWNER_PROOF_ALREADY_EXISTS"):
        auth.approve(release_id)


def test_missing_root_eligible_receipt_cannot_authenticate(monkeypatch):
    monkeypatch.setattr(auth, "installed", lambda: None)
    monkeypatch.setattr(auth, "_safe_public",
                        lambda name, release: OFFER if name == "offers" else {})
    monkeypatch.setattr(auth, "authenticated_owner",
                        lambda: pytest.fail("should not contact Entra"))
    with pytest.raises(sb.ScopedBackportDenied, match="OWNER_EXACT_ELIGIBLE_OFFER_REQUIRED"):
        auth.approve(OFFER["release_id"])
