from __future__ import annotations

from typing import Any, Mapping

import requests

from connectors.core.contracts import (
    ConnectorConfigurationError,
    ConnectorTransportError,
    bounded_transport_timeout,
)

DARKWEBID_API_URL = "https://secure.darkwebid.com/"


def require_darkwebid_credentials(credentials: Mapping[str, str]) -> None:
    missing = [
        key for key in ("username", "password")
        if not str(credentials.get(key, "")).strip()
    ]
    if missing:
        raise ConnectorConfigurationError(
            "Dark Web ID credential contract is incomplete: " + ", ".join(missing)
        )


class DarkWebIdClient:
    """HTTP Basic Auth client for documented Dark Web ID External API reads."""

    def __init__(
        self,
        credentials: Mapping[str, str],
        *,
        timeout_seconds: float = 30.0,
        session: requests.Session | None = None,
    ) -> None:
        require_darkwebid_credentials(credentials)
        self._timeout_seconds = float(timeout_seconds)
        self._session = session or requests.Session()
        self._session.auth = (
            str(credentials["username"]).strip(),
            str(credentials["password"]),
        )
        self._session.headers.update(
            {"Accept": "application/json", "Content-Type": "application/json"}
        )

    def get(self, path: str, params: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
        if path != "services/organization.json" and not path.startswith("services/organization/"):
            raise ConnectorConfigurationError("Dark Web ID operation path is not allowlisted.")
        try:
            response = self._session.get(
                DARKWEBID_API_URL + path,
                params=dict(params or {}),
                timeout=bounded_transport_timeout(self._timeout_seconds),
            )
        except requests.RequestException as exc:
            raise ConnectorTransportError("Dark Web ID HTTP request failed") from exc
        if response.status_code in {401, 403}:
            raise ConnectorTransportError(
                f"Dark Web ID authentication/authorization failed with status {response.status_code}"
            )
        if response.status_code >= 400:
            raise ConnectorTransportError(
                f"Dark Web ID HTTP request failed with status {response.status_code}"
            )
        try:
            decoded = response.json()
        except ValueError as exc:
            raise ConnectorTransportError("Dark Web ID response was not valid JSON") from exc
        if not isinstance(decoded, Mapping):
            raise ConnectorTransportError("Dark Web ID response must be a JSON object.")
        return dict(decoded)
