"""Fail-closed SharePoint pilot reader; only the owner-approved AOT Admin site.

This module is an unactivated connector building block, not a production capability.
Graph application/site consent and Jason's information-release gates remain separate.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol
from urllib.parse import quote

from connectors.core.contracts import ConnectorTransportError, HttpTransport


APPROVED_SITE_ID = (
    "absolnet.sharepoint.com,c85a85f8-6a50-4569-880f-d261c65df2bb,"
    "e5b7a724-dc9b-406b-aed8-2961f1f71153"
)


class TenantTokens(Protocol):
    def access_token_for_tenant(self, *, microsoft_tenant_id: str) -> str: ...


@dataclass(frozen=True, slots=True)
class AOTAdminSharePointReader:
    tokens: TenantTokens
    transport: HttpTransport
    approved_tenant_id: str
    approved_site_id: str = APPROVED_SITE_ID

    def __post_init__(self) -> None:
        if not self.approved_tenant_id.strip() or self.approved_site_id != APPROVED_SITE_ID:
            raise ValueError("Exact approved tenant and AOT Admin site are required")

    def _get(self, tenant_id: str, path: str, params: Mapping[str, object]) -> Mapping[str, Any]:
        if tenant_id != self.approved_tenant_id:
            raise PermissionError("Microsoft tenant mismatch")
        token = self.tokens.access_token_for_tenant(microsoft_tenant_id=tenant_id)
        if not isinstance(token, str) or not token.strip():
            raise PermissionError("Graph token unavailable")
        result = self.transport.request(
            method="GET", url="https://graph.microsoft.com/v1.0/" + path,
            headers={"Authorization": "Bearer " + token},
            params=params, timeout_seconds=20.0,
        )
        if not isinstance(result, Mapping):
            raise ConnectorTransportError("Unexpected Graph result")
        return result

    @staticmethod
    def _id(value: str) -> str:
        if not isinstance(value, str) or not value.strip() or len(value) > 512:
            raise ValueError("A nonempty bounded Graph ID is required")
        if "/" in value or "\\" in value or "?" in value or "#" in value:
            raise ValueError("Graph IDs must not contain path delimiters")
        return quote(value.strip(), safe="")

    def list_libraries(self, *, tenant_id: str) -> tuple[Mapping[str, Any], ...]:
        data = self._get(tenant_id, "sites/" + self._id(self.approved_site_id) + "/drives",
                         {"$top": 25, "$select": "id,name,webUrl,driveType"})
        rows = data.get("value")
        if not isinstance(rows, list) or len(rows) > 25 or data.get("@odata.nextLink"):
            raise ConnectorTransportError("Unbounded or malformed SharePoint libraries")
        return tuple({"id": self._id(row["id"]), "name": row.get("name"),
                      "webUrl": row.get("webUrl")} for row in rows if isinstance(row, dict))

    def item_metadata(self, *, tenant_id: str, drive_id: str, item_id: str) -> Mapping[str, Any]:
        drive = self._id(drive_id)
        item = self._id(item_id)
        # Verify the drive belongs to the approved site, not merely that Graph exposes it.
        libraries = self.list_libraries(tenant_id=tenant_id)
        if drive not in {lib["id"] for lib in libraries}:
            raise PermissionError("Drive not in the approved AOT Admin site")
        data = self._get(tenant_id, f"drives/{drive}/items/{item}",
                         {"$select": "id,name,webUrl,size,eTag,lastModifiedDateTime,parentReference,file"})
        if data.get("id") != item_id.strip() or not isinstance(data.get("file"), Mapping):
            raise ConnectorTransportError("Graph item identity or file type mismatch")
        parent = data.get("parentReference") or {}
        if not isinstance(parent, Mapping) or parent.get("driveId") != drive_id.strip():
            raise ConnectorTransportError("Graph item drive mismatch")
        return {"id": data["id"], "name": data.get("name"), "webUrl": data.get("webUrl"),
                "size": data.get("size"), "eTag": data.get("eTag"),
                "lastModifiedDateTime": data.get("lastModifiedDateTime"),
                "driveId": drive_id.strip(), "siteId": self.approved_site_id}

    def list_files(self, *, tenant_id: str, drive_id: str, folder_id: str = "root",
                   maximum_records: int = 25) -> tuple[Mapping[str, Any], ...]:
        """Bounded folder listing for approved libraries; not a tenant-wide search."""
        if isinstance(maximum_records, bool) or not 1 <= maximum_records <= 25:
            raise ValueError("maximum_records must be between 1 and 25")
        drive = self._id(drive_id)
        if drive not in {row["id"] for row in self.list_libraries(tenant_id=tenant_id)}:
            raise PermissionError("Drive not in the approved AOT Admin site")
        endpoint = (f"drives/{drive}/root/children" if folder_id == "root"
                    else f"drives/{drive}/items/{self._id(folder_id)}/children")
        data = self._get(tenant_id, endpoint,
                         {"$top": maximum_records,
                          "$select": "id,name,webUrl,size,eTag,lastModifiedDateTime,folder,file,parentReference"})
        records = data.get("value")
        if not isinstance(records, list) or len(records) > maximum_records or data.get("@odata.nextLink"):
            raise ConnectorTransportError("Unbounded or malformed SharePoint folder listing")
        results = []
        for record in records:
            if not isinstance(record, Mapping) or not isinstance(record.get("id"), str):
                raise ConnectorTransportError("Malformed SharePoint folder item")
            parent = record.get("parentReference")
            if not isinstance(parent, Mapping) or parent.get("driveId") != drive_id:
                raise ConnectorTransportError("SharePoint folder item drive mismatch")
            results.append({
                "id": record["id"], "name": record.get("name"),
                "webUrl": record.get("webUrl"), "size": record.get("size"),
                "eTag": record.get("eTag"),
                "lastModifiedDateTime": record.get("lastModifiedDateTime"),
                "isFolder": isinstance(record.get("folder"), Mapping),
                "driveId": drive_id, "siteId": self.approved_site_id,
            })
        return tuple(results)

    def file_bytes(self, *, tenant_id: str, drive_id: str, item_id: str,
                   max_bytes: int = 1048576) -> bytes:
        """Retrieve one verified file; no arbitrary Graph URLs or content writes."""
        if isinstance(max_bytes, bool) or not 1 <= max_bytes <= 1048576:
            raise ValueError("Content limit must be between 1 and 1048576 bytes")
        metadata = self.item_metadata(tenant_id=tenant_id, drive_id=drive_id, item_id=item_id)
        if not isinstance(metadata["size"], int) or metadata["size"] > max_bytes:
            raise ValueError("File exceeds approved content-read byte limit")
        token = self.tokens.access_token_for_tenant(microsoft_tenant_id=tenant_id)
        content = self.transport.request_bytes(
            method="GET",
            url="https://graph.microsoft.com/v1.0/drives/" + self._id(drive_id)
                + "/items/" + self._id(item_id) + "/content",
            headers={"Authorization": "Bearer " + token},
            params=None, timeout_seconds=20.0, max_bytes=max_bytes,
        )
        if not isinstance(content, bytes) or len(content) > max_bytes:
            raise ConnectorTransportError("Graph content exceeded bounded byte limit")
        return content
