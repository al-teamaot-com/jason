from __future__ import annotations

import importlib.util
import json
import subprocess
import stat
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "openclaw_authority_health_snapshot.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("openclaw_authority_health_snapshot", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_snapshot_uses_bounded_timeout_for_full_integrity_checks(monkeypatch, tmp_path):
    module = _load_module()
    monkeypatch.setattr(module, "BACKUP_TEMP_ROOT", tmp_path)
    observed = {}

    class Completed:
        stdout = json.dumps({"status": "pass"})
        returncode = 0

    def fake_run(*args, **kwargs):
        observed["timeout"] = kwargs.get("timeout")
        return Completed()

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    monkeypatch.setattr(module.sys, "argv", [str(SCRIPT), "--output", str(tmp_path / "health.json")])

    assert module.main() == 0
    assert observed["timeout"] == 5400
    assert json.loads((tmp_path / "health.json").read_text())["status"] == "pass"


def test_timeout_records_explicit_failure_and_replaces_stale_pass(monkeypatch, tmp_path):
    module = _load_module()
    monkeypatch.setattr(module, "BACKUP_TEMP_ROOT", tmp_path)
    output = tmp_path / "health.json"
    output.write_text(json.dumps({"status": "pass", "stale": True}), encoding="utf-8")

    def expire(*args, **kwargs):
        assert kwargs["timeout"] == module.SOURCE_HEALTH_TIMEOUT_SECONDS
        assert args[0][1].endswith("openclaw_authority_operational_health.py")
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=kwargs["timeout"])

    monkeypatch.setattr(module.subprocess, "run", expire)
    monkeypatch.setattr(module.sys, "argv", [str(SCRIPT), "--output", str(output)])

    assert module.main() == 124
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["status"] == "fail"
    assert result["failures"] == ["operational_health_timeout"]
    assert result["snapshot_timeout_seconds"] == 5400
    assert result["snapshot_source_exit_code"] == 124
    assert "stale" not in result
    assert stat.S_IMODE(output.stat().st_mode) == 0o600


def test_systemd_timeout_exceeds_checker_deadline():
    source = (
        SCRIPT.parents[1]
        / "infrastructure/openclaw-operations/systemd/jason-openclaw-authority-full-integrity.service"
    ).read_text(encoding="utf-8")
    module = _load_module()
    timeouts = [
        int(line.split("=", 1)[1])
        for line in source.splitlines()
        if line.startswith("TimeoutStartSec=")
    ]
    assert len(timeouts) == 1, "Full-integrity systemd job requires one bounded timeout"
    assert 5400 <= module.SOURCE_HEALTH_TIMEOUT_SECONDS < timeouts[0] <= 6000



def test_snapshot_uses_archive_temp_root_and_systemd_allows_only_existing_archive_mount(monkeypatch, tmp_path):
    module = _load_module()
    monkeypatch.setattr(module, "BACKUP_TEMP_ROOT", tmp_path)
    observed = {}

    class Completed:
        stdout = json.dumps({"status": "pass"})
        returncode = 0

    def fake_run(args, **kwargs):
        observed["args"] = args
        return Completed()

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    monkeypatch.setattr(module.sys, "argv", [str(SCRIPT), "--output", str(tmp_path / "health.json")])
    assert module.main() == 0
    assert observed["args"][-2] == "--backup-temp-root"
    assert Path(observed["args"][-1]).parent == tmp_path
    assert Path(observed["args"][-1]).name.startswith("jason-authority-integrity-run-")

    unit = (
        SCRIPT.parents[1]
        / "infrastructure/openclaw-operations/systemd/jason-openclaw-authority-full-integrity.service"
    ).read_text(encoding="utf-8")
    assert "ReadWritePaths=/var/lib/jason/openclaw /srv/jason/archive" in unit

def test_nonzero_source_exit_cannot_publish_pass(monkeypatch, tmp_path):
    module = _load_module()
    monkeypatch.setattr(module, "BACKUP_TEMP_ROOT", tmp_path)

    class Completed:
        stdout = json.dumps({"status": "pass", "failures": []})
        returncode = 2

    monkeypatch.setattr(module.subprocess, "run", lambda *args, **kwargs: Completed())
    output = tmp_path / "health.json"
    monkeypatch.setattr(module.sys, "argv", [str(SCRIPT), "--output", str(output)])
    assert module.main() == 2
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["status"] == "fail"
    assert "source_health_nonzero_exit" in result["failures"]


def test_full_sqlite_integrity_and_authority_restore_checks_remain_enabled():
    checker = SCRIPT.with_name("openclaw_authority_operational_health.py")
    source = checker.read_text(encoding="utf-8")
    assert "PRAGMA integrity_check" in source
    assert "'orchestration_audit': args.orchestration_audit" in source
    assert "backup_restore_proof(args.authority_database, args.backup_temp_root)" in source
    assert "sqlite_integrity(backup)" in source
    assert "sqlite_integrity(restored)" in source


def test_success_snapshot_archived_and_timeout_does_not_erase_pass(monkeypatch, tmp_path):
    module = _load_module()
    monkeypatch.setattr(module, "BACKUP_TEMP_ROOT", tmp_path)
    current = tmp_path / "current.json"
    saved = tmp_path / "saved.json"
    monkeypatch.setattr(module, "LAST_SUCCESS", saved)
    full = {
        "status": "pass", "failures": [],
        "provider_contacted": False, "provider_credentials_used": False,
        "files": {name: {"integrity": "ok"} for name in (
            "authority", "replay", "security_audit", "orchestration_audit")},
        "backup_restore_proof": {
            "backup_integrity": "ok", "restore_integrity": "ok",
            "counts_match": True,
        },
    }

    class Completed:
        stdout = json.dumps(full)
        returncode = 0

    monkeypatch.setattr(module.subprocess, "run", lambda *args, **kw: Completed())
    monkeypatch.setattr(module.sys, "argv", [str(SCRIPT), "--output", str(current)])
    assert module.main() == 0
    assert json.loads(saved.read_text())["status"] == "pass"
    prior = saved.read_bytes()

    def expire(*args, **kw):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=kw["timeout"])

    monkeypatch.setattr(module.subprocess, "run", expire)
    assert module.main() == 124
    assert json.loads(current.read_text())["status"] == "fail"
    assert saved.read_bytes() == prior


def test_timeout_cleans_only_own_partial_backup_and_fails_closed(monkeypatch, tmp_path):
    module = _load_module()
    staging = tmp_path / "archive"
    staging.mkdir()
    unrelated = staging / "owner-unrelated-archive.txt"
    unrelated.write_text("preserve", encoding="utf-8")
    monkeypatch.setattr(module, "BACKUP_TEMP_ROOT", staging)
    monkeypatch.setattr(module.sys, "argv", [str(SCRIPT), "--output", str(tmp_path / "health.json")])

    def timed_out(command, **kwargs):
        owned = Path(command[command.index("--backup-temp-root") + 1])
        assert owned.is_dir() and owned.parent == staging
        (owned / "incomplete-authority-restored.sqlite3").write_bytes(b"partial")
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(module.subprocess, "run", timed_out)
    assert module.main() == 124
    assert unrelated.read_text(encoding="utf-8") == "preserve"
    assert sorted(x.name for x in staging.iterdir()) == [unrelated.name]
    result = json.loads((tmp_path / "health.json").read_text())
    assert result["status"] == "fail"
    assert result["failures"] == ["operational_health_timeout"]
    assert result["snapshot_source_exit_code"] == 124


def test_success_removes_transient_backups_after_proof(monkeypatch, tmp_path):
    module = _load_module()
    staging = tmp_path / "archive"
    staging.mkdir()
    monkeypatch.setattr(module, "BACKUP_TEMP_ROOT", staging)
    monkeypatch.setattr(module.sys, "argv", [str(SCRIPT), "--output", str(tmp_path / "health.json")])

    def completed(command, **kwargs):
        owned = Path(command[command.index("--backup-temp-root") + 1])
        (owned / "complete-copy.sqlite3").write_bytes(b"synthetic")
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps({"status":"pass"}))

    monkeypatch.setattr(module.subprocess, "run", completed)
    assert module.main() == 0
    assert list(staging.iterdir()) == []
    assert json.loads((tmp_path / "health.json").read_text())["status"] == "pass"
