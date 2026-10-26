"""Prevent Teams identity enrichment from silently broadening Graph scope.

The AOT production boundary is directory-read, NOT the optional, unconsented
identity-investigation-read profile. The module is composed without secrets
or network access; no provider mutation is needed for these tests.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from connectors.core.http_transport import UrlLibJsonHttpTransport
from connectors.microsoft_graph.tenant_tokens import GovernedTenantApplicationTokenProvider
from connectors.microsoft_graph.token import MicrosoftBoundaryError
from kernel.client_boundaries import (
    BoundaryStatus, ClientBoundary, SQLiteClientBoundaryRepository,
)
from jason_runtime.microsoft_directory import build_microsoft_directory_runtime


TENANT = "f7054323-d52b-4863-8c2f-1898f0b6077c"
APP_ID = "a4e10000-0000-4000-8000-000000000001"


class StubApplicationTokens:
    def acquire_for_client(self, *, client_id, correlation_id):
        assert client_id == "client-aot-internal"
        assert correlation_id == "microsoft-directory:" + TENANT
        return SimpleNamespace(
            tenant_id=TENANT,
            application_id=APP_ID,
            access_token="synthetic-test-token-never-sent",
        )


def _runtime(tmp_path):
    runtime = build_microsoft_directory_runtime(
        boundary_db=tmp_path / "client-boundaries.sqlite3",
        openbao_url="http://not-used.invalid",
        role_id_path=tmp_path / "not-provisioned-role",
        secret_id_path=tmp_path / "not-provisioned-secret",
        transport=UrlLibJsonHttpTransport(),
    )
    repository = SQLiteClientBoundaryRepository(runtime.store)
    now = datetime(2026, 10, 17, tzinfo=timezone.utc)
    record = ClientBoundary(
        id="boundary-aot-directory",
        client_id="client-aot-internal",
        provider="microsoft_graph",
        external_tenant_id=TENANT,
        primary_domain="teamaot.com",
        profile="directory-read",
        application_id=APP_ID,
        status=BoundaryStatus.VALIDATED,
        consent_transaction_id="validated-aot-consent",
        created_at=now,
        consented_at=now,
        validated_at=now,
    )
    repository.add(record)
    return runtime, repository, record


def test_canonical_teams_directory_uses_existing_approved_narrow_profile(tmp_path):
    runtime, repository, record = _runtime(tmp_path)
    try:
        bound = runtime.directory.tokens
        assert isinstance(bound, GovernedTenantApplicationTokenProvider)
        assert bound.profile_name == "directory-read"
        assert bound.provider_name == "microsoft_graph"
        assert bound.tokens._profile_name == "directory-read"
        assert bound.tokens._provider_name == "microsoft_graph"
        # The directory read boundary is valid; token acquisition itself is
        # stubbed to ensure this test never touches credentials/Graph.
        checked = replace(bound, tokens=StubApplicationTokens())
        assert checked.access_token_for_tenant(
            microsoft_tenant_id=TENANT
        ) == "synthetic-test-token-never-sent"
    finally:
        runtime.store.close()


def test_unconsented_investigation_profile_cannot_authorize_basic_teams_directory(tmp_path):
    runtime, repository, record = _runtime(tmp_path)
    try:
        repository.replace(replace(record, profile="identity-investigation-read"))
        checked = replace(runtime.directory.tokens, tokens=StubApplicationTokens())
        with pytest.raises(MicrosoftBoundaryError) as error:
            checked.access_token_for_tenant(microsoft_tenant_id=TENANT)
        assert error.value.error_code == "MICROSOFT_PROFILE_NOT_APPROVED"
    finally:
        runtime.store.close()
