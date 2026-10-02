from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
from typing import Callable, Mapping, Sequence

from bootstrap.candidate_host import (
    CandidateHostIdentity,
    authorize_mutation_target,
)


class KfsPostgresqlRestoreError(ValueError):
    pass


Runner = Callable[
    [Sequence[str], Mapping[str, str]],
    subprocess.CompletedProcess[str],
]


def _default_runner(
    command: Sequence[str],
    environment: Mapping[str, str],
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        text=True,
        capture_output=True,
        check=False,
        env=dict(environment),
    )


def _private_regular_file(path: Path, *, label: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise KfsPostgresqlRestoreError(f"{label} is unavailable: {path}")
    if path.stat().st_mode & 0o077:
        raise KfsPostgresqlRestoreError(
            f"{label} permissions are too broad"
        )
    return path.read_bytes()


def _validate_text(value: str, *, label: str) -> str:
    value = value.strip()
    if not value or any(character in value for character in "\r\n\x00"):
        raise KfsPostgresqlRestoreError(f"{label} is invalid")
    return value


def restore_kfs_postgresql_backup(
    *,
    target_root: str | Path,
    backup_path: str | Path,
    receipt_path: str | Path,
    password_file: str | Path,
    expected_host: str,
    expected_port: int,
    expected_database: str,
    expected_user: str,
    candidate_instance_id: str,
    authorize_database_restore: bool,
    runner: Runner = _default_runner,
    base_environment: Mapping[str, str] | None = None,
    candidate_identity: CandidateHostIdentity | None = None,
) -> dict:
    root = authorize_mutation_target(
        target_root=target_root,
        candidate_identity=candidate_identity,
        operation="KFS PostgreSQL restore",
    )
    if not candidate_instance_id.strip():
        raise KfsPostgresqlRestoreError(
            "candidate_instance_id must be explicitly supplied"
        )
    if not authorize_database_restore:
        raise PermissionError(
            "KFS PostgreSQL restore requires explicit candidate database restore authorization"
        )

    backup = Path(backup_path)
    receipt = Path(receipt_path)
    password = Path(password_file)
    backup_bytes = _private_regular_file(
        backup,
        label="KFS PostgreSQL backup artifact",
    )
    receipt_bytes = _private_regular_file(
        receipt,
        label="KFS PostgreSQL backup receipt",
    )
    _private_regular_file(
        password,
        label="KFS PostgreSQL password file",
    )

    try:
        metadata = json.loads(receipt_bytes)
    except json.JSONDecodeError as exc:
        raise KfsPostgresqlRestoreError(
            "KFS PostgreSQL backup receipt is invalid JSON"
        ) from exc

    if metadata.get("schema_version") != "1.0":
        raise KfsPostgresqlRestoreError(
            "KFS PostgreSQL backup receipt schema is unsupported"
        )
    if metadata.get("verified") is not True:
        raise KfsPostgresqlRestoreError(
            "KFS PostgreSQL backup receipt is not verified"
        )
    if metadata.get("format") != "postgresql-custom":
        raise KfsPostgresqlRestoreError(
            "KFS PostgreSQL backup format is not postgresql-custom"
        )

    observed = hashlib.sha256(backup_bytes).hexdigest()
    if metadata.get("sha256") != observed:
        raise KfsPostgresqlRestoreError(
            "KFS PostgreSQL backup digest does not match receipt"
        )
    if int(metadata.get("size_bytes") or -1) != len(backup_bytes):
        raise KfsPostgresqlRestoreError(
            "KFS PostgreSQL backup size does not match receipt"
        )

    host = _validate_text(expected_host, label="host")
    database = _validate_text(expected_database, label="database")
    user = _validate_text(expected_user, label="user")
    port = int(expected_port)
    if port < 1 or port > 65535:
        raise KfsPostgresqlRestoreError("port must be between 1 and 65535")

    for label, expected, recorded in (
        ("host", host, str(metadata.get("host") or "")),
        ("database", database, str(metadata.get("database") or "")),
        ("user", user, str(metadata.get("user") or "")),
    ):
        if expected != recorded:
            raise KfsPostgresqlRestoreError(
                f"KFS PostgreSQL restore {label} does not match backup receipt"
            )
    if port != int(metadata.get("port") or 0):
        raise KfsPostgresqlRestoreError(
            "KFS PostgreSQL restore port does not match backup receipt"
        )

    environment = dict(base_environment or os.environ)
    environment["PGPASSFILE"] = str(password)

    verify = runner(
        ("pg_restore", "--list", str(backup)),
        environment,
    )
    if verify.returncode != 0:
        raise KfsPostgresqlRestoreError(
            "pg_restore verification failed before KFS database restore"
        )

    command = (
        "pg_restore",
        "--clean",
        "--if-exists",
        "--no-owner",
        "--no-acl",
        "--exit-on-error",
        "--single-transaction",
        "--host",
        host,
        "--port",
        str(port),
        "--username",
        user,
        "--dbname",
        database,
        str(backup),
    )
    completed = runner(command, environment)
    if completed.returncode != 0:
        raise KfsPostgresqlRestoreError(
            "pg_restore failed while restoring KFS PostgreSQL"
        )

    return {
        "status": "restored",
        "candidate_instance_id": candidate_instance_id.strip(),
        "database": database,
        "host": host,
        "port": port,
        "user": user,
        "backup_sha256": observed,
        "password_value_exposed": False,
        "single_transaction": True,
    }
