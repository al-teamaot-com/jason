from __future__ import annotations

from datetime import datetime, timezone

import pytest

from connectors.core.contracts import (
    ConnectorAuthorizationError,
    ConnectorConfigurationError,
    ConnectorContext,
    ConnectorRequest,
)
from connectors.dnsfilter.mcp_connector import DnsFilterMcpConnector
from connectors.dnsfilter.mcp_oauth import DnsFilterMcpOAuthStore
from kernel.client_boundaries import (
    BoundaryStatus,
    ClientBoundary,
    InMemoryClientBoundaryRepository,
)

COMPANY_ID = "333"
ORG_ID = "9001"


class FakeAudit:
    def __init__(self): self.events = []
    def record(self, event_type, context, details):
        self.events.append((event_type, dict(details)))


class FakeClient:
    calls = []
    response = {}
    def __init__(self, store):
        self.store = store
    def call_tool(self, tool, arguments):
        self.calls.append((tool, dict(arguments)))
        return dict(self.response)


def boundary(*, status=BoundaryStatus.VALIDATED):
    now = datetime(2026, 9, 24, tzinfo=timezone.utc)
    return ClientBoundary(
        id="dnsfilter-boundary-333",
        client_id=COMPANY_ID,
        provider="dnsfilter",
        external_tenant_id=ORG_ID,
        primary_domain="atomic.local",
        profile="dnsfilter-organization-read",
        application_id="dnsfilter-management-api",
        status=status,
        consent_transaction_id="owner-approved-dnsfilter-read",
        created_at=now,
        validated_at=now if status is BoundaryStatus.VALIDATED else None,
    )


def context(capability, *, client_id=None):
    return ConnectorContext(
        correlation_id="corr-dnsfilter-mcp",
        principal_id="person-al",
        organization_id="aot",
        client_id=client_id,
        capability=capability,
        mode="observe",
    )


def build(tmp_path, *, record=None):
    repo = InMemoryClientBoundaryRepository()
    if record is not False:
        repo.add(record or boundary())
    FakeClient.calls.clear()
    FakeClient.response = {}
    audit = FakeAudit()
    connector = DnsFilterMcpConnector(
        oauth_store=DnsFilterMcpOAuthStore(tmp_path / "oauth.sqlite3"),
        audit=audit,
        boundaries=repo,
        client_factory=FakeClient,
    )
    return connector, audit


def test_query_search_injects_exact_mapped_organization(tmp_path):
    connector, audit = build(tmp_path)
    FakeClient.response = {"organization_id": ORG_ID, "data": []}
    result = connector.execute(
        ConnectorRequest(
            context("dnsfilter_mcp.query_logs.search"),
            {
                "company_id": 333,
                "from": "2026-09-23T00:00:00Z",
                "to": "2026-09-24T00:00:00Z",
                "fqdn": "example.com",
            },
        )
    )
    tool, arguments = FakeClient.calls[-1]
    assert tool == "search_query_logs"
    assert arguments["organization_id"] == 9001
    assert arguments["fqdn"] == "example.com"
    assert result.provider == "dnsfilter_mcp"
    assert audit.events[0][1]["organization_boundary_validated"] is True


def test_caller_cannot_supply_provider_scope_or_confirmation(tmp_path):
    connector, _ = build(tmp_path)
    for extra in (
        {"organization_id": 9999},
        {"organization_ids": [9999]},
        {"msp_id": 10},
        {"confirm": True},
    ):
        with pytest.raises(ConnectorAuthorizationError, match="server-derived"):
            connector.execute(
                ConnectorRequest(
                    context("dnsfilter_mcp.query_logs.search"),
                    {
                        "company_id": 333,
                        "from": "2026-09-23",
                        "to": "2026-09-24",
                        **extra,
                    },
                )
            )
    assert FakeClient.calls == []


def test_response_with_wrong_organization_fails_closed(tmp_path):
    connector, _ = build(tmp_path)
    FakeClient.response = {"organization_id": 9999, "data": []}
    with pytest.raises(ConnectorAuthorizationError, match="crossed"):
        connector.execute(
            ConnectorRequest(
                context("dnsfilter_mcp.stale_agents.search"),
                {"company_id": 333, "days": 30},
            )
        )


def test_missing_boundary_and_bad_page_size_fail_before_provider_call(tmp_path):
    connector, _ = build(tmp_path, record=False)
    with pytest.raises(ConnectorAuthorizationError, match="validated"):
        connector.execute(
            ConnectorRequest(
                context("dnsfilter_mcp.stale_agents.search"),
                {"company_id": 333},
            )
        )
    connector, _ = build(tmp_path)
    with pytest.raises(ConnectorConfigurationError, match="per_page"):
        connector.execute(
            ConnectorRequest(
                context("dnsfilter_mcp.query_logs.search"),
                {
                    "company_id": 333,
                    "from": "2026-09-23",
                    "to": "2026-09-24",
                    "per_page": 101,
                },
            )
        )
    assert FakeClient.calls == []



def test_autotask_self_company_zero_is_valid_mcp_boundary(tmp_path):
    record = boundary()
    record = record.__class__(
        id="dnsfilter-boundary-aot-self",
        client_id="0",
        provider=record.provider,
        external_tenant_id=record.external_tenant_id,
        primary_domain="teamaot.com",
        profile=record.profile,
        application_id=record.application_id,
        status=record.status,
        consent_transaction_id=record.consent_transaction_id,
        created_at=record.created_at,
        validated_at=record.validated_at,
    )
    connector, _ = build(tmp_path, record=record)
    FakeClient.response = {"organization_id": ORG_ID, "data": []}
    result = connector.execute(
        ConnectorRequest(
            context("dnsfilter_mcp.stale_agents.search", client_id="0"),
            {"company_id": 0, "days": 30},
        )
    )
    assert result.provider == "dnsfilter_mcp"
    assert FakeClient.calls[-1][1]["organization_id"] == 9001

def test_client_context_must_match_selected_company(tmp_path):
    connector, _ = build(tmp_path)
    with pytest.raises(ConnectorAuthorizationError, match="does not match"):
        connector.execute(
            ConnectorRequest(
                context("dnsfilter_mcp.stale_agents.search", client_id="999"),
                {"company_id": 333},
            )
        )
