from __future__ import annotations

import json
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from connectors.core.contracts import ConnectorTransportError
from .mcp_oauth import (
    DNSFILTER_MCP_URL,
    DnsFilterMcpOAuthError,
    DnsFilterMcpOAuthStore,
    access_token,
)

_USER_AGENT = "Mozilla/5.0 Project-Jason-DNSFilter-MCP/1.0"


class DnsFilterMcpClient:
    """Minimal bounded Streamable-HTTP MCP client for DNSFilter.

    DNSFilter currently exposes stateless JSON-RPC over HTTPS and can return
    either JSON or SSE-framed JSON. Jason never accepts a caller-selected tool
    name; the governed connector maps canonical capabilities to a fixed tool.
    """

    def __init__(
        self,
        oauth_store: DnsFilterMcpOAuthStore,
        *,
        timeout_seconds: float = 60.0,
        opener=None,
    ) -> None:
        self._store = oauth_store
        self._timeout_seconds = float(timeout_seconds)
        self._opener = opener or urlopen

    def call_tool(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        token = access_token(self._store)
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": dict(arguments),
            },
        }
        response = self._post(payload, token)
        if "error" in response:
            message = (
                (response.get("error") or {}).get("message")
                if isinstance(response.get("error"), Mapping)
                else None
            )
            raise ConnectorTransportError(
                "DNSFilter MCP tool call failed"
                + (f": {message}" if message else ".")
            )
        result = response.get("result")
        if not isinstance(result, Mapping):
            raise ConnectorTransportError(
                "DNSFilter MCP tool result had an invalid shape."
            )
        return _normalize_tool_result(result)

    def _post(
        self,
        payload: Mapping[str, Any],
        token: str,
    ) -> Mapping[str, Any]:
        request = Request(
            DNSFILTER_MCP_URL,
            data=json.dumps(dict(payload)).encode("utf-8"),
            method="POST",
            headers={
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
                "User-Agent": _USER_AGENT,
            },
        )
        try:
            response = self._opener(
                request,
                timeout=self._timeout_seconds,
            )
            with response:
                raw = response.read().decode("utf-8")
                content_type = str(
                    response.headers.get("Content-Type") or ""
                )
        except HTTPError as exc:
            if exc.code == 401:
                raise DnsFilterMcpOAuthError(
                    "DNSFilter MCP OAuth session requires re-authentication."
                ) from exc
            raise ConnectorTransportError(
                f"DNSFilter MCP HTTP request failed with status {exc.code}."
            ) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise ConnectorTransportError(
                "DNSFilter MCP HTTP request failed."
            ) from exc

        if "text/event-stream" in content_type or raw.lstrip().startswith("event:"):
            return _parse_sse_json(raw)
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ConnectorTransportError(
                "DNSFilter MCP response was not valid JSON."
            ) from exc
        if not isinstance(decoded, Mapping):
            raise ConnectorTransportError(
                "DNSFilter MCP response had an invalid shape."
            )
        return dict(decoded)


def _parse_sse_json(raw: str) -> Mapping[str, Any]:
    messages: list[Mapping[str, Any]] = []
    for line in raw.splitlines():
        if not line.startswith("data: "):
            continue
        try:
            decoded = json.loads(line[6:])
        except json.JSONDecodeError as exc:
            raise ConnectorTransportError(
                "DNSFilter MCP SSE response contained invalid JSON."
            ) from exc
        if isinstance(decoded, Mapping):
            messages.append(dict(decoded))
    if not messages:
        raise ConnectorTransportError(
            "DNSFilter MCP SSE response contained no JSON-RPC result."
        )
    return messages[-1]


def _normalize_tool_result(result: Mapping[str, Any]) -> Mapping[str, Any]:
    if result.get("isError") is True:
        raise ConnectorTransportError(
            "DNSFilter MCP tool reported an execution error."
        )
    structured = result.get("structuredContent")
    if isinstance(structured, Mapping):
        return dict(structured)

    content = result.get("content")
    if isinstance(content, list) and len(content) == 1:
        item = content[0]
        if isinstance(item, Mapping) and item.get("type") == "text":
            text = str(item.get("text") or "")
            try:
                decoded = json.loads(text)
            except json.JSONDecodeError:
                return {"text": text}
            if isinstance(decoded, Mapping):
                return dict(decoded)
            return {"value": decoded}

    return {"content": content or []}
