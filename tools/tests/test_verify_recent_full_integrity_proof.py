"""24-hour proof reuse is strictly bounded to prior full integrity success."""
import importlib.util
import json
import os
from pathlib import Path
from unittest.mock import patch

PATH = Path(__file__).resolve().parents[1] / "verify_recent_full_integrity_proof.py"
spec = importlib.util.spec_from_file_location("recent_full", PATH)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def valid():
    return {
        "status": "pass", "snapshot_source_exit_code": 0,
        "provider_contacted": False, "provider_credentials_used": False,
        "failures": [],
        "files": {name: {"integrity": "ok"} for name in (
            "authority", "replay", "security_audit", "orchestration_audit")},
        "backup_restore_proof": {
            "backup_integrity": "ok", "restore_integrity": "ok",
            "counts_match": True,
        },
    }


def write(path, value, timestamp=1_000_000):
    path.write_text(json.dumps(value))
    path.chmod(0o600)
    os.utime(path, (timestamp, timestamp))


def test_last_success_reused_after_new_timeout_within_24h(tmp_path):
    current, saved = tmp_path / "current.json", tmp_path / "saved.json"
    write(saved, valid())
    write(current, {"status": "fail", "failures": ["operational_health_timeout"]},
          1_000_100)
    assert m.valid_recent_proof(current, saved, 86400, os.getuid(), 1_000_200)
    assert not m.valid_recent_proof(current, saved, 86400, os.getuid(), 1_086_401)


def test_later_failed_integrity_is_not_ignored(tmp_path):
    current, saved = tmp_path / "current.json", tmp_path / "saved.json"
    write(saved, valid())
    write(current, {"status": "fail", "failures": ["orchestration_audit_integrity"]},
          1_000_100)
    assert not m.valid_recent_proof(current, saved, 86400, os.getuid(), 1_000_200)


def test_missing_backup_proof_and_wrong_metadata_are_denied(tmp_path):
    current, saved = tmp_path / "current.json", tmp_path / "saved.json"
    write(saved, valid())
    assert m.valid_recent_proof(current, saved, 86400, os.getuid(), 1_000_200)
    payload = valid()
    payload["backup_restore_proof"]["counts_match"] = False
    write(saved, payload)
    assert not m.valid_recent_proof(current, saved, 86400, os.getuid(), 1_000_200)
    write(saved, valid())
    saved.chmod(0o644)
    assert not m.valid_recent_proof(current, saved, 86400, os.getuid(), 1_000_200)
    saved.chmod(0o600)
    assert not m.valid_recent_proof(current, saved, 86400, os.getuid()+1, 1_000_200)


def test_valid_pass_after_earlier_failure_supersedes_old_failure(tmp_path):
    current, saved = tmp_path / "current.json", tmp_path / "saved.json"
    write(current, {"status": "fail", "failures": ["authority_integrity"]}, 1_000_000)
    write(saved, valid(), 1_000_100)
    assert m.valid_recent_proof(current, saved, 86400, os.getuid(), 1_000_200)
