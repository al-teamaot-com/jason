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
    assert observed["timeout"] == 3600
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
    assert result["snapshot_timeout_seconds"] == 3600
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
    assert 3600 <= module.SOURCE_HEALTH_TIMEOUT_SECONDS < timeouts[0] <= 4200



def test_snapshot_uses_archive_temp_root_and_systemd_allows_only_existing_archive_mount(monkeypatch, tmp_path):
    module = _load_module()
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
    assert observed["args"][-2:] == ["--backup-temp-root", "/srv/jason/archive"]

    unit = (
        SCRIPT.parents[1]
        / "infrastructure/openclaw-operations/systemd/jason-openclaw-authority-full-integrity.service"
    ).read_text(encoding="utf-8")
    assert "ReadWritePaths=/var/lib/jason/openclaw /srv/jason/archive" in unit

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
    assert "backup_restore_proof(args.authority_database, args.backup_temp_root)" in source
    assert "sqlite_integrity(backup)" in source
    assert "sqlite_integrity(restored)" in source


def test_success_snapshot_archived_and_timeout_does_not_erase_pass(monkeypatch, tmp_path):
    module = _load_module()
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


def test_timeout_retains_only_whitelisted_completed_stage_timings(
        monkeypatch, tmp_path):
    import subprocess
    module = _load_module()
    output = tmp_path / 'full-health.json'

    def expired(*args, **kwargs):
        raise subprocess.TimeoutExpired(
            cmd=args[0],
            timeout=kwargs['timeout'],
            stderr=(
                b'JASON_FULL_INTEGRITY_STAGE_V1|authority|12.5\n'
                b'JASON_FULL_INTEGRITY_STAGE_V1|replay|0.02\n'
                b'JASON_FULL_INTEGRITY_STAGE_V1|authority_backup_restore|140.1\n'
                b'JASON_FULL_INTEGRITY_STAGE_V1|owner_auth|1.0\n'
                b'ACCESS_KEY=must_not_persist\n'
                b'JASON_FULL_INTEGRITY_STAGE_V1|orchestration_audit|bad\n'
            ),
        )

    monkeypatch.setattr(module.subprocess, 'run', expired)
    monkeypatch.setattr(module.sys, 'argv', [
        str(SCRIPT), '--output', str(output),
    ])
    assert module.main() == 124
    report = json.loads(output.read_text())
    assert report['status'] == 'fail'
    assert report['failures'] == ['operational_health_timeout']
    assert report['completed_stage_seconds'] == {
        'authority': 12.5,
        'replay': 0.02,
        'authority_backup_restore': 140.1,
    }
    assert 'ACCESS_KEY' not in output.read_text()
    assert stat.S_IMODE(output.stat().st_mode) == 0o600


def test_completed_timeout_stage_parser_rejects_untrusted_text():
    module = _load_module()
    assert module.completed_timeout_stages(
        'JASON_FULL_INTEGRITY_STAGE_V1|orchestration_audit|120.126\n'
        'JASON_FULL_INTEGRITY_STAGE_V1|orchestration_audit|nan\n'
        'JASON_FULL_INTEGRITY_STAGE_V1|authority|1e6\n'
        'JASON_FULL_INTEGRITY_STAGE_V1|forged|99\n'
    ) == {'orchestration_audit': 120.126}
    assert module.completed_timeout_stages(None) == {}


def test_no_source_json_overwrites_stale_pass_and_fails_closed(
        monkeypatch, tmp_path):
    module = _load_module()
    output = tmp_path / 'health.json'
    output.write_text('{"status":"pass","stale":true}')
    class Completed:
        stdout = ''
        returncode = 1
    monkeypatch.setattr(module.subprocess, 'run', lambda *a, **k: Completed())
    monkeypatch.setattr(module.sys, 'argv', [
        str(SCRIPT), '--output', str(output),
    ])
    assert module.main() == 1
    report = json.loads(output.read_text())
    assert report['status'] == 'fail'
    assert report['failures'] == ['operational_health_missing_output']
    assert 'stale' not in report


def test_malformed_source_json_never_reuses_old_pass(
        monkeypatch, tmp_path):
    module = _load_module()
    output = tmp_path / 'health.json'
    output.write_text('{"status":"pass","stale":true}')
    class Completed:
        stdout = '{"status":"pass"'
        returncode = 0
    monkeypatch.setattr(module.subprocess, 'run', lambda *a, **k: Completed())
    monkeypatch.setattr(module.sys, 'argv', [
        str(SCRIPT), '--output', str(output),
    ])
    assert module.main() == 2
    report = json.loads(output.read_text())
    assert report['status'] == 'fail'
    assert report['failures'] == ['operational_health_invalid_json']


def test_subprocess_launch_error_fails_closed_with_no_secret_text(
        monkeypatch, tmp_path):
    module = _load_module()
    output = tmp_path / 'health.json'
    def unavailable(*a, **k):
        raise OSError('sensitive unexpected provider path')
    monkeypatch.setattr(module.subprocess, 'run', unavailable)
    monkeypatch.setattr(module.sys, 'argv', [
        str(SCRIPT), '--output', str(output),
    ])
    assert module.main() == 2
    report = json.loads(output.read_text())
    assert report['status'] == 'fail'
    assert report['failures'] == ['operational_health_launch_error']
    assert 'sensitive' not in output.read_text()
