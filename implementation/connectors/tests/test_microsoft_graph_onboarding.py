from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import pytest

from connectors.microsoft_graph import (
    MicrosoftConsentConfiguration,
    MicrosoftConsentDeniedError,
    MicrosoftConsentValidationError,
    MicrosoftOnboardingOrchestrator,
)
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
    21,
    0,
    tzinfo=timezone.utc,
)

APPLICATION_ID = (
    "11111111-2222-3333-4444-555555555555"
)

TENANT_ID = (
    "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
)


def build_orchestrator():
    boundaries = InMemoryClientBoundaryRepository()
    transactions = (
        InMemoryOnboardingTransactionRepository()
    )

    state_service = OnboardingStateService(
        signing_key=b"s" * 32,
        transactions=transactions,
        clock=lambda: NOW,
    )

    boundary_service = ClientBoundaryService(
        boundaries=boundaries,
        transactions=transactions,
        state_service=state_service,
        clock=lambda: NOW,
    )

    orchestrator = MicrosoftOnboardingOrchestrator(
        configuration=MicrosoftConsentConfiguration(
            application_id=APPLICATION_ID,
            redirect_uri=(
                "https://jason.example.test/"
                "microsoft/admin-consent/callback"
            ),
        ),
        boundaries=boundary_service,
    )

    return orchestrator, boundaries, transactions


def begin(orchestrator):
    return orchestrator.begin(
        client_id="client_faith",
        primary_domain="FaithFormation.org",
        correlation_id="corr_microsoft_001",
    )


def callback(state: str):
    return {
        "tenant": TENANT_ID,
        "state": state,
        "admin_consent": "True",
    }


def test_begins_complete_microsoft_consent_session() -> None:
    orchestrator, _, transactions = build_orchestrator()

    session = begin(orchestrator)

    parsed = urlparse(session.consent_request.url)
    query = parse_qs(parsed.query)

    assert session.transaction.client_id == (
        "client_faith"
    )
    assert session.transaction.provider == (
        "microsoft_graph"
    )
    assert session.transaction.profile == (
        "directory-read"
    )
    assert session.transaction.primary_domain == (
        "faithformation.org"
    )
    assert session.transaction.status is (
        TransactionStatus.PENDING
    )

    assert parsed.path == (
        "/faithformation.org/v2.0/adminconsent"
    )
    assert query["client_id"] == [APPLICATION_ID]
    assert query["state"] == [session.signed_state]
    assert (
        session.consent_request.transaction_id
        == session.transaction.id
    )
    assert (
        transactions.get(session.transaction.id)
        == session.transaction
    )


def test_completes_consent_and_creates_boundary() -> None:
    orchestrator, boundaries, transactions = (
        build_orchestrator()
    )

    session = begin(orchestrator)

    completion = orchestrator.complete(
        callback_parameters=callback(
            session.signed_state
        ),
        expected_state=session.signed_state,
        consented_at=NOW,
        service_principal_id="sp_faith",
    )

    assert completion.consent_result.tenant_id == (
        TENANT_ID
    )
    assert completion.boundary.client_id == (
        "client_faith"
    )
    assert completion.boundary.external_tenant_id == (
        TENANT_ID
    )
    assert completion.boundary.provider == (
        "microsoft_graph"
    )
    assert completion.boundary.profile == (
        "directory-read"
    )
    assert completion.boundary.application_id == (
        APPLICATION_ID
    )
    assert completion.boundary.status is (
        BoundaryStatus.PENDING
    )
    assert completion.boundary.service_principal_id == (
        "sp_faith"
    )

    stored_transaction = transactions.get(
        session.transaction.id
    )
    assert stored_transaction is not None
    assert stored_transaction.status is (
        TransactionStatus.COMPLETED
    )

    assert boundaries.get(
        completion.boundary.id
    ) == completion.boundary


def test_rejects_callback_state_mismatch() -> None:
    orchestrator, _, _ = build_orchestrator()
    session = begin(orchestrator)

    with pytest.raises(
        MicrosoftConsentValidationError,
        match="state is invalid",
    ):
        orchestrator.complete(
            callback_parameters=callback(
                "different.state"
            ),
            expected_state=session.signed_state,
            consented_at=NOW,
        )


def test_rejects_tampered_signed_state() -> None:
    orchestrator, _, _ = build_orchestrator()
    session = begin(orchestrator)

    tampered = session.signed_state[:-1] + (
        "A"
        if session.signed_state[-1] != "A"
        else "B"
    )

    with pytest.raises(
        OnboardingStateError,
        match="signature is invalid",
    ):
        orchestrator.complete(
            callback_parameters=callback(tampered),
            expected_state=tampered,
            consented_at=NOW,
        )


def test_reports_safe_consent_denial() -> None:
    orchestrator, _, transactions = (
        build_orchestrator()
    )
    session = begin(orchestrator)

    with pytest.raises(
        MicrosoftConsentDeniedError,
        match="permission_denied",
    ):
        orchestrator.complete(
            callback_parameters={
                "state": session.signed_state,
                "error": "permission_denied",
                "error_description": (
                    "Administrator cancelled consent."
                ),
            },
            expected_state=session.signed_state,
            consented_at=NOW,
        )

    stored = transactions.get(
        session.transaction.id
    )
    assert stored is not None
    assert stored.status is TransactionStatus.PENDING


def test_rejects_reused_callback() -> None:
    orchestrator, _, _ = build_orchestrator()
    session = begin(orchestrator)

    orchestrator.complete(
        callback_parameters=callback(
            session.signed_state
        ),
        expected_state=session.signed_state,
        consented_at=NOW,
    )

    with pytest.raises(
        OnboardingStateError,
        match="no longer pending",
    ):
        orchestrator.complete(
            callback_parameters=callback(
                session.signed_state
            ),
            expected_state=session.signed_state,
            consented_at=NOW,
        )


def test_rejects_duplicate_client_onboarding() -> None:
    orchestrator, _, _ = build_orchestrator()
    session = begin(orchestrator)

    orchestrator.complete(
        callback_parameters=callback(
            session.signed_state
        ),
        expected_state=session.signed_state,
        consented_at=NOW,
    )

    with pytest.raises(
        BoundaryConflictError,
        match="Client already has",
    ):
        begin(orchestrator)


def test_rejects_duplicate_external_tenant() -> None:
    orchestrator, _, _ = build_orchestrator()

    first = begin(orchestrator)
    orchestrator.complete(
        callback_parameters=callback(
            first.signed_state
        ),
        expected_state=first.signed_state,
        consented_at=NOW,
    )

    second = orchestrator.begin(
        client_id="client_other",
        primary_domain="other.example",
        correlation_id="corr_microsoft_002",
    )

    with pytest.raises(
        BoundaryConflictError,
        match="External tenant is already mapped",
    ):
        orchestrator.complete(
            callback_parameters=callback(
                second.signed_state
            ),
            expected_state=second.signed_state,
            consented_at=NOW,
        )


def test_uses_custom_positive_lifetime() -> None:
    orchestrator, _, _ = build_orchestrator()

    session = orchestrator.begin(
        client_id="client_faith",
        primary_domain="faithformation.org",
        correlation_id="corr_microsoft_001",
        lifetime=timedelta(minutes=5),
    )

    assert session.transaction.expires_at == (
        NOW + timedelta(minutes=5)
    )


def test_rejects_invalid_domain_before_consent() -> None:
    orchestrator, _, _ = build_orchestrator()

    with pytest.raises(
        ValueError,
        match="valid DNS domain",
    ):
        orchestrator.begin(
            client_id="client_faith",
            primary_domain="common",
            correlation_id="corr_microsoft_001",
        )
