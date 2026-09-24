from __future__ import annotations

from datetime import datetime, timezone

import pytest

from connectors.core.contracts import (
    ConnectorAuthorizationError,
    ConnectorConfigurationError,
    ConnectorContext,
    ConnectorRequest,
)
from connectors.dnsfilter.connector import DnsFilterConnector
from kernel.client_boundaries import (
    BoundaryStatus,
    ClientBoundary,
    InMemoryClientBoundaryRepository,
)

COMPANY_ID = "333"
DNSFILTER_ORG_ID = "9001"


class FakeSecrets:
    def __init__(self): self.calls = []
    def resolve(self, logical_name, context):
        self.calls.append(logical_name)
        return {"api_key": "provider-key"}


class FakeTransport:
    def request(self, **kwargs):
        raise AssertionError("DNSFilter connector uses its dedicated client")


class FakeAudit:
    def __init__(self): self.events = []
    def record(self, event_type, context, details):
        self.events.append((event_type, dict(details)))


class FakeClient:
    calls = []
    response = {"data": []}
    def __init__(self, credentials):
        assert credentials["api_key"] == "provider-key"
    def get(self, path, params=None):
        self.calls.append((path, dict(params or {})))
        return dict(self.response)


def boundary(*, status=BoundaryStatus.VALIDATED, profile="dnsfilter-organization-read"):
    now = datetime(2026, 9, 24, tzinfo=timezone.utc)
    return ClientBoundary(
        id="boundary-dnsfilter-333",
        client_id=COMPANY_ID,
        provider="dnsfilter",
        external_tenant_id=DNSFILTER_ORG_ID,
        primary_domain="atomic.local",
        profile=profile,
        application_id="dnsfilter-management-api",
        status=status,
        consent_transaction_id="owner-approved-dnsfilter-read",
        created_at=now,
        validated_at=now if status is BoundaryStatus.VALIDATED else None,
    )


def context(capability, *, client_id=None, organization_id="aot"):
    return ConnectorContext(
        correlation_id="corr-dnsfilter-001",
        principal_id="person-al",
        organization_id=organization_id,
        client_id=client_id,
        capability=capability,
        mode="observe",
    )


def build(*, record=None):
    repo = InMemoryClientBoundaryRepository()
    if record is not False:
        repo.add(record or boundary())
    secrets = FakeSecrets()
    audit = FakeAudit()
    FakeClient.calls.clear()
    FakeClient.response = {"data": []}
    connector = DnsFilterConnector(
        secrets=secrets,
        transport=FakeTransport(),
        audit=audit,
        boundaries=repo,
        client_factory=FakeClient,
    )
    return connector, secrets, audit


def test_agent_search_derives_organization_scope_from_boundary():
    connector, secrets, audit = build()
    FakeClient.response = {"data": [{"id": "agent-1", "attributes": {"hostname": "Atomic-50291"}}]}
    result = connector.execute(
        ConnectorRequest(
            context("dnsfilter.user_agent.search"),
            {"company_id": 333, "search": "Atomic-50291", "agent_state": "protected"},
        )
    )
    assert result.data["data"][0]["attributes"]["hostname"] == "Atomic-50291"
    path, params = FakeClient.calls[-1]
    assert path == "/v1/user_agents"
    assert params["organization_ids"] == [9001]
    assert params["search"] == "Atomic-50291"
    assert params["agent_state"] == "protected"
    assert secrets.calls == ["dnsfilter.readonly"]
    assert audit.events[0][1]["organization_boundary_validated"] is True


def test_network_search_requires_returned_organization_relationship():
    connector, _, _ = build()
    FakeClient.response = {
        "data": [{
            "id": "77",
            "relationships": {"organization": {"data": {"id": DNSFILTER_ORG_ID}}},
        }]
    }
    connector.execute(
        ConnectorRequest(context("dnsfilter.network.search"), {"company_id": 333})
    )
    path, params = FakeClient.calls[-1]
    assert path == "/v1/networks/msp"
    assert params["organization_id"] == 9001


def test_cross_client_network_response_fails_closed():
    connector, _, _ = build()
    FakeClient.response = {
        "data": [{
            "id": "77",
            "relationships": {"organization": {"data": {"id": "9999"}}},
        }]
    }
    with pytest.raises(ConnectorAuthorizationError, match="crossed"):
        connector.execute(
            ConnectorRequest(context("dnsfilter.network.search"), {"company_id": 333})
        )


def test_organization_scope_cannot_be_supplied_by_caller():
    connector, secrets, _ = build()
    with pytest.raises(ConnectorAuthorizationError, match="server-derived"):
        connector.execute(
            ConnectorRequest(
                context("dnsfilter.user_agent.search"),
                {"company_id": 333, "organization_ids": [9999]},
            )
        )
    assert secrets.calls == []
    assert FakeClient.calls == []


def test_missing_or_unvalidated_boundary_fails_before_secret_resolution():
    connector, secrets, _ = build(record=False)
    with pytest.raises(ConnectorAuthorizationError, match="validated"):
        connector.execute(
            ConnectorRequest(context("dnsfilter.policy.search"), {"company_id": 333})
        )
    assert secrets.calls == []

    connector, secrets, _ = build(record=boundary(status=BoundaryStatus.PENDING))
    with pytest.raises(ConnectorAuthorizationError, match="validated"):
        connector.execute(
            ConnectorRequest(context("dnsfilter.policy.search"), {"company_id": 333})
        )
    assert secrets.calls == []


def test_client_context_must_match_company():
    connector, secrets, _ = build()
    with pytest.raises(ConnectorAuthorizationError, match="does not match"):
        connector.execute(
            ConnectorRequest(
                context("dnsfilter.policy.search", client_id="999"),
                {"company_id": 333},
            )
        )
    assert secrets.calls == []


def test_agent_state_and_page_size_are_bounded_before_provider_call():
    connector, secrets, _ = build()
    with pytest.raises(ConnectorConfigurationError, match="agent_state"):
        connector.execute(
            ConnectorRequest(
                context("dnsfilter.user_agent.search"),
                {"company_id": 333, "agent_state": "mystery"},
            )
        )
    with pytest.raises(ConnectorConfigurationError, match="page_size"):
        connector.execute(
            ConnectorRequest(
                context("dnsfilter.network.search"),
                {"company_id": 333, "page_size": 9999},
            )
        )
    assert secrets.calls == []
    assert FakeClient.calls == []
