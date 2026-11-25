from datetime import datetime, timezone, timedelta
from hashlib import sha256
import json

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pytest

from jason_mcp.independent_component_release_approval import (
    queue_component_release_approval, _offer,
)
from kernel.signed_owner_release import verify_exact_owner_release

SHA = "a" * 40
IMAGE = "sha256:" + "f" * 64
PREV = "0" * 40
KEY = Ed25519PrivateKey.generate()
OWNER = "person-entra-bee80bdcffb04c50b453c09d4d411f5f"
CLAIMS = {
    "tid": "f7054323-d52b-4863-8c2f-1898f0b6077c",
    "oid": "bee80bdc-ffb0-4c50-b453-c09d4d411f5f",
}


def setup(tmp_path):
    root = tmp_path / "state"
    offers = root / "independent-component-offers"
    offers.mkdir(parents=True)
    frozen = b'{"status":"active"}'
    (root / "production-deployment-freeze").write_bytes(frozen)
    offer = {
        "schema_version": "1.0",
        "state": "production_eligible",
        "component_id": "financial-statements",
        "candidate_sha": SHA,
        "rollback_sha": PREV,
        "scope_sha256": "b" * 64,
        "manifest_sha256": "c" * 64,
        "freeze_sha256": sha256(frozen).hexdigest(),
        "image_digest": IMAGE,
        "source_and_ci_verified": True,
        "preproduction_verified": True,
        "rollback_ready": True,
        "no_protected_services_changed": True,
        "prepared_at": datetime.now(timezone.utc).isoformat(),
    }
    path = offers / ("release-" + SHA[:16] + ".json")
    path.write_text(json.dumps(offer) + "\n")
    return root, offer, path


def issue(root, *, identity=CLAIMS, principal=OWNER, signature=KEY, image=IMAGE, decision="approve"):
    return queue_component_release_approval(
        state_root=root, component_id="financial-statements",
        candidate_sha=SHA, image_digest=image,
        approved_by=principal, organization_id="aot",
        verified_token_claims=identity, service_signer=signature,
        confirmed_decision=decision,
    )


def test_exact_oauth_owner_release_produces_one_signed_nonexecuting_receipt(tmp_path):
    root, offer, path = setup(tmp_path)
    result = issue(root)
    assert result["component_id"] == "financial-statements"
    assert result["image_digest"] == IMAGE
    assert result["source"].startswith("authenticated_jason_mcp_owner:owner-mcp-")
    proof = result["signed_owner_proof"]
    decoded = verify_exact_owner_release(
        proof, public_key=KEY.public_key(),
        expected_release_id="release-" + SHA[:16],
        expected_candidate_sha=SHA, expected_rollback_sha=PREV,
        expected_scope_sha256=offer["scope_sha256"],
        expected_manifest_sha256=offer["manifest_sha256"],
        expected_freeze_sha256=offer["freeze_sha256"],
        at=datetime.now(timezone.utc),
    )
    assert decoded["one_release_only"] is True
    assert decoded["standing_authority"] is False
    request_path = root / "independent-component-owner-approvals" / ("release-" + SHA[:16] + ".json")
    assert request_path.is_file()
    assert request_path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(ValueError, match="ALREADY_ISSUED"):
        issue(root)


@pytest.mark.parametrize("kwargs,denial", [
    ({"identity": None}, "SIGNED_OWNER"),
    ({"principal": "person-al"}, "SIGNED_OWNER"),
    ({"signature": None}, "SIGNED_OWNER"),
    ({"decision": ""}, "EXACT_APPROVAL"),
    ({"decision": "deny"}, "EXACT_APPROVAL"),
    ({"image": "sha256:" + "0" * 64}, "OFFER_IDENTITY"),
    ({"identity": {"tid": CLAIMS["tid"], "oid": "00000000-0000-0000-0000-000000000000"}}, "SIGNED_OWNER"),
])
def test_rejects_unauthenticated_or_unreviewed_request(tmp_path, kwargs, denial):
    root, offer, path = setup(tmp_path)
    with pytest.raises(ValueError, match=denial):
        issue(root, **kwargs)
    assert list((root / "independent-component-owner-approvals").glob("*.json")) == [] if (
        root / "independent-component-owner-approvals"
    ).exists() else True


@pytest.mark.parametrize("field,value,code", [
    ("state", "development", "NOT_ELIGIBLE"),
    ("preproduction_verified", False, "NOT_ELIGIBLE"),
    ("rollback_ready", False, "NOT_ELIGIBLE"),
    ("source_and_ci_verified", False, "NOT_ELIGIBLE"),
    ("no_protected_services_changed", False, "NOT_ELIGIBLE"),
    ("manifest_sha256", "bad", "NOT_ELIGIBLE"),
    ("prepared_at", "2026-01-01T00:00:00+00:00", "STALE"),
])
def test_prepared_offer_requires_current_complete_evidence(tmp_path, field, value, code):
    root, offer, path = setup(tmp_path)
    offer[field] = value
    path.write_text(json.dumps(offer))
    with pytest.raises(ValueError, match=code):
        issue(root)


def test_freeze_drift_and_offer_symlink_rejected(tmp_path):
    root, offer, path = setup(tmp_path)
    (root / "production-deployment-freeze").write_text('{"status":"inactive"}')
    with pytest.raises(ValueError, match="FREEZE_DRIFT"):
        issue(root)
    (root / "production-deployment-freeze").write_bytes(b'{"status":"active"}')
    path.unlink()
    path.symlink_to(root / "production-deployment-freeze")
    with pytest.raises(ValueError, match="OFFER_UNTRUSTED"):
        issue(root)


def test_offer_cannot_be_reissued_after_stale_signed_request(tmp_path):
    root, offer, path = setup(tmp_path)
    result = issue(root)
    with pytest.raises(ValueError, match="ALREADY_ISSUED"):
        issue(root)
    request = root / "independent-component-owner-approvals" / ("release-" + SHA[:16] + ".json")
    assert json.loads(request.read_text())["signed_owner_proof"] == result["signed_owner_proof"]
