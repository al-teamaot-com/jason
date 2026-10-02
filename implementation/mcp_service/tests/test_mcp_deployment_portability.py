from __future__ import annotations

from pathlib import Path

import pytest

from jason_mcp.deployment_config import (
    McpDeploymentConfigurationError,
    load_mcp_deployment_configuration,
    validate_mcp_deployment_configuration,
)


def test_generic_mcp_source_contains_no_aot_identity_defaults():
    root = Path(__file__).resolve().parents[3]
    source = (
        root
        / "implementation/mcp_service/src/jason_mcp/server.py"
    ).read_text(encoding="utf-8")
    config_source = (
        root
        / "implementation/mcp_service/src/jason_mcp/deployment_config.py"
    ).read_text(encoding="utf-8")

    combined = source + "\n" + config_source
    assert "f7054323-d52b-4863-8c2f-1898f0b6077c" not in combined
    assert "9b9996e9-5c34-48b7-948c-f44f89352f89" not in combined
    assert "teamaot.com" not in combined
    assert "teamaom.com" not in combined


def test_mcp_entrypoint_configuration_fails_closed_without_tenant_and_client():
    config = load_mcp_deployment_configuration(
        {
            "JASON_MCP_RESOURCE_URL": "http://127.0.0.1:8000/mcp",
        }
    )
    with pytest.raises(McpDeploymentConfigurationError) as exc:
        validate_mcp_deployment_configuration(config)
    message = str(exc.value)
    assert "JASON_MCP_ENTRA_CLIENT_ID" in message
    assert "JASON_MCP_ENTRA_TENANT_ID" in message


def test_mcp_accepts_explicit_provider_neutral_identity():
    config = load_mcp_deployment_configuration(
        {
            "JASON_MCP_ENTRA_TENANT_ID": (
                "00000000-0000-0000-0000-000000000001"
            ),
            "JASON_MCP_ENTRA_CLIENT_ID": (
                "00000000-0000-0000-0000-000000000002"
            ),
            "JASON_MCP_RESOURCE_URL": "https://mcp.example.invalid/mcp",
            "JASON_MCP_OAUTH_ISSUER_URL": "https://mcp.example.invalid/",
            "JASON_MCP_AUTOENROLL_DOMAINS": "example.invalid",
        }
    )
    validate_mcp_deployment_configuration(config)
    assert config.autoenroll_domains == frozenset({"example.invalid"})
    assert "mcp.example.invalid" in config.allowed_hosts
    assert "https://mcp.example.invalid" in config.allowed_origins


def test_autoenroll_domains_default_empty_and_transport_defaults_are_generic():
    config = load_mcp_deployment_configuration(
        {
            "JASON_MCP_ENTRA_TENANT_ID": (
                "00000000-0000-0000-0000-000000000001"
            ),
            "JASON_MCP_ENTRA_CLIENT_ID": (
                "00000000-0000-0000-0000-000000000002"
            ),
        }
    )
    assert config.autoenroll_domains == frozenset()
    assert config.resource_url == "http://127.0.0.1:8000/mcp"
    assert "127.0.0.1:8000" in config.allowed_hosts
    assert "https://chatgpt.com" in config.allowed_origins


def test_allowed_hosts_and_origins_can_be_explicitly_configured():
    config = load_mcp_deployment_configuration(
        {
            "JASON_MCP_ENTRA_TENANT_ID": "tenant",
            "JASON_MCP_ENTRA_CLIENT_ID": "client",
            "JASON_MCP_ALLOWED_HOSTS": "mcp.example.invalid,mcp.example.invalid:*",
            "JASON_MCP_ALLOWED_ORIGINS": (
                "https://chatgpt.com,https://mcp.example.invalid"
            ),
        }
    )
    assert config.allowed_hosts == (
        "mcp.example.invalid",
        "mcp.example.invalid:*",
    )
    assert config.allowed_origins == (
        "https://chatgpt.com",
        "https://mcp.example.invalid",
    )
