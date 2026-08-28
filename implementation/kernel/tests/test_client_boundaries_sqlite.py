from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from kernel.client_boundaries import (
    BoundaryConflictError,
    BoundaryStatus,
    ClientBoundary,
    OnboardingTransaction,
    SQLiteClientBoundaryRepository,
    SQLiteClientBoundaryStore,
    SQLiteOnboardingTransactionRepository,
    TransactionStatus,
)


def now() -> datetime:
    return datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)


def boundary(*, boundary_id="boundary-1", client_id="aot", tenant_id="tenant-1") -> ClientBoundary:
    return ClientBoundary(
        id=boundary_id,
        client_id=client_id,
        provider="microsoft_graph",
        external_tenant_id=tenant_id,
        primary_domain="teamaot.com",
        profile="directory-read",
        application_id="app-1",
        status=BoundaryStatus.VALIDATED,
        consent_transaction_id="tx-1",
        created_at=now(),
        consented_at=now(),
        validated_at=now(),
        service_principal_id="sp-1",
    )


def transaction(*, transaction_id="tx-1") -> OnboardingTransaction:
    return OnboardingTransaction(
        id=transaction_id,
        client_id="aot",
        provider="microsoft_graph",
        primary_domain="teamaot.com",
        profile="directory-read",
        application_id="app-1",
        correlation_id="corr-1",
        nonce="nonce-1",
        status=TransactionStatus.COMPLETED,
        created_at=now(),
        expires_at=now() + timedelta(minutes=15),
        completed_at=now() + timedelta(minutes=1),
        external_tenant_id="tenant-1",
    )


def test_boundary_and_transaction_survive_store_reopen(tmp_path):
    path = tmp_path / "client-boundaries.sqlite3"
    store = SQLiteClientBoundaryStore(path)
    boundaries = SQLiteClientBoundaryRepository(store)
    transactions = SQLiteOnboardingTransactionRepository(store)
    transactions.add(transaction())
    boundaries.add(boundary())
    store.close()

    reopened = SQLiteClientBoundaryStore(path)
    reopened_boundaries = SQLiteClientBoundaryRepository(reopened)
    reopened_transactions = SQLiteOnboardingTransactionRepository(reopened)

    assert reopened_boundaries.get("boundary-1") == boundary()
    assert reopened_boundaries.find_active_for_client(
        client_id="aot", provider="microsoft_graph"
    ) == boundary()
    assert reopened_boundaries.find_active_for_external_tenant(
        provider="microsoft_graph", external_tenant_id="tenant-1"
    ) == boundary()
    assert reopened_transactions.get("tx-1") == transaction()
    reopened.close()


def test_active_client_conflict_fails_closed(tmp_path):
    store = SQLiteClientBoundaryStore(tmp_path / "boundaries.sqlite3")
    repository = SQLiteClientBoundaryRepository(store)
    repository.add(boundary())

    with pytest.raises(BoundaryConflictError):
        repository.add(boundary(boundary_id="boundary-2", tenant_id="tenant-2"))
    store.close()


def test_external_tenant_conflict_fails_closed(tmp_path):
    store = SQLiteClientBoundaryStore(tmp_path / "boundaries.sqlite3")
    repository = SQLiteClientBoundaryRepository(store)
    repository.add(boundary())

    with pytest.raises(BoundaryConflictError):
        repository.add(boundary(boundary_id="boundary-2", client_id="other"))
    store.close()


def test_revoked_boundary_allows_replacement_active_mapping(tmp_path):
    store = SQLiteClientBoundaryStore(tmp_path / "boundaries.sqlite3")
    repository = SQLiteClientBoundaryRepository(store)
    first = boundary()
    repository.add(first)
    repository.replace(replace(first, status=BoundaryStatus.REVOKED))
    second = boundary(boundary_id="boundary-2")
    repository.add(second)
    assert repository.find_active_for_client(
        client_id="aot", provider="microsoft_graph"
    ) == second
    store.close()
