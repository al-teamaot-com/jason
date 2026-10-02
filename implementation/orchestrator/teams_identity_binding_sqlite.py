from __future__ import annotations

from dataclasses import dataclass, replace
import os
import re
import sqlite3
from pathlib import Path
from typing import Protocol

from connectors.core.contracts import ConnectorTransportError
from kernel.identity_authority import IdentityRecord

from .teams_identity_binding import (
    MicrosoftIdentityBinding,
    MicrosoftUserDirectoryReader,
)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS microsoft_identity_bindings (
    microsoft_tenant_id TEXT NOT NULL,
    microsoft_object_id TEXT NOT NULL,
    jason_identity_id TEXT NOT NULL,
    client_id TEXT,
    email_address TEXT,
    status TEXT NOT NULL,
    PRIMARY KEY (microsoft_tenant_id, microsoft_object_id)
);
CREATE INDEX IF NOT EXISTS ix_microsoft_identity_binding_jason_identity
  ON microsoft_identity_bindings(jason_identity_id);
"""


class ActiveJasonIdentityBindingReader(Protocol):
    def find_active_by_jason_identity(
        self,
        *,
        jason_identity_id: str,
    ) -> MicrosoftIdentityBinding | None: ...


@dataclass(frozen=True, slots=True)
class AutoEnrollingMicrosoftIdentityBindingStore:
    bindings: "SQLiteMicrosoftIdentityBindingStore"
    directory: object
    authority_store: object
    allowed_domains: frozenset[str]

    def find(
        self,
        *,
        microsoft_tenant_id: str,
        microsoft_object_id: str,
    ) -> MicrosoftIdentityBinding | None:
        binding = self.bindings.find(
            microsoft_tenant_id=microsoft_tenant_id,
            microsoft_object_id=microsoft_object_id,
        )
        if binding is not None:
            return binding

        try:
            user = self.directory.read_user(
                microsoft_tenant_id=microsoft_tenant_id,
                microsoft_object_id=microsoft_object_id,
            )
        except Exception:
            return None
        if user.get("accountEnabled") is False:
            return None

        upn = str(user.get("userPrincipalName") or "").strip().casefold()
        if "@" not in upn or upn.rsplit("@", 1)[1] not in self.allowed_domains:
            return None
        mail = str(user.get("mail") or "").strip().casefold()
        email = upn
        if "@" in mail and mail.rsplit("@", 1)[1] in self.allowed_domains:
            email = mail

        compact = re.sub(r"[^a-f0-9]", "", microsoft_object_id.casefold())
        if len(compact) < 12:
            return None
        principal_id = f"person-entra-{compact}"
        expected = IdentityRecord(
            identity_id=principal_id,
            identity_type="human",
            organization_id="aot",
            status="active",
        )
        existing = self.authority_store.get_identity(principal_id)
        if existing is None:
            self.authority_store.put_identity(expected)
        elif existing != expected:
            return None

        binding = MicrosoftIdentityBinding(
            microsoft_tenant_id=microsoft_tenant_id.strip(),
            microsoft_object_id=microsoft_object_id.strip(),
            jason_identity_id=principal_id,
            client_id=None,
            email_address=email,
            status="active",
        )
        self.bindings.put(binding)
        return binding

    def find_active_by_jason_identity(
        self,
        *,
        jason_identity_id: str,
    ) -> MicrosoftIdentityBinding | None:
        return self.bindings.find_active_by_jason_identity(
            jason_identity_id=jason_identity_id,
        )

    def put(self, binding: MicrosoftIdentityBinding) -> None:
        self.bindings.put(binding)


class SQLiteMicrosoftIdentityBindingStore:
    """Explicit, durable Microsoft -> Jason identity bindings.

    The store never auto-provisions a Jason identity from Microsoft claims. Writes
    are intended for a separate governed administration path; conversational runtime
    uses only ``find``. Optional delivery addresses are Jason-owned binding data used
    to resolve first-person communication targets such as "send me an email" without
    trusting the transport to assert an address at execution time.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # MCP synchronous tools are dispatched through worker threads while the
        # runtime is process-cached. Allow this durable connection to follow the
        # governed runtime across those threads instead of failing before authority
        # evaluation with sqlite3.ProgrammingError.
        self._connection = sqlite3.connect(
            str(self._path),
            check_same_thread=False,
        )
        self._connection.executescript(_SCHEMA)
        self._migrate_email_address()
        self._connection.commit()
        os.chmod(self._path, 0o600)

    def _migrate_email_address(self) -> None:
        columns = {
            str(row[1])
            for row in self._connection.execute(
                "PRAGMA table_info(microsoft_identity_bindings)"
            ).fetchall()
        }
        if "email_address" not in columns:
            self._connection.execute(
                "ALTER TABLE microsoft_identity_bindings ADD COLUMN email_address TEXT"
            )

    @staticmethod
    def _from_row(row) -> MicrosoftIdentityBinding:
        return MicrosoftIdentityBinding(
            microsoft_tenant_id=str(row[0]),
            microsoft_object_id=str(row[1]),
            jason_identity_id=str(row[2]),
            client_id=None if row[3] is None else str(row[3]),
            email_address=None if row[4] is None else str(row[4]),
            status=str(row[5]),
        )

    def find(
        self,
        *,
        microsoft_tenant_id: str,
        microsoft_object_id: str,
    ) -> MicrosoftIdentityBinding | None:
        row = self._connection.execute(
            """
            SELECT microsoft_tenant_id, microsoft_object_id, jason_identity_id,
                   client_id, email_address, status
            FROM microsoft_identity_bindings
            WHERE microsoft_tenant_id = ? AND microsoft_object_id = ?
            """,
            (microsoft_tenant_id, microsoft_object_id),
        ).fetchone()
        if row is None:
            return None
        return self._from_row(row)

    def find_active_by_jason_identity(
        self,
        *,
        jason_identity_id: str,
    ) -> MicrosoftIdentityBinding | None:
        """Resolve one trusted active Microsoft binding for an authenticated identity.

        Source authorization must not guess when more than one active Microsoft
        binding exists for the same Jason identity. Ambiguity therefore returns None
        and causes the downstream information-release policy to fail closed.
        """

        rows = self._connection.execute(
            """
            SELECT microsoft_tenant_id, microsoft_object_id, jason_identity_id,
                   client_id, email_address, status
            FROM microsoft_identity_bindings
            WHERE jason_identity_id = ? AND status = 'active'
            ORDER BY microsoft_tenant_id, microsoft_object_id
            LIMIT 2
            """,
            (jason_identity_id,),
        ).fetchall()
        if len(rows) != 1:
            return None
        return self._from_row(rows[0])

    def put(self, binding: MicrosoftIdentityBinding) -> None:
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO microsoft_identity_bindings(
                    microsoft_tenant_id, microsoft_object_id, jason_identity_id,
                    client_id, email_address, status
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(microsoft_tenant_id, microsoft_object_id) DO UPDATE SET
                    jason_identity_id = excluded.jason_identity_id,
                    client_id = excluded.client_id,
                    email_address = excluded.email_address,
                    status = excluded.status
                """,
                (
                    binding.microsoft_tenant_id,
                    binding.microsoft_object_id,
                    binding.jason_identity_id,
                    binding.client_id,
                    binding.email_address,
                    binding.status,
                ),
            )

    def close(self) -> None:
        self._connection.close()


@dataclass(frozen=True, slots=True)
class DirectoryEnrichedMicrosoftIdentityBindingResolver:
    """Resolve current provider-mapping email from authenticated Microsoft identity.

    The durable Microsoft tenant/object -> Jason identity binding remains the
    authority anchor. Email is mutable profile data, so source authorization resolves
    the current value from Microsoft Graph instead of requiring it to have been
    copied into the binding database. The directory lookup is keyed only by the
    already-bound Microsoft tenant/object identity; caller-supplied email values are
    never consulted.

    Any missing/ambiguous binding, disabled/mismatched Microsoft identity, invalid
    directory profile, missing email, or provider transport failure returns no
    enriched binding. Downstream source authorization therefore fails closed rather
    than falling back to a stale stored address or the provider service identity.
    """

    bindings: ActiveJasonIdentityBindingReader
    directory: MicrosoftUserDirectoryReader

    def find_active_by_jason_identity(
        self,
        *,
        jason_identity_id: str,
    ) -> MicrosoftIdentityBinding | None:
        principal_id = str(jason_identity_id).strip()
        if not principal_id:
            return None

        binding = self.bindings.find_active_by_jason_identity(
            jason_identity_id=principal_id
        )
        if binding is None:
            return None
        if binding.status != "active" or binding.jason_identity_id != principal_id:
            return None

        try:
            email = self.directory.resolve_email(
                microsoft_tenant_id=binding.microsoft_tenant_id,
                microsoft_object_id=binding.microsoft_object_id,
            )
        except (ConnectorTransportError, PermissionError, ValueError):
            return None

        normalized = str(email or "").strip().casefold()
        if not normalized:
            return None

        return replace(binding, email_address=normalized)


class AuthorityIdentityRecordReader:
    """Expose the narrow identity-reader contract from the JKD-001 repository."""

    def __init__(self, authority_repository) -> None:
        self._authority_repository = authority_repository

    def get(self, identity_id: str) -> IdentityRecord | None:
        return self._authority_repository.get_identity(identity_id)
