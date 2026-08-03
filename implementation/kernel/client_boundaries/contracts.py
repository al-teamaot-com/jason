from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol


class BoundaryStatus(StrEnum):
    PENDING = "pending"
    VALIDATED = "validated"
    FAILED = "failed"
    REVOKED = "revoked"
    OFFBOARDED = "offboarded"


class TransactionStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class ClientBoundary:
    id: str
    client_id: str
    provider: str
    external_tenant_id: str
    primary_domain: str
    profile: str
    application_id: str
    status: BoundaryStatus
    consent_transaction_id: str
    created_at: datetime
    consented_at: datetime | None = None
    validated_at: datetime | None = None
    service_principal_id: str | None = None
    last_error_code: str | None = None
    offboarded_at: datetime | None = None


@dataclass(frozen=True)
class OnboardingTransaction:
    id: str
    client_id: str
    provider: str
    primary_domain: str
    profile: str
    application_id: str
    correlation_id: str
    nonce: str
    status: TransactionStatus
    created_at: datetime
    expires_at: datetime
    completed_at: datetime | None = None
    external_tenant_id: str | None = None
    last_error_code: str | None = None


@dataclass(frozen=True)
class SignedOnboardingState:
    value: str
    transaction_id: str
    expires_at: datetime


class ClientBoundaryRepository(Protocol):
    def add(self, boundary: ClientBoundary) -> None:
        ...

    def get(self, boundary_id: str) -> ClientBoundary | None:
        ...

    def find_active_for_client(
        self,
        *,
        client_id: str,
        provider: str,
    ) -> ClientBoundary | None:
        ...

    def find_active_for_external_tenant(
        self,
        *,
        provider: str,
        external_tenant_id: str,
    ) -> ClientBoundary | None:
        ...

    def replace(self, boundary: ClientBoundary) -> None:
        ...


class OnboardingTransactionRepository(Protocol):
    def add(self, transaction: OnboardingTransaction) -> None:
        ...

    def get(
        self,
        transaction_id: str,
    ) -> OnboardingTransaction | None:
        ...

    def replace(
        self,
        transaction: OnboardingTransaction,
    ) -> None:
        ...
