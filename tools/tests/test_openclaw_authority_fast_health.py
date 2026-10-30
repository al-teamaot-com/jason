from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sqlite3
import stat
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import openclaw_authority_fast_health as fast


@pytest.fixture
def seeded(tmp_path: Path):
    databases = {}
    for name in ("authority", "replay", "security_audit", "orchestration_audit"):
        path = tmp_path / (name + ".sqlite3")
        with sqlite3.connect(path) as connection:
            connection.execute("CREATE TABLE marker(value TEXT)")
        os.chmod(path, 0o600)
        databases[name] = path
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps({"keys": [{"status": "active"}]}), encoding="utf-8")
    os.chmod(registry, 0o600)
    full = tmp_path / "full-health.json"
    report = {
        "status": "pass",
        "snapshot_source_exit_code": 0,
        "files": {
            name: {"path": str(path), "present": True, "mode": "0o600", "integrity": "ok"}
            for name, path in databases.items()
        },
        "authority_counts": {"identities": 1},
        "delegations": {"active": 0, "expired_active_records": 0, "inactive": 0},
        "trusted_key_registry": {"present": True, "active_records": 1, "mode": "0o600"},
        "backup_restore_proof": {
            "backup_integrity": "ok", "restore_integrity": "ok",
            "backup_mode": "0o600", "restore_mode": "0o600", "counts_match": True,
        },
        "provider_contacted": False,
        "provider_credentials_used": False,
    }
    full.write_text(json.dumps(report), encoding="utf-8")
    os.chmod(full, 0o600)
    return databases, registry, full, report, tmp_path / "fast-health.json"


def probe(seeded):
    db, registry, full, _, output = seeded
    return fast.check(output=output, full_path=full, databases=db, registry_path=registry)


def test_recent_full_proof_and_read_only_databases_pass(seeded):
    report = probe(seeded)
    assert report["status"] == "pass"
    assert report["check_mode"] == "frequent_read_only_plus_recent_full_integrity"
    assert report["full_proof_status"] == "pass"
    assert report["backup_restore_proof"]["counts_match"] is True
    assert report["provider_contacted"] is False
    assert all(v["integrity"] == "not_run_in_frequent_check" for v in report["files"].values())


def test_missing_full_evidence_fails_closed(seeded):
    *_, full, old, output = seeded
    full.unlink()
    result = probe(seeded)
    assert result["status"] == "fail"
    assert "full_integrity_proof_missing_stale_or_invalid" in result["failures"]


def test_stale_full_evidence_cannot_be_rejuvenated(seeded):
    _, _, full, _, output = seeded
    stale = datetime.now(timezone.utc) - timedelta(hours=31)
    os.utime(full, (stale.timestamp(), stale.timestamp()))
    result = probe(seeded)
    assert result["status"] == "fail"


@pytest.mark.parametrize("alter", ["status", "backup", "integrity", "provider", "source_exit", "path"])
def test_full_proof_validates_actual_integrity_and_source(seeded, alter):
    db, _, full, payload, _ = seeded
    if alter == "status":
        payload["status"] = "fail"
    elif alter == "backup":
        payload["backup_restore_proof"]["counts_match"] = False
    elif alter == "integrity":
        payload["files"]["authority"]["integrity"] = "not_checked"
    elif alter == "provider":
        payload["provider_contacted"] = True
    elif alter == "source_exit":
        payload["snapshot_source_exit_code"] = 124
    elif alter == "path":
        payload["files"]["authority"]["path"] = str(full)
    full.write_text(json.dumps(payload), encoding="utf-8")
    assert probe(seeded)["status"] == "fail"


def test_world_readable_full_proof_rejected(seeded):
    _, _, full, _, _ = seeded
    os.chmod(full, 0o644)
    assert probe(seeded)["status"] == "fail"


def test_database_unavailable_fails_even_with_full_proof(seeded):
    db, _, _, _, _ = seeded
    db["replay"].unlink()
    result = probe(seeded)
    assert result["status"] == "fail"
    assert "replay_unavailable_or_unsafe" in result["failures"]


def test_symlinked_database_rejected_even_if_target_is_readable(seeded):
    db, _, _, _, _ = seeded
    replacement = db["replay"].with_name("replacement.sqlite3")
    db["replay"].rename(replacement)
    db["replay"].symlink_to(replacement)
    result = probe(seeded)
    assert result["status"] == "fail"
    assert "replay_unavailable_or_unsafe" in result["failures"]


def test_bad_signing_registry_fails_even_with_full_proof(seeded):
    _, registry, _, _, _ = seeded
    registry.write_text(json.dumps({"keys": []}), encoding="utf-8")
    assert probe(seeded)["status"] == "fail"


def test_legacy_full_proof_adoption_preserves_source_age(seeded):
    db, registry, full, report, output = seeded
    output.write_text(json.dumps(report), encoding="utf-8")
    os.chmod(output, 0o600)
    old = datetime.now(timezone.utc) - timedelta(hours=3)
    os.utime(output, (old.timestamp(), old.timestamp()))
    full.unlink()
    result = fast.check(output=output, full_path=full, databases=db, registry_path=registry)
    assert result["status"] == "pass"
    assert full.is_file()
    assert stat.S_IMODE(full.stat().st_mode) == 0o600
    assert abs(full.stat().st_mtime - old.timestamp()) < 2
    assert 2 * 3600 < result["full_proof_age_seconds"] < 4 * 3600


def test_legacy_failed_proof_never_adopted(seeded):
    db, registry, full, report, output = seeded
    report["status"] = "fail"
    output.write_text(json.dumps(report), encoding="utf-8")
    os.chmod(output, 0o600)
    full.unlink()
    result = fast.check(output=output, full_path=full, databases=db, registry_path=registry)
    assert result["status"] == "fail"
    assert not full.exists()


def test_legacy_stale_full_proof_is_not_adopted_or_refreshed(seeded):
    db, registry, full, report, output = seeded
    output.write_text(json.dumps(report), encoding="utf-8")
    os.chmod(output, 0o600)
    stale = datetime.now(timezone.utc) - timedelta(hours=31)
    os.utime(output, (stale.timestamp(), stale.timestamp()))
    full.unlink()
    result = fast.check(output=output, full_path=full, databases=db, registry_path=registry)
    assert result["status"] == "fail"
    assert not full.exists()


def test_read_only_probes_do_not_write_schema(seeded, monkeypatch):
    db, registry, full, _, output = seeded
    real_connect = sqlite3.connect
    seen = []

    def inspect_connection(database, *args, **kwargs):
        seen.append((database, kwargs))
        assert str(database).endswith("?mode=ro")
        assert kwargs.get("uri") is True
        return real_connect(database, *args, **kwargs)

    monkeypatch.setattr(fast.sqlite3, "connect", inspect_connection)
    assert fast.check(output=output, full_path=full, databases=db, registry_path=registry)["status"] == "pass"
    assert len(seen) == 5  # Four probes and read-only delegations lookup
