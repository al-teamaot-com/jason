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
