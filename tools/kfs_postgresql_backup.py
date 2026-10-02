from __future__ import annotations

from dataclasses import dataclass, asdict
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Callable, Mapping, Sequence

from bootstrap.candidate_host import (
    CandidateHostIdentity,
    authorize_mutation_target,
)


class KfsPostgresqlBackupError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class KfsPostgresqlBackupResult:
    schema_version: str
    output_path: str
    sha256: str
    size_bytes: int
    database: str
    host: str
    port: int
    user: str
    format: str
    verified: bool


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


def _require_private_regular_file(path: Path, *, label: str) -> None:
    if path.is_symlink() or not path.is_file():
        raise KfsPostgresqlBackupError(f"{label} is unavailable: {path}")
    if path.stat().st_mode & 0o077:
        raise KfsPostgresqlBackupError(
            f"{label} permissions are too broad"
        )


def _validate_identifier(value: str, *, label: str) -> str:
    value = value.strip()
    if not value:
        raise KfsPostgresqlBackupError(f"{label} must be non-empty")
    if any(character in value for character in "\r\n\x00"):
        raise KfsPostgresqlBackupError(f"{label} contains invalid characters")
    return value


def _validate_port(port: int) -> int:
    value = int(port)
    if value < 1 or value > 65535:
        raise KfsPostgresqlBackupError("port must be between 1 and 65535")
    return value


def create_kfs_postgresql_backup(
    *,
    target_root: str | Path,
    host: str,
    port: int,
    database: str,
    user: str,
    password_file: str | Path,
    output_relative_path: str = "var/lib/jason/recovery/kfs/kfs-postgresql.dump",
    runner: Runner = _default_runner,
    base_environment: Mapping[str, str] | None = None,
    candidate_identity: CandidateHostIdentity | None = None,
) -> KfsPostgresqlBackupResult:
    root = authorize_mutation_target(
        target_root=target_root,
        candidate_identity=candidate_identity,
        operation="KFS PostgreSQL backup",
    )

    relative = Path(output_relative_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise KfsPostgresqlBackupError("output_relative_path must be safe and relative")

    password_path = Path(password_file)
    _require_private_regular_file(
        password_path,
        label="KFS PostgreSQL password file",
    )

    host_value = _validate_identifier(host, label="host")
    database_value = _validate_identifier(database, label="database")
    user_value = _validate_identifier(user, label="user")
    port_value = _validate_port(port)

    output = root / relative
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() or output.is_symlink():
        raise KfsPostgresqlBackupError(
            f"KFS PostgreSQL backup output already exists: {output}"
        )

    fd, temp_name = tempfile.mkstemp(
        prefix=".kfs-postgresql-",
        suffix=".dump",
        dir=output.parent,
    )
    os.close(fd)
    temporary = Path(temp_name)
    temporary.unlink(missing_ok=True)

    environment = dict(base_environment or os.environ)
    environment["PGPASSFILE"] = str(password_path)

    dump_command = (
        "pg_dump",
        "--format=custom",
        "--no-owner",
        "--no-acl",
        "--host",
        host_value,
        "--port",
        str(port_value),
        "--username",
        user_value,
        "--file",
        str(temporary),
        database_value,
    )
    completed = runner(dump_command, environment)
    if completed.returncode != 0:
        temporary.unlink(missing_ok=True)
        raise KfsPostgresqlBackupError(
            "pg_dump failed for KFS PostgreSQL backup"
        )

    if not temporary.is_file() or temporary.stat().st_size <= 0:
        temporary.unlink(missing_ok=True)
        raise KfsPostgresqlBackupError(
            "pg_dump did not produce a non-empty backup artifact"
        )

    verify = runner(
        ("pg_restore", "--list", str(temporary)),
        environment,
    )
    if verify.returncode != 0:
        temporary.unlink(missing_ok=True)
        raise KfsPostgresqlBackupError(
            "pg_restore verification failed for KFS PostgreSQL backup"
        )

    os.chmod(temporary, 0o600)
    os.replace(temporary, output)
    os.chmod(output, 0o600)

    data = output.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    result = KfsPostgresqlBackupResult(
        schema_version="1.0",
        output_path=str(output),
        sha256=digest,
        size_bytes=len(data),
        database=database_value,
        host=host_value,
        port=port_value,
        user=user_value,
        format="postgresql-custom",
        verified=True,
    )

    receipt = output.with_suffix(output.suffix + ".receipt.json")
    receipt.write_text(
        json.dumps(asdict(result), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.chmod(receipt, 0o600)
    return result
