from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol
from urllib.parse import quote

from connectors.core.contracts import (
    AuditSink,
    ConnectorAuthorizationError,
    ConnectorContext,
    ConnectorRequest,
    ConnectorResult,
    HttpTransport,
    require_capability,
)
from connectors.microsoft_graph.token import MicrosoftApplicationTokenProvider


@dataclass(frozen=True, slots=True)
class MicrosoftSharePointReadConnector:
    """Governed read-only SharePoint/OneDrive connector for Jason."""

    tokens: MicrosoftApplicationTokenProvider
    transport: HttpTransport
    audit: AuditSink
    default_client_id: str = "client-aot-internal"
    base_url: str = "https://graph.microsoft.com/v1.0"
    provider_name: str = "microsoft_sharepoint"

    capabilities = frozenset(
        {
            "microsoft_sharepoint.site.search",
            "microsoft_sharepoint.library.list",
            "microsoft_sharepoint.document.search",
            "microsoft_sharepoint.item.read",
        }
    )

    def execute(self, request: ConnectorRequest) -> ConnectorResult:
        require_capability(request, self.capabilities)
        if request.context.organization_id != "aot":
            raise ConnectorAuthorizationError("SharePoint read is restricted to the AOT organization boundary.")
        client_id = (request.context.client_id or self.default_client_id).strip()
        if not client_id:
            raise ConnectorAuthorizationError("A governed Microsoft client boundary is required.")

        token = self.tokens.acquire_for_client(
            client_id=client_id,
            correlation_id=request.context.correlation_id,
        )
        try:
            data = self._execute_with_token(request=request, access_token=token.access_token)
        finally:
            token = None
        return ConnectorResult(
            capability=request.context.capability,
            provider=self.provider_name,
            data=data,
        )

    def _execute_with_token(self, *, request: ConnectorRequest, access_token: str) -> Mapping[str, Any]:
        capability = request.context.capability
        args = request.arguments
        headers = {"Authorization": f"Bearer {access_token}"}

        if capability == "microsoft_sharepoint.site.search":
            query = self._required(args, "query")
            url = f"{self.base_url}/sites"
            params = {"search": query, "$select": "id,name,displayName,webUrl"}
            body = None
        elif capability == "microsoft_sharepoint.library.list":
            site_id = quote(self._required(args, "site_id"), safe=",-")
            url = f"{self.base_url}/sites/{site_id}/drives"
            params = {"$select": "id,name,driveType,webUrl"}
            body = None
        elif capability == "microsoft_sharepoint.item.read":
            drive_id = quote(self._required(args, "drive_id"), safe="!-_")
            item_id = quote(self._required(args, "item_id"), safe="!-_")
            url = f"{self.base_url}/drives/{drive_id}/items/{item_id}"
            params = {"$select": "id,name,webUrl,size,file,folder,parentReference,lastModifiedDateTime,createdDateTime"}
            body = None
        elif capability == "microsoft_sharepoint.document.search":
            query = self._required(args, "query")
            url = f"{self.base_url}/search/query"
            params = None
            body = {
                "requests": [
                    {
                        "entityTypes": ["driveItem"],
                        "query": {"queryString": query},
                        "from": 0,
                        "size": self._bounded_size(args.get("page_size")),
                        "fields": [
                            "id",
                            "name",
                            "webUrl",
                            "size",
                            "file",
                            "folder",
                            "parentReference",
                            "lastModifiedDateTime",
                            "createdDateTime",
                        ],
                    }
                ]
            }
        else:
            raise ConnectorAuthorizationError("Unsupported SharePoint read capability.")

        operation = capability
        self.audit.record(
            "connector.requested",
            request.context,
            {"provider": self.provider_name, "operation": operation},
        )
        payload = self.transport.request(
            method="POST" if body is not None else "GET",
            url=url,
            headers=headers,
            params=params,
            json=body,
            timeout_seconds=30.0,
        )
        self.audit.record(
            "connector.completed",
            request.context,
            {"provider": self.provider_name, "operation": operation},
        )
        return payload

    @staticmethod
    def _required(args: Mapping[str, Any], name: str) -> str:
        value = str(args.get(name) or "").strip()
        if not value:
            raise ValueError(f"{name} is required")
        return value

    @staticmethod
    def _bounded_size(value: object) -> int:
        try:
            parsed = int(value) if value is not None else 25
        except (TypeError, ValueError):
            parsed = 25
        return max(1, min(parsed, 100))
