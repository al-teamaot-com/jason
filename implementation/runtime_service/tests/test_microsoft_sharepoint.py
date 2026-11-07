from pathlib import Path
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from kernel.client_boundaries import ClientBoundary, BoundaryStatus

from jason_runtime.microsoft_sharepoint import (
    build_microsoft_sharepoint_runtime,
    require_validated_sharepoint_service_boundary,
)


def test_sharepoint_runtime_has_isolated_openbao_and_read_only_profile(tmp_path: Path):
    runtime = build_microsoft_sharepoint_runtime(
        boundary_db=tmp_path / "clients.sqlite",
        openbao_url="https://openbao.invalid",
        role_id_path=tmp_path / "role-id",
        secret_id_path=tmp_path / "secret-id",
        transport=object(),
    )
    tenant_tokens = runtime.reader.tokens
    assert tenant_tokens.provider_name == "microsoft_graph_sharepoint"
    assert tenant_tokens.profile_name == "sharepoint-read"
    assert tenant_tokens.tokens._logical_secret == "microsoft_graph.sharepoint_read"
    assert tenant_tokens.tokens._provider_name == "microsoft_graph_sharepoint"
    assert tenant_tokens.tokens._profile_name == "sharepoint-read"
    # Runtime composition must not perform Microsoft calls or read certificates.
    assert tenant_tokens.tokens._applications == {}



AOT_TENANT = "f7054323-d52b-4863-8c2f-1898f0b6077c"
AOT_CLIENT = "client-aot-internal"


def sample_approved_boundary():
    return ClientBoundary(
        id="validated-sharepoint-aot",
        client_id=AOT_CLIENT,
        provider="microsoft_graph_sharepoint",
        external_tenant_id=AOT_TENANT,
        primary_domain="teamaot.com",
        profile="sharepoint-read",
        application_id="ecf6be34-5233-49ab-9dae-feb0c7fb47e2",
        status=BoundaryStatus.VALIDATED,
        consent_transaction_id="approval-1117",
        created_at=datetime(2026, 10, 30, tzinfo=timezone.utc),
        consented_at=datetime(2026, 10, 30, tzinfo=timezone.utc),
        validated_at=datetime(2026, 10, 30, tzinfo=timezone.utc),
        service_principal_id="dedicated-sharepoint-service",
    )


class FakeBoundaryLookup:
    def __init__(self, entry=None):
        self.entry = entry
        self.calls = []

    def find_active_for_external_tenant(self, *, provider, external_tenant_id):
        self.calls.append((provider, external_tenant_id))
        return self.entry


def require_aot_boundary(entry):
    repo = FakeBoundaryLookup(entry)
    require_validated_sharepoint_service_boundary(
        boundaries=repo, tenant_id=AOT_TENANT,
        expected_client_id=AOT_CLIENT, expected_domain="teamaot.com",
    )
    assert repo.calls == [("microsoft_graph_sharepoint", AOT_TENANT)]


def test_dedicated_validated_sharepoint_boundary_is_accepted():
    require_aot_boundary(sample_approved_boundary())


@pytest.mark.parametrize("changes", [
    {"provider": "microsoft_graph"},
    {"provider": "microsoft_graph_mail"},
    {"profile": "directory-read"},
    {"status": BoundaryStatus.PENDING},
    {"status": BoundaryStatus.REVOKED},
    {"client_id": "other-client"},
    {"external_tenant_id": "d5078ed8-e0a3-4b6c-8000-08dbf33241c8"},
    {"primary_domain": "other-domain.com"},
    {"service_principal_id": None},
    {"validated_at": None},
])
def test_unconsented_wrong_or_incomplete_sharepoint_boundary_fails_closed(changes):
    entry = replace(sample_approved_boundary(), **changes)
    with pytest.raises(PermissionError, match="Dedicated validated"):
        require_aot_boundary(entry)


def test_missing_sharepoint_binding_denies_even_if_directory_profile_exists():
    with pytest.raises(PermissionError, match="Dedicated validated"):
        require_aot_boundary(None)
