"""Independent root authorization for signed, single-release Owner decisions."""
import importlib.util
import json
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[2]
HOST_SCRIPT = ROOT / "tools/release_host_reconcile_worker.py"
spec = importlib.util.spec_from_file_location("test_root_signed_mcp_worker", HOST_SCRIPT)
root = importlib.util.module_from_spec(spec)
spec.loader.exec_module(root)

lib = ROOT / "implementation/kernel/signed_owner_release.py"
libspec = importlib.util.spec_from_file_location("signed_owner_release_test", lib)
signature = importlib.util.module_from_spec(libspec)
libspec.loader.exec_module(signature)

CANDIDATE = "a" * 40
ROLLBACK = "b" * 40
SCOPE = "c" * 64
IDENTITY = signature.OWNER_PRINCIPAL


def _state(tmp_path, monkeypatch):
    key = Ed25519PrivateKey.generate()
    record = {
        "release_id": "release-" + CANDIDATE[:16],
        "state": "production",
        "rollback_sha": ROLLBACK,
        "release_candidate": {"candidate_sha": CANDIDATE},
        "release_manifest": {
            "candidate_sha": CANDIDATE,
            "rollback_sha": ROLLBACK,
            "one_transaction_freeze_exception": {
                "required_recovery_profile_id": "provider_identity_and_authority_recovery",
                "authenticated_owner_release_required": True,
                "standing_authority": False,
                "restore_freeze_after_transaction": True,
            },
        },
        "manual_scope_review": {
            "candidate_sha": CANDIDATE,
            "baseline_sha": ROLLBACK,
            "scope_sha256": SCOPE,
            "included_prs": [2410],
            "included_commits": [CANDIDATE],
        },
    }
    manifest_digest = sha256(json.dumps(
        record["release_manifest"], sort_keys=True, separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")).hexdigest()
    record["owner_approval"] = {
        "approved": True, "candidate_sha": CANDIDATE,
        "source": "authenticated_signed_mcp_owner:owner-mcp-" + "f" * 32,
        "transaction_binding": {
            "candidate_sha": CANDIDATE,
            "rollback_sha": ROLLBACK,
            "scope_sha256": SCOPE,
            "manifest_sha256": manifest_digest,
        },
    }
    freeze = tmp_path / "production-deployment-freeze"
    freeze.write_text('{"status":"active"}')
    freeze.chmod(0o600)
    frozen_digest = sha256(freeze.read_bytes()).hexdigest()
    proof = signature.issue_exact_owner_release(
        approval_id="owner-mcp-" + "f" * 32,
        release_id=record["release_id"],
        candidate_sha=CANDIDATE, rollback_sha=ROLLBACK,
        scope_sha256=SCOPE, manifest_sha256=manifest_digest,
        freeze_sha256=frozen_digest,
        verified_tenant_id=signature.TID,
        verified_owner_oid=signature.OWNER_OID,
        verified_principal=IDENTITY,
        verified_organization_id="aot",
        confirmed_decision="approve",
        at=datetime.now(timezone.utc),
        private_key=key,
    )
    request_dir = tmp_path / "owner-approval-requests-processed"
    request_dir.mkdir()
    request_path = request_dir / (record["release_id"] + ".json")
    request_path.write_text(json.dumps({
        "release_id": record["release_id"],
        "candidate_sha": CANDIDATE,
        "approved_by": IDENTITY,
        "organization_id": "aot",
        "source": "authenticated_jason_mcp_owner:owner-mcp-" + "f" * 32,
        "signed_owner_proof": proof,
    }))
    request_path.chmod(0o600)
    monkeypatch.setattr(root, "RELEASE_STATE", tmp_path)
    monkeypatch.setattr(root, "_host_operator_uid", lambda: request_path.stat().st_uid)
    monkeypatch.setattr(root, "_root_owner_identity_is_active", lambda oid, principal: True)
    monkeypatch.setattr(root, "_trusted_owner_proof_module", lambda: SimpleNamespace(
        read_pinned_root_owner_public_key=lambda path: key.public_key(),
        verify_exact_owner_release=signature.verify_exact_owner_release,
    ))
    return key, record, request_path, freeze


def test_root_independently_verifies_signed_owner_without_teams(tmp_path, monkeypatch):
    key, record, request_path, freeze = _state(tmp_path, monkeypatch)
    assert root._signed_mcp_owner_release_authorized(CANDIDATE, ROLLBACK, record)
    assert root._authenticated_rollback_evidence(CANDIDATE, ROLLBACK, record)


@pytest.mark.parametrize("mutation", ["freeze", "source", "tenant",
                                     "rollback", "manifest", "scope",
                                     "binding", "owner_identity", "expired"])
def test_root_blocks_untrusted_or_mismatched_owner_evidence(tmp_path, monkeypatch, mutation):
    key, record, request_path, freeze = _state(tmp_path, monkeypatch)
    request = json.loads(request_path.read_text())
    if mutation == "freeze":
        freeze.write_text("changed")
    elif mutation == "source":
        record["owner_approval"]["source"] = "authenticated_signed_mcp_owner:owner-mcp-" + "0" * 32
    elif mutation == "tenant":
        request["signed_owner_proof"]["payload"]["tenant_id"] = "wrong-tenant"
    elif mutation == "rollback":
        record["rollback_sha"] = "e" * 40
    elif mutation == "manifest":
        record["release_manifest"]["changed"] = True
    elif mutation == "scope":
        record["manual_scope_review"]["scope_sha256"] = "d" * 64
    elif mutation == "binding":
        record["owner_approval"]["transaction_binding"]["scope_sha256"] = "e" * 64
    elif mutation == "owner_identity":
        monkeypatch.setattr(root, "_root_owner_identity_is_active", lambda oid, principal: False)
    elif mutation == "expired":
        request["signed_owner_proof"]["payload"]["expires_at"] = "2026-11-10T20:00:00+00:00"
    request_path.write_text(json.dumps(request))
    assert not root._signed_mcp_owner_release_authorized(CANDIDATE, ROLLBACK, record)


def test_root_rejects_untrusted_root_verifier_file(tmp_path, monkeypatch):
    target = tmp_path / "owner-root-verifier.py"
    target.write_text("pass\n")
    target.chmod(0o666)
    monkeypatch.setattr(root, "ROOT_OWNER_PROOF_VERIFIER", target)
    with pytest.raises(root.HostReconcileError, match="not independently trusted"):
        root._trusted_owner_proof_module()


def test_root_requires_active_approved_entra_subject(tmp_path, monkeypatch):
    import sqlite3
    binding = tmp_path / "bindings.db"
    authority = tmp_path / "authority.db"
    with sqlite3.connect(binding) as c:
        c.execute("""CREATE TABLE microsoft_identity_bindings(
            microsoft_tenant_id TEXT, microsoft_object_id TEXT,
            jason_identity_id TEXT, client_id TEXT, status TEXT)""")
        c.execute("INSERT INTO microsoft_identity_bindings VALUES(?,?,?,?,?)",(
            signature.TID, signature.OWNER_OID, IDENTITY, None, "active"))
    with sqlite3.connect(authority) as c:
        c.execute("CREATE TABLE identities(identity_id TEXT,payload TEXT)")
        c.execute("INSERT INTO identities VALUES(?,?)",(
            IDENTITY, json.dumps({
                "identity_id": IDENTITY, "organization_id": "aot",
                "status": "active", "identity_type": "human"})))
    monkeypatch.setattr(root, "ROOT_OWNER_BINDINGS", binding)
    monkeypatch.setattr(root, "ROOT_OWNER_AUTHORITY", authority)
    assert root._root_owner_identity_is_active(signature.OWNER_OID, IDENTITY)
    with sqlite3.connect(binding) as c:
        c.execute("UPDATE microsoft_identity_bindings SET status='inactive'")
    assert not root._root_owner_identity_is_active(signature.OWNER_OID, IDENTITY)


def test_root_new_channel_remains_fail_closed_without_any_key(tmp_path, monkeypatch):
    _, record, _, _ = _state(tmp_path, monkeypatch)
    def missing():
        raise root.HostReconcileError("root signer not installed")
    monkeypatch.setattr(root, "_trusted_owner_proof_module", missing)
    assert not root._authenticated_rollback_evidence(CANDIDATE, ROLLBACK, record)
