"""Detached release-manager verifier: no production files, no provider access."""
import importlib.util
import hashlib
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
import sys

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))
spec = importlib.util.spec_from_file_location(
    "release_manager_host_runner", TOOLS / "release_manager_host_runner.py"
)
runner = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = runner
spec.loader.exec_module(runner)

source = ROOT / "implementation"
sys.path.insert(0, str(source))
from kernel.signed_owner_release import issue_exact_owner_release

SHA = "a" * 40
PREV = "b" * 40
SCOPE = "c" * 64
RID = "release-" + SHA[:16]
AID = "owner-mcp-" + "d" * 32
AT = datetime(2026, 11, 10, 20, 0, tzinfo=timezone.utc)


def _fixture(tmp_path):
    frozen = tmp_path / "production-deployment-freeze"
    frozen.write_text('{"status":"active"}', encoding="utf-8")
    frozen.chmod(0o600)
    key = Ed25519PrivateKey.generate()
    manifest = {"candidate_sha": SHA, "rollback_sha": PREV, "scope": "exact"}
    manifest_digest = hashlib.sha256(json.dumps(
        manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode()).hexdigest()
    freeze_hash = hashlib.sha256(frozen.read_bytes()).hexdigest()
    signed = issue_exact_owner_release(
        approval_id=AID, release_id=RID, candidate_sha=SHA,
        rollback_sha=PREV, scope_sha256=SCOPE,
        manifest_sha256=manifest_digest, freeze_sha256=freeze_hash,
        verified_tenant_id="f7054323-d52b-4863-8c2f-1898f0b6077c",
        verified_owner_oid="bee80bdc-ffb0-4c50-b453-c09d4d411f5f",
        verified_principal="person-entra-bee80bdcffb04c50b453c09d4d411f5f",
        verified_organization_id="aot", confirmed_decision="approve", at=AT,
        private_key=key,
    )
    record = {
        "state": "production_eligible",
        "release_candidate": {"candidate_sha": SHA},
        "rollback_sha": PREV,
        "manual_scope_review": {
            "candidate_sha": SHA, "baseline_sha": PREV, "scope_sha256": SCOPE,
            "included_prs": [2410],
            "included_commits": [SHA],
        },
        "release_manifest": manifest,
    }
    request = {
        "source": "authenticated_jason_mcp_owner:" + AID,
        "signed_owner_proof": signed,
        "release_id": RID, "candidate_sha": SHA,
        "approved_by": "person-entra-bee80bdcffb04c50b453c09d4d411f5f",
        "organization_id": "aot",
    }
    return record, request, key


def test_independent_verified_owner_auth_source(tmp_path):
    record, req, key = _fixture(tmp_path)
    result = runner.verify_signed_mcp_owner_request(
        tmp_path, record, req, public_key=key.public_key(),
        at=AT + timedelta(seconds=30),
    )
    assert result["approval_id"] == AID
    assert result["scope_sha256"] == SCOPE


@pytest.mark.parametrize("field,value", [
    ("source", "governed_mcp_owner:person-al"),
    ("source", "authenticated_jason_mcp_owner:owner-mcp-" + "0" * 32),
    ("approved_by", "person-al"),
    ("release_id", "release-" + "f" * 16),
    ("organization_id", "other"),
])
def test_malformed_request_is_never_root_authorization(tmp_path, field, value):
    record, req, key = _fixture(tmp_path)
    req[field] = value
    with pytest.raises(runner.ReleaseManagerError):
        runner.verify_signed_mcp_owner_request(
            tmp_path, record, req, public_key=key.public_key(),
            at=AT + timedelta(seconds=5),
        )


def test_unsigned_mcp_request_rejected(tmp_path):
    record, req, key = _fixture(tmp_path)
    req.pop("signed_owner_proof")
    with pytest.raises(runner.ReleaseManagerError):
        runner.verify_signed_mcp_owner_request(
            tmp_path, record, req, public_key=key.public_key(),
            at=AT + timedelta(seconds=5),
        )


def test_freeze_changed_after_signed_owner_decision_denied(tmp_path):
    record, req, key = _fixture(tmp_path)
    (tmp_path / "production-deployment-freeze").write_text("modified")
    with pytest.raises(runner.ReleaseManagerError, match="TRANSACTION_BINDING"):
        runner.verify_signed_mcp_owner_request(
            tmp_path, record, req, public_key=key.public_key(),
            at=AT + timedelta(seconds=5),
        )


def test_scope_changed_after_signed_owner_decision_denied(tmp_path):
    record, req, key = _fixture(tmp_path)
    record["manual_scope_review"]["scope_sha256"] = "1" * 64
    with pytest.raises(runner.ReleaseManagerError, match="TRANSACTION_BINDING"):
        runner.verify_signed_mcp_owner_request(
            tmp_path, record, req, public_key=key.public_key(),
            at=AT + timedelta(seconds=5),
        )


def test_signed_owner_expiration_fails_closed(tmp_path):
    record, req, key = _fixture(tmp_path)
    with pytest.raises(runner.ReleaseManagerError, match="EXPIRED"):
        runner.verify_signed_mcp_owner_request(
            tmp_path, record, req, public_key=key.public_key(),
            at=AT + timedelta(minutes=16),
        )


def test_previous_legacy_unsigned_approved_by_is_not_authority(tmp_path):
    record, req, key = _fixture(tmp_path)
    req["signed_owner_proof"] = {"approved": True}
    with pytest.raises(runner.ReleaseManagerError):
        runner.verify_signed_mcp_owner_request(
            tmp_path, record, req, public_key=key.public_key(),
            at=AT + timedelta(seconds=5),
        )
