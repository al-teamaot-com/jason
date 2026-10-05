#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from connectors.core.contracts import ConnectorContext
from connectors.core.openbao_secrets import OpenBaoSecretResolver
from connectors.quickbooks.connector import QUICKBOOKS_LOGICAL_SECRET
from connectors.quickbooks.oauth import (
    QUICKBOOKS_OAUTH_DB_DEFAULT,
    QUICKBOOKS_REDIRECT_URI_DEFAULT,
    QuickBooksOAuthError,
    QuickBooksOAuthStore,
    begin_quickbooks_oauth,
)

DEFAULT_ROLE_ID = Path(
    "/var/lib/jason/runtime-secrets/openbao/"
    "quickbooks-development-oauth-client-approle/role-id"
)
DEFAULT_SECRET_ID = Path(
    "/var/lib/jason/runtime-secrets/openbao/"
    "quickbooks-development-oauth-client-approle/secret-id"
)


def _credentials(args) -> dict[str, str]:
    resolver = OpenBaoSecretResolver(
        base_url=args.openbao_url,
        role_id_path=Path(args.role_id),
        secret_id_path=Path(args.secret_id),
    )
    return dict(
        resolver.resolve(
            QUICKBOOKS_LOGICAL_SECRET,
            ConnectorContext(
                correlation_id="quickbooks-oauth-operator",
                principal_id="aot-operator",
                organization_id="aot",
                client_id=None,
                capability="quickbooks.oauth.start",
                mode="execute",
            ),
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Manage Project Jason's QuickBooks OAuth sandbox connection."
    )
    parser.add_argument("action", choices=("status", "start", "clear"))
    parser.add_argument("--db", default=str(QUICKBOOKS_OAUTH_DB_DEFAULT))
    parser.add_argument("--redirect-uri", default=QUICKBOOKS_REDIRECT_URI_DEFAULT)
    parser.add_argument("--environment", choices=("sandbox",), default="sandbox")
    parser.add_argument("--openbao-url", default="http://127.0.0.1:8200")
    parser.add_argument("--role-id", default=str(DEFAULT_ROLE_ID))
    parser.add_argument("--secret-id", default=str(DEFAULT_SECRET_ID))
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args()

    store = QuickBooksOAuthStore(Path(args.db))
    if args.action == "status":
        status = store.status()
        print(
            json.dumps(
                {
                    "provider": "quickbooks",
                    "connected": status.connected,
                    "environment": status.environment,
                    "realm_bound": bool(status.realm_id),
                    "expires_at": status.expires_at,
                    "has_refresh_token": status.has_refresh_token,
                    "pending_authorization": status.pending_authorization,
                    "secret_values_printed": False,
                },
                sort_keys=True,
            )
        )
        return 0

    if args.action == "clear":
        if not args.confirm:
            raise SystemExit("--confirm is required to clear QuickBooks OAuth state")
        store.clear()
        print("QUICKBOOKS_OAUTH=CLEARED")
        return 0

    credentials = _credentials(args)
    try:
        client_id = str(credentials.get("client_id") or "").strip()
        if not client_id:
            raise QuickBooksOAuthError(
                "QuickBooks OAuth client ID is unavailable."
            )
        url = begin_quickbooks_oauth(
            store,
            client_id=client_id,
            environment=args.environment,
            redirect_uri=args.redirect_uri,
        )
    finally:
        credentials.clear()

    print("QUICKBOOKS_OAUTH=ACTION_REQUIRED")
    print("Open this authorization URL in a browser:")
    print(url)
    print("The URL contains the public client ID and one-time state, but no client secret.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
