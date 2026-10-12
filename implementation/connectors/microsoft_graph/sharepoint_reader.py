"""Reusable, bounded Microsoft Graph SharePoint reader.

Transport only: capability registration and requester information release MUST
happen in Jason's governed orchestrator before invoking these methods.
Never accept raw URLs, tokens, or tenant IDs from untrusted conversation text.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol
from urllib.parse import quote
from uuid import UUID

from connectors.core.contracts import ConnectorTransportError, HttpTransport


class SharePointTokenProvider(Protocol):
    def access_token_for_tenant(self, *, microsoft_tenant_id: str) -> str: ...


@dataclass(frozen=True, slots=True)
class MicrosoftGraphSharePointReader:
    tokens: SharePointTokenProvider
    transport: HttpTransport
    max_items: int = 50
    max_content_bytes: int = 10 * 1024 * 1024
    base_url: str = "https://graph.microsoft.com/v1.0"

    def __post_init__(self) -> None:
        if self.base_url != "https://graph.microsoft.com/v1.0":
            raise ValueError("Graph SharePoint reader requires canonical endpoint")
        if not (1 <= self.max_items <= 100):
            raise ValueError("max_items must be between 1 and 100")
        if not (1 <= self.max_content_bytes <= 25 * 1024 * 1024):
            raise ValueError("invalid document byte limit")

    @staticmethod
    def _id(value: str, name: str) -> str:
        if not isinstance(value, str) or not value or len(value) > 512:
            raise ValueError(f"{name} is required")
        if any(ch in value for ch in ("/", "?", "#", "\\", "%", "\r", "\n")):
            raise ValueError(f"unsafe {name}")
        return quote(value, safe=",-_.")

    def _auth(self, tenant_id: str) -> Mapping[str, str]:
        try:
            UUID(tenant_id)
        except (ValueError, AttributeError, TypeError) as exc:
            raise ValueError("validated Microsoft tenant ID is required") from exc
        token = self.tokens.access_token_for_tenant(microsoft_tenant_id=tenant_id)
        if not isinstance(token, str) or not token.strip():
            raise PermissionError("Microsoft application token is unavailable")
        return {"Authorization": "Bearer " + token.strip()}

    def _get(self, tenant_id: str, path: str, params: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
        response = self.transport.request(
            method="GET", url=self.base_url + path,
            headers=self._auth(tenant_id), params=params, timeout_seconds=20,
        )
        if not isinstance(response, Mapping):
            raise ConnectorTransportError("Unexpected Graph result shape")
        return response

    def list_libraries(self, *, tenant_id: str, site_id: str) -> Mapping[str, Any]:
        data = self._get(tenant_id, "/sites/" + self._id(site_id, "site_id") + "/drives",
                         {"$top": self.max_items})
        return self._list(data, {"id", "name", "webUrl", "driveType"}, "library")

    def list_children(self, *, tenant_id: str, drive_id: str,
                      folder_id: str | None = None) -> Mapping[str, Any]:
        path = "/drives/" + self._id(drive_id, "drive_id")
        path += "/root/children" if folder_id is None else "/items/" + self._id(folder_id, "folder_id") + "/children"
        data = self._get(tenant_id, path, {"$top": self.max_items})
        return self._list(data, {"id", "name", "webUrl", "size", "eTag", "lastModifiedDateTime", "file", "folder"}, "item")

    def read_metadata(self, *, tenant_id: str, drive_id: str, item_id: str) -> Mapping[str, Any]:
        data = self._get(tenant_id, "/drives/" + self._id(drive_id, "drive_id") +
                         "/items/" + self._id(item_id, "item_id"))
        if data.get("id") != item_id:
            raise ConnectorTransportError("Graph returned mismatched document identity")
        return {k: data[k] for k in
                ("id", "name", "webUrl", "size", "eTag", "lastModifiedDateTime", "file", "folder")
                if k in data}

    def read_bytes(self, *, tenant_id: str, drive_id: str, item_id: str) -> bytes:
        path = "/drives/" + self._id(drive_id, "drive_id") + "/items/" + self._id(item_id, "item_id") + "/content"
        data = self.transport.request_bytes(
            method="GET", url=self.base_url + path,
            headers=self._auth(tenant_id), timeout_seconds=30, max_bytes=self.max_content_bytes,
        )
        if not isinstance(data, bytes) or len(data) > self.max_content_bytes:
            raise ConnectorTransportError("Document exceeded bounded byte limit")
        return data

    def _list(self, response: Mapping[str, Any], fields: set[str], kind: str) -> Mapping[str, Any]:
        items = response.get("value")
        if not isinstance(items, list) or len(items) > self.max_items:
            raise ConnectorTransportError("Graph response missing/overran bounded item list")
        projected = []
        for entry in items:
            if not isinstance(entry, Mapping) or not isinstance(entry.get("id"), str):
                raise ConnectorTransportError("Graph item lacks verified identity")
            projected.append({k: entry[k] for k in fields if k in entry})
        return {"kind": kind, "items": projected, "count": len(projected),
                "more": bool(response.get("@odata.nextLink"))}
