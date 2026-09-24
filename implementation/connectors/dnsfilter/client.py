from __future__ import annotations

import json
import re
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, build_opener

from connectors.core.contracts import (
    ConnectorConfigurationError,
    ConnectorTransportError,
    bounded_transport_timeout,
)

DNSFILTER_API_URL = "https://api.dnsfilter.com"

_STATIC_PATHS = frozenset(
    {
        "/v1/networks/msp",
        "/v1/policies",
        "/v1/user_agents",
        "/v1/user_agents/counts",
    }
)
_RESOURCE_PATH = re.compile(r"^/v1/organizations/[1-9][0-9]*$")


def require_dnsfilter_credentials(credentials: Mapping[str, str]) -> None:
    api_key = str(credentials.get("api_key", "")).strip()
    if not api_key:
        raise ConnectorConfigurationError(
            "DNSFilter credential contract is incomplete: api_key"
        )


class DnsFilterClient:
    """Read-only client for the documented DNSFilter management API."""

    def __init__(
        self,
        credentials: Mapping[str, str],
        *,
        timeout_seconds: float = 30.0,
        opener=None,
    ) -> None:
        require_dnsfilter_credentials(credentials)
        self._api_key = str(credentials["api_key"]).strip()
        self._timeout_seconds = float(timeout_seconds)
        self._opener = opener or build_opener()

    def get(
        self,
        path: str,
        params: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        if path not in _STATIC_PATHS and _RESOURCE_PATH.fullmatch(path) is None:
            raise ConnectorConfigurationError(
                "DNSFilter operation path is not allowlisted."
            )

        pairs: list[tuple[str, str]] = []
        for key, value in (params or {}).items():
            if value is None or value == "":
                continue
            if isinstance(value, (list, tuple, frozenset)):
                pairs.extend((str(key), str(item)) for item in value)
            elif isinstance(value, bool):
                pairs.append((str(key), str(value).lower()))
            else:
                pairs.append((str(key), str(value)))

        target = f"{DNSFILTER_API_URL}{path}"
        query = urlencode(pairs, doseq=True)
        if query:
            target = f"{target}?{query}"
        request = Request(
            target,
            headers={
                "Accept": "application/json",
                "Authorization": self._api_key,
            },
            method="GET",
        )
        decoded = self._send_json(request)
        if isinstance(decoded, Mapping):
            return dict(decoded)
        raise ConnectorTransportError(
            "DNSFilter response must be a JSON object."
        )

    def _send_json(self, request: Request) -> Any:
        try:
            with self._opener.open(
                request,
                timeout=bounded_transport_timeout(self._timeout_seconds),
            ) as response:
                raw = response.read()
        except HTTPError as exc:
            raise ConnectorTransportError(
                f"DNSFilter HTTP request failed with status {exc.code}"
            ) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise ConnectorTransportError(
                "DNSFilter HTTP request failed"
            ) from exc

        try:
            return json.loads(raw.decode("utf-8")) if raw else {}
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ConnectorTransportError(
                "DNSFilter response was not valid JSON"
            ) from exc
