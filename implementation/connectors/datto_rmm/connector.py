from __future__ import annotations

from typing import Any, Mapping

from connectors.core.contracts import AuditSink, ConnectorRequest, ConnectorResult, HttpTransport, SecretResolver, require_capability


class DattoRmmConnector:
    provider_name = "datto_rmm"
    capabilities = frozenset(
        {
            "datto_rmm.device.get",
            "datto_rmm.device.search",
            "datto_rmm.alerts.list",
            "datto_rmm.patch_status.get",
            "datto_rmm.component_results.list",
        }
    )

    def __init__(self, secrets: SecretResolver, transport: HttpTransport, audit: AuditSink) -> None:
        self._secrets = secrets
        self._transport = transport
        self._audit = audit

    def execute(self, request: ConnectorRequest) -> ConnectorResult:
        require_capability(request, self.capabilities)
        credentials = self._secrets.resolve("datto_rmm.readonly", request.context)
        base_url = credentials["base_url"].rstrip("/")
        headers = {"Authorization": f"Bearer {credentials['access_token']}", "Accept": "application/json"}
        path, params = self._resolve_operation(request.context.capability, request.arguments)
        self._audit.record("connector.requested", request.context, {"provider": self.provider_name, "operation": path})
        payload = self._transport.request(method="GET", url=f"{base_url}{path}", headers=headers, params=params)
        self._audit.record("connector.completed", request.context, {"provider": self.provider_name})
        return ConnectorResult(request.context.capability, self.provider_name, payload)

    @staticmethod
    def _resolve_operation(capability: str, arguments: Mapping[str, Any]) -> tuple[str, Mapping[str, Any] | None]:
        # Endpoint templates remain isolated here so vendor API changes do not affect Jason capabilities.
        if capability == "datto_rmm.device.get":
            return f"/api/v2/device/{arguments['device_uid']}", None
        if capability == "datto_rmm.device.search":
            return "/api/v2/account/devices", {"search": arguments.get("search", "")}
        if capability == "datto_rmm.alerts.list":
            return "/api/v2/account/alerts/open", {"siteUid": arguments.get("site_uid")}
        if capability == "datto_rmm.patch_status.get":
            return f"/api/v2/device/{arguments['device_uid']}/audit", None
        if capability == "datto_rmm.component_results.list":
            return f"/api/v2/device/{arguments['device_uid']}/jobs", None
        raise ValueError(f"Unsupported capability: {capability}")
