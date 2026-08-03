from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from kernel.client_boundaries import (
    BoundaryConflictError,
    BoundaryStatus,
    ClientBoundaryService,
    InMemoryClientBoundaryRepository,
    InMemoryOnboardingTransactionRepository,
    OnboardingStateError,
    OnboardingStateService,
    TransactionStatus,
)


NOW = datetime(
    2026,
    8,
    3,
    19,
    30,
    tzinfo=timezone.utc,
)


def build_service():
    boundaries = InMemoryClientBoundaryRepository()
    transactions = InMemoryOnboardingTransactionRepository()

    state_service = OnboardingStateService(
        signing_key=b"x" * 32,
        transactions=transactions,
        clock=lambda: NOW,
    )

    service = ClientBoundaryService(
        boundaries=boundaries,
        transactions=transactions,
        state_service=state_service,
        clock=lambda: NOW,
    )

    return service, boundaries, transactions


def begin(service: ClientBoundaryService):
    return service.begin_onboarding(
        client_id="client_faith",
        provider="microsoft_graph",
        primary_domain="FaithFormation.org",
        profile="directory-read",
        application_id="app_directory_read",
        correlation_id="corr_001",
    )


def test_begins_signed_onboarding_transaction() -> None:
    service, _, transactions = build_service()

    transaction, state = begin(service)

    assert transaction.status is TransactionStatus.PENDING
    assert transaction.primary_domain == "faithformation.org"
    assert transaction.expires_at == NOW + timedelta(
        minutes=15
    )
    assert state.transaction_id == transaction.id
    assert "." in state.value
    assert transactions.get(transaction.id) == transaction


def test_completes_onboarding_once() -> None:
    service, boundaries, transactions = build_service()

    transaction, state = begin(service)

    boundary = service.complete_onboarding(
        state=state.value,
        external_tenant_id="tenant-faith",
        consented_at=NOW,
        service_principal_id="sp-faith",
    )

    assert boundary.client_id == "client_faith"
    assert boundary.provider == "microsoft_graph"
    assert boundary.status is BoundaryStatus.PENDING
    assert boundary.external_tenant_id == "tenant-faith"
    assert boundary.service_principal_id == "sp-faith"

    completed = transactions.get(transaction.id)
    assert completed is not None
    assert completed.status is TransactionStatus.COMPLETED
    assert boundaries.get(boundary.id) == boundary

    with pytest.raises(
        OnboardingStateError,
        match="no longer pending",
    ):
        service.complete_onboarding(
            state=state.value,
            external_tenant_id="tenant-faith",
            consented_at=NOW,
        )


def test_rejects_tampered_state() -> None:
    service, _, _ = build_service()
    _, state = begin(service)

    tampered = state.value[:-1] + (
        "A" if state.value[-1] != "A" else "B"
    )

    with pytest.raises(
        OnboardingStateError,
        match="signature is invalid",
    ):
        service.complete_onboarding(
            state=tampered,
            external_tenant_id="tenant-faith",
            consented_at=NOW,
        )


def test_rejects_expired_transaction() -> None:
    boundaries = InMemoryClientBoundaryRepository()
    transactions = InMemoryOnboardingTransactionRepository()

    current = NOW

    state_service = OnboardingStateService(
        signing_key=b"x" * 32,
        transactions=transactions,
        clock=lambda: current,
    )
    service = ClientBoundaryService(
        boundaries=boundaries,
        transactions=transactions,
        state_service=state_service,
        clock=lambda: current,
    )

    transaction, state = service.begin_onboarding(
        client_id="client_faith",
        provider="microsoft_graph",
        primary_domain="faithformation.org",
        profile="directory-read",
        application_id="app_directory_read",
        correlation_id="corr_001",
        lifetime=timedelta(minutes=1),
    )

    current = NOW + timedelta(minutes=2)

    with pytest.raises(
        OnboardingStateError,
        match="expired",
    ):
        service.complete_onboarding(
            state=state.value,
            external_tenant_id="tenant-faith",
            consented_at=current,
        )

    expired = transactions.get(transaction.id)
    assert expired is not None
    assert expired.status is TransactionStatus.EXPIRED


def test_rejects_duplicate_client_provider_boundary() -> None:
    service, _, _ = build_service()

    _, state = begin(service)
    service.complete_onboarding(
        state=state.value,
        external_tenant_id="tenant-faith",
        consented_at=NOW,
    )

    with pytest.raises(
        BoundaryConflictError,
        match="Client already has",
    ):
        begin(service)


def test_rejects_external_tenant_mapped_to_other_client() -> None:
    service, _, _ = build_service()

    _, first_state = begin(service)
    service.complete_onboarding(
        state=first_state.value,
        external_tenant_id="tenant-shared",
        consented_at=NOW,
    )

    _, second_state = service.begin_onboarding(
        client_id="client_other",
        provider="microsoft_graph",
        primary_domain="other.example",
        profile="directory-read",
        application_id="app_directory_read",
        correlation_id="corr_002",
    )

    with pytest.raises(
        BoundaryConflictError,
        match="External tenant is already mapped",
    ):
        service.complete_onboarding(
            state=second_state.value,
            external_tenant_id="tenant-shared",
            consented_at=NOW,
        )


def test_marks_boundary_validated() -> None:
    service, _, _ = build_service()

    _, state = begin(service)
    boundary = service.complete_onboarding(
        state=state.value,
        external_tenant_id="tenant-faith",
        consented_at=NOW,
    )

    validated = service.mark_validated(
        boundary_id=boundary.id,
        validated_at=NOW + timedelta(minutes=1),
    )

    assert validated.status is BoundaryStatus.VALIDATED
    assert validated.validated_at == NOW + timedelta(
        minutes=1
    )


def test_offboarding_releases_client_and_tenant() -> None:
    service, _, _ = build_service()

    _, state = begin(service)
    boundary = service.complete_onboarding(
        state=state.value,
        external_tenant_id="tenant-faith",
        consented_at=NOW,
    )

    offboarded = service.disable_for_offboarding(
        boundary_id=boundary.id,
        offboarded_at=NOW + timedelta(days=1),
    )

    assert offboarded.status is BoundaryStatus.OFFBOARDED

    transaction, _ = begin(service)
    assert transaction.status is TransactionStatus.PENDING


@pytest.mark.parametrize(
    "domain",
    [
        "",
        "not a domain",
        "-invalid.example",
        "invalid-.example",
        "localhost",
    ],
)
def test_rejects_invalid_primary_domain(domain: str) -> None:
    service, _, _ = build_service()

    with pytest.raises(
        ValueError,
        match="valid DNS domain",
    ):
        service.begin_onboarding(
            client_id="client_faith",
            provider="microsoft_graph",
            primary_domain=domain,
            profile="directory-read",
            application_id="app_directory_read",
            correlation_id="corr_001",
        )


def test_rejects_short_signing_key() -> None:
    with pytest.raises(
        ValueError,
        match="at least 32 bytes",
    ):
        OnboardingStateService(
            signing_key=b"short",
            transactions=(
                InMemoryOnboardingTransactionRepository()
            ),
        )
