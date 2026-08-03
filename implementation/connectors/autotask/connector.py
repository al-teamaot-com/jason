from __future__ import annotations

from typing import Any, Mapping

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
            "autotask.ticket.get",
            "autotask.ticket.search",
            "autotask.ticket.notes.list",
            "autotask.company.get",
            "autotask.contact.get",
            "autotask.configuration_item.get",
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

        method, path, params = self._resolve_operation(
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

    @staticmethod
    def _resolve_operation(
        capability: str,
        arguments: Mapping[str, Any],
    ) -> tuple[str, str, Mapping[str, Any] | None]:
        if capability == "autotask.ticket.get":
            return (
                "GET",
                f"/V1.0/Tickets/{int(arguments['ticket_id'])}",
                None,
            )

        if capability == "autotask.ticket.notes.list":
            return (
                "GET",
                f"/V1.0/Tickets/{int(arguments['ticket_id'])}/Notes",
                None,
            )

        if capability == "autotask.company.get":
            return (
                "GET",
                f"/V1.0/Companies/{int(arguments['company_id'])}",
                None,
            )

        if capability == "autotask.contact.get":
            return (
                "GET",
                f"/V1.0/Contacts/{int(arguments['contact_id'])}",
                None,
            )

        if capability == "autotask.configuration_item.get":
            return (
                "GET",
                "/V1.0/ConfigurationItems/"
                f"{int(arguments['configuration_item_id'])}",
                None,
            )

        if capability == "autotask.ticket.search":
            query = arguments.get("search")

            if not isinstance(query, str) or not query.strip():
                raise ValueError(
                    "A non-empty structured Autotask "
                    "search expression is required."
                )

            return (
                "GET",
                "/V1.0/Tickets/query",
                {"search": query},
            )

        raise ValueError(
            f"Unsupported capability: {capability}"
        )
