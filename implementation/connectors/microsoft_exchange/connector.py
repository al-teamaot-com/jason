from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from connectors.core.contracts import (
    AuditSink,
    ConnectorAuthorizationError,
    ConnectorContext,
    ConnectorRequest,
    ConnectorResult,
    require_capability,
)
from kernel.client_boundaries import BoundaryStatus, ClientBoundaryRepository
from connectors.microsoft_graph.service_catalog import MICROSOFT_MAIL_INVESTIGATION_BOUNDARY_PROVIDER

from .worker_client import ExchangeReadWorkerClient


MESSAGE_TRACE_SEARCH = "microsoft_exchange.message_trace.search"
MESSAGE_TRACE_DETAIL = "microsoft_exchange.message_trace.detail"
MAILBOX_FORWARDING_READ = "microsoft_exchange.mailbox.forwarding.read"
MAILBOX_INBOX_RULES_READ = "microsoft_exchange.mailbox.inbox_rules.read_hidden"
MAILBOX_FULL_ACCESS_READ = "microsoft_exchange.mailbox.full_access.read"
MAILBOX_SEND_AS_READ = "microsoft_exchange.mailbox.send_as.read"
MAILBOX_SEND_ON_BEHALF_READ = "microsoft_exchange.mailbox.send_on_behalf.read"
MAILBOX_TRANSPORT_RULES_READ = "microsoft_exchange.mailbox.transport_rules.read"
MAILBOX_MOBILE_DEVICES_READ = "microsoft_exchange.mailbox.mobile_devices.read"
MAILBOX_RETENTION_AUDIT_READ = "microsoft_exchange.mailbox.retention_audit_config.read"

_PROVIDER_TO_WORKER = {
    MESSAGE_TRACE_SEARCH: "message_trace.search",
    MESSAGE_TRACE_DETAIL: "message_trace.detail",
    MAILBOX_FORWARDING_READ: "mailbox.forwarding.read",
    MAILBOX_INBOX_RULES_READ: "mailbox.inbox_rules.read_hidden",
    MAILBOX_FULL_ACCESS_READ: "mailbox.full_access.read",
    MAILBOX_SEND_AS_READ: "mailbox.send_as.read",
    MAILBOX_SEND_ON_BEHALF_READ: "mailbox.send_on_behalf.read",
    MAILBOX_TRANSPORT_RULES_READ: "mailbox.transport_rules.read",
    MAILBOX_MOBILE_DEVICES_READ: "mailbox.mobile_devices.read",
    MAILBOX_RETENTION_AUDIT_READ: "mailbox.retention_audit_config.read",
}


@dataclass(frozen=True, slots=True)
class MicrosoftExchangeReadConnector:
    worker: ExchangeReadWorkerClient
    boundaries: ClientBoundaryRepository
    audit: AuditSink

    provider_name = "microsoft_exchange_online"
    capabilities = frozenset(_PROVIDER_TO_WORKER)

    def _boundary(self, context: ConnectorContext):
        client_id = str(context.client_id or "").strip()
        if not client_id:
            raise ConnectorAuthorizationError(
                "A governed client is required for Microsoft Exchange investigation."
            )
        boundary = self.boundaries.find_active_for_client(
            client_id=client_id,
            provider=MICROSOFT_MAIL_INVESTIGATION_BOUNDARY_PROVIDER,
        )
        if boundary is None or boundary.status is not BoundaryStatus.VALIDATED:
            raise ConnectorAuthorizationError(
                "A validated Microsoft client boundary is required."
            )
        if boundary.profile != "mail-investigation-read":
            raise ConnectorAuthorizationError(
                "The Microsoft client boundary is not approved for mail investigation."
            )
        if not boundary.external_tenant_id.strip():
            raise ConnectorAuthorizationError(
                "The Microsoft client boundary does not identify a tenant."
            )
        return boundary

    @staticmethod
    def _exchange_organization(boundary) -> str:
        for scope in boundary.external_scope_ids:
            value = str(scope).strip().casefold()
            if value.startswith("exchange_org:"):
                organization = value.split(":", 1)[1].strip()
                if organization.endswith(".onmicrosoft.com"):
                    return organization
        primary = str(boundary.primary_domain or "").strip().casefold()
        if primary.endswith(".onmicrosoft.com"):
            return primary
        raise ConnectorAuthorizationError(
            "The validated Microsoft boundary does not contain an Exchange organization domain."
        )

    def execute(self, request: ConnectorRequest) -> ConnectorResult:
        require_capability(request, self.capabilities)
        boundary = self._boundary(request.context)
        organization = self._exchange_organization(boundary)
        capability = request.context.capability
        operation = _PROVIDER_TO_WORKER[capability]

        arguments: Mapping[str, object] = dict(request.arguments)
        if "tenant_id" in arguments or "organization" in arguments:
            raise ConnectorAuthorizationError(
                "Tenant and Exchange organization are derived from the governed client boundary."
            )

        self.audit.record(
            "connector.requested",
            request.context,
            {
                "provider": self.provider_name,
                "operation": capability,
                "tenant_id": boundary.external_tenant_id,
                "exchange_organization": organization,
            },
        )
        data = self.worker.execute(
            microsoft_tenant_id=boundary.external_tenant_id,
            organization=organization,
            operation=operation,
            arguments=arguments,
            correlation_id=request.context.correlation_id,
        )
        self.audit.record(
            "connector.completed",
            request.context,
            {
                "provider": self.provider_name,
                "operation": capability,
            },
        )
        return ConnectorResult(
            capability=capability,
            provider=self.provider_name,
            data=data,
        )
