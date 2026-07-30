from __future__ import annotations

from typing import Any, Mapping

from connectors.core.contracts import AuditSink, ConnectorRequest, ConnectorResult, HttpTransport, SecretResolver, require_capability


class ItGlueConnector:
    provider_name = "it_glue"
    capabilities = frozenset({"it_glue.organization.get", "it_glue.configuration.search", "it_glue.flexible_asset.search", "it_glue.document.get", "it_glue.relationships.list"})

    def __init__(self, secrets: SecretResolver, transport: HttpTransport, audit: AuditSink) -> None:
        self._secrets = secrets
        self._transport = transport
        self._audit = audit

    def execute(self, request: ConnectorRequest) -> ConnectorResult:
        require_capability(request, self.capabilities)
        credentials = self._secrets.resolve("it_glue.readonly", request.context)
        base_url = credentials["base_url"].rstrip("/")
        headers = {"x-api-key": credentials["api_key"], "Accept": "application/vnd.api+json"}
        path, params = self._resolve_operation(request.context.capability, request.arguments)
        self._audit.record("connector.requested", request.context, {"provider": self.provider_name, "operation": path})
        payload = self._transport.request(method="GET", url=f"{base_url}{path}", headers=headers, params=params)
        self._audit.record("connector.completed", request.context, {"provider": self.provider_name})
        return ConnectorResult(request.context.capability, self.provider_name, payload)

    @staticmethod
    def _resolve_operation(capability: str, arguments: Mapping[str, Any]) -> tuple[str, Mapping[str, Any] | None]:
        if capability == "it_glue.organization.get":
            return f"/organizations/{int(arguments['organization_id'])}", None
        if capability == "it_glue.configuration.search":
            return "/configurations", {"filter[organization_id]": arguments["organization_id"], "filter[name]": arguments.get("name")}
        if capability == "it_glue.flexible_asset.search":
            return "/flexible_assets", {"filter[organization_id]": arguments["organization_id"], "filter[flexible_asset_type_id]": arguments.get("flexible_asset_type_id")}
        if capability == "it_glue.document.get":
            return f"/documents/{int(arguments['document_id'])}", None
        if capability == "it_glue.relationships.list":
            return "/relationships", {"filter[resource_type]": arguments["resource_type"], "filter[resource_id]": arguments["resource_id"]}
        raise ValueError(f"Unsupported capability: {capability}")
