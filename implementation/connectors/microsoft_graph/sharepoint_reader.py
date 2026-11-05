"""Read-only Microsoft Graph SharePoint transport used by governed Jason connectors.

This is not an access control boundary by itself. Calling code MUST resolve the
tenant and authorized site from Jason's validated identity and information-release
policy. Never expose this transport as an unrestricted agent or MCP capability.
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
        if isinstance(self.max_items, bool) or not 1 <= self.max_items <= 100:
            raise ValueError("max_items must be between 1 and 100")
        if isinstance(self.max_content_bytes, bool) or not 1 <= self.max_content_bytes <= 15 * 1024 * 1024:
            raise ValueError("invalid document byte limit")

    @staticmethod
    def _id(value: str, name: str) -> str:
        if not isinstance(value, str) or not value.strip() or value != value.strip() or len(value) > 512:
            raise ValueError(f"{name} is required")
        if any(ch in value for ch in ("/", "?", "#", "\\", "%", "\r", "\n", "\x00")):
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

    def _list(self, response: Mapping[str, Any], fields: set[str]) -> list[Mapping[str, Any]]:
        items = response.get("value")
        # An unresolved Graph nextLink must fail closed rather than quietly dropping records.
        if not isinstance(items, list) or len(items) > self.max_items or response.get("@odata.nextLink"):
            raise ConnectorTransportError("Unbounded or paged SharePoint response")
        projected = []
        for entry in items:
            if not isinstance(entry, Mapping) or not isinstance(entry.get("id"), str):
                raise ConnectorTransportError("Graph item lacks verified identity")
            projected.append({k: entry[k] for k in fields if k in entry})
        return projected

    def list_libraries(self, *, tenant_id: str, site_id: str) -> Mapping[str, Any]:
        data = self._get(tenant_id, "/sites/" + self._id(site_id, "site_id") + "/drives",
                         {"$top": self.max_items, "$select": "id,name,webUrl,driveType"})
        items = self._list(data, {"id", "name", "webUrl", "driveType"})
        return {"items": items, "count": len(items), "site_id": site_id}

    def _require_site_drive(self, tenant_id: str, site_id: str, drive_id: str) -> None:
        libraries = self.list_libraries(tenant_id=tenant_id, site_id=site_id)["items"]
        if drive_id not in {entry["id"] for entry in libraries}:
            raise PermissionError("Drive is not in the approved SharePoint site")

    def list_children(self, *, tenant_id: str, site_id: str, drive_id: str,
                      folder_id: str | None = None) -> Mapping[str, Any]:
        self._id(drive_id, "drive_id")
        if folder_id is not None:
            self._id(folder_id, "folder_id")
        self._require_site_drive(tenant_id, site_id, drive_id)
        path = "/drives/" + self._id(drive_id, "drive_id")
        path += "/root/children" if folder_id is None else "/items/" + self._id(folder_id, "folder_id") + "/children"
        data = self._get(tenant_id, path, {
            "$top": self.max_items,
            "$select": "id,name,webUrl,size,eTag,lastModifiedDateTime,file,folder,parentReference",
        })
        items = self._list(data, {"id", "name", "webUrl", "size", "eTag",
                                  "lastModifiedDateTime", "file", "folder"})
        original = data["value"]
        for entry in original:
            parent = entry.get("parentReference")
            if not isinstance(parent, Mapping) or parent.get("driveId") != drive_id:
                raise ConnectorTransportError("Graph returned an item outside the verified drive")
        return {"items": items, "count": len(items), "site_id": site_id, "drive_id": drive_id}

    def _metadata_for_verified_drive(self, tenant_id: str, drive_id: str, item_id: str) -> Mapping[str, Any]:
        data = self._get(tenant_id, "/drives/" + self._id(drive_id, "drive_id") +
                         "/items/" + self._id(item_id, "item_id"), {
                             "$select": "id,name,webUrl,size,eTag,lastModifiedDateTime,file,parentReference"
                         })
        parent = data.get("parentReference")
        if (data.get("id") != item_id or
            not isinstance(data.get("file"), Mapping) or
            not isinstance(parent, Mapping) or parent.get("driveId") != drive_id):
            raise ConnectorTransportError("Graph returned mismatched file or drive identity")
        return {k: data[k] for k in (
            "id", "name", "webUrl", "size", "eTag", "lastModifiedDateTime", "file"
        ) if k in data}

    def read_metadata(self, *, tenant_id: str, site_id: str, drive_id: str,
                      item_id: str) -> Mapping[str, Any]:
        self._id(item_id, "item_id")
        self._id(drive_id, "drive_id")
        self._require_site_drive(tenant_id, site_id, drive_id)
        data = dict(self._metadata_for_verified_drive(tenant_id, drive_id, item_id))
        data["site_id"] = site_id
        data["drive_id"] = drive_id
        return data

    def read_bytes(self, *, tenant_id: str, site_id: str, drive_id: str,
                   item_id: str) -> bytes:
        info = self.read_metadata(tenant_id=tenant_id, site_id=site_id,
                                  drive_id=drive_id, item_id=item_id)
        size = info.get("size")
        if isinstance(size, bool) or not isinstance(size, int) or size < 0 or size > self.max_content_bytes:
            raise ValueError("File has no verified bounded byte size")
        path = "/drives/" + self._id(drive_id, "drive_id") + "/items/" + self._id(item_id, "item_id") + "/content"
        data = self.transport.request_bytes(
            method="GET", url=self.base_url + path,
            headers=self._auth(tenant_id), timeout_seconds=30, max_bytes=self.max_content_bytes,
        )
        if not isinstance(data, bytes) or len(data) > self.max_content_bytes or len(data) != size:
            raise ConnectorTransportError("Document content failed the bounded size check")
        return data
