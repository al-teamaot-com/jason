"""Signed historical release proof and inert root-installer regression tests.

Only simulated data, generated temporary Ed25519 keys, and private temp files.
No root operations, OpenBao secrets, or provider network traffic.
"""
from __future__ import annotations

import hashlib
import json
import os
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from kernel import signed_owner_release as owner
from tools import it_glue_approle_recovery as recovery
from tools import install_it_glue_approle_recovery as installer


def _make_signed_release(tmp_path, monkeypatch):
    candidate = "c" * 40
    rollback = "d" * 40
    approval_id = "owner-mcp-" + "e" * 32
    release_id = "release-" + candidate[:16]
    freeze = tmp_path / "freeze"
    freeze.write_bytes(b"locked-frozen-test")
    manifest = {"candidate_sha": candidate, "rollback_sha": rollback}
    manifest_digest = hashlib.sha256(json.dumps(
        manifest, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False).encode()).hexdigest()
    now = datetime(2026, 11, 12, 14, 0, tzinfo=timezone.utc)
    signing_key = Ed25519PrivateKey.generate()
    signed = owner.issue_exact_owner_release(
        approval_id=approval_id, release_id=release_id, candidate_sha=candidate,
        rollback_sha=rollback, scope_sha256="a" * 64,
        manifest_sha256=manifest_digest,
        freeze_sha256=hashlib.sha256(freeze.read_bytes()).hexdigest(),
        verified_tenant_id=owner.TID,
        verified_owner_oid=owner.OWNER_OID,
        verified_principal=owner.OWNER_PRINCIPAL,
        verified_organization_id="aot", confirmed_decision="approve",
        at=now, private_key=signing_key,
    )
    processed = tmp_path / "processed"
    processed.mkdir()
    request = {
        "signed_owner_proof": signed, "release_id": release_id,
        "candidate_sha": candidate, "organization_id": "aot",
        "source": "authenticated_jason_mcp_owner:" + approval_id,
        "approved_by": owner.OWNER_PRINCIPAL,
    }
    f = processed / (release_id + ".json")
    f.write_text(json.dumps(request))
    f.chmod(0o600)
    monkeypatch.setattr(recovery, "FREEZE", freeze)
    monkeypatch.setattr(recovery, "PROCESSED", processed)
    monkeypatch.setattr(recovery, "_load_pinned_owner_verifier",
                        lambda: (owner, signing_key.public_key()))
    record = {
        "state": "closed",
        "release_candidate": {"candidate_sha": candidate},
        "rollback_sha": rollback,
        "release_manifest": manifest,
        "manual_scope_review": {
            "candidate_sha": candidate, "baseline_sha": rollback,
            "scope_sha256": "a" * 64,
        },
        "owner_approval": {
            "approved": True, "candidate_sha": candidate,
            "source": "authenticated_signed_mcp_owner:" + approval_id,
            "recorded_at": (now + timedelta(seconds=37)).isoformat(),
        },
        "changed_files": ["tools/it_glue_approle_recovery.py"],
    }
    return record, candidate, f, freeze


def test_signed_historical_owner_release_verifies_with_real_ed25519(tmp_path, monkeypatch):
    record, candidate, _, _ = _make_signed_release(tmp_path, monkeypatch)
    recovery._verify_historical_signed_release(record, candidate)


def test_changed_record_scope_rejected(tmp_path, monkeypatch):
    record, candidate, _, _ = _make_signed_release(tmp_path, monkeypatch)
    record["manual_scope_review"]["scope_sha256"] = "b" * 64
    with pytest.raises(recovery.ItGlueIdentityError, match="SIGNATURE_OR_BINDING"):
        recovery._verify_historical_signed_release(record, candidate)


def test_modified_owner_proof_signature_rejected(tmp_path, monkeypatch):
    record, candidate, file, _ = _make_signed_release(tmp_path, monkeypatch)
    data = json.loads(file.read_text())
    signature = data["signed_owner_proof"]["signature_base64url"]
    data["signed_owner_proof"]["signature_base64url"] = (
        ("A" if signature[0] != "A" else "B") + signature[1:]
    )
    file.write_text(json.dumps(data))
    file.chmod(0o600)
    with pytest.raises(recovery.ItGlueIdentityError, match="SIGNATURE_OR_BINDING"):
        recovery._verify_historical_signed_release(record, candidate)


def test_release_approval_after_expiry_rejected(tmp_path, monkeypatch):
    record, candidate, _, _ = _make_signed_release(tmp_path, monkeypatch)
    record["owner_approval"]["recorded_at"] = (
        datetime(2026, 11, 12, 14, 20, tzinfo=timezone.utc).isoformat()
    )
    with pytest.raises(recovery.ItGlueIdentityError, match="SIGNATURE_OR_BINDING"):
        recovery._verify_historical_signed_release(record, candidate)


def test_freeze_drift_rejected(tmp_path, monkeypatch):
    record, candidate, _, freeze = _make_signed_release(tmp_path, monkeypatch)
    freeze.write_bytes(b"unexpected-unfreeze")
    with pytest.raises(recovery.ItGlueIdentityError, match="SIGNATURE_OR_BINDING"):
        recovery._verify_historical_signed_release(record, candidate)


def test_missing_release_helper_file_rejected(tmp_path, monkeypatch):
    record, candidate, _, _ = _make_signed_release(tmp_path, monkeypatch)
    record["changed_files"].clear()
    with pytest.raises(recovery.ItGlueIdentityError, match="NOT_PROVEN"):
        recovery._verify_historical_signed_release(record, candidate)


def test_root_install_denied_under_regular_technician(monkeypatch):
    monkeypatch.setattr(installer.os, "geteuid", lambda: 1000)
    with pytest.raises(installer.InstallDenied, match="ROOT_ONLY"):
        installer._trusted_source("f" * 40)


def test_root_install_denies_non_exact_revision(monkeypatch):
    monkeypatch.setattr(installer.os, "geteuid", lambda: 0)
    with pytest.raises(installer.InstallDenied, match="EXACT_SOURCE"):
        installer._trusted_source("../current")


def test_source_only_root_file_copy_is_atomic_and_permission_bounded(tmp_path):
    src = tmp_path / "source.py"
    src.write_text("print('inert')\n")
    folder = tmp_path / "destination"
    folder.mkdir()
    folder.chmod(0o700)
    dst = folder / "source.py"
    digest = installer._atomic_install(
        src, dst, root_uid=os.geteuid(), root_gid=os.getegid())
    assert digest == hashlib.sha256(src.read_bytes()).hexdigest()
    assert dst.read_bytes() == src.read_bytes()
    assert stat.S_IMODE(dst.stat().st_mode) == 0o500
    assert not any(p.name.startswith(".itglue-root-") for p in folder.iterdir())


def test_root_file_install_refuses_symlink_destination(tmp_path):
    src = tmp_path / "source"
    src.write_text("read-only-helper")
    folder = tmp_path / "destination"
    folder.mkdir()
    folder.chmod(0o700)
    actual = folder / "unrelated"
    actual.write_text("must remain unchanged")
    linked = folder / "source.py"
    linked.symlink_to(actual)
    with pytest.raises(installer.InstallDenied, match="ROOT_LIBRARY_FILE_UNSAFE"):
        installer._atomic_install(
            src, linked, root_uid=os.geteuid(), root_gid=os.getegid())
    assert actual.read_text() == "must remain unchanged"


def test_native_host_reconciliation_has_install_only_exact_source():
    root = Path(__file__).resolve().parents[2]
    host = (root / "tools/reconcile_production_host_services.sh").read_text()
    assert 'step_start itglue_read_owner_helper_install' in host
    assert 'if [ -f "$RELEASE_DIR/tools/install_it_glue_approle_recovery.py" ]; then' in host
    assert '--source-revision "$SOURCE_REVISION"' in host
    assert 'installed IT Glue helper differs from reviewed release' in host
    section = host.split("step_start itglue_read_owner_helper_install", 1)[1].split(
        "step_pass itglue_read_owner_helper_install", 1)[0]
    assert "docker restart" not in section
    assert "systemctl restart" not in section
    assert "disable" not in section
    assert "secret-id" not in section
