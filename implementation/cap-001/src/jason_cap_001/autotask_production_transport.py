from __future__ import annotations

from dataclasses import dataclass
import json
import time
from typing import Any, Callable, Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .autotask_http_transport import (
    AutotaskCredentialReferences,
    AutotaskHttpTicketTransport,
    AutotaskTransportError,
    SecretBroker,
)


class UrlOpener(Protocol):
    def __call__(self, request: Request, *, timeout: float): ...


class ProductionJsonHttpClient:
    """Small HTTPS JSON client with bounded retries and redacted failures."""

    def __init__(
        self,
        *,
        opener: UrlOpener = urlopen,
        retry_attempts: int = 2,
        retry_delay_seconds: float = 0.25,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if retry_attempts < 0:
            raise ValueError("retry_attempts must be zero or greater.")
        if retry_delay_seconds < 0:
            raise ValueError("retry_delay_seconds must be zero or greater.")
        self._opener = opener
        self._retry_attempts = retry_attempts
        self._retry_delay_seconds = retry_delay_seconds
        self._sleeper = sleeper

    def get_json(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        params: Mapping[str, str],
        timeout_seconds: float,
    ) -> tuple[int, Any]:
        if not url.startswith("https://"):
            raise ValueError("Production HTTP requests must use HTTPS.")

        query = urlencode(dict(params))
        request_url = f"{url}?{query}" if query else url
        request = Request(request_url, headers=dict(headers), method="GET")

        for attempt in range(self._retry_attempts + 1):
            try:
                with self._opener(request, timeout=timeout_seconds) as response:
                    status = int(response.getcode())
                    raw = response.read()
                try:
                    payload = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise AutotaskTransportError(
                        "Autotask returned an invalid JSON response."
                    ) from exc
                return status, payload
            except HTTPError as exc:
                if exc.code not in {429, 500, 502, 503, 504}:
                    return int(exc.code), {}
                retryable = True
            except (URLError, TimeoutError, OSError):
                retryable = True

            if not retryable or attempt >= self._retry_attempts:
                break
            if self._retry_delay_seconds:
                self._sleeper(self._retry_delay_seconds)

        raise AutotaskTransportError(
            "Autotask network request failed after bounded retries."
        )


@dataclass(frozen=True, slots=True)
class AutotaskZoneDiscovery:
    """Resolve a validated Autotask API zone from a brokered username."""

    discovery_url: str = (
        "https://webservices.autotask.net/atservicesrest/v1.0/zoneInformation"
    )
    timeout_seconds: float = 10.0

    def resolve_base_url(
        self,
        *,
        username_reference: str,
        secrets: SecretBroker,
        http: ProductionJsonHttpClient,
    ) -> str:
        username = secrets.get_secret(username_reference).strip()
        if not username:
            raise AutotaskTransportError("Autotask username secret is empty.")

        status, payload = http.get_json(
            self.discovery_url,
            headers={"Accept": "application/json"},
            params={"user": username},
            timeout_seconds=self.timeout_seconds,
        )
        if status != 200 or not isinstance(payload, dict):
            raise AutotaskTransportError("Autotask zone discovery failed.")

        url = payload.get("url")
        if not isinstance(url, str):
            raise AutotaskTransportError(
                "Autotask zone discovery response is missing the API URL."
            )
        normalized = url.strip().rstrip("/")
        if not normalized.startswith("https://"):
            raise AutotaskTransportError(
                "Autotask zone discovery returned a non-HTTPS URL."
            )
        return normalized


def build_autotask_ticket_transport(
    *,
    credentials: AutotaskCredentialReferences,
    secrets: SecretBroker,
    http: ProductionJsonHttpClient | None = None,
    zone_discovery: AutotaskZoneDiscovery | None = None,
    timeout_seconds: float = 15.0,
) -> AutotaskHttpTicketTransport:
    """Construct the read-only ticket transport using brokered zone discovery."""

    production_http = http or ProductionJsonHttpClient()
    discovery = zone_discovery or AutotaskZoneDiscovery()
    base_url = discovery.resolve_base_url(
        username_reference=credentials.username,
        secrets=secrets,
        http=production_http,
    )
    return AutotaskHttpTicketTransport(
        base_url=base_url,
        credentials=credentials,
        secrets=secrets,
        http=production_http,
        timeout_seconds=timeout_seconds,
    )
