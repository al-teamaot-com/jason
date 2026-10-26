from __future__ import annotations

import importlib.util
import json
import stat
import subprocess
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
    assert observed["timeout"] == 1800
    assert json.loads((tmp_path / "health.json").read_text())["status"] == "pass"


def test_timeout_records_explicit_failure_and_replaces_stale_pass(monkeypatch, tmp_path):
    module = _load_module()
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
    assert result["snapshot_timeout_seconds"] == 1800
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
    assert 1800 <= module.SOURCE_HEALTH_TIMEOUT_SECONDS < timeouts[0] <= 2400


def test_nonzero_source_exit_cannot_publish_pass(monkeypatch, tmp_path):
    module = _load_module()

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
    assert "backup_restore_proof(args.authority_database)" in source
    assert "sqlite_integrity(backup)" in source
    assert "sqlite_integrity(restored)" in source
