from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol


class AutotaskTransportError(RuntimeError):
    """Raised when the Autotask transport cannot complete safely."""


class SecretBroker(Protocol):
    def get_secret(self, reference: str) -> str: ...


class JsonHttpClient(Protocol):
    def get_json(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        params: Mapping[str, str],
        timeout_seconds: float,
    ) -> tuple[int, Any]: ...


@dataclass(frozen=True, slots=True)
class AutotaskCredentialReferences:
    username: str
    secret: str
    integration_code: str


class AutotaskHttpTicketTransport:
    """Read-only HTTP transport for exact, client-scoped Autotask ticket queries."""

    def __init__(
        self,
        *,
        base_url: str,
        credentials: AutotaskCredentialReferences,
        secrets: SecretBroker,
        http: JsonHttpClient,
        timeout_seconds: float = 15.0,
    ) -> None:
        normalized = base_url.strip().rstrip("/")
        if not normalized.startswith("https://"):
            raise ValueError("Autotask base_url must use HTTPS.")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive.")
        self._base_url = normalized
        self._credentials = credentials
        self._secrets = secrets
        self._http = http
        self._timeout_seconds = timeout_seconds

    def query_tickets(
        self,
        *,
        ticket_number: str,
        company_id: str,
    ) -> list[dict[str, Any]]:
        ticket_number = ticket_number.strip()
        company_id = company_id.strip()
        if not ticket_number or not company_id:
            raise ValueError("ticket_number and company_id are required.")

        headers = {
            "ApiIntegrationCode": self._secrets.get_secret(
                self._credentials.integration_code
            ),
            "UserName": self._secrets.get_secret(self._credentials.username),
            "Secret": self._secrets.get_secret(self._credentials.secret),
            "Accept": "application/json",
        }
        params = {
            "search": (
                '{"filter":['
                '{"op":"eq","field":"ticketNumber","value":"'
                + ticket_number.replace('"', '\\"')
                + '"},'
                '{"op":"eq","field":"companyID","value":"'
                + company_id.replace('"', '\\"')
                + '"}]}'
            )
        }

        try:
            status, payload = self._http.get_json(
                f"{self._base_url}/v1.0/Tickets/query",
                headers=headers,
                params=params,
                timeout_seconds=self._timeout_seconds,
            )
        except Exception as exc:
            raise AutotaskTransportError(
                "Autotask request failed without exposing credentials."
            ) from exc

        if status != 200:
            raise AutotaskTransportError(
                f"Autotask returned unexpected HTTP status {status}."
            )
        if not isinstance(payload, dict):
            raise AutotaskTransportError("Autotask response must be an object.")

        items = payload.get("items")
        if not isinstance(items, list):
            raise AutotaskTransportError(
                "Autotask response is missing the items collection."
            )
        if not all(isinstance(item, dict) for item in items):
            raise AutotaskTransportError(
                "Autotask items must contain objects only."
            )

        return [dict(item) for item in items]
