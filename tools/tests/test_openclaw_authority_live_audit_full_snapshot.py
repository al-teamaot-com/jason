"""Non-production tests for scoped, root-install-gated full-health snapshot."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "openclaw_authority_live_audit_full_snapshot.py"


def load():
    spec = importlib.util.spec_from_file_location("test_live_full_wrapper", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def approved_proof(module):
    return {
        "status": "pass", "failures": [],
        "provider_contacted": False, "provider_credentials_used": False,
        "files": {name: {
            "path": str(module.AUDIT) if name == "orchestration_audit"
                    else "/synthetic/" + name + ".sqlite3",
            "integrity": "ok", "mode": "0o600", "present": True,
        } for name in module.FULL_NAMES},
        "backup_restore_proof": {
            "backup_integrity": "ok", "restore_integrity": "ok",
            "backup_mode": "0o600", "restore_mode": "0o600",
            "counts_match": True,
        },
        "trusted_key_registry": {
            "present": True, "mode": "0o600", "active_records": 1,
        },
        "delegations": {"expired_active_records": 0},
    }


def sandbox(monkeypatch, tmp_path):
    module = load()
    audit = tmp_path / "real-audit.sqlite3"
    audit.write_bytes(b"synthetic")
    audit.chmod(0o600)
    monkeypatch.setattr(module, "AUDIT", audit)
    archive = tmp_path / "archive"
    archive.mkdir()
    return module, audit, archive, tmp_path / "full.json"


def test_production_cli_rejects_uninstalled_worktree(monkeypatch):
    module = load()
    monkeypatch.setattr(module.sys, "argv", [str(SCRIPT)])
    with pytest.raises(SystemExit, match="GOVERNED_ROOT_INSTALL"):
        module.main()


def test_synthetic_full_pass_with_exact_audit_path_and_cleanup(monkeypatch, tmp_path):
    module, audit, archive, output = sandbox(monkeypatch, tmp_path)
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        assert kwargs["timeout"] == 5400
        assert command[-2:] == ["--orchestration-audit", str(audit)]
        assert Path(command[command.index("--backup-temp-root")+1]).parent == archive
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps(approved_proof(module)))

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    assert module.full_snapshot(output=output, archive=archive) == 0
    proof = json.loads(output.read_text())
    assert proof["status"] == "pass"
    assert proof["snapshot_source_exit_code"] == 0
    assert proof["files"]["orchestration_audit"]["path"] == str(audit)
    assert not list(archive.iterdir())
    assert output.stat().st_mode & 0o777 == 0o600


def test_stale_pass_is_replaced_with_failure_on_timeout(monkeypatch, tmp_path):
    module, audit, archive, output = sandbox(monkeypatch, tmp_path)
    output.write_text('{"status":"pass","stale":true}')
    def timeout(command, **kwargs):
        scratch = Path(command[command.index("--backup-temp-root")+1])
        (scratch / "partial.sqlite3").write_bytes(b"partial")
        raise subprocess.TimeoutExpired(command, 5400)
    monkeypatch.setattr(module.subprocess, "run", timeout)
    assert module.full_snapshot(output=output, archive=archive) == 124
    proof = json.loads(output.read_text())
    assert proof["status"] == "fail"
    assert proof["failures"] == ["operational_health_timeout"]
    assert proof["snapshot_source_exit_code"] == 124
    assert "stale" not in proof
    assert list(archive.iterdir()) == []


@pytest.mark.parametrize("change", [
    lambda v: v.update({"status":"pass","failures":[],"provider_contacted":True}),
    lambda v: v.update({"status":"pass","failures":[],"provider_credentials_used":True}),
    lambda v: v["files"]["orchestration_audit"].update({"path":"/wrong/audit.sqlite3"}),
    lambda v: v["files"]["orchestration_audit"].update({"integrity":"unknown"}),
    lambda v: v["files"]["orchestration_audit"].update({"mode":"0o666"}),
    lambda v: v["backup_restore_proof"].update({"counts_match":False}),
    lambda v: v["trusted_key_registry"].update({"active_records":0}),
    lambda v: v["delegations"].update({"expired_active_records":1}),
])
def test_untrusted_claims_never_publish_pass(monkeypatch, tmp_path, change):
    module, audit, archive, output = sandbox(monkeypatch, tmp_path)
    evidence = approved_proof(module)
    change(evidence)
    monkeypatch.setattr(
        module.subprocess, "run",
        lambda command, **kwargs:
            subprocess.CompletedProcess(command, 0, stdout=json.dumps(evidence)),
    )
    assert module.full_snapshot(output=output, archive=archive) == 2
    assert json.loads(output.read_text())["status"] == "fail"


def test_missing_or_symlink_audit_denied_without_launch(monkeypatch, tmp_path):
    module, audit, archive, output = sandbox(monkeypatch, tmp_path)
    launched = []
    monkeypatch.setattr(module.subprocess, "run", lambda *a, **k: launched.append(a))
    audit.unlink()
    assert module.full_snapshot(output=output, archive=archive) == 2
    assert not launched
    audit.symlink_to(tmp_path / "not-here")
    assert module.full_snapshot(output=output, archive=archive) == 2
    assert not launched


def test_source_uses_no_root_install_or_breaker_mutations():
    source = SCRIPT.read_text()
    assert "systemctl" not in source
    assert "docker" not in source
    assert "production-deployment-freeze" not in source
    assert "chown" not in source
    assert "--orchestration-audit" in source
