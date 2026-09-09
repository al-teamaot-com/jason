from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse


EXPECTED_RESOURCE = "https://mcp-jason.teamaot.com/mcp"
EXPECTED_ISSUER = "https://mcp-jason.teamaot.com/"
EXPECTED_SCOPE = (
    "https://mcp-jason.teamaot.com/mcp/Jason.Read"
)
EXPECTED_SHORT_SCOPE = "Jason.Read"

EXPECTED_TOOLS = {
    "jason_mcp_status",
    "discover_capabilities",
    "execute_read_capability",
}

EXPECTED_SERVER_SHA256 = (
    "118a016029f7c25e03f95110a1c114d64cddca85ccff1f7bf8d9d50addff8351"
)

TENANT_ID = "f7054323-d52b-4863-8c2f-1898f0b6077c"

EXPECTED_AUTHORIZATION_ENDPOINT = (
    "https://login.microsoftonline.com/"
    f"{TENANT_ID}/oauth2/v2.0/authorize"
)

EXPECTED_TOKEN_ENDPOINT = (
    "https://login.microsoftonline.com/"
    f"{TENANT_ID}/oauth2/v2.0/token"
)

EXPECTED_RESOURCE_METADATA = (
    "https://mcp-jason.teamaot.com/"
    ".well-known/oauth-protected-resource/mcp"
)


class SmokeFailure(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeFailure(message)


def request(
    base_url: str,
    method: str,
    path: str,
    *,
    host_header: str,
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], bytes]:
    parsed = urlparse(base_url)

    require(
        parsed.scheme in {"http", "https"},
        f"unsupported URL scheme: {parsed.scheme}",
    )

    connection_class = (
        http.client.HTTPSConnection
        if parsed.scheme == "https"
        else http.client.HTTPConnection
    )

    port = parsed.port

    if port is None:
        port = 443 if parsed.scheme == "https" else 80

    connection = connection_class(
        parsed.hostname,
        port,
        timeout=15,
    )

    request_headers = {
        "Host": host_header,
        "User-Agent": "Jason-MCP-Durability-Smoke/1.0",
    }

    if headers:
        request_headers.update(headers)

    connection.request(
        method,
        path,
        body=body,
        headers=request_headers,
    )

    response = connection.getresponse()
    payload = response.read()

    response_headers = {
        key.lower(): value
        for key, value in response.getheaders()
    }

    status = response.status

    connection.close()

    return status, response_headers, payload


def parse_json(payload: bytes, label: str) -> dict:
    try:
        result = json.loads(
            payload.decode("utf-8")
        )
    except Exception as exc:
        raise SmokeFailure(
            f"{label}: invalid JSON: {exc}"
        ) from exc

    require(
        isinstance(result, dict),
        f"{label}: JSON was not an object",
    )

    return result


def inspect_container(container: str) -> dict:
    script = r'''
import asyncio
import hashlib
import importlib.metadata
import json
from pathlib import Path

import jason_mcp.server as server
from mcp.server.transport_security import TransportSecurityMiddleware
from starlette.requests import Request


def _transport_request(
    host: str,
    *,
    origin: str | None = None,
) -> Request:
    headers = [
        (b"host", host.encode("ascii")),
        (b"content-type", b"application/json"),
    ]

    if origin is not None:
        headers.append(
            (b"origin", origin.encode("ascii"))
        )

    scope = {
        "type": "http",
        "asgi": {
            "version": "3.0",
            "spec_version": "2.3",
        },
        "http_version": "1.1",
        "server": ("127.0.0.1", 8000),
        "client": ("127.0.0.1", 12345),
        "scheme": "https",
        "method": "POST",
        "root_path": "",
        "path": "/mcp",
        "raw_path": b"/mcp",
        "query_string": b"",
        "headers": headers,
    }

    return Request(scope)


async def main():
    tools = await server.mcp.list_tools()

    path = Path(server.__file__)

    transport = TransportSecurityMiddleware(
        server.transport_security
    )

    expected_host_response = await transport.validate_request(
        _transport_request(
            "mcp-jason.teamaot.com"
        ),
        is_post=True,
    )

    expected_host_port_response = (
        await transport.validate_request(
            _transport_request(
                "mcp-jason.teamaot.com:443"
            ),
            is_post=True,
        )
    )

    hostile_host_response = await transport.validate_request(
        _transport_request(
            "hostile.invalid"
        ),
        is_post=True,
    )

    chatgpt_origin_response = (
        await transport.validate_request(
            _transport_request(
                "mcp-jason.teamaot.com",
                origin="https://chatgpt.com",
            ),
            is_post=True,
        )
    )

    hostile_origin_response = (
        await transport.validate_request(
            _transport_request(
                "mcp-jason.teamaot.com",
                origin="https://hostile.invalid",
            ),
            is_post=True,
        )
    )

    result = {
        "mcp_version": importlib.metadata.version("mcp"),
        "server_file": str(path),
        "server_sha256": hashlib.sha256(
            path.read_bytes()
        ).hexdigest(),
        "required_scope": server.JASON_REQUIRED_SCOPE,
        "oauth_request_scope": (
            server.JASON_OAUTH_REQUEST_SCOPE
        ),
        "resource_url": server.JASON_RESOURCE_URL,
        "oauth_issuer_url": (
            server.JASON_OAUTH_ISSUER_URL
        ),
        "tools": sorted(
            tool.name
            for tool in tools
        ),
        "transport_rebinding_enabled": (
            server.transport_security
            .enable_dns_rebinding_protection
        ),
        "transport_allowed_hosts": list(
            server.transport_security.allowed_hosts
        ),
        "transport_allowed_origins": list(
            server.transport_security.allowed_origins
        ),
        "expected_host_status": (
            None
            if expected_host_response is None
            else expected_host_response.status_code
        ),
        "expected_host_port_status": (
            None
            if expected_host_port_response is None
            else expected_host_port_response.status_code
        ),
        "hostile_host_status": (
            None
            if hostile_host_response is None
            else hostile_host_response.status_code
        ),
        "chatgpt_origin_status": (
            None
            if chatgpt_origin_response is None
            else chatgpt_origin_response.status_code
        ),
        "hostile_origin_status": (
            None
            if hostile_origin_response is None
            else hostile_origin_response.status_code
        ),
    }

    print(json.dumps(result))


asyncio.run(main())
'''

    raw = subprocess.check_output(
        [
            "docker",
            "exec",
            "-i",
            container,
            "python",
            "-c",
            script,
        ],
        text=True,
    )

    return json.loads(raw)


def main() -> int:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8765",
    )

    parser.add_argument(
        "--container",
        default="jason-mcp-pilot",
    )

    parser.add_argument(
        "--expected-host",
        default="mcp-jason.teamaot.com",
    )

    parser.add_argument(
        "--verify-real-transport-path",
        action="store_true",
        help=(
            "verify Host/Origin rejection through the "
            "actual unauthenticated HTTP /mcp path"
        ),
    )

    args = parser.parse_args()

    print("============================================================")
    print(" JASON MCP DURABILITY SMOKE")
    print("============================================================")

    # --------------------------------------------------------
    # Installed source / tool contract
    # --------------------------------------------------------

    print()
    print("=== INSTALLED MCP CONTRACT ===")

    info = inspect_container(args.container)

    print("MCP_VERSION =", info["mcp_version"])
    print("SERVER_FILE =", info["server_file"])
    print("SERVER_SHA256 =", info["server_sha256"])
    print("RESOURCE_URL =", info["resource_url"])
    print("JWT_SCOPE =", info["required_scope"])
    print(
        "OAUTH_REQUEST_SCOPE =",
        info["oauth_request_scope"],
    )
    print(
        "OAUTH_ISSUER =",
        info["oauth_issuer_url"],
    )

    for tool in info["tools"]:
        print("TOOL =", tool)

    require(
        info["mcp_version"] == "2.2.0",
        "unexpected MCP package version",
    )

    require(
        info["server_sha256"]
        == EXPECTED_SERVER_SHA256,
        "installed server.py does not match "
        "proven pilot source",
    )

    require(
        info["resource_url"] == EXPECTED_RESOURCE,
        "canonical MCP resource mismatch",
    )

    require(
        info["required_scope"]
        == EXPECTED_SHORT_SCOPE,
        "JWT validation scope mismatch",
    )

    require(
        info["oauth_request_scope"]
        == EXPECTED_SCOPE,
        "OAuth request scope mismatch",
    )

    require(
        info["oauth_issuer_url"]
        == EXPECTED_ISSUER,
        "OAuth compatibility issuer mismatch",
    )

    require(
        set(info["tools"]) == EXPECTED_TOOLS,
        "registered MCP tool surface mismatch",
    )

    print("TOOL_COUNT =", len(info["tools"]))
    print("EXACT_READ_TOOL_SURFACE = PASS")

    # --------------------------------------------------------
    # MCP transport security
    # --------------------------------------------------------

    print()
    print("=== TRANSPORT SECURITY ===")

    print(
        "REBINDING_PROTECTION =",
        info["transport_rebinding_enabled"],
    )
    print(
        "ALLOWED_HOSTS =",
        info["transport_allowed_hosts"],
    )
    print(
        "ALLOWED_ORIGINS =",
        info["transport_allowed_origins"],
    )
    print(
        "EXPECTED_HOST_STATUS =",
        info["expected_host_status"],
    )
    print(
        "EXPECTED_HOST_PORT_STATUS =",
        info["expected_host_port_status"],
    )
    print(
        "HOSTILE_HOST_STATUS =",
        info["hostile_host_status"],
    )
    print(
        "CHATGPT_ORIGIN_STATUS =",
        info["chatgpt_origin_status"],
    )
    print(
        "HOSTILE_ORIGIN_STATUS =",
        info["hostile_origin_status"],
    )

    require(
        info["transport_rebinding_enabled"] is True,
        "DNS rebinding protection is disabled",
    )

    require(
        info["expected_host_status"] is None,
        "canonical Jason Host was rejected",
    )

    require(
        info["expected_host_port_status"] is None,
        "Jason Host with port was rejected",
    )

    require(
        info["hostile_host_status"] == 421,
        "transport layer did not reject hostile Host "
        "with HTTP 421",
    )

    require(
        info["chatgpt_origin_status"] is None,
        "ChatGPT Origin was rejected",
    )

    require(
        info["hostile_origin_status"] == 403,
        "transport layer did not reject hostile Origin "
        "with HTTP 403",
    )

    print("HOST_VALIDATION = PASS")
    print("ORIGIN_VALIDATION = PASS")
    print("TRANSPORT_SECURITY = PASS")

    # --------------------------------------------------------
    # Actual unauthenticated HTTP transport path
    # --------------------------------------------------------

    if args.verify_real_transport_path:
        print()
        print("=== REAL MCP TRANSPORT PATH ===")

        transport_initialize = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {
                        "name": (
                            "jason-mcp-real-transport-smoke"
                        ),
                        "version": "1.0",
                    },
                },
            }
        ).encode("utf-8")

        transport_headers = {
            "Content-Type": "application/json",
            "Accept": (
                "application/json, text/event-stream"
            ),
        }

        valid_status, _, _ = request(
            args.base_url,
            "POST",
            "/mcp",
            host_header=args.expected_host,
            body=transport_initialize,
            headers=transport_headers,
        )

        hostile_host_status, _, _ = request(
            args.base_url,
            "POST",
            "/mcp",
            host_header="hostile.invalid",
            body=transport_initialize,
            headers=transport_headers,
        )

        hostile_origin_headers = dict(
            transport_headers
        )
        hostile_origin_headers["Origin"] = (
            "https://hostile.invalid"
        )

        hostile_origin_status, _, _ = request(
            args.base_url,
            "POST",
            "/mcp",
            host_header=args.expected_host,
            body=transport_initialize,
            headers=hostile_origin_headers,
        )

        chatgpt_origin_headers = dict(
            transport_headers
        )
        chatgpt_origin_headers["Origin"] = (
            "https://chatgpt.com"
        )

        chatgpt_origin_status, _, _ = request(
            args.base_url,
            "POST",
            "/mcp",
            host_header=args.expected_host,
            body=transport_initialize,
            headers=chatgpt_origin_headers,
        )

        print(
            "REAL_VALID_HOST_NO_AUTH =",
            valid_status,
        )
        print(
            "REAL_HOSTILE_HOST_NO_AUTH =",
            hostile_host_status,
        )
        print(
            "REAL_HOSTILE_ORIGIN_NO_AUTH =",
            hostile_origin_status,
        )
        print(
            "REAL_CHATGPT_ORIGIN_NO_AUTH =",
            chatgpt_origin_status,
        )

        require(
            valid_status == 401,
            "actual MCP path did not challenge "
            "valid unauthenticated Host with 401",
        )

        require(
            hostile_host_status == 421,
            "actual MCP path did not reject "
            "hostile Host with 421 before auth",
        )

        require(
            hostile_origin_status == 403,
            "actual MCP path did not reject "
            "hostile Origin with 403 before auth",
        )

        require(
            chatgpt_origin_status == 401,
            "actual MCP path rejected ChatGPT "
            "Origin instead of reaching auth",
        )

        print(
            "REAL_TRANSPORT_PATH = PASS"
        )

    # --------------------------------------------------------
    # Accepted host / health
    # --------------------------------------------------------

    print()
    print("=== HEALTH ===")

    status, _, payload = request(
        args.base_url,
        "GET",
        "/healthz",
        host_header=args.expected_host,
    )

    print("HTTP_STATUS =", status)

    require(
        status == 200,
        f"healthz expected 200, got {status}",
    )

    health = parse_json(payload, "healthz")

    require(
        health.get("status") == "ok",
        "healthz status mismatch",
    )

    require(
        health.get("mode") == "read-only",
        "healthz mode is not read-only",
    )

    print("HEALTH = PASS")

    # --------------------------------------------------------
    # Protected-resource metadata
    # --------------------------------------------------------

    print()
    print("=== PROTECTED RESOURCE METADATA ===")

    status, _, payload = request(
        args.base_url,
        "GET",
        "/.well-known/oauth-protected-resource/mcp",
        host_header=args.expected_host,
    )

    print("HTTP_STATUS =", status)

    require(
        status == 200,
        "protected-resource metadata "
        f"expected 200, got {status}",
    )

    metadata = parse_json(
        payload,
        "protected-resource metadata",
    )

    print("RESOURCE =", metadata.get("resource"))
    print(
        "AUTHORIZATION_SERVERS =",
        metadata.get("authorization_servers"),
    )
    print(
        "SCOPES_SUPPORTED =",
        metadata.get("scopes_supported"),
    )

    require(
        metadata.get("resource")
        == EXPECTED_RESOURCE,
        "protected-resource resource mismatch",
    )

    require(
        EXPECTED_ISSUER
        in metadata.get(
            "authorization_servers",
            [],
        ),
        "authorization server issuer missing",
    )

    require(
        EXPECTED_SCOPE
        in metadata.get(
            "scopes_supported",
            [],
        ),
        "full OAuth scope missing from "
        "protected-resource metadata",
    )

    print("PROTECTED_RESOURCE_METADATA = PASS")

    # --------------------------------------------------------
    # RFC 8414 authorization-server metadata
    # --------------------------------------------------------

    print()
    print("=== AUTHORIZATION SERVER METADATA ===")

    status, _, payload = request(
        args.base_url,
        "GET",
        "/.well-known/oauth-authorization-server",
        host_header=args.expected_host,
    )

    print("HTTP_STATUS =", status)

    require(
        status == 200,
        "authorization-server metadata "
        f"expected 200, got {status}",
    )

    auth_metadata = parse_json(
        payload,
        "authorization-server metadata",
    )

    print("ISSUER =", auth_metadata.get("issuer"))

    require(
        auth_metadata.get("issuer")
        == EXPECTED_ISSUER,
        "authorization-server issuer mismatch",
    )

    require(
        auth_metadata.get(
            "authorization_endpoint"
        )
        == EXPECTED_AUTHORIZATION_ENDPOINT,
        "Entra authorization endpoint mismatch",
    )

    require(
        auth_metadata.get("token_endpoint")
        == EXPECTED_TOKEN_ENDPOINT,
        "Entra token endpoint mismatch",
    )

    require(
        "S256"
        in auth_metadata.get(
            "code_challenge_methods_supported",
            [],
        ),
        "S256 is not advertised",
    )

    require(
        EXPECTED_SCOPE
        in auth_metadata.get(
            "scopes_supported",
            [],
        ),
        "full OAuth scope missing from "
        "authorization-server metadata",
    )

    print("ISSUER_EXACT_MATCH = PASS")
    print("S256 = PASS")
    print("AUTHORIZATION_SERVER_METADATA = PASS")

    # --------------------------------------------------------
    # Entra OIDC compatibility shim
    # --------------------------------------------------------

    print()
    print("=== OIDC COMPATIBILITY SHIM ===")

    status, _, payload = request(
        args.base_url,
        "GET",
        "/oauth/entra-openid-configuration",
        host_header=args.expected_host,
    )

    print("HTTP_STATUS =", status)

    require(
        status == 200,
        "OIDC compatibility shim "
        f"expected 200, got {status}",
    )

    oidc_metadata = parse_json(
        payload,
        "OIDC compatibility shim",
    )

    expected_entra_issuer = (
        "https://login.microsoftonline.com/"
        f"{TENANT_ID}/v2.0"
    )

    print(
        "OIDC_ISSUER =",
        oidc_metadata.get("issuer"),
    )

    require(
        str(
            oidc_metadata.get("issuer") or ""
        ).rstrip("/")
        == expected_entra_issuer.rstrip("/"),
        "OIDC shim Entra issuer mismatch",
    )

    require(
        "S256"
        in oidc_metadata.get(
            "code_challenge_methods_supported",
            [],
        ),
        "OIDC shim does not advertise S256",
    )

    print("OIDC_ISSUER = PASS")
    print("OIDC_S256 = PASS")
    print("OIDC_COMPATIBILITY_SHIM = PASS")

    # --------------------------------------------------------
    # Anonymous MCP request must challenge with OAuth metadata
    # --------------------------------------------------------

    print()
    print("=== ANONYMOUS MCP CHALLENGE ===")

    initialize = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {
                    "name": "jason-mcp-smoke",
                    "version": "1.0",
                },
            },
        }
    ).encode("utf-8")

    status, headers, _ = request(
        args.base_url,
        "POST",
        "/mcp",
        host_header=args.expected_host,
        body=initialize,
        headers={
            "Content-Type": "application/json",
            "Accept": (
                "application/json, text/event-stream"
            ),
        },
    )

    print("HTTP_STATUS =", status)

    require(
        status == 401,
        f"anonymous MCP expected 401, got {status}",
    )

    challenge = headers.get(
        "www-authenticate",
        "",
    )

    print(
        "WWW_AUTHENTICATE_PRESENT =",
        bool(challenge),
    )

    require(
        EXPECTED_RESOURCE_METADATA
        in challenge,
        "401 challenge missing correct "
        "resource_metadata pointer",
    )

    print("ANONYMOUS_401 = PASS")

    # --------------------------------------------------------
    # Final
    # --------------------------------------------------------

    print()
    print("============================================================")
    print(" MCP DURABILITY SMOKE = PASS")
    print("============================================================")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SmokeFailure as exc:
        print()
        print("============================================================")
        print(" MCP DURABILITY SMOKE = FAIL")
        print("============================================================")
        print("REASON =", exc)
        raise SystemExit(1)
