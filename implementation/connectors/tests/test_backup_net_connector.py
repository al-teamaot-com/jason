from __future__ import annotations

from datetime import datetime, timezone

import pytest

from connectors.backup_net.connector import (
    BACKUP_NET_FULL_ACCESS_SECRET,
    BackupNetConnector,
)
from connectors.core.contracts import (
    ConnectorAuthorizationError,
    ConnectorConfigurationError,
    ConnectorContext,
    ConnectorRequest,
)
from kernel.client_boundaries import (
    BoundaryStatus,
    ClientBoundary,
    InMemoryClientBoundaryRepository,
)


CUSTOMER_ID = "d28a556c-d8de-48f9-8a64-90fdf03ec4d0"
COMPANY_ID = "1627"


class FakeSecrets:
    def __init__(self):
        self.calls = []

    def resolve(self, logical_name, context):
        self.calls.append(logical_name)
        return {"client_id": "public-client", "client_secret": "secret-value"}


class FakeTransport:
    def request(self, **kwargs):
        raise AssertionError("Backup.net uses its OAuth session client")


class FakeAudit:
    def __init__(self):
        self.events = []

    def record(self, event_type, context, details):
        self.events.append((event_type, dict(details)))


class FakeClient:
    calls = []
    response = {"items": []}

    def __init__(self, credentials):
        assert credentials["client_id"] == "public-client"

    def get(self, path, params):
        self.calls.append((path, dict(params)))
        return dict(self.response)

def boundary(*, status=BoundaryStatus.VALIDATED, profile="endpoint-backup-read"):
    now = datetime(2026, 9, 23, tzinfo=timezone.utc)
    return ClientBoundary(
        id="boundary-backup-1627",
        client_id=COMPANY_ID,
        provider="backup_net",
        external_tenant_id=CUSTOMER_ID,
        primary_domain="virtuoldesigns.com",
        profile=profile,
        application_id="backup-net-public-api",
        status=status,
        consent_transaction_id="owner-approved-backup-net",
        created_at=now,
        validated_at=now if status is BoundaryStatus.VALIDATED else None,
    )


def context(capability, *, client_id=None, organization_id="aot"):
    return ConnectorContext(
        correlation_id="corr-backup-001",
        principal_id="person-al",
        organization_id=organization_id,
        client_id=client_id,
        capability=capability,
        mode="observe",
    )

def build(*, record=None, logical_secret="backup_net.readonly"):
    repo = InMemoryClientBoundaryRepository()
    if record is not False:
        repo.add(record or boundary())
    secrets = FakeSecrets()
    audit = FakeAudit()
    FakeClient.calls.clear()
    FakeClient.response = {"items": []}
    connector = BackupNetConnector(
        secrets=secrets,
        transport=FakeTransport(),
        audit=audit,
        boundaries=repo,
        logical_secret=logical_secret,
        client_factory=FakeClient,
    )
    return connector, secrets, audit


def test_asset_search_derives_customer_id_from_validated_boundary():
    connector, secrets, audit = build()
    FakeClient.response = {
        "items": [{"id": "asset-1", "name": "DGV-50859", "customerId": CUSTOMER_ID}]
    }
    result = connector.execute(
        ConnectorRequest(
            context("backup_net.endpoint_asset.search"),
            {"company_id": 1627, "name": "DGV-50859"},
        )
    )
    assert result.data["items"][0]["name"] == "DGV-50859"
    path, params = FakeClient.calls[-1]
    assert path == "/api/epb/v1/assets"
    assert params["customer_id"] == CUSTOMER_ID
    assert params["name"] == "DGV-50859"
    assert params["page_number"] == 1
    assert params["page_size"] == 50
    assert secrets.calls == ["backup_net.readonly"]
    assert audit.events[0][1]["customer_boundary_validated"] is True


def test_provider_customer_id_cannot_be_supplied_by_caller():
    connector, secrets, _ = build()
    with pytest.raises(ConnectorAuthorizationError, match="server-derived"):
        connector.execute(
            ConnectorRequest(
                context("backup_net.endpoint_asset.search"),
                {
                    "company_id": 1627,
                    "customer_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                },
            )
        )
    assert secrets.calls == []
    assert FakeClient.calls == []

def test_missing_boundary_fails_before_secret_resolution():
    connector, secrets, _ = build(record=False)
    with pytest.raises(ConnectorAuthorizationError, match="validated"):
        connector.execute(
            ConnectorRequest(
                context("backup_net.endpoint_asset.search"),
                {"company_id": 1627, "name": "DGV-50859"},
            )
        )
    assert secrets.calls == []
    assert FakeClient.calls == []


def test_unvalidated_boundary_fails_closed():
    connector, secrets, _ = build(record=boundary(status=BoundaryStatus.PENDING))
    with pytest.raises(ConnectorAuthorizationError, match="validated"):
        connector.execute(
            ConnectorRequest(
                context("backup_net.endpoint_asset.search"),
                {"company_id": 1627},
            )
        )
    assert secrets.calls == []


def test_response_crossing_customer_boundary_is_rejected():
    connector, _, _ = build()
    FakeClient.response = {
        "items": [
            {
                "id": "asset-2",
                "name": "OTHER-DEVICE",
                "customerId": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            }
        ]
    }
    with pytest.raises(ConnectorAuthorizationError, match="crossed"):
        connector.execute(
            ConnectorRequest(
                context("backup_net.endpoint_asset.search"),
                {"company_id": 1627},
            )
        )


def test_response_without_customer_proof_is_rejected():
    connector, _, _ = build()
    FakeClient.response = {"items": [{"id": "asset-1", "name": "DGV-50859"}]}
    with pytest.raises(ConnectorAuthorizationError, match="did not prove"):
        connector.execute(
            ConnectorRequest(
                context("backup_net.endpoint_asset.search"),
                {"company_id": 1627},
            )
        )

def test_backupiq_type_is_required_and_bounded():
    connector, secrets, _ = build()
    with pytest.raises(ConnectorConfigurationError, match="alert type"):
        connector.execute(
            ConnectorRequest(
                context("backup_net.backupiq_alert.search"),
                {"company_id": 1627},
            )
        )
    assert secrets.calls == []


def test_page_size_is_bounded_before_provider_call():
    connector, secrets, _ = build()
    with pytest.raises(ConnectorConfigurationError, match="page_size"):
        connector.execute(
            ConnectorRequest(
                context("backup_net.endpoint_asset.search"),
                {"company_id": 1627, "page_size": 1000},
            )
        )
    assert secrets.calls == []


def test_client_context_must_match_selected_company():
    connector, secrets, _ = build()
    with pytest.raises(ConnectorAuthorizationError, match="does not match"):
        connector.execute(
            ConnectorRequest(
                context("backup_net.endpoint_asset.search", client_id="999"),
                {"company_id": 1627},
            )
        )
    assert secrets.calls == []

def test_full_access_profile_uses_separate_logical_secret():
    connector, secrets, _ = build(logical_secret=BACKUP_NET_FULL_ACCESS_SECRET)
    FakeClient.response = {
        "items": [{"id": "asset-1", "name": "DGV-50859", "customerId": CUSTOMER_ID}]
    }
    connector.execute(
        ConnectorRequest(
            context("backup_net.endpoint_asset.search"),
            {"company_id": 1627, "name": "DGV-50859"},
        )
    )
    assert secrets.calls == ["backup_net.fullaccess"]


def test_unapproved_logical_secret_profile_fails_closed():
    with pytest.raises(ConnectorConfigurationError, match="logical secret profile"):
        build(logical_secret="backup_net.unmanaged")
