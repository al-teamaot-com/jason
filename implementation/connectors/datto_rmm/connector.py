from __future__ import annotations

from typing import Any, Mapping

from connectors.core.connector_base import (
    ConnectorBase,
    PreparedRequest,
)
from connectors.core.contracts import ConnectorRequest


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

    def prepare_request(
        self,
        request: ConnectorRequest,
        credentials: Mapping[str, str],
    ) -> PreparedRequest:
        path, params = self._resolve_operation(
            request.context.capability,
            request.arguments,
        )

        return PreparedRequest(
            method="GET",
            url=f"{credentials['base_url'].rstrip('/')}{path}",
            headers={
                "Authorization": (
                    f"Bearer {credentials['access_token']}"
                ),
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
            return (
                f"/api/v2/device/{arguments['device_uid']}",
                None,
            )

        if capability == "datto_rmm.device.search":
            return (
                "/api/v2/account/devices",
                {"search": arguments.get("search", "")},
            )

        if capability == "datto_rmm.alerts.list":
            return (
                "/api/v2/account/alerts/open",
                {"siteUid": arguments.get("site_uid")},
            )

        if capability == "datto_rmm.patch_status.get":
            return (
                f"/api/v2/device/{arguments['device_uid']}/audit",
                None,
            )

        if capability == "datto_rmm.component_results.list":
            return (
                f"/api/v2/device/{arguments['device_uid']}/jobs",
                None,
            )

        raise ValueError(
            f"Unsupported capability: {capability}"
        )
