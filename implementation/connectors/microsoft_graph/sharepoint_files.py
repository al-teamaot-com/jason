"""Bounded Microsoft Graph SharePoint file operations for governed workflows."""
from __future__ import annotations

from dataclasses import dataclass, field
from time import sleep
from typing import Any, Callable, Mapping, Protocol
from urllib.parse import quote

from connectors.core.contracts import ConnectorTransportError, HttpTransport


class TenantTokenProvider(Protocol):
    def access_token_for_tenant(self, *, microsoft_tenant_id: str) -> str: ...


@dataclass(frozen=True, slots=True)
class SharePointFileClient:
    tokens: TenantTokenProvider
    transport: HttpTransport
    base_url: str = "https://graph.microsoft.com/v1.0"
    timeout_seconds: float = 30.0
    max_attempts: int = 3
    max_retry_delay_seconds: float = 10.0
    max_download_bytes: int = 16 * 1024 * 1024
    sleeper: Callable[[float], None] = field(default=sleep, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.base_url.rstrip("/") != "https://graph.microsoft.com/v1.0":
            raise ValueError("SharePoint client must use Microsoft Graph v1.0")
        if not 1 <= self.max_attempts <= 5:
            raise ValueError("max_attempts must be between 1 and 5")
        if not 0 <= self.max_retry_delay_seconds <= 60:
            raise ValueError("max_retry_delay_seconds must be between 0 and 60")
        if not 1 <= self.max_download_bytes <= 32 * 1024 * 1024:
            raise ValueError("max_download_bytes exceeds governed bound")

    def _headers(self, tenant_id: str) -> Mapping[str, str]:
        token = self.tokens.access_token_for_tenant(microsoft_tenant_id=tenant_id)
        if not token or not str(token).strip():
            raise PermissionError("Microsoft Graph application token is unavailable")
        return {"Authorization": f"Bearer {str(token).strip()}"}

    def _request(self, *, tenant_id: str, method: str, url: str,
                 body: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
        headers = self._headers(tenant_id)
        for attempt in range(1, self.max_attempts + 1):
            try:
                result = self.transport.request(method=method, url=url, headers=headers,
                                                json=body, timeout_seconds=self.timeout_seconds)
                if not isinstance(result, Mapping):
                    raise ConnectorTransportError("Microsoft Graph returned an unexpected shape")
                return dict(result)
            except ConnectorTransportError as error:
                if error.status_code != 429 or attempt >= self.max_attempts:
                    raise
                delay = error.retry_after_seconds
                if delay is None:
                    delay = float(2 ** (attempt - 1))
                delay = min(max(float(delay), 0.0), self.max_retry_delay_seconds)
                if delay:
                    self.sleeper(delay)
        raise RuntimeError("unreachable SharePoint retry state")

    def _request_bytes(self, *, tenant_id: str, url: str) -> bytes:
        headers = self._headers(tenant_id)
        for attempt in range(1, self.max_attempts + 1):
            try:
                return self.transport.request_bytes(method="GET", url=url, headers=headers,
                                                    timeout_seconds=self.timeout_seconds,
                                                    max_bytes=self.max_download_bytes)
            except ConnectorTransportError as error:
                if error.status_code != 429 or attempt >= self.max_attempts:
                    raise
                delay = error.retry_after_seconds
                if delay is None:
                    delay = float(2 ** (attempt - 1))
                delay = min(max(float(delay), 0.0), self.max_retry_delay_seconds)
                if delay:
                    self.sleeper(delay)
        raise RuntimeError("unreachable SharePoint retry state")

    def get_item_by_path(self, *, tenant_id: str, drive_id: str, path: str) -> Mapping[str, Any]:
        normalized = path.strip().strip("/")
        if not normalized or ".." in normalized.split("/"):
            raise ValueError("SharePoint path is invalid")
        encoded = quote(normalized, safe="/")
        return self._request(
            tenant_id=tenant_id, method="GET",
            url=f"{self.base_url}/drives/{quote(drive_id.strip(), safe='')}/root:/{encoded}",
        )

    def list_children(self, *, tenant_id: str, drive_id: str, item_id: str) -> tuple[Mapping[str, Any], ...]:
        drive = quote(drive_id.strip(), safe="")
        item = quote(item_id.strip(), safe="")
        if not drive or not item:
            raise ValueError("drive_id and item_id are required")
        url = f"{self.base_url}/drives/{drive}/items/{item}/children?$top=200"
        values: list[Mapping[str, Any]] = []
        pages = 0
        while url:
            pages += 1
            if pages > 50:
                raise ConnectorTransportError("SharePoint folder traversal exceeded page bound")
            data = self._request(tenant_id=tenant_id, method="GET", url=url)
            raw = data.get("value")
            if not isinstance(raw, list):
                raise ConnectorTransportError("SharePoint children response is invalid")
            for entry in raw:
                if isinstance(entry, Mapping):
                    values.append(dict(entry))
            nxt = data.get("@odata.nextLink")
            url = str(nxt).strip() if isinstance(nxt, str) and nxt.strip() else ""
        return tuple(values)

    def download_file(self, *, tenant_id: str, drive_id: str, item_id: str) -> bytes:
        return self._request_bytes(
            tenant_id=tenant_id,
            url=f"{self.base_url}/drives/{quote(drive_id.strip(), safe='')}/items/{quote(item_id.strip(), safe='')}/content",
        )

    def create_folder(self, *, tenant_id: str, drive_id: str, parent_id: str, name: str) -> Mapping[str, Any]:
        folder_name = name.strip()
        if not folder_name or "/" in folder_name or "\\" in folder_name:
            raise ValueError("folder name is invalid")
        return self._request(
            tenant_id=tenant_id, method="POST",
            url=f"{self.base_url}/drives/{quote(drive_id.strip(), safe='')}/items/{quote(parent_id.strip(), safe='')}/children",
            body={"name": folder_name, "folder": {}, "@microsoft.graph.conflictBehavior": "fail"},
        )

    def move_and_rename(self, *, tenant_id: str, drive_id: str, item_id: str,
                        destination_parent_id: str, new_name: str) -> Mapping[str, Any]:
        name = new_name.strip()
        if not name or "/" in name or "\\" in name:
            raise ValueError("destination filename is invalid")
        return self._request(
            tenant_id=tenant_id, method="PATCH",
            url=f"{self.base_url}/drives/{quote(drive_id.strip(), safe='')}/items/{quote(item_id.strip(), safe='')}",
            body={"name": name, "parentReference": {"id": destination_parent_id.strip()}},
        )

    def get_item(self, *, tenant_id: str, drive_id: str, item_id: str) -> Mapping[str, Any]:
        return self._request(
            tenant_id=tenant_id, method="GET",
            url=f"{self.base_url}/drives/{quote(drive_id.strip(), safe='')}/items/{quote(item_id.strip(), safe='')}",
        )
