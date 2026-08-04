from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from connectors.microsoft_graph import (
    GRAPH_DEFAULT_SCOPE,
    MICROSOFT_AUTHORITY_HOST,
    MicrosoftBoundaryError,
    MicrosoftCertificateCredential,
    MicrosoftCredentialError,
    MicrosoftTokenAcquisitionError,
    MsalCertificateTokenProvider,
)
from kernel.client_boundaries import (
    BoundaryStatus,
    ClientBoundary,
    InMemoryClientBoundaryRepository,
)


APPLICATION_ID = (
    "11111111-2222-3333-4444-555555555555"
)
TENANT_ID = (
    "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
)
NOW = datetime(
    2026,
    8,
    3,
    22,
    0,
    tzinfo=timezone.utc,
)

PRIVATE_KEY = """-----BEGIN PRIVATE KEY-----
TEST-PRIVATE-KEY
-----END PRIVATE KEY-----"""

CERTIFICATE = """-----BEGIN CERTIFICATE-----
TEST-CERTIFICATE
-----END CERTIFICATE-----"""

THUMBPRINT = "A1" * 20


class FakeCredentialSource:
    def __init__(
        self,
        credential: MicrosoftCertificateCredential,
    ) -> None:
        self.credential = credential
        self.calls: list[str] = []

    def resolve(
        self,
        logical_secret: str,
    ) -> MicrosoftCertificateCredential:
        self.calls.append(logical_secret)
        return self.credential


class FailingCredentialSource:
    def resolve(
        self,
        logical_secret: str,
    ) -> MicrosoftCertificateCredential:
        raise RuntimeError(
            f"Secret failure for {logical_secret}"
        )


class FakeMsalApplication:
    def __init__(
        self,
        responses: list[dict[str, object]],
    ) -> None:
        self.responses = responses
        self.scopes: list[list[str]] = []
        self.remove_calls = 0

    def acquire_token_for_client(
        self,
        scopes: list[str],
    ) -> dict[str, object]:
        self.scopes.append(scopes)
        return self.responses.pop(0)

    def remove_tokens_for_client(self) -> None:
        self.remove_calls += 1


class FakeMsalFactory:
    def __init__(
        self,
        responses: list[dict[str, object]],
    ) -> None:
        self.responses = responses
        self.calls: list[dict[str, object]] = []
        self.applications: list[FakeMsalApplication] = []

    def __call__(
        self,
        *,
        client_id: str,
        authority: str,
        client_credential: dict[str, str],
    ) -> FakeMsalApplication:
        self.calls.append(
            {
                "client_id": client_id,
                "authority": authority,
                "client_credential": client_credential,
            }
        )

        application = FakeMsalApplication(
            self.responses.copy()
        )
        self.applications.append(application)
        return application


def credential(
    *,
    generation: str = "generation-1",
) -> MicrosoftCertificateCredential:
    return MicrosoftCertificateCredential(
        private_key_pem=PRIVATE_KEY,
        certificate_pem=CERTIFICATE,
        certificate_thumbprint=THUMBPRINT,
        generation=generation,
    )


def boundary(
    *,
    status: BoundaryStatus = BoundaryStatus.VALIDATED,
    client_id: str = "client_faith",
    profile: str = "directory-read",
    tenant_id: str = TENANT_ID,
    application_id: str = APPLICATION_ID,
) -> ClientBoundary:
    return ClientBoundary(
        id="bnd_001",
        client_id=client_id,
        provider="microsoft_graph",
        external_tenant_id=tenant_id,
        primary_domain="faithformation.org",
        profile=profile,
        application_id=application_id,
        status=status,
        consent_transaction_id="txn_001",
        created_at=NOW,
        consented_at=NOW,
        validated_at=(
            NOW
            if status is BoundaryStatus.VALIDATED
            else None
        ),
    )


def build_provider(
    *,
    record: ClientBoundary | None = None,
    responses: list[dict[str, object]] | None = None,
    credential_source=None,
):
    boundaries = InMemoryClientBoundaryRepository()

    if record is not None:
        boundaries.add(record)

    source = (
        credential_source
        if credential_source is not None
        else FakeCredentialSource(credential())
    )

    factory = FakeMsalFactory(
        responses
        or [
            {
                "access_token": "TEST-ACCESS-TOKEN",
                "token_type": "Bearer",
                "expires_in": 3600,
            }
        ]
    )

    provider = MsalCertificateTokenProvider(
        boundaries=boundaries,
        credentials=source,
        application_factory=factory,
        clock=lambda: 1_785_800_000,
    )

    return provider, boundaries, source, factory


def test_acquires_token_for_validated_boundary() -> None:
    provider, _, source, factory = build_provider(
        record=boundary()
    )

    result = provider.acquire_for_client(
        client_id="client_faith",
        correlation_id="corr_001",
    )

    assert result.access_token == "TEST-ACCESS-TOKEN"
    assert result.token_type == "Bearer"
    assert result.expires_at_epoch == 1_785_803_600
    assert result.tenant_id == TENANT_ID
    assert result.application_id == APPLICATION_ID
    assert result.scope == GRAPH_DEFAULT_SCOPE
    assert result.certificate_thumbprint == THUMBPRINT

    assert source.calls == [
        "microsoft_graph.directory_read"
    ]

    assert factory.calls == [
        {
            "client_id": APPLICATION_ID,
            "authority": (
                f"{MICROSOFT_AUTHORITY_HOST}/{TENANT_ID}"
            ),
            "client_credential": {
                "private_key": PRIVATE_KEY,
                "thumbprint": THUMBPRINT,
                "public_certificate": CERTIFICATE,
            },
        }
    ]

    assert factory.applications[0].scopes == [
        [GRAPH_DEFAULT_SCOPE]
    ]


def test_reuses_msal_application_for_same_cache_key() -> None:
    provider, _, _, factory = build_provider(
        record=boundary(),
        responses=[
            {
                "access_token": "TOKEN-1",
                "token_type": "Bearer",
                "expires_in": 3600,
            },
            {
                "access_token": "TOKEN-2",
                "token_type": "Bearer",
                "expires_in": 3600,
            },
        ],
    )

    first = provider.acquire_for_client(
        client_id="client_faith",
        correlation_id="corr_001",
    )
    second = provider.acquire_for_client(
        client_id="client_faith",
        correlation_id="corr_002",
    )

    assert first.access_token == "TOKEN-1"
    assert second.access_token == "TOKEN-2"
    assert len(factory.calls) == 1
    assert len(factory.applications) == 1


def test_new_credential_generation_uses_new_application() -> None:
    record = boundary()
    boundaries = InMemoryClientBoundaryRepository()
    boundaries.add(record)

    source = FakeCredentialSource(
        credential(generation="generation-1")
    )
    factory = FakeMsalFactory(
        [
            {
                "access_token": "TOKEN",
                "token_type": "Bearer",
                "expires_in": 3600,
            }
        ]
    )

    provider = MsalCertificateTokenProvider(
        boundaries=boundaries,
        credentials=source,
        application_factory=factory,
    )

    provider.acquire_for_client(
        client_id="client_faith",
        correlation_id="corr_001",
    )

    source.credential = credential(
        generation="generation-2"
    )

    provider.acquire_for_client(
        client_id="client_faith",
        correlation_id="corr_002",
    )

    assert len(factory.calls) == 2


def test_invalidates_client_application_cache() -> None:
    provider, _, _, factory = build_provider(
        record=boundary()
    )

    provider.acquire_for_client(
        client_id="client_faith",
        correlation_id="corr_001",
    )

    first_application = factory.applications[0]

    provider.invalidate_client(
        client_id="client_faith"
    )

    assert first_application.remove_calls == 1

    provider.acquire_for_client(
        client_id="client_faith",
        correlation_id="corr_002",
    )

    assert len(factory.calls) == 2


def test_rejects_pending_unvalidated_boundary() -> None:
    provider, _, _, factory = build_provider(
        record=boundary(status=BoundaryStatus.PENDING)
    )

    with pytest.raises(
        MicrosoftBoundaryError,
        match="not validated",
    ) as captured:
        provider.acquire_for_client(
            client_id="client_faith",
            correlation_id="corr_001",
        )

    assert captured.value.error_code == (
        "MICROSOFT_BOUNDARY_NOT_VALIDATED"
    )
    assert factory.calls == []


def test_rejects_failed_boundary_as_inactive() -> None:
    provider, _, _, factory = build_provider(
        record=boundary(status=BoundaryStatus.FAILED)
    )

    with pytest.raises(
        MicrosoftBoundaryError,
        match="No active",
    ) as captured:
        provider.acquire_for_client(
            client_id="client_faith",
            correlation_id="corr_001",
        )

    assert captured.value.error_code == (
        "MICROSOFT_BOUNDARY_NOT_FOUND"
    )
    assert factory.calls == []


@pytest.mark.parametrize(
    "status",
    [
        BoundaryStatus.REVOKED,
        BoundaryStatus.OFFBOARDED,
    ],
)
def test_rejects_inactive_boundary(
    status: BoundaryStatus,
) -> None:
    provider, _, _, factory = build_provider(
        record=boundary(status=status)
    )

    with pytest.raises(
        MicrosoftBoundaryError,
        match="No active",
    ) as captured:
        provider.acquire_for_client(
            client_id="client_faith",
            correlation_id="corr_001",
        )

    assert captured.value.error_code == (
        "MICROSOFT_BOUNDARY_NOT_FOUND"
    )
    assert factory.calls == []


def test_rejects_missing_boundary() -> None:
    provider, _, _, factory = build_provider()

    with pytest.raises(
        MicrosoftBoundaryError,
        match="No active",
    ):
        provider.acquire_for_client(
            client_id="client_missing",
            correlation_id="corr_001",
        )

    assert factory.calls == []


def test_rejects_unapproved_profile() -> None:
    provider, _, _, factory = build_provider(
        record=boundary(profile="security-read")
    )

    with pytest.raises(
        MicrosoftBoundaryError,
        match="unapproved profile",
    ) as captured:
        provider.acquire_for_client(
            client_id="client_faith",
            correlation_id="corr_001",
        )

    assert captured.value.error_code == (
        "MICROSOFT_PROFILE_NOT_APPROVED"
    )
    assert factory.calls == []


@pytest.mark.parametrize(
    ("tenant_id", "application_id"),
    [
        ("not-a-uuid", APPLICATION_ID),
        (TENANT_ID, "not-a-uuid"),
    ],
)
def test_rejects_invalid_boundary_identifiers(
    tenant_id: str,
    application_id: str,
) -> None:
    provider, _, _, factory = build_provider(
        record=boundary(
            tenant_id=tenant_id,
            application_id=application_id,
        )
    )

    with pytest.raises(
        MicrosoftBoundaryError,
        match="invalid identifier",
    ) as captured:
        provider.acquire_for_client(
            client_id="client_faith",
            correlation_id="corr_001",
        )

    assert captured.value.error_code == (
        "MICROSOFT_BOUNDARY_IDENTIFIER_INVALID"
    )
    assert factory.calls == []


def test_translates_credential_resolution_failure() -> None:
    provider, _, _, factory = build_provider(
        record=boundary(),
        credential_source=FailingCredentialSource(),
    )

    with pytest.raises(
        MicrosoftCredentialError,
        match="could not be resolved",
    ) as captured:
        provider.acquire_for_client(
            client_id="client_faith",
            correlation_id="corr_001",
        )

    assert captured.value.error_code == (
        "MICROSOFT_CREDENTIAL_RESOLUTION_FAILED"
    )
    assert "Secret failure" not in str(captured.value)
    assert factory.calls == []


@pytest.mark.parametrize(
    ("provider_error", "expected_code"),
    [
        (
            "invalid_client",
            "MICROSOFT_CERTIFICATE_REJECTED",
        ),
        (
            "unauthorized_client",
            "MICROSOFT_APPLICATION_NOT_FOUND",
        ),
        (
            "invalid_grant",
            "MICROSOFT_CONSENT_REQUIRED",
        ),
        (
            "invalid_scope",
            "MICROSOFT_PERMISSION_DENIED",
        ),
        (
            "unexpected_error",
            "MICROSOFT_TOKEN_ACQUISITION_FAILED",
        ),
    ],
)
def test_translates_msal_errors(
    provider_error: str,
    expected_code: str,
) -> None:
    provider, _, _, _ = build_provider(
        record=boundary(),
        responses=[
            {
                "error": provider_error,
                "error_description": (
                    "Sensitive Microsoft description"
                ),
            }
        ],
    )

    with pytest.raises(
        MicrosoftTokenAcquisitionError,
        match="could not be acquired",
    ) as captured:
        provider.acquire_for_client(
            client_id="client_faith",
            correlation_id="corr_001",
        )

    assert captured.value.error_code == expected_code
    assert "Sensitive" not in str(captured.value)


@pytest.mark.parametrize(
    "response",
    [
        {},
        {
            "access_token": "",
            "expires_in": 3600,
        },
        {
            "access_token": "TOKEN",
            "token_type": "NotBearer",
            "expires_in": 3600,
        },
        {
            "access_token": "TOKEN",
            "token_type": "Bearer",
        },
        {
            "access_token": "TOKEN",
            "token_type": "Bearer",
            "expires_in": 0,
        },
        {
            "access_token": "TOKEN",
            "token_type": "Bearer",
            "expires_in": True,
        },
    ],
)
def test_rejects_invalid_token_response(
    response: dict[str, object],
) -> None:
    provider, _, _, _ = build_provider(
        record=boundary(),
        responses=[response],
    )

    with pytest.raises(
        MicrosoftTokenAcquisitionError,
    ) as captured:
        provider.acquire_for_client(
            client_id="client_faith",
            correlation_id="corr_001",
        )

    assert captured.value.error_code == (
        "MICROSOFT_TOKEN_RESPONSE_INVALID"
    )


@pytest.mark.parametrize(
    ("private_key", "certificate", "thumbprint", "generation"),
    [
        (
            "not-a-key",
            CERTIFICATE,
            THUMBPRINT,
            "generation-1",
        ),
        (
            PRIVATE_KEY,
            "not-a-certificate",
            THUMBPRINT,
            "generation-1",
        ),
        (
            PRIVATE_KEY,
            CERTIFICATE,
            "invalid",
            "generation-1",
        ),
        (
            PRIVATE_KEY,
            CERTIFICATE,
            THUMBPRINT,
            "",
        ),
    ],
)
def test_rejects_invalid_certificate_credential(
    private_key: str,
    certificate: str,
    thumbprint: str,
    generation: str,
) -> None:
    with pytest.raises(ValueError):
        MicrosoftCertificateCredential(
            private_key_pem=private_key,
            certificate_pem=certificate,
            certificate_thumbprint=thumbprint,
            generation=generation,
        )


def test_normalizes_formatted_thumbprint() -> None:
    formatted = ":".join(
        THUMBPRINT[index:index + 2]
        for index in range(0, len(THUMBPRINT), 2)
    )

    result = MicrosoftCertificateCredential(
        private_key_pem=PRIVATE_KEY,
        certificate_pem=CERTIFICATE,
        certificate_thumbprint=formatted.lower(),
        generation="generation-1",
    )

    assert result.certificate_thumbprint == THUMBPRINT


def test_rejects_non_default_scope() -> None:
    boundaries = InMemoryClientBoundaryRepository()

    with pytest.raises(
        ValueError,
        match=r"Graph \.default scope",
    ):
        MsalCertificateTokenProvider(
            boundaries=boundaries,
            credentials=FakeCredentialSource(
                credential()
            ),
            application_factory=FakeMsalFactory([]),
            scope="User.Read.All",
        )


def test_rejects_unapproved_authority_host() -> None:
    boundaries = InMemoryClientBoundaryRepository()

    with pytest.raises(
        ValueError,
        match="public-cloud authority",
    ):
        MsalCertificateTokenProvider(
            boundaries=boundaries,
            credentials=FakeCredentialSource(
                credential()
            ),
            application_factory=FakeMsalFactory([]),
            authority_host="https://login.example.test",
        )


@pytest.mark.parametrize(
    ("client_id", "correlation_id"),
    [
        ("", "corr_001"),
        ("client_faith", ""),
    ],
)
def test_rejects_missing_request_identifiers(
    client_id: str,
    correlation_id: str,
) -> None:
    provider, _, _, factory = build_provider(
        record=boundary()
    )

    with pytest.raises(
        ValueError,
        match="non-empty string",
    ):
        provider.acquire_for_client(
            client_id=client_id,
            correlation_id=correlation_id,
        )

    assert factory.calls == []
