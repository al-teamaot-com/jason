from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from kernel.client_boundaries.contracts import (
    BoundaryStatus,
    ClientBoundary,
    OnboardingTransaction,
    TransactionStatus,
)
from kernel.client_boundaries.repositories import (
    BoundaryConflictError,
    RecordNotFoundError,
)


_SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS client_boundaries (
    id TEXT PRIMARY KEY,
    client_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    external_tenant_id TEXT NOT NULL,
    primary_domain TEXT NOT NULL,
    profile TEXT NOT NULL,
    application_id TEXT NOT NULL,
    status TEXT NOT NULL,
    consent_transaction_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    consented_at TEXT,
    validated_at TEXT,
    service_principal_id TEXT,
    last_error_code TEXT,
    offboarded_at TEXT
);

CREATE INDEX IF NOT EXISTS ix_client_boundaries_client_provider
    ON client_boundaries(client_id, provider);
CREATE INDEX IF NOT EXISTS ix_client_boundaries_external_tenant
    ON client_boundaries(provider, external_tenant_id);

CREATE TABLE IF NOT EXISTS onboarding_transactions (
    id TEXT PRIMARY KEY,
    client_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    primary_domain TEXT NOT NULL,
    profile TEXT NOT NULL,
    application_id TEXT NOT NULL,
    correlation_id TEXT NOT NULL,
    nonce TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    completed_at TEXT,
    external_tenant_id TEXT,
    last_error_code TEXT
);

CREATE INDEX IF NOT EXISTS ix_onboarding_transactions_client_provider
    ON onboarding_transactions(client_id, provider);
"""

_ACTIVE_BOUNDARY_STATUSES = (
    BoundaryStatus.PENDING.value,
    BoundaryStatus.VALIDATED.value,
)


class SQLiteClientBoundaryStore:
    """Durable, provider-neutral persistence for client boundaries and onboarding.

    The store contains identifiers, status, consent metadata, and governance state only.
    It never stores provider credentials, access tokens, certificates, or secret material.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(self.path))
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.executescript(_SCHEMA)
        self.connection.commit()
        os.chmod(self.path, 0o600)

    def close(self) -> None:
        self.connection.close()


class SQLiteClientBoundaryRepository:
    def __init__(self, store: SQLiteClientBoundaryStore) -> None:
        self._store = store

    def add(self, boundary: ClientBoundary) -> None:
        with self._store.connection:
            self._assert_no_active_conflict(boundary)
            try:
                self._store.connection.execute(
                    """
                    INSERT INTO client_boundaries(
                        id, client_id, provider, external_tenant_id, primary_domain,
                        profile, application_id, status, consent_transaction_id,
                        created_at, consented_at, validated_at, service_principal_id,
                        last_error_code, offboarded_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    _boundary_values(boundary),
                )
            except sqlite3.IntegrityError as exc:
                raise BoundaryConflictError("Client boundary ID already exists.") from exc

    def get(self, boundary_id: str) -> ClientBoundary | None:
        row = self._store.connection.execute(
            "SELECT * FROM client_boundaries WHERE id = ?",
            (boundary_id,),
        ).fetchone()
        return None if row is None else _boundary_from_row(row)

    def find_active_for_client(
        self,
        *,
        client_id: str,
        provider: str,
    ) -> ClientBoundary | None:
        row = self._store.connection.execute(
            """
            SELECT * FROM client_boundaries
            WHERE client_id = ? AND provider = ? AND status IN (?, ?)
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (client_id, provider, *_ACTIVE_BOUNDARY_STATUSES),
        ).fetchone()
        return None if row is None else _boundary_from_row(row)

    def find_active_for_external_tenant(
        self,
        *,
        provider: str,
        external_tenant_id: str,
    ) -> ClientBoundary | None:
        row = self._store.connection.execute(
            """
            SELECT * FROM client_boundaries
            WHERE provider = ? AND external_tenant_id = ? AND status IN (?, ?)
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (provider, external_tenant_id, *_ACTIVE_BOUNDARY_STATUSES),
        ).fetchone()
        return None if row is None else _boundary_from_row(row)

    def replace(self, boundary: ClientBoundary) -> None:
        with self._store.connection:
            if self.get(boundary.id) is None:
                raise RecordNotFoundError("Client boundary does not exist.")
            self._assert_no_active_conflict(boundary, exclude_id=boundary.id)
            self._store.connection.execute(
                """
                UPDATE client_boundaries SET
                    client_id = ?, provider = ?, external_tenant_id = ?,
                    primary_domain = ?, profile = ?, application_id = ?, status = ?,
                    consent_transaction_id = ?, created_at = ?, consented_at = ?,
                    validated_at = ?, service_principal_id = ?, last_error_code = ?,
                    offboarded_at = ?
                WHERE id = ?
                """,
                (*_boundary_values(boundary)[1:], boundary.id),
            )

    def _assert_no_active_conflict(
        self,
        boundary: ClientBoundary,
        *,
        exclude_id: str | None = None,
    ) -> None:
        if boundary.status.value not in _ACTIVE_BOUNDARY_STATUSES:
            return

        parameters: list[str] = [
            boundary.provider,
            boundary.client_id,
            boundary.external_tenant_id,
            *_ACTIVE_BOUNDARY_STATUSES,
        ]
        exclusion = ""
        if exclude_id is not None:
            exclusion = " AND id <> ?"
            parameters.append(exclude_id)

        row = self._store.connection.execute(
            f"""
            SELECT client_id, external_tenant_id
            FROM client_boundaries
            WHERE provider = ?
              AND (client_id = ? OR external_tenant_id = ?)
              AND status IN (?, ?)
              {exclusion}
            LIMIT 1
            """,
            tuple(parameters),
        ).fetchone()
        if row is None:
            return
        if str(row[0]) == boundary.client_id:
            raise BoundaryConflictError("Client already has an active provider boundary.")
        raise BoundaryConflictError(
            "External tenant is already mapped to another active client boundary."
        )


class SQLiteOnboardingTransactionRepository:
    def __init__(self, store: SQLiteClientBoundaryStore) -> None:
        self._store = store

    def add(self, transaction: OnboardingTransaction) -> None:
        with self._store.connection:
            try:
                self._store.connection.execute(
                    """
                    INSERT INTO onboarding_transactions(
                        id, client_id, provider, primary_domain, profile,
                        application_id, correlation_id, nonce, status, created_at,
                        expires_at, completed_at, external_tenant_id, last_error_code
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    _transaction_values(transaction),
                )
            except sqlite3.IntegrityError as exc:
                raise BoundaryConflictError("Onboarding transaction ID already exists.") from exc

    def get(self, transaction_id: str) -> OnboardingTransaction | None:
        row = self._store.connection.execute(
            "SELECT * FROM onboarding_transactions WHERE id = ?",
            (transaction_id,),
        ).fetchone()
        return None if row is None else _transaction_from_row(row)

    def replace(self, transaction: OnboardingTransaction) -> None:
        with self._store.connection:
            if self.get(transaction.id) is None:
                raise RecordNotFoundError("Onboarding transaction does not exist.")
            self._store.connection.execute(
                """
                UPDATE onboarding_transactions SET
                    client_id = ?, provider = ?, primary_domain = ?, profile = ?,
                    application_id = ?, correlation_id = ?, nonce = ?, status = ?,
                    created_at = ?, expires_at = ?, completed_at = ?,
                    external_tenant_id = ?, last_error_code = ?
                WHERE id = ?
                """,
                (*_transaction_values(transaction)[1:], transaction.id),
            )


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        raise ValueError("client-boundary timestamps must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat()


def _dt(value: str | None) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("persisted client-boundary timestamp is not timezone-aware")
    return parsed.astimezone(timezone.utc)


def _boundary_values(boundary: ClientBoundary) -> tuple[object, ...]:
    return (
        boundary.id,
        boundary.client_id,
        boundary.provider,
        boundary.external_tenant_id,
        boundary.primary_domain,
        boundary.profile,
        boundary.application_id,
        boundary.status.value,
        boundary.consent_transaction_id,
        _iso(boundary.created_at),
        _iso(boundary.consented_at),
        _iso(boundary.validated_at),
        boundary.service_principal_id,
        boundary.last_error_code,
        _iso(boundary.offboarded_at),
    )


def _boundary_from_row(row: tuple[object, ...]) -> ClientBoundary:
    return ClientBoundary(
        id=str(row[0]),
        client_id=str(row[1]),
        provider=str(row[2]),
        external_tenant_id=str(row[3]),
        primary_domain=str(row[4]),
        profile=str(row[5]),
        application_id=str(row[6]),
        status=BoundaryStatus(str(row[7])),
        consent_transaction_id=str(row[8]),
        created_at=_dt(str(row[9])) or datetime.now(timezone.utc),
        consented_at=_dt(None if row[10] is None else str(row[10])),
        validated_at=_dt(None if row[11] is None else str(row[11])),
        service_principal_id=None if row[12] is None else str(row[12]),
        last_error_code=None if row[13] is None else str(row[13]),
        offboarded_at=_dt(None if row[14] is None else str(row[14])),
    )


def _transaction_values(transaction: OnboardingTransaction) -> tuple[object, ...]:
    return (
        transaction.id,
        transaction.client_id,
        transaction.provider,
        transaction.primary_domain,
        transaction.profile,
        transaction.application_id,
        transaction.correlation_id,
        transaction.nonce,
        transaction.status.value,
        _iso(transaction.created_at),
        _iso(transaction.expires_at),
        _iso(transaction.completed_at),
        transaction.external_tenant_id,
        transaction.last_error_code,
    )


def _transaction_from_row(row: tuple[object, ...]) -> OnboardingTransaction:
    return OnboardingTransaction(
        id=str(row[0]),
        client_id=str(row[1]),
        provider=str(row[2]),
        primary_domain=str(row[3]),
        profile=str(row[4]),
        application_id=str(row[5]),
        correlation_id=str(row[6]),
        nonce=str(row[7]),
        status=TransactionStatus(str(row[8])),
        created_at=_dt(str(row[9])) or datetime.now(timezone.utc),
        expires_at=_dt(str(row[10])) or datetime.now(timezone.utc),
        completed_at=_dt(None if row[11] is None else str(row[11])),
        external_tenant_id=None if row[12] is None else str(row[12]),
        last_error_code=None if row[13] is None else str(row[13]),
    )
