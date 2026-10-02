from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools.kfs_postgresql_restore import (
    KfsPostgresqlRestoreError,
    restore_kfs_postgresql_backup,
)


def fixtures(tmp_path: Path):
    backup = tmp_path / "kfs.dump"
    backup.write_bytes(b"PGDMP-synthetic-backup")
    backup.chmod(0o600)
    receipt = tmp_path / "kfs.dump.receipt.json"
    receipt.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "output_path": str(backup),
                "sha256": hashlib.sha256(backup.read_bytes()).hexdigest(),
                "size_bytes": backup.stat().st_size,
                "database": "kfs_collector",
                "host": "127.0.0.1",
                "port": 5432,
                "user": "kfs_collector",
                "format": "postgresql-custom",
                "verified": True,
            }
        )
    )
    receipt.chmod(0o600)
    password = tmp_path / "pgpass"
    password.write_text(
        "127.0.0.1:5432:kfs_collector:kfs_collector:synthetic\n"
    )
    password.chmod(0o600)
    return backup, receipt, password


def test_candidate_kfs_restore_verifies_then_uses_single_transaction(tmp_path):
    backup, receipt, password = fixtures(tmp_path)
    calls = []

    def runner(command, environment):
        calls.append((tuple(command), dict(environment)))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    result = restore_kfs_postgresql_backup(
        target_root=tmp_path / "candidate",
        backup_path=backup,
        receipt_path=receipt,
        password_file=password,
        expected_host="127.0.0.1",
        expected_port=5432,
        expected_database="kfs_collector",
        expected_user="kfs_collector",
        candidate_instance_id="jason-b",
        authorize_database_restore=True,
        runner=runner,
        base_environment={"PATH": "/usr/bin"},
    )
    assert result["status"] == "restored"
    assert result["single_transaction"] is True
    assert result["password_value_exposed"] is False

    assert calls[0][0] == ("pg_restore", "--list", str(backup))
    restore = calls[1][0]
    assert restore[0] == "pg_restore"
    assert "--single-transaction" in restore
    assert "--clean" in restore
    assert "--if-exists" in restore
    assert "--exit-on-error" in restore
    assert calls[1][1]["PGPASSFILE"] == str(password)
    assert "synthetic" not in " ".join(restore)


def test_database_restore_requires_explicit_authorization(tmp_path):
    backup, receipt, password = fixtures(tmp_path)
    with pytest.raises(PermissionError, match="explicit candidate"):
        restore_kfs_postgresql_backup(
            target_root=tmp_path / "candidate",
            backup_path=backup,
            receipt_path=receipt,
            password_file=password,
            expected_host="127.0.0.1",
            expected_port=5432,
            expected_database="kfs_collector",
            expected_user="kfs_collector",
            candidate_instance_id="jason-b",
            authorize_database_restore=False,
            runner=lambda command, environment: None,
        )


def test_restore_target_must_match_backup_receipt(tmp_path):
    backup, receipt, password = fixtures(tmp_path)
    with pytest.raises(
        KfsPostgresqlRestoreError,
        match="database does not match",
    ):
        restore_kfs_postgresql_backup(
            target_root=tmp_path / "candidate",
            backup_path=backup,
            receipt_path=receipt,
            password_file=password,
            expected_host="127.0.0.1",
            expected_port=5432,
            expected_database="wrong_database",
            expected_user="kfs_collector",
            candidate_instance_id="jason-b",
            authorize_database_restore=True,
            runner=lambda command, environment: None,
        )


def test_digest_tampering_blocks_restore_before_pg_restore(tmp_path):
    backup, receipt, password = fixtures(tmp_path)
    backup.write_bytes(b"tampered")
    calls = []
    with pytest.raises(KfsPostgresqlRestoreError, match="digest does not match"):
        restore_kfs_postgresql_backup(
            target_root=tmp_path / "candidate",
            backup_path=backup,
            receipt_path=receipt,
            password_file=password,
            expected_host="127.0.0.1",
            expected_port=5432,
            expected_database="kfs_collector",
            expected_user="kfs_collector",
            candidate_instance_id="jason-b",
            authorize_database_restore=True,
            runner=lambda command, environment: calls.append(command),
        )
    assert calls == []


def test_live_root_is_refused(tmp_path):
    backup, receipt, password = fixtures(tmp_path)
    with pytest.raises(PermissionError, match="live filesystem root"):
        restore_kfs_postgresql_backup(
            target_root="/",
            backup_path=backup,
            receipt_path=receipt,
            password_file=password,
            expected_host="127.0.0.1",
            expected_port=5432,
            expected_database="kfs_collector",
            expected_user="kfs_collector",
            candidate_instance_id="jason-b",
            authorize_database_restore=True,
            runner=lambda command, environment: None,
        )
