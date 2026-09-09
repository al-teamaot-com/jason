from __future__ import annotations

from datetime import datetime, timezone

import pytest

from kernel.client_boundaries import (
    BoundaryStatus,
    ClientBoundary,
    InMemoryClientBoundaryRepository,
)
from connectors.microsoft_graph.tenant_tokens import GovernedTenantApplicationTokenProvider
from connectors.microsoft_graph.token import MicrosoftApplicationToken, MicrosoftBoundaryError


TENANT_ID = "f7054323-d52b-4863-8c2f-1898f0b6077c"
APP_ID = "c94301b7-7194-46ab-aab7-94f9366f51a9"


def boundary(*, status=BoundaryStatus.VALIDATED, profile="directory-read") -> ClientBoundary:
    now = datetime(2026, 8, 11, tzinfo=timezone.utc)
    return ClientBoundary(
        id="boundary-aot",
        client_id="aot",
        provider="microsoft_graph",
        external_tenant_id=TENANT_ID,
        primary_domain="teamaot.com",
        profile=profile,
        application_id=APP_ID,
        status=status,
        consent_transaction_id="consent-aot",
        created_at=now,
        consented_at=now,
        validated_at=now if status is BoundaryStatus.VALIDATED else None,
    )


class FakeTokens:
    def __init__(self, *, tenant_id=TENANT_ID, application_id=APP_ID):
        self.tenant_id = tenant_id
        self.application_id = application_id
        self.calls = []

    def acquire_for_client(self, *, client_id: str, correlation_id: str):
        self.calls.append((client_id, correlation_id))
        return MicrosoftApplicationToken(
            access_token="token-value",
            token_type="Bearer",
            expires_at_epoch=2_000_000_000,
            tenant_id=self.tenant_id,
            application_id=self.application_id,
            scope="https://graph.microsoft.com/.default",
            certificate_thumbprint="A" * 40,
        )

    def invalidate_client(self, *, client_id: str) -> None:
        pass


def provider(*, stored_boundary=None, tokens=None):
    boundaries = InMemoryClientBoundaryRepository()
    if stored_boundary is not None:
        boundaries.add(stored_boundary)
    token_provider = tokens or FakeTokens()
    return GovernedTenantApplicationTokenProvider(
        boundaries=boundaries,
        tokens=token_provider,
    ), token_provider


def test_resolves_authenticated_tenant_through_validated_boundary():
    adapter, tokens = provider(stored_boundary=boundary())
    assert adapter.access_token_for_tenant(microsoft_tenant_id=TENANT_ID) == "token-value"
    assert tokens.calls == [("aot", f"microsoft-directory:{TENANT_ID}")]


def test_missing_boundary_fails_closed():
    adapter, _ = provider()
    with pytest.raises(MicrosoftBoundaryError) as exc:
        adapter.access_token_for_tenant(microsoft_tenant_id=TENANT_ID)
    assert exc.value.error_code == "MICROSOFT_BOUNDARY_NOT_FOUND"


def test_wrong_profile_fails_closed():
    adapter, _ = provider(stored_boundary=boundary(profile="other"))
    with pytest.raises(MicrosoftBoundaryError) as exc:
        adapter.access_token_for_tenant(microsoft_tenant_id=TENANT_ID)
    assert exc.value.error_code == "MICROSOFT_PROFILE_NOT_APPROVED"


def test_token_tenant_must_match_authenticated_tenant():
    adapter, _ = provider(
        stored_boundary=boundary(),
        tokens=FakeTokens(tenant_id="11111111-1111-1111-1111-111111111111"),
    )
    with pytest.raises(MicrosoftBoundaryError) as exc:
        adapter.access_token_for_tenant(microsoft_tenant_id=TENANT_ID)
    assert exc.value.error_code == "MICROSOFT_TOKEN_TENANT_MISMATCH"


def test_token_application_must_match_boundary():
    adapter, _ = provider(
        stored_boundary=boundary(),
        tokens=FakeTokens(application_id="22222222-2222-2222-2222-222222222222"),
    )
    with pytest.raises(MicrosoftBoundaryError) as exc:
        adapter.access_token_for_tenant(microsoft_tenant_id=TENANT_ID)
    assert exc.value.error_code == "MICROSOFT_TOKEN_APPLICATION_MISMATCH"
