#!/usr/bin/env python3
from __future__ import annotations

import base64
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4

from connectors.core.contracts import ConnectorContext
from connectors.core.openbao_secrets import OpenBaoSecretResolver


def main() -> int:
    context = ConnectorContext(
        correlation_id=f"corr_backup_auth_{uuid4().hex}",
        principal_id="operator-auth-check",
        organization_id="aot",
        client_id=None,
        capability="backup_net.auth.check",
        mode="observe",
    )
    resolver = OpenBaoSecretResolver(
        base_url="http://openbao:8200",
        role_id_path=Path("/run/jason-secrets/openbao/backup-net/role_id"),
        secret_id_path=Path("/run/jason-secrets/openbao/backup-net/secret_id"),
    )
    values = dict(resolver.resolve("backup_net.readonly", context))
    client_id = str(values.get("client_id") or "")
    client_secret = str(values.get("client_secret") or "")
    values.clear()
    raw = f"{client_id}:{client_secret}".encode("utf-8")
    basic = base64.b64encode(raw).decode("ascii")
    raw = b""
    request = Request(
        "https://login.backup.net/connect/token",
        data=urlencode({"grant_type": "client_credentials"}).encode("utf-8"),
        headers={
            "Accept": "*/*",
            "Authorization": f"Basic {basic}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    basic = ""
    try:
        with urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
            print(json.dumps({
                "status": "pass",
                "http_status": response.status,
                "token_returned": bool(payload.get("access_token")),
                "client_id_present": bool(client_id),
                "client_secret_present": bool(client_secret),
                "client_id_length": len(client_id),
                "client_secret_length": len(client_secret),
                "secret_values_printed": False,
            }, indent=2, sort_keys=True))
            return 0
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        safe = body.replace(client_id, "[redacted-client-id]").replace(
            client_secret, "[redacted-client-secret]"
        )
        try:
            parsed = json.loads(safe)
            error = parsed.get("error")
            description = parsed.get("error_description")
        except json.JSONDecodeError:
            error = "non_json_error"
            description = safe[:300]
        www_authenticate = str(exc.headers.get("WWW-Authenticate") or "")
        www_authenticate = www_authenticate.replace(
            client_id, "[redacted-client-id]"
        ).replace(client_secret, "[redacted-client-secret]")
        print(json.dumps({
            "status": "failed",
            "http_status": exc.code,
            "oauth_error": error,
            "oauth_error_description": description,
            "www_authenticate": www_authenticate,
            "client_id_present": bool(client_id),
            "client_secret_present": bool(client_secret),
            "client_id_length": len(client_id),
            "client_secret_length": len(client_secret),
            "secret_values_printed": False,
        }, indent=2, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
