"""Source-only regression and failure-mode tests for exact health relocation."""
from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from tools import authority_health_live_recovery_root as root
from tools import authority_health_live_recovery_bundle as bundle
from tools import authority_health_live_recovery_owner as owner

SRC = Path(__file__).resolve().parents[1]


def test_source_allows_only_exact_health_related_targets():
    assert set(root.FILES) == {
        "openclaw_authority_live_audit_full_snapshot.py",
        "openclaw_authority_health_snapshot.py",
        "openclaw_authority_operational_health.py",
        "openclaw_authority_fast_health.py",
        "full-dropin.conf", "fast-dropin.conf",
    }
    assert all("jason-openclaw-authority" in str(p) or
               str(p).startswith(str(root.ROOT_BASE))
               for p in root.FILES.values())
    assert root.FREEZE_SHA == bundle.FREEZE_SHA
    assert root.EMERGENCY_SHA == bundle.EMERGENCY_SHA
    assert root.LKG == bundle.LKG
    assert root.FULL_EXPECTED_PATH.endswith(
        "/governed-ticket-shared/orchestration-events.sqlite3")
    assert root.ACTION == owner.ACTION == bundle.ACTION


def test_source_is_not_a_general_root_shell():
    text = (SRC / "authority_health_live_recovery_root.py").read_text()
    assert "shell=True" not in text
    assert "os.system(" not in text
    assert "subprocess.Popen(" not in text
    assert "system(\"restart\"" not in text
    assert "system(\"stop\"" not in text
    assert "system(\"disable\"" not in text
    assert "os.chown(" not in text
    assert "os.chmod(" not in text


def test_manifest_is_exact_single_action_and_scope(tmp_path, monkeypatch):
    freeze = tmp_path / "freeze"
    freeze.write_bytes(b"frozen")
    hold = tmp_path / "hold"
    hold.write_bytes(b"hold")
    monkeypatch.setattr(bundle, "FREEZE", freeze)
    monkeypatch.setattr(bundle, "HOLD", hold)
    monkeypatch.setattr(bundle, "FREEZE_SHA", bundle.digest(b"frozen"))
    blobs = {n: n.encode() for n in bundle.SOURCE_GIT}
    blobs["full-dropin.conf"] = bundle.FULL_UNIT
    blobs["fast-dropin.conf"] = bundle.FAST_UNIT
    manifest = bundle.create_manifest("a" * 40, blobs)
    assert manifest["provider_mutations"] == 0
    assert manifest["financial_scheduler_activation"] is False
    assert manifest["one_use"] is True
    assert manifest["rollback_sha"] == root.LKG
    assert manifest["full_scan_seconds"] == 5400
    unsigned = dict(manifest)
    unsigned.pop("scope_sha256")
    assert manifest["scope_sha256"] == bundle.digest(bundle.canonical(unsigned))
    manifest["provider_mutations"] = 1
    unsigned = dict(manifest)
    unsigned.pop("scope_sha256")
    assert manifest["scope_sha256"] != bundle.digest(bundle.canonical(unsigned))


def test_root_uses_open_breaker_and_refuses_unrelated_incident():
    source = (SRC / "authority_health_live_recovery_root.py").read_text()
    assert "PROTECTED_BREAKER_UNRELATED" in source
    assert "failed_system_unit" in source
    assert "jason-openclaw-authority-health.service" in source
    assert "NOT_REVIEWED_OLD_PATH_INCIDENT" in source
    assert "EMERGENCY_OVERLAY_DRIFT" in source
    assert "PROTECTED_CONTAINER_CHANGED:" in source


def test_fresh_full_evidence_checks_path_integrity_and_actual_backup(tmp_path, monkeypatch):
    full = tmp_path / "full.json"
    report = {
        "status": "pass", "failures": [],
        "snapshot_source_exit_code": 0, "provider_contacted": False,
        "provider_credentials_used": False,
        "files": {name: {"integrity": "ok", "mode": "0o600",
                         "present": True,
                         "path": root.FULL_EXPECTED_PATH if name ==
                         "orchestration_audit" else "/synthetic/" + name}
                  for name in ("authority", "replay", "security_audit",
                               "orchestration_audit")},
        "backup_restore_proof": {
            "backup_integrity": "ok", "restore_integrity": "ok",
            "counts_match": True, "backup_mode": "0o600",
            "restore_mode": "0o600",
        },
    }
    full.write_text(json.dumps(report))
    full.chmod(0o600)
    monkeypatch.setattr(root, "FULL", full)
    monkeypatch.setattr(root, "verify_full_since", root.verify_full_since)
    root.verify_full_since(full.stat().st_mtime - 1)
    report["files"]["orchestration_audit"]["path"] = "/legacy/stale/audit"
    full.write_text(json.dumps(report))
    with pytest.raises(root.Denied, match="LIVE_FULL_INTEGRITY_NOT_PASS"):
        root.verify_full_since(full.stat().st_mtime - 1)
    report["files"]["orchestration_audit"]["path"] = root.FULL_EXPECTED_PATH
    report["backup_restore_proof"]["backup_integrity"] = "unknown"
    full.write_text(json.dumps(report))
    with pytest.raises(root.Denied, match="FULL_BACKUP_RESTORE_NOT_PASS"):
        root.verify_full_since(full.stat().st_mtime - 1)


def test_fast_health_refuses_stale_pass(tmp_path, monkeypatch):
    p = tmp_path / "fast.json"
    p.write_text('{"status":"pass","failures":[]}')
    p.chmod(0o600)
    monkeypatch.setattr(root, "FAST", p)
    with pytest.raises(root.Denied, match="FRESH_FAST_EVIDENCE_NOT_PRESENT"):
        root.verify_fast_since(time.time() + 5)
    root.verify_fast_since(p.stat().st_mtime - 5)
    p.write_text('{"status":"fail","failures":["stale"]}')
    with pytest.raises(root.Denied, match="FRESH_FAST_HEALTH_NOT_PASS"):
        root.verify_fast_since(p.stat().st_mtime - 1)


def test_oneuse_ledger_claim_precedes_release_actions():
    source = (SRC / "authority_health_live_recovery_root.py").read_text()
    assert source.index("verify_owner(directory, manifest)") < source.index(
        'root_record(LEDGER / "attempt.json", outcome)')
    assert source.index('root_record(LEDGER / "attempt.json", outcome)') < source.index(
        "root_install(blobs, installed)")
    assert source.index("verify_full_since(started)") < source.index(
        "EMERGENCY.unlink()")
    assert source.index("verify_fast_since(started_fast)") < source.index(
        "        native_revalidate()")
    assert source.index("native_unlock(lockfd)\n        lockfd = None") < source.index(
        'system("start", "jason-openclaw-authority-full-integrity.service"')


def test_owner_signer_separate_and_no_root_sudo():
    source = (SRC / "authority_health_live_recovery_owner.py").read_text()
    assert "root_install(" not in source
    assert "systemctl" not in source
    assert "sudo" not in source
    assert "issue_exact_owner_release(" in source
    assert "jwt_owner(" in source
    assert "private_key=private" in source
    assert "O_EXCL" in source


def test_unprivileged_execute_denied(monkeypatch, tmp_path):
    monkeypatch.setattr(root.os, "geteuid", lambda: 1000)
    with pytest.raises(root.Denied, match="ISOLATED_TRUSTED_ROOT_REQUIRED"):
        root.execute(tmp_path)


def test_native_release_lock_rejects_untrusted_mode(tmp_path, monkeypatch):
    p = tmp_path / "lock"
    p.write_bytes(b"")
    p.chmod(0o666)
    monkeypatch.setattr(root, "NATIVE_LOCK", p)
    with pytest.raises(root.Denied, match="RELEASE_LOCK_UNTRUSTED"):
        root.native_lock()


def test_root_install_only_declared_files_and_readback(tmp_path, monkeypatch):
    rootdir = tmp_path / "root-code"
    files = {
        "openclaw_authority_health_snapshot.py": rootdir / "snap.py",
        "fast-dropin.conf": tmp_path / "fast.conf",
    }
    monkeypatch.setattr(root, "ROOT_BASE", rootdir)
    monkeypatch.setattr(root, "FILES", files)
    installed = []
    root.root_install({
        "openclaw_authority_health_snapshot.py": b"source-only\n",
        "fast-dropin.conf": b"[Service]\n",
    }, installed)
    assert installed == list(files.values())
    assert all(p.is_file() for p in installed)
    assert installed[0].stat().st_mode & 0o777 == 0o444
    assert installed[1].stat().st_mode & 0o777 == 0o644
    with pytest.raises(root.Denied, match="INSTALL_OBJECT_PREEXISTS"):
        root.root_install({}, [])
    assert all(p.read_bytes() for p in installed)


def test_no_breaker_release_without_real_complete_proof():
    script = (SRC / "authority_health_live_recovery_root.py").read_text()
    assert "native_revalidate()" in script
    assert 'drift.get("status") == "pass"' in script
    assert 'drift.get("problems") == []' in script
    assert 'outcome["native_breaker_closed"] = True' in script


def test_bundle_inputs_are_read_from_git_sha_not_mutable_workspace():
    source = (SRC / "authority_health_live_recovery_bundle.py").read_text()
    assert '["git", "-C", str(repo), "show"' in source
    assert "source + \":\" + ref" in source
    assert "mode=0o700" in source
    assert '"files_sha256"' in source


def test_root_does_not_implicitly_start_financial_or_mcp():
    source = (SRC / "authority_health_live_recovery_root.py").read_text()
    assert "jason-financial-statements" not in source
    assert "docker run" not in source
    assert "docker restart" not in source
    assert "systemctl stop" not in source
    assert "systemctl restart" not in source


def test_disposable_root_transaction_orders_signed_claim_before_full_proof(
        tmp_path, monkeypatch):
    """No real root privilege, provider, systemd, production paths or containers."""
    source = (SRC / "authority_health_live_recovery_root.py").read_bytes()
    packet = tmp_path / "signed-packet"
    packet.mkdir()
    emergency = tmp_path / "expired-health.conf"
    emergency.write_bytes(b"expired")
    monkeypatch.setattr(root, "EMERGENCY_SHA", root.digest(b"expired"))
    ledger = tmp_path / "root-audit"
    drift = tmp_path / "drift.json"
    drift.write_text('{"status":"pass","problems":[]}')
    manifest = {"root_script_sha256": root.digest(source),
                "source_sha": "a" * 40, "scope_sha256": "b" * 64,
                "freeze_sha256": root.FREEZE_SHA}
    events = []
    monkeypatch.setattr(root.os, "geteuid", lambda: 0)
    monkeypatch.setattr(root, "sys", SimpleNamespace(flags=SimpleNamespace(isolated=1)))
    monkeypatch.setattr(root, "read_manifest", lambda directory:
        (manifest, {root.ROOT_RUNNER_FILE: source}))
    monkeypatch.setattr(root, "LEDGER", ledger)
    monkeypatch.setattr(root, "EMERGENCY", emergency)
    monkeypatch.setattr(root, "DRIFT", drift)
    monkeypatch.setattr(root, "live_gate", lambda m: {"jason-runtime": "unchanged"})
    monkeypatch.setattr(root, "verify_owner", lambda d, m: "owner-mcp-" + "c" * 32)
    monkeypatch.setattr(root, "native_lock", lambda: events.append("lock") or 42)
    monkeypatch.setattr(root, "native_unlock", lambda fd: events.append("unlock"))
    monkeypatch.setattr(root, "root_install", lambda b, files:
                        events.append("install"))
    monkeypatch.setattr(root, "protected_unchanged",
                        lambda before: events.append("protected_unchanged"))
    monkeypatch.setattr(root, "system", lambda *args, **kwargs:
                        events.append("system:" + ":".join(args)) or "")
    monkeypatch.setattr(root, "verify_full_since",
                        lambda started: events.append("full:verified"))
    monkeypatch.setattr(root, "verify_fast_since",
                        lambda started: events.append("fast:verified"))
    monkeypatch.setattr(root, "native_revalidate",
                        lambda: events.append("breaker:verified"))
    monkeypatch.setattr(root.time, "sleep", lambda seconds: None)
    root.execute(packet)
    assert (ledger / "attempt.json").exists()
    result = json.loads((ledger / "result.json").read_text())
    assert result["status"] == "verified"
    assert result["full_integrity_pass"] is True
    assert result["native_breaker_closed"] is True
    assert not emergency.exists()
    assert events.index("install") < events.index("unlock")
    assert events.index("unlock") < events.index(
        "system:start:jason-openclaw-authority-full-integrity.service")
    assert events.index("full:verified") < events.index("fast:verified")
    assert events.index("fast:verified") < events.index("breaker:verified")


def test_disposable_root_timeout_fails_closed_and_rolls_back(
        tmp_path, monkeypatch):
    source = (SRC / "authority_health_live_recovery_root.py").read_bytes()
    packet = tmp_path / "packet"
    packet.mkdir()
    expired = tmp_path / "expired"
    expired.write_bytes(b"same")
    ledger = tmp_path / "audit"
    released = []
    removed = []
    monkeypatch.setattr(root.os, "geteuid", lambda: 0)
    monkeypatch.setattr(root, "sys", SimpleNamespace(flags=SimpleNamespace(isolated=1)))
    monkeypatch.setattr(root, "read_manifest", lambda d:
        ({"root_script_sha256": root.digest(source),
          "source_sha": "a" * 40, "scope_sha256": "b" * 64,
          "freeze_sha256": root.FREEZE_SHA},
         {root.ROOT_RUNNER_FILE: source}))
    monkeypatch.setattr(root, "LEDGER", ledger)
    monkeypatch.setattr(root, "EMERGENCY", expired)
    monkeypatch.setattr(root, "live_gate", lambda m: {})
    monkeypatch.setattr(root, "verify_owner", lambda d, m:
                        "owner-mcp-" + "c" * 32)
    monkeypatch.setattr(root, "native_lock", lambda: 5)
    monkeypatch.setattr(root, "native_unlock", lambda fd: released.append(fd))
    monkeypatch.setattr(root, "root_install", lambda b, files: files.append(tmp_path / "installed"))
    monkeypatch.setattr(root, "protected_unchanged", lambda b: None)
    monkeypatch.setattr(root, "system", lambda *a, **k: "")
    monkeypatch.setattr(root, "verify_full_since",
                        lambda now: (_ for _ in ()).throw(root.Denied("REAL_FULL_TIMEOUT")))
    monkeypatch.setattr(root, "rollback", lambda files, **k:
                        removed.extend(files))
    monkeypatch.setattr(root, "native_revalidate",
                        lambda: pytest.fail("must not revalidate breaker"))
    with pytest.raises(root.Denied, match="REAL_FULL_TIMEOUT"):
        root.execute(packet)
    result = json.loads((ledger / "result.json").read_text())
    assert result["status"] == "failed"
    assert result["native_breaker_closed"] is False
    assert result["full_integrity_pass"] is False
    assert removed and released == [5]
    assert expired.exists()


def test_root_verifies_actual_ephemeral_owner_signature_and_exact_scope(
        tmp_path, monkeypatch):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    import importlib.util
    pinned = Path("/usr/local/lib/jason/owner_signed_release.py")
    spec = importlib.util.spec_from_file_location("test_pinned_owner_signature", pinned)
    signer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(signer)
    key = Ed25519PrivateKey.generate()
    sha = "a" * 40
    manifest = {
        "source_sha": sha, "rollback_sha": root.LKG,
        "scope_sha256": "b" * 64, "freeze_sha256": root.FREEZE_SHA,
    }
    at = datetime.now(timezone.utc)
    oid, principal = sorted(signer.EXACT_OWNER_OAUTH_SUBJECTS.items())[0]
    signature = signer.issue_exact_owner_release(
        approval_id="owner-mcp-" + "f" * 32,
        release_id="release-" + sha[:16], candidate_sha=sha,
        rollback_sha=root.LKG, scope_sha256=manifest["scope_sha256"],
        manifest_sha256=root.digest(root.canonical(manifest)),
        freeze_sha256=root.FREEZE_SHA,
        verified_tenant_id=signer.TID, verified_owner_oid=oid,
        verified_principal=principal, verified_organization_id="aot",
        confirmed_decision="approve", at=at, private_key=key)
    signed = {
        "schema_version": "1.0", "action": root.ACTION,
        "manifest_sha256": root.digest(root.canonical(manifest)),
        "signed_owner_proof": signature,
    }
    packet = tmp_path / "signed"
    packet.mkdir()
    proof_file = packet / "owner-proof.json"
    proof_file.write_text(json.dumps(signed))
    proof_file.chmod(0o400)
    original = signer.read_pinned_root_owner_public_key
    monkeypatch.setattr(signer, "read_pinned_root_owner_public_key",
                        lambda *a, **k: key.public_key())
    monkeypatch.setattr(root, "read_pinned_owner_module", lambda: signer)
    assert root.verify_owner(packet, manifest) == "owner-mcp-" + "f" * 32
    tampered = dict(manifest)
    tampered["scope_sha256"] = "c" * 64
    with pytest.raises(signer.OwnerReleaseProofDenied,
                       match="OWNER_RELEASE_TRANSACTION_BINDING_MISMATCH"):
        signed["manifest_sha256"] = root.digest(root.canonical(tampered))
        proof_file.chmod(0o600)
        proof_file.write_text(json.dumps(signed))
        proof_file.chmod(0o400)
        root.verify_owner(packet, tampered)
