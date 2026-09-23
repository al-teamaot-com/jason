from __future__ import annotations

import base64
import json
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, build_opener

from connectors.core.contracts import (
    ConnectorConfigurationError,
    ConnectorTransportError,
)

BACKUP_NET_AUTH_URL = "https://login.backup.net/connect/token"
BACKUP_NET_API_URL = "https://public-api.backup.net"

_ALLOWED_PATHS = frozenset(
    {
        "/api/epb/v1/assets",
        "/v1/backups",
        "/v1/backupiq/alerts",
        "/v1/customers",
    }
)

def require_backup_net_credentials(credentials: Mapping[str, str]) -> None:
    missing = [
        field
        for field in ("client_id", "client_secret")
        if not str(credentials.get(field, "")).strip()
    ]
    if missing:
        raise ConnectorConfigurationError(
            "Backup.net credential contract is incomplete: " + ", ".join(missing)
        )


class BackupNetClient:
    """Short-lived OAuth client for the documented UniView Public API."""

    def __init__(
        self,
        credentials: Mapping[str, str],
        *,
        timeout_seconds: float = 30.0,
        opener=None,
    ) -> None:
        require_backup_net_credentials(credentials)
        self._client_id = str(credentials["client_id"]).strip()
        self._client_secret = str(credentials["client_secret"]).strip()
        self._timeout_seconds = float(timeout_seconds)
        self._opener = opener or build_opener()

    def get(
        self,
        path: str,
        params: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        if path not in _ALLOWED_PATHS:
            raise ConnectorConfigurationError(
                "Backup.net operation path is not allowlisted."
            )

        token = self._access_token()
        try:
            query = urlencode(
                [
                    (
                        str(key),
                        str(value).lower() if isinstance(value, bool) else str(value),
                    )
                    for key, value in params.items()
                    if value is not None and str(value).strip() != ""
                ],
                doseq=True,
            )
            target = f"{BACKUP_NET_API_URL}{path}"
            if query:
                target = f"{target}?{query}"
            request = Request(
                target,
                headers={
                    "Accept": "application/json",
                    "Authorization": f"Bearer {token}",
                },
                method="GET",
            )
            decoded = self._send_json(request)
        finally:
            token = ""

        if isinstance(decoded, list):
            return {"items": decoded}
        if isinstance(decoded, Mapping):
            return dict(decoded)
        raise ConnectorTransportError("Backup.net response must be JSON.")

    def _access_token(self) -> str:
        payload = urlencode(
            {"grant_type": "client_credentials"}
        ).encode("utf-8")
        basic = base64.b64encode(
            f"{self._client_id}:{self._client_secret}".encode("utf-8")
        ).decode("ascii")
        request = Request(
            BACKUP_NET_AUTH_URL,
            data=payload,
            headers={
                "Accept": "*/*",
                "Authorization": f"Basic {basic}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )
        basic = ""
        decoded = self._send_json(request)
        if not isinstance(decoded, Mapping):
            raise ConnectorTransportError(
                "Backup.net token response must be a JSON object."
            )
        token = decoded.get("access_token")
        if not isinstance(token, str) or not token.strip():
            raise ConnectorTransportError(
                "Backup.net authentication did not return an access token."
            )
        return token.strip()

    def _send_json(self, request: Request) -> Any:
        try:
            with self._opener.open(
                request,
                timeout=self._timeout_seconds,
            ) as response:
                raw = response.read()
        except HTTPError as exc:
            raise ConnectorTransportError(
                f"Backup.net HTTP request failed with status {exc.code}"
            ) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise ConnectorTransportError(
                "Backup.net HTTP request failed"
            ) from exc

        try:
            return json.loads(raw.decode("utf-8")) if raw else {}
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ConnectorTransportError(
                "Backup.net response was not valid JSON"
            ) from exc
