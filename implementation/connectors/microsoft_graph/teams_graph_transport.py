"""Concrete Microsoft Graph transport for governed Teams approval delivery.

The transport is intentionally narrow at the network boundary but generic at the
message level: it posts an already-governed Teams channel message and returns the
Graph response. Authentication is injected through a token provider so secret
retrieval remains outside this module and can use Jason's canonical secret boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Mapping, Protocol
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


class MicrosoftGraphAccessTokenProvider(Protocol):
    def access_token(self) -> str: ...


class JsonHttpTransport(Protocol):
    def post_json(
        self,
        *,
        url: str,
        headers: Mapping[str, str],
        body: Mapping[str, Any],
        timeout_seconds: float,
    ) -> Mapping[str, Any]: ...


@dataclass(frozen=True, slots=True)
class UrllibJsonHttpTransport:
    """Small standard-library HTTP implementation for Graph JSON POSTs."""

    def post_json(
        self,
        *,
        url: str,
        headers: Mapping[str, str],
        body: Mapping[str, Any],
        timeout_seconds: float,
    ) -> Mapping[str, Any]:
        payload = json.dumps(body, separators=(",", ":")).encode("utf-8")
        request = Request(url=url, data=payload, method="POST", headers=dict(headers))
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                raw = response.read()
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:1000]
            raise RuntimeError(f"Microsoft Graph HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise RuntimeError("Microsoft Graph transport failed") from exc
        if not raw:
            raise RuntimeError("Microsoft Graph returned an empty response")
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("Microsoft Graph returned invalid JSON") from exc
        if not isinstance(parsed, dict):
            raise RuntimeError("Microsoft Graph response must be a JSON object")
        return parsed


@dataclass(frozen=True, slots=True)
class MicrosoftGraphTeamsMessageTransport:
    token_provider: MicrosoftGraphAccessTokenProvider
    http: JsonHttpTransport = UrllibJsonHttpTransport()
    graph_base_url: str = "https://graph.microsoft.com/v1.0"
    timeout_seconds: float = 20.0

    def __post_init__(self) -> None:
        if self.graph_base_url.rstrip("/") != "https://graph.microsoft.com/v1.0":
            raise ValueError("Teams approval delivery must use Microsoft Graph v1.0")
        if self.timeout_seconds <= 0 or self.timeout_seconds > 60:
            raise ValueError("Graph timeout must be greater than 0 and at most 60 seconds")

    def post_channel_message(
        self,
        *,
        team_id: str,
        channel_id: str,
        message: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        team = self._validate_identifier(team_id, "team_id")
        channel = self._validate_identifier(channel_id, "channel_id")
        if not isinstance(message, Mapping) or not message:
            raise ValueError("Teams message body must be a non-empty mapping")

        token = self.token_provider.access_token()
        if not isinstance(token, str) or not token.strip():
            raise PermissionError("Microsoft Graph access token is unavailable")
        if any(char.isspace() for char in token.strip()):
            raise PermissionError("Microsoft Graph access token is malformed")

        url = (
            f"{self.graph_base_url}/teams/{quote(team, safe='')}/"
            f"channels/{quote(channel, safe='')}/messages"
        )
        response = self.http.post_json(
            url=url,
            headers={
                "Authorization": f"Bearer {token.strip()}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            body=message,
            timeout_seconds=self.timeout_seconds,
        )
        message_id = response.get("id")
        if not isinstance(message_id, str) or not message_id.strip():
            raise RuntimeError("Microsoft Graph Teams response missing message id")
        return response

    @staticmethod
    def _validate_identifier(value: str, name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be non-empty")
        normalized = value.strip()
        if len(normalized) > 512:
            raise ValueError(f"{name} is too long")
        if any(ord(char) < 32 for char in normalized):
            raise ValueError(f"{name} contains control characters")
        return normalized
