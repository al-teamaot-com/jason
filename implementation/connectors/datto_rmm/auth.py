from __future__ import annotations

import base64
import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from socket import timeout as SocketTimeout
from typing import Any, Callable, Mapping

from connectors.core.contracts import (
    ConnectorConfigurationError,
    ConnectorExecutionDeadlineExceeded,
    ConnectorTransportError,
    bounded_transport_timeout,
)


@dataclass(frozen=True)
class DattoRmmAccessToken:
    access_token: str
    token_type: str = "Bearer"
    expires_in: int | None = None


def require_durable_credentials(credentials: Mapping[str, str]) -> None:
    required = ("api_url", "api_key", "api_secret")
    missing = [name for name in required if not credentials.get(name)]
    if missing:
        raise ConnectorConfigurationError(
            "Datto RMM durable credential contract is incomplete: " + ", ".join(missing)
        )
    forbidden = ("access_token", "refresh_token")
    if any(credentials.get(name) for name in forbidden):
        raise ConnectorConfigurationError(
            "Datto RMM bearer tokens are runtime-only and may not be persisted."
        )


def acquire_access_token(
    *,
    credentials: Mapping[str, str],
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> DattoRmmAccessToken:
    """Exchange durable API credentials for a runtime-only Datto bearer token."""
    require_durable_credentials(credentials)
    api_url = credentials["api_url"].rstrip("/")
    body = urllib.parse.urlencode(
        {
            "grant_type": "password",
            "username": credentials["api_key"],
            "password": credentials["api_secret"],
        }
    ).encode("utf-8")
    basic = base64.b64encode(b"public-client:public").decode("ascii")
    request = urllib.request.Request(
        f"{api_url}/auth/oauth/token",
        data=body,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {basic}",
        },
        method="POST",
    )
    effective_timeout = bounded_transport_timeout(30.0)
    deadline_limited = effective_timeout < 30.0
    try:
        with opener(request, timeout=effective_timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raise ConnectorTransportError(
            f"Datto RMM token exchange failed with HTTP {exc.code}."
        ) from exc
    except (TimeoutError, SocketTimeout) as exc:
        if deadline_limited:
            raise ConnectorExecutionDeadlineExceeded(
                "governed provider execution deadline exceeded during token exchange"
            ) from exc
        raise ConnectorTransportError("Datto RMM token exchange failed.") from exc
    except urllib.error.URLError as exc:
        if deadline_limited and isinstance(exc.reason, (TimeoutError, SocketTimeout)):
            raise ConnectorExecutionDeadlineExceeded(
                "governed provider execution deadline exceeded during token exchange"
            ) from exc
        raise ConnectorTransportError("Datto RMM token exchange failed.") from exc
    except OSError as exc:
        raise ConnectorTransportError("Datto RMM token exchange failed.") from exc

    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ConnectorTransportError("Datto RMM token exchange returned invalid JSON.") from exc
    if not isinstance(payload, Mapping):
        raise ConnectorTransportError("Datto RMM token exchange returned an invalid shape.")

    token = payload.get("access_token")
    if not isinstance(token, str) or not token:
        raise ConnectorConfigurationError(
            "Datto RMM token exchange did not return an access token."
        )
    token_type = payload.get("token_type", "Bearer")
    raw_expires = payload.get("expires_in")
    expires_in: int | None = None
    if isinstance(raw_expires, int):
        expires_in = raw_expires
    elif isinstance(raw_expires, str) and raw_expires.isdigit():
        expires_in = int(raw_expires)
    return DattoRmmAccessToken(
        access_token=token,
        token_type=str(token_type),
        expires_in=expires_in,
    )
