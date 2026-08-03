from __future__ import annotations

from typing import Any, Mapping

from connectors.core.connector_base import (
    ConnectorBase,
    PreparedRequest,
)
from connectors.core.contracts import ConnectorRequest


class ItGlueConnector(ConnectorBase):
    provider_name = "it_glue"
    logical_secret = "it_glue.readonly"

    capabilities = frozenset(
        {
            "it_glue.organization.get",
            "it_glue.configuration.search",
            "it_glue.flexible_asset.search",
            "it_glue.document.get",
            "it_glue.relationships.list",
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
                "x-api-key": credentials["api_key"],
                "Accept": "application/vnd.api+json",
            },
            params=params,
            audit_operation=path,
        )

    @staticmethod
    def _resolve_operation(
        capability: str,
        arguments: Mapping[str, Any],
    ) -> tuple[str, Mapping[str, Any] | None]:
        if capability == "it_glue.organization.get":
            return (
                f"/organizations/{int(arguments['organization_id'])}",
                None,
            )

        if capability == "it_glue.configuration.search":
            return (
                "/configurations",
                {
                    "filter[organization_id]": (
                        arguments["organization_id"]
                    ),
                    "filter[name]": arguments.get("name"),
                },
            )

        if capability == "it_glue.flexible_asset.search":
            return (
                "/flexible_assets",
                {
                    "filter[organization_id]": (
                        arguments["organization_id"]
                    ),
                    "filter[flexible_asset_type_id]": (
                        arguments.get("flexible_asset_type_id")
                    ),
                },
            )

        if capability == "it_glue.document.get":
            return (
                f"/documents/{int(arguments['document_id'])}",
                None,
            )

        if capability == "it_glue.relationships.list":
            return (
                "/relationships",
                {
                    "filter[resource_type]": (
                        arguments["resource_type"]
                    ),
                    "filter[resource_id]": (
                        arguments["resource_id"]
                    ),
                },
            )

        raise ValueError(
            f"Unsupported capability: {capability}"
        )
