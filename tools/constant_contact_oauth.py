#!/usr/bin/env python3
"""Owner-local Constant Contact OAuth initiation. Never prints secrets/tokens.

Run only after the isolated production credential projection is installed.
The user must complete consent in their browser; Jason cannot simulate it.
"""
from __future__ import annotations

import argparse
import base64
import os
from pathlib import Path

from connectors.constant_contact.oauth import authorization_url
from connectors.constant_contact.oauth_store import EncryptedOAuthStore
from connectors.core.contracts import ConnectorContext
from connectors.core.openbao_secrets import OpenBaoSecretResolver

DEFAULT_DB = "/var/lib/jason/openclaw/constant-contact/oauth.sqlite3"
DEFAULT_APPROLE = "/var/lib/jason/runtime-secrets/openbao/constant-contact-oauth-client-approle"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Constant Contact governed OAuth bootstrap")
    parser.add_argument("command", choices=("begin", "status"))
    parser.add_argument("--db", default=DEFAULT_DB)
    parser.add_argument("--approle-dir", default=DEFAULT_APPROLE)
    args = parser.parse_args(argv)
    base = Path(args.approle_dir)
    resolver = OpenBaoSecretResolver(
        base_url=os.environ.get("JASON_OPENBAO_URL", "http://127.0.0.1:8200"),
        # The root-managed provisioning tool creates hyphenated filenames.
        # Do not create an alternate ungoverned credential layout.
        role_id_path=base / "role-id", secret_id_path=base / "secret-id",
    )
    credentials = resolver.resolve(
        "constant_contact.oauth_client",
        ConnectorContext(correlation_id="constant-contact-owner-bootstrap",
                         principal_id="svc-jason-oauth-owner", organization_id="aot",
                         client_id=None, capability="constant_contact.oauth.begin", mode="execute"),
    )
    try:
        key = base64.b64decode(credentials["token_key_b64"], validate=True)
        store = EncryptedOAuthStore(Path(args.db), key)
        if args.command == "status":
            print("CONSTANT_CONTACT_CONNECTED=" + str(bool(store.load_tokens())).upper())
            return 0
        if store.load_tokens():
            print("Constant Contact has an existing token. No new flow started.")
            return 2
        url = authorization_url(client_id=credentials["client_id"], state=store.issue_state())
        print("Open this link in an authenticated Constant Contact browser session:")
        print(url)
        print("The redirect will complete only after the callback route is deployed.")
        return 0
    except Exception:
        print("Constant Contact OAuth bootstrap failed (secret-safe).")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
