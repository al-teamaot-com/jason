from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping
from urllib.parse import urlparse
import os


class McpDeploymentConfigurationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class McpDeploymentConfiguration:
    tenant_id: str
    client_id: str
    required_scope: str
    resource_url: str
    oauth_request_scope: str
    oauth_issuer_url: str
    autoenroll_domains: frozenset[str]
    allowed_hosts: tuple[str, ...]
    allowed_origins: tuple[str, ...]


def _split_csv(value: str) -> tuple[str, ...]:
    return tuple(
        item.strip()
        for item in value.split(",")
        if item.strip()
    )


def _resource_defaults(resource_url: str) -> tuple[str, str]:
    parsed = urlparse(resource_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise McpDeploymentConfigurationError(
            "JASON_MCP_RESOURCE_URL must be an absolute HTTP(S) URL"
        )

    host = parsed.hostname
    if parsed.port is not None:
        canonical_host = f"{host}:{parsed.port}"
    else:
        canonical_host = host

    origin = f"{parsed.scheme}://{canonical_host}"
    return canonical_host, origin


def load_mcp_deployment_configuration(
    environment: Mapping[str, str] | None = None,
) -> McpDeploymentConfiguration:
    env = os.environ if environment is None else environment

    tenant_id = str(env.get("JASON_MCP_ENTRA_TENANT_ID", "")).strip()
    client_id = str(env.get("JASON_MCP_ENTRA_CLIENT_ID", "")).strip()
    required_scope = str(
        env.get("JASON_MCP_REQUIRED_SCOPE", "Jason.Read")
    ).strip()
    resource_url = str(
        env.get(
            "JASON_MCP_RESOURCE_URL",
            "http://127.0.0.1:8000/mcp",
        )
    ).strip()

    canonical_host, default_origin = _resource_defaults(resource_url)

    oauth_request_scope = str(
        env.get(
            "JASON_MCP_OAUTH_REQUEST_SCOPE",
            resource_url.rstrip("/") + "/" + required_scope,
        )
    ).strip()
    oauth_issuer_url = str(
        env.get(
            "JASON_MCP_OAUTH_ISSUER_URL",
            resource_url.removesuffix("/mcp").rstrip("/") + "/",
        )
    ).strip()

    autoenroll_domains = frozenset(
        item.casefold()
        for item in _split_csv(
            str(env.get("JASON_MCP_AUTOENROLL_DOMAINS", ""))
        )
    )

    allowed_hosts = _split_csv(
        str(env.get("JASON_MCP_ALLOWED_HOSTS", ""))
    )
    if not allowed_hosts:
        allowed_hosts = (
            canonical_host,
            f"{urlparse(resource_url).hostname}:*",
        )

    allowed_origins = _split_csv(
        str(env.get("JASON_MCP_ALLOWED_ORIGINS", ""))
    )
    if not allowed_origins:
        allowed_origins = (
            "https://chatgpt.com",
            "https://chatgpt.com:*",
            default_origin,
            default_origin + ":*",
        )

    return McpDeploymentConfiguration(
        tenant_id=tenant_id,
        client_id=client_id,
        required_scope=required_scope,
        resource_url=resource_url,
        oauth_request_scope=oauth_request_scope,
        oauth_issuer_url=oauth_issuer_url,
        autoenroll_domains=autoenroll_domains,
        allowed_hosts=tuple(dict.fromkeys(allowed_hosts)),
        allowed_origins=tuple(dict.fromkeys(allowed_origins)),
    )


def validate_mcp_deployment_configuration(
    config: McpDeploymentConfiguration,
) -> None:
    required = {
        "JASON_MCP_ENTRA_TENANT_ID": config.tenant_id,
        "JASON_MCP_ENTRA_CLIENT_ID": config.client_id,
        "JASON_MCP_REQUIRED_SCOPE": config.required_scope,
        "JASON_MCP_RESOURCE_URL": config.resource_url,
        "JASON_MCP_OAUTH_ISSUER_URL": config.oauth_issuer_url,
    }
    missing = sorted(
        name
        for name, value in required.items()
        if not str(value).strip()
    )
    if missing:
        raise McpDeploymentConfigurationError(
            "MCP deployment configuration is incomplete: "
            + ", ".join(missing)
        )

    for name, value in (
        ("JASON_MCP_RESOURCE_URL", config.resource_url),
        ("JASON_MCP_OAUTH_ISSUER_URL", config.oauth_issuer_url),
    ):
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise McpDeploymentConfigurationError(
                f"{name} must be an absolute HTTP(S) URL"
            )

    if not config.allowed_hosts:
        raise McpDeploymentConfigurationError(
            "MCP transport allowed-host set must not be empty"
        )
    if not config.allowed_origins:
        raise McpDeploymentConfigurationError(
            "MCP transport allowed-origin set must not be empty"
        )
