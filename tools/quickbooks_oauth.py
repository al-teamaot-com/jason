#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from connectors.core.contracts import ConnectorContext
from connectors.core.openbao_secrets import OpenBaoSecretResolver
from connectors.quickbooks.connector import (
    QUICKBOOKS_LOGICAL_SECRET,
    QUICKBOOKS_PRODUCTION_LOGICAL_SECRET,
)
from connectors.quickbooks.oauth import (
    QUICKBOOKS_OAUTH_DB_DEFAULT,
    QUICKBOOKS_PRODUCTION_OAUTH_DB_DEFAULT,
    QUICKBOOKS_REDIRECT_URI_DEFAULT,
    QUICKBOOKS_PRODUCTION_REDIRECT_URI_DEFAULT,
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
PRODUCTION_ROLE_ID = Path(
    "/var/lib/jason/runtime-secrets/openbao/"
    "quickbooks-production-oauth-client-approle/role-id"
)
PRODUCTION_SECRET_ID = Path(
    "/var/lib/jason/runtime-secrets/openbao/"
    "quickbooks-production-oauth-client-approle/secret-id"
)


def _credentials(args) -> dict[str, str]:
    resolver = OpenBaoSecretResolver(
        base_url=args.openbao_url,
        role_id_path=Path(args.role_id),
        secret_id_path=Path(args.secret_id),
    )
    logical_secret = (
        QUICKBOOKS_PRODUCTION_LOGICAL_SECRET
        if args.environment == "production"
        else QUICKBOOKS_LOGICAL_SECRET
    )
    return dict(
        resolver.resolve(
            logical_secret,
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
        description="Manage Project Jason QuickBooks OAuth connections."
    )
    parser.add_argument("action", choices=("status", "start", "clear"))
    parser.add_argument("--db")
    parser.add_argument("--redirect-uri")
    parser.add_argument("--environment", choices=("sandbox", "production"), default="sandbox")
    parser.add_argument("--openbao-url", default="http://127.0.0.1:8200")
    parser.add_argument("--role-id")
    parser.add_argument("--secret-id")
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args()

    if args.environment == "production":
        args.db = args.db or str(QUICKBOOKS_PRODUCTION_OAUTH_DB_DEFAULT)
        args.redirect_uri = args.redirect_uri or QUICKBOOKS_PRODUCTION_REDIRECT_URI_DEFAULT
        args.role_id = args.role_id or str(PRODUCTION_ROLE_ID)
        args.secret_id = args.secret_id or str(PRODUCTION_SECRET_ID)
    else:
        args.db = args.db or str(QUICKBOOKS_OAUTH_DB_DEFAULT)
        args.redirect_uri = args.redirect_uri or QUICKBOOKS_REDIRECT_URI_DEFAULT
        args.role_id = args.role_id or str(DEFAULT_ROLE_ID)
        args.secret_id = args.secret_id or str(DEFAULT_SECRET_ID)

    store = QuickBooksOAuthStore(
        Path(args.db),
        require_encryption=(args.environment == "production"),
    )
    if args.action == "status":
        credentials = _credentials(args) if args.environment == "production" else None
        try:
            status = store.status(credentials=credentials)
        finally:
            if credentials is not None:
                credentials.clear()
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
