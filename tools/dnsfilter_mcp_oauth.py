#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from connectors.dnsfilter.mcp_client import DnsFilterMcpClient
from connectors.dnsfilter.mcp_oauth import (
    DNSFILTER_MCP_OAUTH_DB_DEFAULT,
    DNSFILTER_MCP_REDIRECT_URI_DEFAULT,
    DnsFilterMcpOAuthError,
    DnsFilterMcpOAuthStore,
    begin_dnsfilter_oauth,
)


def _status(store: DnsFilterMcpOAuthStore) -> int:
    status = store.status()
    print(
        json.dumps(
            {
                "provider": "dnsfilter_mcp",
                "registered": status.registered,
                "connected": status.connected,
                "expires_at": status.expires_at,
                "has_refresh_token": status.has_refresh_token,
                "pending_authorization": status.pending_authorization,
            },
            sort_keys=True,
        )
    )
    return 0


def _start(
    store: DnsFilterMcpOAuthStore,
    redirect_uri: str,
) -> int:
    url = begin_dnsfilter_oauth(store, redirect_uri=redirect_uri)
    print("DNSFILTER_MCP_OAUTH=ACTION_REQUIRED")
    print("Open this authorization URL in a browser:")
    print(url)
    print(
        "After DNSFilter completes the redirect, this command can be "
        "re-run with 'status'."
    )
    return 0


def _verify(store: DnsFilterMcpOAuthStore) -> int:
    result = DnsFilterMcpClient(store).call_tool("get_current_user", {})
    print(
        json.dumps(
            {
                "provider": "dnsfilter_mcp",
                "verification": "ok",
                "authenticated_user_present": bool(result),
            },
            sort_keys=True,
        )
    )
    return 0


def _clear(store: DnsFilterMcpOAuthStore, confirm: bool) -> int:
    if not confirm:
        raise SystemExit("--confirm is required to clear DNSFilter OAuth tokens")
    store.clear_token()
    print("DNSFILTER_MCP_OAUTH=CLEARED")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Manage Project Jason's DNSFilter MCP OAuth session."
    )
    parser.add_argument(
        "action",
        choices=("status", "start", "verify", "clear"),
    )
    parser.add_argument(
        "--db",
        default=str(DNSFILTER_MCP_OAUTH_DB_DEFAULT),
    )
    parser.add_argument(
        "--redirect-uri",
        default=DNSFILTER_MCP_REDIRECT_URI_DEFAULT,
    )
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args()

    store = DnsFilterMcpOAuthStore(Path(args.db))
    try:
        if args.action == "status":
            return _status(store)
        if args.action == "start":
            return _start(store, args.redirect_uri)
        if args.action == "verify":
            return _verify(store)
        return _clear(store, args.confirm)
    except DnsFilterMcpOAuthError as exc:
        print(f"DNSFILTER_MCP_OAUTH=ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
