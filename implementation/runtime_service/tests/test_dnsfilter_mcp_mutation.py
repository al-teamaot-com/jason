from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from connectors.core.contracts import (
    ConnectorAuthorizationError,
    ConnectorContext,
    ConnectorRequest,
    ConnectorTransportError,
)
from connectors.dnsfilter.mcp_oauth import DnsFilterMcpOAuthStore
from kernel.client_boundaries import (
    BoundaryStatus,
    ClientBoundary,
    InMemoryClientBoundaryRepository,
)
from orchestrator.dnsfilter_mcp_mutation_capability_catalog import (
    DNSFILTER_MCP_MUTATION_PROVIDER_CAPABILITIES,
)
from jason_runtime.dnsfilter_mcp_mutation import (
    DnsFilterMcpGovernedConnector,
    DnsFilterMutationUnknownOutcomeError,
    _ALLOWED,
    _REQUIRED,
)

ORG_ID = 1110483
POLICY_ID = 320854
BLOCK_CAP = DNSFILTER_MCP_MUTATION_PROVIDER_CAPABILITIES[
    "dns.protection.policy.domain.block.add"
]
CREATE_CAP = DNSFILTER_MCP_MUTATION_PROVIDER_CAPABILITIES[
    "dns.protection.policy.create"
]
class FakeAudit:
    def __init__(self):
        self.events = []

    def record(self, event_type, context, details):
        self.events.append((event_type, dict(details)))


class FakeClient:
    calls = []
    domains = set()
    cross_org = False
    fail_mutation = False

    def __init__(self, store):
        self.store = store

    @classmethod
    def reset(cls):
        cls.calls = []
        cls.domains = set()
        cls.cross_org = False
        cls.fail_mutation = False

    def call_tool(self, tool, arguments):
        args = dict(arguments)
        self.calls.append((tool, args))
        if tool == "get_policy":
            org = 999999 if self.cross_org else ORG_ID
            return {
                "data": {
                    "id": str(POLICY_ID),
                    "attributes": {
                        "organization_id": org,
                        "blacklist_domains": sorted(self.domains),
                        "whitelist_domains": [],
                        "blacklist_categories": [],
                    },
                    "relationships": {
                        "organization": {"data": {"id": str(org)}},
                    },
                }
            }
        if tool == "add_blocklist_domain":
            if self.fail_mutation:
                raise ConnectorTransportError("synthetic transport failure")
            assert args["confirm"] is True
            self.domains.add(args["domain"])
            return {"status": "accepted"}
        if tool == "create_policy":
            assert args["confirm"] is True
            return {
                "data": {
                    "id": "444001",
                    "attributes": {
                        "organization_id": ORG_ID,
                        "name": args["name"],
                    },
                    "relationships": {
                        "organization": {"data": {"id": str(ORG_ID)}},
                    },
                }
            }
        raise AssertionError(f"unexpected fake tool call: {tool}")


def boundary(*, org_id=ORG_ID):
    now = datetime(2026, 9, 24, tzinfo=timezone.utc)
    return ClientBoundary(
        id="dnsfilter-aot-boundary",
        client_id="0",
        provider="dnsfilter",
        external_tenant_id=str(org_id),
        primary_domain="teamaot.com",
        profile="dnsfilter-organization-read",
        application_id="dnsfilter-management-api",
        status=BoundaryStatus.VALIDATED,
        consent_transaction_id="owner-approved-dnsfilter-read",
        created_at=now,
        consented_at=now,
        validated_at=now,
    )
def context(capability):
    return ConnectorContext(
        correlation_id="corr-dnsfilter-write-local",
        principal_id="person-al",
        organization_id="aot",
        client_id="0",
        capability=capability,
        mode="execute",
    )


def build(tmp_path, *, record=None):
    repo = InMemoryClientBoundaryRepository()
    repo.add(record or boundary())
    audit = FakeAudit()
    FakeClient.reset()
    connector = DnsFilterMcpGovernedConnector(
        oauth_store=DnsFilterMcpOAuthStore(tmp_path / "oauth.sqlite3"),
        audit=audit,
        boundaries=repo,
        client_factory=FakeClient,
    )
    return connector, audit


def test_all_25_mutation_capabilities_are_present_but_not_enabled_by_default(
    tmp_path, monkeypatch
):
    connector, _ = build(tmp_path)
    assert len(connector.mutation_capabilities) == 25
    assert set(connector.mutation_capabilities) == set(
        DNSFILTER_MCP_MUTATION_PROVIDER_CAPABILITIES.values()
    )
    monkeypatch.delenv("JASON_DNSFILTER_MCP_MUTATION_ENABLED", raising=False)
    with pytest.raises(PermissionError, match="EXECUTION_DISABLED"):
        connector.prepare_governed_execution(
            ConnectorRequest(
                context(BLOCK_CAP),
                {"company_id": 0, "policy_id": POLICY_ID, "domain": "example.com"},
            )
        )
    assert FakeClient.calls == []
def test_prepare_injects_scope_and_confirm_after_preflight(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("JASON_DNSFILTER_MCP_MUTATION_ENABLED", "true")
    connector, audit = build(tmp_path)
    prepared = connector.prepare_governed_execution(
        ConnectorRequest(
            context(BLOCK_CAP),
            {
                "company_id": 0,
                "policy_id": POLICY_ID,
                "domain": "Example.COM",
            },
        )
    )
    assert prepared.provider_capability == BLOCK_CAP
    assert prepared.action_method == "MCP_TOOL_CALL"
    assert prepared.resource_identifier == str(POLICY_ID)
    assert prepared.payload["domain"] == "example.com"
    assert prepared.payload["confirm"] is True
    assert "organization_id" not in prepared.payload
    assert prepared.symbolic_resolutions["organization_id"] == ORG_ID
    assert FakeClient.calls == [
        (
            "get_policy",
            {"policy_id": POLICY_ID, "include_relationships": True},
        )
    ]
    assert audit.events[-1][0] == "connector.mutation.prepared"


def test_org_scoped_create_injects_mapped_organization(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("JASON_DNSFILTER_MCP_MUTATION_ENABLED", "true")
    connector, _ = build(tmp_path)
    prepared = connector.prepare_governed_execution(
        ConnectorRequest(
            context(CREATE_CAP),
            {"company_id": 0, "name": "Local Test Policy"},
        )
    )
    assert prepared.payload["organization_id"] == ORG_ID
    assert prepared.payload["confirm"] is True
@pytest.mark.parametrize(
    "extra",
    [
        {"organization_id": ORG_ID},
        {"target_organization_id": ORG_ID},
        {"msp_id": 1537},
        {"confirm": True},
    ],
)
def test_caller_cannot_supply_provider_scope_or_confirmation(
    tmp_path, monkeypatch, extra
):
    monkeypatch.setenv("JASON_DNSFILTER_MCP_MUTATION_ENABLED", "true")
    connector, _ = build(tmp_path)
    with pytest.raises(ConnectorAuthorizationError, match="server-derived"):
        connector.prepare_governed_execution(
            ConnectorRequest(
                context(BLOCK_CAP),
                {
                    "company_id": 0,
                    "policy_id": POLICY_ID,
                    "domain": "example.com",
                    **extra,
                },
            )
        )


def test_cross_organization_target_fails_before_mutation(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("JASON_DNSFILTER_MCP_MUTATION_ENABLED", "true")
    connector, _ = build(tmp_path)
    FakeClient.cross_org = True
    with pytest.raises(ConnectorAuthorizationError, match="boundary"):
        connector.prepare_governed_execution(
            ConnectorRequest(
                context(BLOCK_CAP),
                {"company_id": 0, "policy_id": POLICY_ID, "domain": "example.com"},
            )
        )
    assert not any(tool == "add_blocklist_domain" for tool, _ in FakeClient.calls)
def test_execute_is_exactly_once_and_requires_post_write_readback(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("JASON_DNSFILTER_MCP_MUTATION_ENABLED", "true")
    connector, _ = build(tmp_path)
    prepared = connector.prepare_governed_execution(
        ConnectorRequest(
            context(BLOCK_CAP),
            {"company_id": 0, "policy_id": POLICY_ID, "domain": "example.com"},
        )
    )
    result = connector.execute_governed_execution(prepared)
    writes = [
        args for tool, args in FakeClient.calls
        if tool == "add_blocklist_domain"
    ]
    assert len(writes) == 1
    assert writes[0]["confirm"] is True
    assert result.data["jasonVerification"]["readbackVerified"] is True
    assert "example.com" in FakeClient.domains
    assert FakeClient.calls[-1][0] == "get_policy"


def test_execution_plan_payload_tamper_fails_before_provider_write(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("JASON_DNSFILTER_MCP_MUTATION_ENABLED", "true")
    connector, _ = build(tmp_path)
    prepared = connector.prepare_governed_execution(
        ConnectorRequest(
            context(BLOCK_CAP),
            {"company_id": 0, "policy_id": POLICY_ID, "domain": "example.com"},
        )
    )
    tampered = replace(
        prepared,
        payload={**dict(prepared.payload), "domain": "evil.example"},
    )
    with pytest.raises(PermissionError, match="payload binding"):
        connector.execute_governed_execution(tampered)
    assert not any(tool == "add_blocklist_domain" for tool, _ in FakeClient.calls)
def test_transport_ambiguity_never_retries_provider_mutation(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("JASON_DNSFILTER_MCP_MUTATION_ENABLED", "true")
    connector, audit = build(tmp_path)
    prepared = connector.prepare_governed_execution(
        ConnectorRequest(
            context(BLOCK_CAP),
            {"company_id": 0, "policy_id": POLICY_ID, "domain": "example.com"},
        )
    )
    FakeClient.fail_mutation = True
    with pytest.raises(DnsFilterMutationUnknownOutcomeError):
        connector.execute_governed_execution(prepared)
    writes = [
        args for tool, args in FakeClient.calls
        if tool == "add_blocklist_domain"
    ]
    assert len(writes) == 1
    assert any(
        event == "connector.mutation.unknown_outcome"
        for event, _ in audit.events
    )

def test_every_provider_mutation_tool_has_bounded_argument_contract():
    expected_tools = {
        provider_capability.split("dnsfilter_mcp.", 1)[1]
        for provider_capability in DNSFILTER_MCP_MUTATION_PROVIDER_CAPABILITIES.values()
    }
    assert set(_ALLOWED) == expected_tools
    assert set(_REQUIRED) == expected_tools
    assert all("company_id" in allowed for allowed in _ALLOWED.values())


def test_direct_execute_rejects_mutation_path(tmp_path, monkeypatch):
    monkeypatch.setenv("JASON_DNSFILTER_MCP_MUTATION_ENABLED", "true")
    connector, _ = build(tmp_path)
    with pytest.raises(ConnectorAuthorizationError, match="execution-plan"):
        connector.execute(
            ConnectorRequest(
                context(BLOCK_CAP),
                {"company_id": 0, "policy_id": POLICY_ID, "domain": "example.com"},
            )
        )
    assert FakeClient.calls == []

def test_all_25_argument_contracts_match_provider_snapshot():
    catalog = json.loads(
        Path(
            "docs/reference/DNSFilter-MCP-Tool-Catalog-2026-09-24.json"
        ).read_text()
    )
    provider_derived = {
        "confirm",
        "organization_id",
        "target_organization_id",
        "organization_ids",
        "msp_id",
    }
    confirm_gated = {
        tool["name"]: tool["inputSchema"]
        for tool in catalog["tools"]
        if (
            (tool.get("inputSchema") or {})
            .get("properties", {})
            .get("confirm", {})
            .get("const")
            is True
        )
    }
    assert set(confirm_gated) == set(_ALLOWED) == set(_REQUIRED)
    for tool_name, schema in confirm_gated.items():
        provider_properties = set((schema.get("properties") or {}))
        expected_allowed = (
            provider_properties - provider_derived
        ) | {"company_id"}
        expected_required = set(schema.get("required") or ()) - provider_derived
        assert _ALLOWED[tool_name] == expected_allowed
        assert _REQUIRED[tool_name] == expected_required
