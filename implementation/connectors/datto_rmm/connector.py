from __future__ import annotations

from typing import Any, Mapping

from connectors.core.connector_base import ConnectorBase, PreparedRequest
from connectors.core.contracts import ConnectorRequest, ConnectorResult, require_capability
from connectors.datto_rmm.auth import acquire_access_token, require_durable_credentials


class DattoRmmConnector(ConnectorBase):
    provider_name = "datto_rmm"
    logical_secret = "datto_rmm.readonly"

    capabilities = frozenset(
        {
            "datto_rmm.device.get",
            "datto_rmm.device.search",
            "datto_rmm.alerts.list",
            "datto_rmm.patch_status.get",
            "datto_rmm.component_results.list",
        }
    )

    def execute(self, request: ConnectorRequest) -> ConnectorResult:
        require_capability(request, self.capabilities)
        credentials = self._secrets.resolve(self.logical_secret, request.context)
        require_durable_credentials(credentials)

        token = acquire_access_token(
            credentials=credentials,
            transport=self._transport,
        )
        prepared = self._prepare_api_request(
            request=request,
            credentials=credentials,
            access_token=token.access_token,
            token_type=token.token_type,
        )

        operation = prepared.audit_operation or prepared.url
        self._audit.record(
            "connector.requested",
            request.context,
            {"provider": self.provider_name, "operation": operation},
        )
        payload = self._transport.request(
            method=prepared.method,
            url=prepared.url,
            headers=prepared.headers,
            params=prepared.params,
            json=prepared.json,
            timeout_seconds=prepared.timeout_seconds,
        )
        self._audit.record(
            "connector.completed",
            request.context,
            {"provider": self.provider_name},
        )
        return ConnectorResult(
            capability=request.context.capability,
            provider=self.provider_name,
            data=payload,
        )

    def prepare_request(
        self,
        request: ConnectorRequest,
        credentials: Mapping[str, str],
    ) -> PreparedRequest:
        """Reject callers that try to persist a bearer token as configuration."""
        require_durable_credentials(credentials)
        raise RuntimeError(
            "Datto RMM API requests require runtime token acquisition; use execute()."
        )

    def _prepare_api_request(
        self,
        *,
        request: ConnectorRequest,
        credentials: Mapping[str, str],
        access_token: str,
        token_type: str,
    ) -> PreparedRequest:
        path, params = self._resolve_operation(
            request.context.capability,
            request.arguments,
        )
        return PreparedRequest(
            method="GET",
            url=f"{credentials['api_url'].rstrip('/')}{path}",
            headers={
                "Authorization": f"{token_type} {access_token}",
                "Accept": "application/json",
            },
            params=params,
            audit_operation=path,
        )

    @staticmethod
    def _resolve_operation(
        capability: str,
        arguments: Mapping[str, Any],
    ) -> tuple[str, Mapping[str, Any] | None]:
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
