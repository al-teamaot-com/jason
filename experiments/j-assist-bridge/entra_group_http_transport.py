"""Narrow server-only Graph transport for AOT J-Assist group verification.

It consumes Jason's EXISTING tenant-bound Graph token provider and governed
HttpTransport conventions. No client secrets, tokens, app consent or network
listener is defined here; nothing is registered in production.

Only two exact Microsoft Graph v1.0 operations are permitted:
GET /users/{oid}?$select=id,accountEnabled
POST /users/{oid}/checkMemberGroups {groupIds:[approved group ID]}
"""
from __future__ import annotations

from typing import Protocol, Mapping, Any
from urllib.parse import urlsplit
import re

from entra_group_screen_authority import AOT_JASSIST_PILOT_GROUP_ID
from entra_send_authority import AOT_ENTRA_TENANT_ID

_GRAPH_ROOT = "https://graph.microsoft.com/v1.0"
_USER_PATH = re.compile(r"^/v1\.0/users/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})(/checkMemberGroups)?$", re.I)


class TenantTokenProvider(Protocol):
    def access_token_for_tenant(self, *, microsoft_tenant_id: str) -> str: ...


class HttpTransport(Protocol):
    def request(
        self, *, method: str, url: str, headers: Mapping[str, str],
        params: Mapping[str, Any] | None = None,
        json: Mapping[str, Any] | None = None,
        timeout_seconds: float = 30.0,
    ) -> Any: ...


class AotGraphMembershipHttpTransport:
    """Graph credentials stay server-side, never in Chrome or a model tool."""

    def __init__(self, *, tokens: TenantTokenProvider, transport: HttpTransport):
        if (not callable(getattr(tokens, "access_token_for_tenant", None))
                or not callable(getattr(transport, "request", None))):
            raise ValueError("trusted Graph token provider and transport required")
        self._tokens = tokens
        self._transport = transport

    @staticmethod
    def _check_url(url: str, *, method: str) -> str:
        if not isinstance(url, str):
            raise ValueError("invalid Graph URL")
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.netloc != "graph.microsoft.com":
            raise ValueError("Graph request must use canonical HTTPS host")
        match = _USER_PATH.fullmatch(parsed.path)
        if not match:
            raise ValueError("unsupported Graph path")
        oid, suffix = match.groups()
        if method == "GET":
            if suffix or parsed.query != "$select=id,accountEnabled":
                raise ValueError("unapproved Graph user read")
        elif method == "POST":
            if suffix != "/checkMemberGroups" or parsed.query:
                raise ValueError("unapproved Graph membership check")
        else:
            raise ValueError("unsupported Graph method")
        if parsed.fragment or parsed.username or parsed.password or parsed.port:
            raise ValueError("Graph authority modified")
        return _GRAPH_ROOT + "/users/" + oid.lower() + (suffix or "")

    def _headers(self) -> dict[str, str]:
        token = self._tokens.access_token_for_tenant(
            microsoft_tenant_id=AOT_ENTRA_TENANT_ID
        )
        if not isinstance(token, str) or not token.strip():
            raise PermissionError("AOT Graph read-only token unavailable")
        return {"Authorization": "Bearer " + token.strip()}

    def get_json(self, url: str) -> dict:
        canonical = self._check_url(url, method="GET")
        result = self._transport.request(
            method="GET", url=canonical,
            headers=self._headers(),
            params={"$select": "id,accountEnabled"},
            timeout_seconds=10.0,
        )
        if not isinstance(result, dict):
            raise ValueError("invalid Graph user response")
        return result

    def post_json(self, url: str, body: dict) -> dict:
        canonical = self._check_url(url, method="POST")
        if (not isinstance(body, dict)
                or body != {"groupIds": [AOT_JASSIST_PILOT_GROUP_ID]}):
            raise ValueError("membership scope exceeds exact approved group")
        result = self._transport.request(
            method="POST", url=canonical,
            headers=self._headers(),
            json={"groupIds": [AOT_JASSIST_PILOT_GROUP_ID]},
            timeout_seconds=10.0,
        )
        if not isinstance(result, dict):
            raise ValueError("invalid Graph membership response")
        return result
