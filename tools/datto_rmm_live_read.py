#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "implementation"))

from connectors.core.contracts import ConnectorContext
from connectors.core.openbao_secrets import OpenBaoSecretResolver


class LiveReadError(RuntimeError):
    pass


def _request_json(req: urllib.request.Request, *, timeout: float = 20.0) -> Mapping[str, Any]:
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raise LiveReadError(f"Datto RMM returned HTTP {exc.code}.") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise LiveReadError("Datto RMM network request failed.") from exc

    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LiveReadError("Datto RMM returned invalid JSON.") from exc
    if not isinstance(parsed, Mapping):
        raise LiveReadError("Datto RMM returned an unexpected response shape.")
    return parsed


def acquire_access_token(api_url: str, api_key: str, api_secret: str) -> str:
    body = urllib.parse.urlencode(
        {
            "grant_type": "password",
            "username": api_key,
            "password": api_secret,
        }
    ).encode("utf-8")
    basic = base64.b64encode(b"public-client:public").decode("ascii")
    req = urllib.request.Request(
        f"{api_url.rstrip('/')}/auth/oauth/token",
        data=body,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {basic}",
        },
        method="POST",
    )
    payload = _request_json(req)
    token = payload.get("access_token")
    if not isinstance(token, str) or not token:
        raise LiveReadError("Datto RMM token exchange returned no access token.")
    return token


def account_probe(api_url: str, token: str) -> Mapping[str, Any]:
    req = urllib.request.Request(
        f"{api_url.rstrip('/')}/api/v2/account",
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
        },
        method="GET",
    )
    return _request_json(req)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Perform one bounded Datto RMM authentication/account read without "
            "printing credentials, bearer tokens, or raw provider data."
        )
    )
    parser.add_argument("--live-read", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not args.live_read:
        print(
            json.dumps(
                {
                    "provider": "datto_rmm",
                    "logical_secret": "datto_rmm.readonly",
                    "operation": "GET /api/v2/account",
                    "network_contacted": False,
                    "provider_credentials_used": False,
                    "raw_provider_payload_persisted": False,
                    "status": "credential_safe_preflight",
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    resolver = OpenBaoSecretResolver(
        base_url="http://127.0.0.1:8200",
        role_id_path=Path(
            "/opt/jason/bootstrap/secrets/openbao/datto-rmm-read-approle/role-id"
        ),
        secret_id_path=Path(
            "/opt/jason/bootstrap/secrets/openbao/datto-rmm-read-approle/secret-id"
        ),
    )
    context = ConnectorContext(
        correlation_id="drmm-first-live-read",
        principal_id="operator-al",
        organization_id="aot",
        client_id=None,
        capability="datto_rmm.account.get",
        mode="observe",
    )
    credentials = dict(resolver.resolve("datto_rmm.readonly", context))
    account: Mapping[str, Any] = {}
    try:
        required = {"api_url", "api_key", "api_secret"}
        if set(credentials) != required:
            raise LiveReadError("Datto RMM credential contract mismatch.")
        token = acquire_access_token(
            credentials["api_url"],
            credentials["api_key"],
            credentials["api_secret"],
        )
        try:
            account = account_probe(credentials["api_url"], token)
        finally:
            token = ""
    finally:
        credentials.clear()

    top_level_keys = sorted(str(key) for key in account.keys())
    print(
        json.dumps(
            {
                "provider": "datto_rmm",
                "logical_secret": "datto_rmm.readonly",
                "operation": "GET /api/v2/account",
                "network_contacted": True,
                "provider_credentials_used": True,
                "access_token_persisted": False,
                "raw_provider_payload_persisted": False,
                "raw_provider_payload_printed": False,
                "response_top_level_keys": top_level_keys,
                "status": "pass",
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except LiveReadError as exc:
        print(f"DENIED: {exc}", file=sys.stderr)
        raise SystemExit(1)
