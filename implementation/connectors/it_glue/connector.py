from __future__ import annotations

from typing import Mapping

from connectors.it_glue.operations import resolve_operation
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
        method, path, params = resolve_operation(
            request.context.capability,
            request.arguments,
        )

        return PreparedRequest(
            method=method,
            url=f"{credentials['base_url'].rstrip('/')}{path}",
            headers={
                "x-api-key": credentials["api_key"],
                "Accept": "application/vnd.api+json",
            },
            params=params,
            audit_operation=path,
        )
