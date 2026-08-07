from __future__ import annotations

from typing import Mapping

from connectors.autotask.operations import resolve_operation
from connectors.core.connector_base import (
    ConnectorBase,
    PreparedRequest,
)
from connectors.core.contracts import (
    ConnectorConfigurationError,
    ConnectorRequest,
)


class AutotaskConnector(ConnectorBase):
    provider_name = "autotask"
    logical_secret = "autotask.readonly"

    capabilities = frozenset(
        {
            "autotask.entity.describe",
            "autotask.entity.get",
            "autotask.entity.query",
            "autotask.ticket.get",
            "autotask.ticket.search",
            "autotask.ticket.notes.list",
            "autotask.company.get",
            "autotask.company.search",
            "autotask.contact.get",
            "autotask.contact.search",
            "autotask.configuration.get",
            "autotask.configuration.search",
            "autotask.contract.search",
            "autotask.project.search",
        }
    )

    def prepare_request(
        self,
        request: ConnectorRequest,
        credentials: Mapping[str, str],
    ) -> PreparedRequest:
        zone_information = self._transport.request(
            method="GET",
            url=(
                "https://webservices.autotask.net/"
                "atservicesrest/v1.0/zoneInformation"
            ),
            headers={"Accept": "application/json"},
            params={"user": credentials["username"]},
            timeout_seconds=30.0,
        )

        discovered_url = zone_information.get("url")

        if (
            not isinstance(discovered_url, str)
            or not discovered_url.strip()
        ):
            raise ConnectorConfigurationError(
                "Autotask zone discovery returned an invalid API URL."
            )

        method, path, params = resolve_operation(
            request.context.capability,
            request.arguments,
        )

        return PreparedRequest(
            method=method,
            url=f"{discovered_url.rstrip('/')}{path}",
            headers={
                "ApiIntegrationCode": credentials["integration_code"],
                "UserName": credentials["username"],
                "Secret": credentials["secret"],
                "Accept": "application/json",
            },
            params=params,
            timeout_seconds=30.0,
            audit_operation=path,
        )
