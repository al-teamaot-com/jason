from __future__ import annotations

import json
from pathlib import Path

from connectors.dnsfilter.mcp_connector import _CAPABILITY_TO_TOOL
from orchestrator.dnsfilter_mcp_mutation_capability_catalog import (
    DNSFILTER_MCP_MUTATION_TOOLS,
)


CATALOG = (
    Path(__file__).resolve().parents[3]
    / "docs/reference/DNSFilter-MCP-Tool-Catalog-2026-09-24.json"
)


def _tools():
    payload = json.loads(CATALOG.read_text(encoding="utf-8"))
    assert payload["server"]["name"] == "dnsfilter-public"
    assert payload["server"]["protocolVersion"] == "2025-06-18"
    assert payload["tool_count"] == len(payload["tools"])
    return {item["name"]: item for item in payload["tools"]}


def test_registered_mcp_reads_exist_are_readonly_and_accept_exact_org_scope():
    tools = _tools()
    for tool_name in _CAPABILITY_TO_TOOL.values():
        tool = tools[tool_name]
        assert tool["annotations"]["readOnlyHint"] is True
        properties = tool["inputSchema"].get("properties", {})
        assert "organization_id" in properties
        assert properties["organization_id"]["type"] in {"integer", "number"}


def test_dormant_mutation_tools_exist_and_require_provider_confirmation():
    tools = _tools()
    assert len(DNSFILTER_MCP_MUTATION_TOOLS) == 25
    for tool_name in DNSFILTER_MCP_MUTATION_TOOLS.values():
        tool = tools[tool_name]
        assert tool["annotations"]["readOnlyHint"] is False
        schema = tool["inputSchema"]
        properties = schema.get("properties", {})
        assert "confirm" in properties
        assert properties["confirm"].get("const") is True
        assert "confirm" in schema.get("required", [])


def test_no_generic_arbitrary_mcp_tool_capability_is_registered():
    assert all("*" not in name for name in _CAPABILITY_TO_TOOL)
    assert all("*" not in name for name in DNSFILTER_MCP_MUTATION_TOOLS)
