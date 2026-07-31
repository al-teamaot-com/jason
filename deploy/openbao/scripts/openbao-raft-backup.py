#!/usr/bin/env python3

import hashlib
import json
import os
import socket
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path


BASE_URL = "http://127.0.0.1:8200"

CREDENTIAL_DIR = Path(
    "/opt/jason/bootstrap/secrets/openbao/backup-approle"
)
ROLE_ID_PATH = CREDENTIAL_DIR / "role-id"
SECRET_ID_PATH = CREDENTIAL_DIR / "secret-id"
METADATA_PATH = CREDENTIAL_DIR / "credential-metadata.json"

BACKUP_DIR = Path("/opt/jason/backups/openbao")
MINIMUM_CREDENTIAL_LIFETIME = timedelta(days=7)
MINIMUM_SNAPSHOT_SIZE = 1024


class BackupError(Exception):
    pass


class BaoRequestError(BackupError):
    def __init__(self, method, url, status, detail):
        self.status = status
        super().__init__(
            f"{method} {url} failed with HTTP {status}: {detail}"
        )


def request(
    url,
    method="GET",
    token=None,
    payload=None,
    timeout=30,
):
    headers = {}

    if token:
        headers["X-Vault-Token"] = token

    data = None

    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    http_request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers=headers,
    )

    try:
        return urllib.request.urlopen(
            http_request,
            timeout=timeout,
        )

    except urllib.error.HTTPError as error:
        detail = error.read().decode(
            "utf-8",
            errors="replace",
        ).strip()

        raise BaoRequestError(
            method,
            url,
            error.code,
            detail,
        ) from error

    except urllib.error.URLError as error:
        raise BackupError(
            f"{method} {url} failed: {error.reason}"
        ) from error


def request_json(
    url,
    method="GET",
    token=None,
    payload=None,
    timeout=30,
):
    with request(
        url,
        method=method,
        token=token,
        payload=payload,
        timeout=timeout,
    ) as response:
        body = response.read()

        if not body:
            return {}

        try:
            return json.loads(body.decode("utf-8"))
        except json.JSONDecodeError as error:
            raise BackupError(
                f"{method} {url} returned invalid JSON."
            ) from error


def verify_root_only_path(path, expected_mode, kind):
    try:
        stat = path.stat()
    except FileNotFoundError as error:
        raise BackupError(
            f"Required {kind} does not exist: {path}"
        ) from error

    if stat.st_uid != 0 or stat.st_gid != 0:
        raise BackupError(
            f"{kind} is not owned by root:root: {path}"
        )

    actual_mode = stat.st_mode & 0o777

    if actual_mode != expected_mode:
        raise BackupError(
            f"{kind} permissions are "
            f"{actual_mode:03o}, expected "
            f"{expected_mode:03o}: {path}"
        )


def read_single_line(path):
    value = path.read_text(
        encoding="utf-8"
    ).strip()

    if not value:
        raise BackupError(
            f"Credential file is empty: {path}"
        )

    if "\n" in value or "\r" in value:
        raise BackupError(
            f"Credential file contains multiple lines: {path}"
        )

    return value


def parse_utc_datetime(value):
    if not isinstance(value, str) or not value:
        raise BackupError(
            "Credential expiration metadata is missing."
        )

    normalized = value

    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"

    try:
        result = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise BackupError(
            "Credential expiration metadata is invalid."
        ) from error

    if result.tzinfo is None:
        raise BackupError(
            "Credential expiration metadata lacks a timezone."
        )

    return result.astimezone(timezone.utc)


def revoke_token(token):
    try:
        request_json(
            f"{BASE_URL}/v1/auth/token/revoke-self",
            method="POST",
            token=token,
            payload={},
        )
        return True

    except Exception as error:
        print(
            "WARNING: Temporary backup token could not "
            f"be revoked explicitly: {error}",
            file=sys.stderr,
        )
        return False


def main():
    if os.geteuid() != 0:
        raise BackupError(
            "This backup script must run as root."
        )

    verify_root_only_path(
        CREDENTIAL_DIR,
        0o700,
        "credential directory",
    )

    for credential_path in (
        ROLE_ID_PATH,
        SECRET_ID_PATH,
        METADATA_PATH,
    ):
        verify_root_only_path(
            credential_path,
            0o600,
            "credential file",
        )

    metadata = json.loads(
        METADATA_PATH.read_text(encoding="utf-8")
    )

    if metadata.get("role_name") != "jason-openbao-backup":
        raise BackupError(
            "Credential metadata contains an unexpected role."
        )

    if metadata.get("policy") != "jason-openbao-backup":
        raise BackupError(
            "Credential metadata contains an unexpected policy."
        )

    expires_at = parse_utc_datetime(
        metadata.get("expires_at_utc")
    )
    now = datetime.now(timezone.utc)
    remaining_lifetime = expires_at - now

    if remaining_lifetime <= timedelta(0):
        raise BackupError(
            "The backup AppRole SecretID has expired."
        )

    if remaining_lifetime < MINIMUM_CREDENTIAL_LIFETIME:
        raise BackupError(
            "The backup AppRole SecretID expires in fewer "
            "than seven days. Rotate it before continuing."
        )

    role_id = read_single_line(ROLE_ID_PATH)
    secret_id = read_single_line(SECRET_ID_PATH)

    service_token = None
    token_revoked = False
    snapshot_path = None
    checksum_path = None
    temporary_path = None

    try:
        login_data = request_json(
            f"{BASE_URL}/v1/auth/approle/login",
            method="POST",
            payload={
                "role_id": role_id,
                "secret_id": secret_id,
            },
        )

        auth = login_data.get("auth") or {}
        service_token = auth.get("client_token")
        policies = set(auth.get("policies") or [])
        lease_duration = auth.get("lease_duration")

        if not service_token:
            raise BackupError(
                "AppRole login did not issue a service token."
            )

        if policies != {"jason-openbao-backup"}:
            raise BackupError(
                "Backup token received unexpected policies."
            )

        if lease_duration != 3600:
            raise BackupError(
                "Backup token did not receive the expected "
                "one-hour initial lifetime."
            )

        raft_data = request_json(
            f"{BASE_URL}/v1/sys/storage/raft/configuration",
            method="GET",
            token=service_token,
        )

        servers = (
            ((raft_data.get("data") or {}).get("config") or {})
            .get("servers")
            or []
        )

        leaders = [
            server
            for server in servers
            if server.get("leader") is True
        ]

        if len(leaders) != 1:
            raise BackupError(
                "Expected exactly one Raft leader; found "
                f"{len(leaders)}."
            )

        BACKUP_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )
        os.chown(BACKUP_DIR, 0, 0)
        os.chmod(BACKUP_DIR, 0o700)

        timestamp = now.strftime("%Y%m%dT%H%M%SZ")
        hostname = socket.gethostname().split(".")[0]

        snapshot_name = (
            f"openbao-raft-{hostname}-{timestamp}.snap"
        )
        snapshot_path = BACKUP_DIR / snapshot_name
        checksum_path = BACKUP_DIR / (
            snapshot_name + ".sha256"
        )

        if snapshot_path.exists() or checksum_path.exists():
            raise BackupError(
                "A backup with this timestamp already exists."
            )

        file_descriptor, temporary_name = tempfile.mkstemp(
            prefix=".openbao-raft-",
            suffix=".tmp",
            dir=str(BACKUP_DIR),
        )
        os.close(file_descriptor)
        temporary_path = Path(temporary_name)

        digest = hashlib.sha256()
        total_bytes = 0

        with request(
            f"{BASE_URL}/v1/sys/storage/raft/snapshot",
            method="GET",
            token=service_token,
            timeout=300,
        ) as response:
            with temporary_path.open("wb") as output:
                while True:
                    chunk = response.read(1024 * 1024)

                    if not chunk:
                        break

                    output.write(chunk)
                    digest.update(chunk)
                    total_bytes += len(chunk)

                output.flush()
                os.fsync(output.fileno())

        if total_bytes < MINIMUM_SNAPSHOT_SIZE:
            raise BackupError(
                "Snapshot was unexpectedly small: "
                f"{total_bytes} bytes."
            )

        os.chown(temporary_path, 0, 0)
        os.chmod(temporary_path, 0o600)
        temporary_path.replace(snapshot_path)
        temporary_path = None

        checksum = digest.hexdigest()

        checksum_temporary = checksum_path.with_name(
            "." + checksum_path.name + ".tmp"
        )

        try:
            with checksum_temporary.open(
                "w",
                encoding="ascii",
                newline="\n",
            ) as output:
                output.write(
                    f"{checksum}  {snapshot_path.name}\n"
                )
                output.flush()
                os.fsync(output.fileno())

            os.chown(checksum_temporary, 0, 0)
            os.chmod(checksum_temporary, 0o600)
            checksum_temporary.replace(checksum_path)

        finally:
            if checksum_temporary.exists():
                checksum_temporary.unlink()

        verification_digest = hashlib.sha256()

        with snapshot_path.open("rb") as snapshot:
            for chunk in iter(
                lambda: snapshot.read(1024 * 1024),
                b"",
            ):
                verification_digest.update(chunk)

        if verification_digest.hexdigest() != checksum:
            raise BackupError(
                "Post-write snapshot checksum verification failed."
            )

        verify_root_only_path(
            snapshot_path,
            0o600,
            "snapshot file",
        )
        verify_root_only_path(
            checksum_path,
            0o600,
            "checksum file",
        )

        print("OpenBao AppRole authentication succeeded.")
        print("Backup-only policy assignment verified.")
        print("Raft leader verification succeeded.")
        print("OpenBao Raft snapshot created.")
        print(f"Snapshot file: {snapshot_path}")
        print(f"Snapshot size: {total_bytes} bytes")
        print("Snapshot checksum created and verified.")
        print("Snapshot ownership verified: root:root.")
        print("Snapshot permissions verified: 600.")
        print(
            "Automatic retention deletion is not yet enabled."
        )

    except Exception:
        if snapshot_path and snapshot_path.exists():
            snapshot_path.unlink()

        if checksum_path and checksum_path.exists():
            checksum_path.unlink()

        raise

    finally:
        role_id = None
        secret_id = None

        if temporary_path and temporary_path.exists():
            temporary_path.unlink()

        if service_token:
            token_revoked = revoke_token(service_token)
            service_token = None

    if not token_revoked:
        raise BackupError(
            "Snapshot succeeded, but explicit temporary-token "
            "revocation was not verified."
        )

    print("Temporary backup token revoked.")
    print("No credential or token value was displayed or stored.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(
            f"ERROR: OpenBao backup failed: {error}",
            file=sys.stderr,
        )
        sys.exit(1)
