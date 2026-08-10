from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from kernel.identity_authority import IdentityRecord

from .teams_identity_binding import MicrosoftIdentityBinding


_SCHEMA = """
CREATE TABLE IF NOT EXISTS microsoft_identity_bindings (
    microsoft_tenant_id TEXT NOT NULL,
    microsoft_object_id TEXT NOT NULL,
    jason_identity_id TEXT NOT NULL,
    client_id TEXT,
    status TEXT NOT NULL,
    PRIMARY KEY (microsoft_tenant_id, microsoft_object_id)
);
CREATE INDEX IF NOT EXISTS ix_microsoft_identity_binding_jason_identity
    ON microsoft_identity_bindings(jason_identity_id);
"""


class SQLiteMicrosoftIdentityBindingStore:
    """Explicit, durable Microsoft -> Jason identity bindings.

    The store never auto-provisions a Jason identity from Microsoft claims. Writes
    are intended for a separate governed administration path; conversational runtime
    uses only ``find``.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(str(self._path))
        self._connection.executescript(_SCHEMA)
        self._connection.commit()
        os.chmod(self._path, 0o600)

    def find(
        self,
        *,
        microsoft_tenant_id: str,
        microsoft_object_id: str,
    ) -> MicrosoftIdentityBinding | None:
        row = self._connection.execute(
            """
            SELECT microsoft_tenant_id, microsoft_object_id, jason_identity_id,
                   client_id, status
            FROM microsoft_identity_bindings
            WHERE microsoft_tenant_id = ? AND microsoft_object_id = ?
            """,
            (microsoft_tenant_id, microsoft_object_id),
        ).fetchone()
        if row is None:
            return None
        return MicrosoftIdentityBinding(
            microsoft_tenant_id=str(row[0]),
            microsoft_object_id=str(row[1]),
            jason_identity_id=str(row[2]),
            client_id=None if row[3] is None else str(row[3]),
            status=str(row[4]),
        )

    def put(self, binding: MicrosoftIdentityBinding) -> None:
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO microsoft_identity_bindings(
                    microsoft_tenant_id, microsoft_object_id, jason_identity_id,
                    client_id, status
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(microsoft_tenant_id, microsoft_object_id) DO UPDATE SET
                    jason_identity_id = excluded.jason_identity_id,
                    client_id = excluded.client_id,
                    status = excluded.status
                """,
                (
                    binding.microsoft_tenant_id,
                    binding.microsoft_object_id,
                    binding.jason_identity_id,
                    binding.client_id,
                    binding.status,
                ),
            )

    def close(self) -> None:
        self._connection.close()


class AuthorityIdentityRecordReader:
    """Expose the narrow identity-reader contract from the JKD-001 repository."""

    def __init__(self, authority_repository) -> None:
        self._authority_repository = authority_repository

    def get(self, identity_id: str) -> IdentityRecord | None:
        return self._authority_repository.get_identity(identity_id)
