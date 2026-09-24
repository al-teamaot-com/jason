from datetime import datetime, timezone
import json
from pathlib import Path

from kernel.capabilities import CapabilityLifecycle
from orchestrator.dnsfilter_mcp_mutation_capability_catalog import (
    DNSFILTER_MCP_MUTATION_PROVIDER_CAPABILITIES,
    DNSFILTER_MCP_MUTATION_TOOLS,
    dnsfilter_mcp_mutation_capabilities,
)

NOW = datetime(2026, 9, 24, tzinfo=timezone.utc)


def test_all_public_confirm_gated_writes_have_dormant_capability_contracts():
    catalog = json.loads(
        Path("docs/reference/DNSFilter-MCP-Tool-Catalog-2026-09-24.json").read_text()
    )
    confirm_gated = {
        tool["name"]
        for tool in catalog["tools"]
        if (
            (tool.get("inputSchema") or {})
            .get("properties", {})
            .get("confirm", {})
            .get("const")
            is True
        )
    }
    assert set(DNSFILTER_MCP_MUTATION_TOOLS.values()) == confirm_gated
    assert set(DNSFILTER_MCP_MUTATION_PROVIDER_CAPABILITIES) == set(DNSFILTER_MCP_MUTATION_TOOLS)
    assert len(set(DNSFILTER_MCP_MUTATION_PROVIDER_CAPABILITIES.values())) == len(confirm_gated)
    assert all(value.startswith("dnsfilter_mcp.") for value in DNSFILTER_MCP_MUTATION_PROVIDER_CAPABILITIES.values())
    definitions = dnsfilter_mcp_mutation_capabilities(NOW)
    assert len(definitions) == len(confirm_gated)
    for item in definitions:
        assert item.lifecycle_status is CapabilityLifecycle.BUILDING
        assert item.approval.required is True
        assert item.maximum_attempts == 1
        assert item.metadata["provider_confirmation_required"] == "true"
        assert item.metadata["activation_state"] == "source_only_not_registered"
