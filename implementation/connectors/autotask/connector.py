from __future__ import annotations

from typing import Any, Mapping

from connectors.core.contracts import (
    AuditSink,
    ConnectorRequest,
    ConnectorResult,
    HttpTransport,
    SecretResolver,
    require_capability,
)


class AutotaskConnector:
    provider_name = "autotask"
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

    def __init__(self, secrets: SecretResolver, transport: HttpTransport, audit: AuditSink) -> None:
        self._secrets = secrets
        self._transport = transport
        self._audit = audit

    def execute(self, request: ConnectorRequest) -> ConnectorResult:
        require_capability(request, self.capabilities)
        credentials = self._secrets.resolve("autotask.readonly", request.context)
        base_url = credentials["zone_url"].rstrip("/")
        headers = {
            "ApiIntegrationCode": credentials["integration_code"],
            "UserName": credentials["username"],
            "Secret": credentials["secret"],
            "Accept": "application/json",
        }
        method, path, params = self._resolve_operation(request.context.capability, request.arguments)
        self._audit.record("connector.requested", request.context, {"provider": self.provider_name, "operation": path})
        payload = self._transport.request(
            method=method,
            url=f"{base_url}{path}",
            headers=headers,
            params=params,
            timeout_seconds=30.0,
        )
        self._audit.record("connector.completed", request.context, {"provider": self.provider_name})
        return ConnectorResult(request.context.capability, self.provider_name, payload)

    @staticmethod
    def _resolve_operation(capability: str, arguments: Mapping[str, Any]) -> tuple[str, str, Mapping[str, Any] | None]:
        if capability == "autotask.ticket.get":
            return "GET", f"/V1.0/Tickets/{int(arguments['ticket_id'])}", None
        if capability == "autotask.ticket.notes.list":
            return "GET", f"/V1.0/Tickets/{int(arguments['ticket_id'])}/Notes", None
        if capability == "autotask.company.get":
            return "GET", f"/V1.0/Companies/{int(arguments['company_id'])}", None
        if capability == "autotask.contact.get":
            return "GET", f"/V1.0/Contacts/{int(arguments['contact_id'])}", None
        if capability == "autotask.configuration_item.get":
            return "GET", f"/V1.0/ConfigurationItems/{int(arguments['configuration_item_id'])}", None
        if capability == "autotask.ticket.search":
            query = arguments.get("search")
            if not isinstance(query, str) or not query.strip():
                raise ValueError("A non-empty structured Autotask search expression is required.")
            return "GET", "/V1.0/Tickets/query", {"search": query}
        raise ValueError(f"Unsupported capability: {capability}")
