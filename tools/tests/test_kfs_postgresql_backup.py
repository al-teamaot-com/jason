from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from tools.kfs_postgresql_backup import (
    KfsPostgresqlBackupError,
    create_kfs_postgresql_backup,
)


def private_password(tmp_path: Path):
    path = tmp_path / "pgpass"
    path.write_text("127.0.0.1:5432:kfs_collector:kfs_collector:synthetic\n")
    path.chmod(0o600)
    return path


def test_kfs_pg_dump_backup_uses_pgpass_and_verifies_custom_dump(tmp_path):
    target = tmp_path / "candidate"
    password = private_password(tmp_path)
    calls = []

    def runner(command, environment):
        calls.append((tuple(command), dict(environment)))
        if command[0] == "pg_dump":
            output = Path(command[command.index("--file") + 1])
            output.write_bytes(b"PGDMP-synthetic-custom-format")
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if command[0] == "pg_restore":
            return SimpleNamespace(
                returncode=0,
                stdout=";\n; Archive created at synthetic\n",
                stderr="",
            )
        raise AssertionError(command)

    result = create_kfs_postgresql_backup(
        target_root=target,
        host="127.0.0.1",
        port=5432,
        database="kfs_collector",
        user="kfs_collector",
        password_file=password,
        runner=runner,
        base_environment={"PATH": "/usr/bin"},
    )

    output = Path(result.output_path)
    assert output.read_bytes().startswith(b"PGDMP")
    assert result.verified is True
    assert result.format == "postgresql-custom"
    assert (output.stat().st_mode & 0o777) == 0o600
    assert output.with_suffix(".dump.receipt.json").is_file()

    dump_command, dump_env = calls[0]
    assert dump_command[0] == "pg_dump"
    assert "--format=custom" in dump_command
    assert "--no-owner" in dump_command
    assert "--no-acl" in dump_command
    assert dump_env["PGPASSFILE"] == str(password)
    assert "synthetic" not in " ".join(dump_command)
    assert calls[1][0][0] == "pg_restore"
    assert calls[1][0][1] == "--list"


def test_pg_dump_failure_removes_partial_artifact(tmp_path):
    password = private_password(tmp_path)
    target = tmp_path / "candidate"

    def runner(command, environment):
        if command[0] == "pg_dump":
            output = Path(command[command.index("--file") + 1])
            output.write_bytes(b"partial")
            return SimpleNamespace(returncode=1, stdout="", stderr="failure")
        raise AssertionError(command)

    with pytest.raises(KfsPostgresqlBackupError, match="pg_dump failed"):
        create_kfs_postgresql_backup(
            target_root=target,
            host="127.0.0.1",
            port=5432,
            database="kfs_collector",
            user="kfs_collector",
            password_file=password,
            runner=runner,
        )
    assert not (target / "var/lib/jason/recovery/kfs/kfs-postgresql.dump").exists()


def test_pg_restore_verification_failure_blocks_backup(tmp_path):
    password = private_password(tmp_path)
    target = tmp_path / "candidate"

    def runner(command, environment):
        if command[0] == "pg_dump":
            output = Path(command[command.index("--file") + 1])
            output.write_bytes(b"bad-dump")
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        return SimpleNamespace(returncode=1, stdout="", stderr="bad archive")

    with pytest.raises(KfsPostgresqlBackupError, match="pg_restore verification failed"):
        create_kfs_postgresql_backup(
            target_root=target,
            host="127.0.0.1",
            port=5432,
            database="kfs_collector",
            user="kfs_collector",
            password_file=password,
            runner=runner,
        )


def test_password_file_must_be_private(tmp_path):
    password = private_password(tmp_path)
    password.chmod(0o644)
    with pytest.raises(KfsPostgresqlBackupError, match="permissions are too broad"):
        create_kfs_postgresql_backup(
            target_root=tmp_path / "candidate",
            host="127.0.0.1",
            port=5432,
            database="kfs_collector",
            user="kfs_collector",
            password_file=password,
            runner=lambda command, environment: None,
        )


def test_live_root_is_refused_before_database_access(tmp_path):
    password = private_password(tmp_path)
    with pytest.raises(PermissionError, match="live filesystem root"):
        create_kfs_postgresql_backup(
            target_root="/",
            host="127.0.0.1",
            port=5432,
            database="kfs_collector",
            user="kfs_collector",
            password_file=password,
            runner=lambda command, environment: None,
        )
