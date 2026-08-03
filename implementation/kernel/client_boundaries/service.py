from __future__ import annotations

import re
import secrets
import uuid
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Callable

from kernel.client_boundaries.contracts import (
    BoundaryStatus,
    ClientBoundary,
    OnboardingTransaction,
    SignedOnboardingState,
    TransactionStatus,
)
from kernel.client_boundaries.repositories import (
    BoundaryConflictError,
    InMemoryClientBoundaryRepository,
    InMemoryOnboardingTransactionRepository,
)
from kernel.client_boundaries.state import (
    OnboardingStateService,
)


_DOMAIN_PATTERN = re.compile(
    r"^(?=.{1,253}$)"
    r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z]{2,63}$"
)


class ClientBoundaryService:
    def __init__(
        self,
        *,
        boundaries: InMemoryClientBoundaryRepository,
        transactions: InMemoryOnboardingTransactionRepository,
        state_service: OnboardingStateService,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._boundaries = boundaries
        self._transactions = transactions
        self._state_service = state_service
        self._clock = clock or (
            lambda: datetime.now(timezone.utc)
        )

    def begin_onboarding(
        self,
        *,
        client_id: str,
        provider: str,
        primary_domain: str,
        profile: str,
        application_id: str,
        correlation_id: str,
        lifetime: timedelta = timedelta(minutes=15),
    ) -> tuple[OnboardingTransaction, SignedOnboardingState]:
        self._require_identifier(client_id, "client_id")
        self._require_identifier(provider, "provider")
        self._require_identifier(profile, "profile")
        self._require_identifier(
            application_id,
            "application_id",
        )
        self._require_identifier(
            correlation_id,
            "correlation_id",
        )

        normalized_domain = primary_domain.strip().lower()
        if not _DOMAIN_PATTERN.fullmatch(normalized_domain):
            raise ValueError(
                "primary_domain must be a valid DNS domain."
            )

        if lifetime <= timedelta(0):
            raise ValueError(
                "Onboarding lifetime must be positive."
            )

        existing = self._boundaries.find_active_for_client(
            client_id=client_id,
            provider=provider,
        )
        if existing is not None:
            raise BoundaryConflictError(
                "Client already has an active provider boundary."
            )

        now = self._aware_now()

        transaction = OnboardingTransaction(
            id=f"txn_{uuid.uuid4().hex}",
            client_id=client_id,
            provider=provider,
            primary_domain=normalized_domain,
            profile=profile,
            application_id=application_id,
            correlation_id=correlation_id,
            nonce=secrets.token_urlsafe(32),
            status=TransactionStatus.PENDING,
            created_at=now,
            expires_at=now + lifetime,
        )

        self._transactions.add(transaction)

        return (
            transaction,
            self._state_service.issue(transaction),
        )

    def complete_onboarding(
        self,
        *,
        state: str,
        external_tenant_id: str,
        consented_at: datetime,
        service_principal_id: str | None = None,
    ) -> ClientBoundary:
        self._require_identifier(
            external_tenant_id,
            "external_tenant_id",
        )

        consumed = self._state_service.consume(state)

        existing_tenant = (
            self._boundaries.find_active_for_external_tenant(
                provider=consumed.provider,
                external_tenant_id=external_tenant_id,
            )
        )
        if existing_tenant is not None:
            raise BoundaryConflictError(
                "External tenant is already mapped "
                "to an active client boundary."
            )

        boundary = ClientBoundary(
            id=f"bnd_{uuid.uuid4().hex}",
            client_id=consumed.client_id,
            provider=consumed.provider,
            external_tenant_id=external_tenant_id,
            primary_domain=consumed.primary_domain,
            profile=consumed.profile,
            application_id=consumed.application_id,
            service_principal_id=service_principal_id,
            status=BoundaryStatus.PENDING,
            consent_transaction_id=consumed.id,
            created_at=self._aware_now(),
            consented_at=self._require_aware(
                consented_at,
                "consented_at",
            ),
        )

        self._boundaries.add(boundary)
        return boundary

    def mark_validated(
        self,
        *,
        boundary_id: str,
        validated_at: datetime,
    ) -> ClientBoundary:
        boundary = self._require_boundary(boundary_id)

        updated = replace(
            boundary,
            status=BoundaryStatus.VALIDATED,
            validated_at=self._require_aware(
                validated_at,
                "validated_at",
            ),
            last_error_code=None,
        )
        self._boundaries.replace(updated)
        return updated

    def disable_for_offboarding(
        self,
        *,
        boundary_id: str,
        offboarded_at: datetime,
    ) -> ClientBoundary:
        boundary = self._require_boundary(boundary_id)

        updated = replace(
            boundary,
            status=BoundaryStatus.OFFBOARDED,
            offboarded_at=self._require_aware(
                offboarded_at,
                "offboarded_at",
            ),
        )
        self._boundaries.replace(updated)
        return updated

    def _require_boundary(
        self,
        boundary_id: str,
    ) -> ClientBoundary:
        boundary = self._boundaries.get(boundary_id)
        if boundary is None:
            raise ValueError(
                "Client boundary does not exist."
            )

        return boundary

    def _aware_now(self) -> datetime:
        return self._require_aware(
            self._clock(),
            "clock",
        )

    @staticmethod
    def _require_identifier(
        value: str,
        field_name: str,
    ) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(
                f"{field_name} must be a non-empty string."
            )

    @staticmethod
    def _require_aware(
        value: datetime,
        field_name: str,
    ) -> datetime:
        if value.tzinfo is None:
            raise ValueError(
                f"{field_name} must be timezone aware."
            )

        return value
