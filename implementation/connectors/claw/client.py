from __future__ import annotations

import json
import ssl
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

from connectors.core.contracts import (
    ConnectorConfigurationError,
    ConnectorTransportError,
)


class ClawMcpClient:
    """Minimal MCP-over-HTTPS client for the governed external Claw bridge."""

    def __init__(
        self,
        credentials: Mapping[str, str],
        *,
        opener: Callable[..., object] = urlopen,
        timeout_seconds: float = 15.0,
    ) -> None:
        self._url = str(credentials.get("mcp_url") or "").strip()
        self._token = str(credentials.get("bearer_token") or "").strip()
        self._ca_cert_pem = str(credentials.get("ca_cert_pem") or "").strip()
        self._opener = opener
        self._timeout_seconds = timeout_seconds

        if not self._url.startswith("https://"):
            raise ConnectorConfigurationError("Claw MCP URL must use HTTPS.")
        if not self._token:
            raise ConnectorConfigurationError("Claw bearer token is unavailable.")
        if "BEGIN CERTIFICATE" not in self._ca_cert_pem:
            raise ConnectorConfigurationError("Claw CA certificate is invalid.")

        try:
            self._ssl_context = ssl.create_default_context(cadata=self._ca_cert_pem)
        except (ValueError, ssl.SSLError) as exc:
            raise ConnectorConfigurationError(
                "Claw CA certificate could not be loaded."
            ) from exc

    def call_tool(self, name: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        rpc_result = self._rpc(
            "tools/call",
            {
                "name": name,
                "arguments": dict(arguments),
            },
        )
        content = rpc_result.get("content")
        if isinstance(content, list):
            for item in content:
                if not isinstance(item, Mapping):
                    continue
                if item.get("type") != "text":
                    continue
                text = item.get("text")
                if not isinstance(text, str):
                    continue
                try:
                    decoded = json.loads(text)
                except json.JSONDecodeError as exc:
                    raise ConnectorTransportError(
                        "Claw returned malformed tool JSON."
                    ) from exc
                if not isinstance(decoded, Mapping):
                    raise ConnectorTransportError(
                        "Claw tool result must be a JSON object."
                    )
                return dict(decoded)
        return dict(rpc_result)

    def _rpc(self, method: str, params: Mapping[str, Any]) -> Mapping[str, Any]:
        body = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": f"jason-{uuid4().hex}",
                "method": method,
                "params": dict(params),
            },
            separators=(",", ":"),
        ).encode("utf-8")
        request = Request(
            self._url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "Authorization": f"Bearer {self._token}",
            },
            method="POST",
        )
        try:
            with self._opener(
                request,
                timeout=self._timeout_seconds,
                context=self._ssl_context,
            ) as response:
                raw = response.read()
        except HTTPError as exc:
            raise ConnectorTransportError(
                f"Claw MCP request failed with HTTP {exc.code}."
            ) from exc
        except (URLError, TimeoutError, OSError, ssl.SSLError) as exc:
            raise ConnectorTransportError("Claw MCP request failed.") from exc

        return self._decode_rpc(raw)

    @staticmethod
    def _decode_rpc(raw: bytes) -> Mapping[str, Any]:
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ConnectorTransportError("Claw MCP response was not UTF-8.") from exc

        candidates: list[Mapping[str, Any]] = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("data:"):
                line = line[5:].strip()
            if not line or line == "[DONE]":
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, Mapping):
                candidates.append(parsed)

        if candidates:
            payload = candidates[-1]
        else:
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ConnectorTransportError(
                    "Claw MCP response was not valid JSON."
                ) from exc
            if not isinstance(parsed, Mapping):
                raise ConnectorTransportError(
                    "Claw MCP response must be a JSON object."
                )
            payload = parsed

        if payload.get("error") is not None:
            raise ConnectorTransportError("Claw MCP returned a JSON-RPC error.")

        result = payload.get("result")
        if not isinstance(result, Mapping):
            raise ConnectorTransportError("Claw MCP result is missing or invalid.")
        return dict(result)
