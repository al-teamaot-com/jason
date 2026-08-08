from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from connectors.core.contracts import ConnectorConfigurationError, HttpTransport


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
            "Datto RMM durable credential contract is incomplete: "
            + ", ".join(missing)
        )


def acquire_access_token(
    *,
    credentials: Mapping[str, str],
    transport: HttpTransport,
) -> DattoRmmAccessToken:
    """Exchange durable Datto API credentials for a short-lived bearer token.

    The durable secret remains behind Jason's logical-secret boundary. The
    resulting bearer token is runtime material and must not be persisted in the
    logical secret, repository, normal logs, or evidence.
    """
    require_durable_credentials(credentials)

    api_url = credentials["api_url"].rstrip("/")
    payload = transport.request(
        method="POST",
        url=f"{api_url}/auth/oauth/token",
        headers={"Accept": "application/json"},
        params=None,
        json={
            "grant_type": "password",
            "username": credentials["api_key"],
            "password": credentials["api_secret"],
        },
        timeout_seconds=30.0,
    )

    token = payload.get("access_token")
    if not isinstance(token, str) or not token:
        raise ConnectorConfigurationError(
            "Datto RMM token exchange did not return an access token."
        )

    token_type = payload.get("token_type", "Bearer")
    expires_in: int | None = None
    raw_expires = payload.get("expires_in")
    if isinstance(raw_expires, int):
        expires_in = raw_expires
    elif isinstance(raw_expires, str) and raw_expires.isdigit():
        expires_in = int(raw_expires)

    return DattoRmmAccessToken(
        access_token=token,
        token_type=str(token_type),
        expires_in=expires_in,
    )
