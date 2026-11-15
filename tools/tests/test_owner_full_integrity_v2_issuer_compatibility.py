"""Source-only cryptographic acceptance of an already-approved PMv4 issuer.

The existing V2 integrity scan remains unchanged; only read-only proof that
the SAME original running MCP had a signed, root-audited issuer activation is
permitted. No live issuer mutation or fresh approval is minted by tests.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import stat
from types import SimpleNamespace

import pytest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from implementation.kernel import signed_owner_release as verifier
from tools import owner_full_integrity_v2_root_repair as repair


class FakeRootLedger:
    """Test metadata projection only; production uses actual lstat + root files."""
    def __init__(self, path: Path, *, uid=0):
        self.path = path
        self.uid = uid

    def lstat(self):
        return SimpleNamespace(
            st_mode=stat.S_IFDIR | 0o700, st_uid=self.uid, st_gid=0,
        )

    def is_symlink(self):
        return False

    def iterdir(self):
        return self.path.iterdir()

    def __truediv__(self, other):
        return self.path / other


@pytest.fixture
def issuer_case(tmp_path, monkeypatch):
    # A disposable Ed25519 key proves that old Owner authorization can be
    # authenticated AT ITS ORIGINAL ISSUANCE INSTANT, never reused for writes.
    private = Ed25519PrivateKey.generate()
    issued = datetime.now(timezone.utc)
    root = tmp_path / "root-ledger"
    root.mkdir(mode=0o700)
    issuer_code = b"root-pinned-existing-issuer-module"
    root_module = tmp_path / "trusted-issuer-code.py"
    root_policy = tmp_path / "trusted-issuer-policy.json"
    ledger = FakeRootLedger(root)
    monkeypatch.setattr(repair, "ISSUER_LEDGER", ledger)
    monkeypatch.setattr(repair, "ISSUER_CODE", root_module)
    monkeypatch.setattr(repair, "ISSUER_POLICY", root_policy)
    policy = {
        "source_sha": repair.ISSUER_SOURCE,
        "exact_action": repair.ISSUER_ACTION,
        "mcp_image_sha256": "sha256:" + "b" * 64,
        "runtime_image_sha256": "sha256:" + "c" * 64,
        "freeze_sha256": "a" * 64,
        "change": "same-mcp-image-one-env-flag-only",
        "one_shot": True,
        "provider_writes": False,
        "script_sha256": sha256(issuer_code).hexdigest(),
    }
    issuer_scope = repair.digest(repair.canonical({
        "schema_version": "1.0", "action": repair.ISSUER_ACTION,
        "source_sha": repair.ISSUER_SOURCE,
        "runtime_image": policy["runtime_image_sha256"],
        "mcp_image": policy["mcp_image_sha256"],
        "flag": "JASON_PMV4_STAGE_A0_ISSUER_ENABLED=true",
        "rollback": "same-image-original-container-issuer-off",
        "provider_writes": False, "core_mutation": False,
    }))
    proof = verifier.issue_exact_owner_release(
        approval_id="owner-mcp-" + "e" * 32,
        release_id="release-" + repair.ISSUER_SOURCE[:16],
        candidate_sha=repair.ISSUER_SOURCE,
        rollback_sha=repair.ISSUER_SOURCE,
        scope_sha256=issuer_scope,
        manifest_sha256=repair.digest(repair.canonical(policy)),
        freeze_sha256=policy["freeze_sha256"],
        verified_tenant_id=verifier.TID,
        verified_owner_oid=verifier.OWNER_OID,
        verified_principal=verifier.EXACT_OWNER_OAUTH_SUBJECTS[verifier.OWNER_OID],
        verified_organization_id="aot",
        confirmed_decision="approve",
        at=issued, private_key=private,
    )
    attempt = {
        "schema_version": "1.0", "action": repair.ISSUER_ACTION,
        "source": repair.ISSUER_SOURCE,
        "mcp_image": policy["mcp_image_sha256"],
        "freeze_sha256": policy["freeze_sha256"],
        "status": "exact_one_use_claimed_before_mutation",
        "approved_script_sha256": policy["script_sha256"],
        "scope_sha256": issuer_scope,
        "owner_signed_exact_action": proof,
    }
    result = {
        "schema_version": "1.0", "action": repair.ISSUER_ACTION,
        "result": "verified", "new_mcp_id": "exact-running-mcp-id",
    }
    attempt_path = root / (repair.ISSUER_ACTION + ".attempt.json")
    result_path = root / (repair.ISSUER_ACTION + ".result.json")
    def persist():
        root_policy.write_text(json.dumps(policy))
        attempt_path.write_text(json.dumps(attempt))
        result_path.write_text(json.dumps(result))
    persist()
    monkeypatch.setattr(repair, "read_secure_root",
                        lambda path,*args,**kwargs: (
                            issuer_code if path == root_module else Path(path).read_bytes()
                        ))
    monkeypatch.setattr(repair, "load_trust", lambda *args,**kwargs: verifier)
    monkeypatch.setattr(verifier, "read_pinned_root_owner_public_key",
                        lambda *args,**kwargs: private.public_key())
    return SimpleNamespace(
        policy=policy, attempt=attempt, result=result, persist=persist,
        root=root, ledger=ledger, attempt_path=attempt_path,
        result_path=result_path, expected_mcp="exact-running-mcp-id",
    )


def verify(case):
    return repair.verify_previous_issuer_activation(
        mcp_id=case.expected_mcp,
        mcp_image=case.policy["mcp_image_sha256"],
        freeze_sha256=case.policy["freeze_sha256"],
    )


def test_exact_original_signed_root_activation_is_accepted(issuer_case):
    assert verify(issuer_case) is True


@pytest.mark.parametrize("field, value", [
    ("result", "failed"),
    ("new_mcp_id", "foreign-or-restarted-mcp-id"),
    ("action", "wrong-action"),
])
def test_wrong_root_result_does_not_authorize_issuer(issuer_case, field, value):
    issuer_case.result[field] = value
    issuer_case.persist()
    with pytest.raises(repair.RepairDenied, match="ROOT_RECEIPT_CHANGED"):
        verify(issuer_case)


def test_tampered_signed_owner_activation_denied(issuer_case):
    issuer_case.attempt["owner_signed_exact_action"]["signature_base64url"] = "a" * 86
    issuer_case.persist()
    with pytest.raises(Exception):
        verify(issuer_case)


def test_changed_issuer_scope_fails(issuer_case):
    issuer_case.attempt["scope_sha256"] = "f" * 64
    issuer_case.persist()
    with pytest.raises(repair.RepairDenied, match="EXACT_SCOPE_CHANGED"):
        verify(issuer_case)


def test_changed_issuer_policy_fails(issuer_case):
    issuer_case.policy["change"] = "replace-entire-runtime"
    issuer_case.persist()
    with pytest.raises(repair.RepairDenied, match="ROOT_POLICY_CHANGED"):
        verify(issuer_case)


def test_root_ledger_foreign_file_rejected(issuer_case):
    (issuer_case.root / "unexpected.json").write_text("{}")
    with pytest.raises(repair.RepairDenied, match="FOREIGN_OR_INCOMPLETE"):
        verify(issuer_case)


def test_nonroot_ledger_metadata_rejected(issuer_case):
    issuer_case.ledger.uid = 1000
    with pytest.raises(repair.RepairDenied, match="ROOT_LEDGER_UNTRUSTED"):
        verify(issuer_case)


def test_current_mcp_id_must_match_original_verified_receipt(issuer_case):
    issuer_case.expected_mcp = "another-mcp-container"
    with pytest.raises(repair.RepairDenied, match="ROOT_RECEIPT_CHANGED"):
        verify(issuer_case)
