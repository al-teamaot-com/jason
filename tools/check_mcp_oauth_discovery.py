#!/usr/bin/env python3
"""Read-only MCP OAuth discovery contract probe (not a session-renewal test)."""
import argparse
import json
import sys
import urllib.error
import urllib.request
from urllib.parse import urlsplit


def get_json(url):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=8) as response:
        if response.status != 200:
            raise ValueError("unexpected HTTP status")
        return json.load(response)


def validate(base, resource, auth):
    expected = base.rstrip("/") + "/mcp"
    if resource.get("resource") != expected:
        raise ValueError("resource mismatch")
    servers = resource.get("authorization_servers")
    if not isinstance(servers, list) or len(servers) != 1:
        raise ValueError("authorization server missing or ambiguous")
    if auth.get("issuer", "").rstrip("/") != servers[0].rstrip("/"):
        raise ValueError("issuer mismatch between discovery documents")
    for key in ("authorization_endpoint", "token_endpoint"):
        url = auth.get(key, "")
        if urlsplit(url).scheme != "https" or not urlsplit(url).hostname:
            raise ValueError("invalid " + key)
    if not resource.get("scopes_supported"):
        raise ValueError("missing scope")
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="https://mcp-jason.teamaot.com")
    args = parser.parse_args()
    base = args.base.rstrip("/")
    try:
        resource = get_json(base + "/.well-known/oauth-protected-resource/mcp")
        auth = get_json(base + "/.well-known/oauth-authorization-server")
        validate(base, resource, auth)
    except (ValueError, urllib.error.URLError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "fail", "check": "mcp_oauth_discovery", "error_type": type(exc).__name__}))
        return 1
    print(json.dumps({"status": "pass", "check": "mcp_oauth_discovery", "session_renewal_verified": False}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
