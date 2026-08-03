from __future__ import annotations

from threading import RLock

from kernel.client_boundaries.contracts import (
    BoundaryStatus,
    ClientBoundary,
    OnboardingTransaction,
)


class BoundaryConflictError(RuntimeError):
    """A client or external tenant already has an active mapping."""


class RecordNotFoundError(RuntimeError):
    """A requested boundary or transaction does not exist."""


_ACTIVE_BOUNDARY_STATUSES = frozenset(
    {
        BoundaryStatus.PENDING,
        BoundaryStatus.VALIDATED,
    }
)


class InMemoryClientBoundaryRepository:
    def __init__(self) -> None:
        self._records: dict[str, ClientBoundary] = {}
        self._lock = RLock()

    def add(self, boundary: ClientBoundary) -> None:
        with self._lock:
            if boundary.id in self._records:
                raise BoundaryConflictError(
                    "Client boundary ID already exists."
                )

            self._assert_no_active_conflict(boundary)
            self._records[boundary.id] = boundary

    def get(self, boundary_id: str) -> ClientBoundary | None:
        with self._lock:
            return self._records.get(boundary_id)

    def find_active_for_client(
        self,
        *,
        client_id: str,
        provider: str,
    ) -> ClientBoundary | None:
        with self._lock:
            for boundary in self._records.values():
                if (
                    boundary.client_id == client_id
                    and boundary.provider == provider
                    and boundary.status
                    in _ACTIVE_BOUNDARY_STATUSES
                ):
                    return boundary

        return None

    def find_active_for_external_tenant(
        self,
        *,
        provider: str,
        external_tenant_id: str,
    ) -> ClientBoundary | None:
        with self._lock:
            for boundary in self._records.values():
                if (
                    boundary.provider == provider
                    and boundary.external_tenant_id
                    == external_tenant_id
                    and boundary.status
                    in _ACTIVE_BOUNDARY_STATUSES
                ):
                    return boundary

        return None

    def replace(self, boundary: ClientBoundary) -> None:
        with self._lock:
            if boundary.id not in self._records:
                raise RecordNotFoundError(
                    "Client boundary does not exist."
                )

            self._assert_no_active_conflict(
                boundary,
                exclude_id=boundary.id,
            )
            self._records[boundary.id] = boundary

    def _assert_no_active_conflict(
        self,
        boundary: ClientBoundary,
        *,
        exclude_id: str | None = None,
    ) -> None:
        if boundary.status not in _ACTIVE_BOUNDARY_STATUSES:
            return

        for current in self._records.values():
            if current.id == exclude_id:
                continue

            if current.status not in _ACTIVE_BOUNDARY_STATUSES:
                continue

            if (
                current.provider == boundary.provider
                and current.client_id == boundary.client_id
            ):
                raise BoundaryConflictError(
                    "Client already has an active provider boundary."
                )

            if (
                current.provider == boundary.provider
                and current.external_tenant_id
                == boundary.external_tenant_id
            ):
                raise BoundaryConflictError(
                    "External tenant is already mapped "
                    "to another active client boundary."
                )


class InMemoryOnboardingTransactionRepository:
    def __init__(self) -> None:
        self._records: dict[str, OnboardingTransaction] = {}
        self._lock = RLock()

    def add(self, transaction: OnboardingTransaction) -> None:
        with self._lock:
            if transaction.id in self._records:
                raise BoundaryConflictError(
                    "Onboarding transaction ID already exists."
                )

            self._records[transaction.id] = transaction

    def get(
        self,
        transaction_id: str,
    ) -> OnboardingTransaction | None:
        with self._lock:
            return self._records.get(transaction_id)

    def replace(
        self,
        transaction: OnboardingTransaction,
    ) -> None:
        with self._lock:
            if transaction.id not in self._records:
                raise RecordNotFoundError(
                    "Onboarding transaction does not exist."
                )

            self._records[transaction.id] = transaction
