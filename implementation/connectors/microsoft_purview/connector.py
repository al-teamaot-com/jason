from __future__ import annotations

from dataclasses import dataclass

from connectors.core.contracts import (
    AuditSink,
    ConnectorAuthorizationError,
    ConnectorContext,
    ConnectorRequest,
    ConnectorResult,
    require_capability,
)
from kernel.client_boundaries import BoundaryStatus, ClientBoundaryRepository

from connectors.microsoft_graph.service_catalog import (
    MICROSOFT_MAIL_INVESTIGATION_BOUNDARY_PROVIDER,
)
from .exchange_audit_reader import MicrosoftPurviewExchangeAuditReader


PURVIEW_MAILBOX_AUDIT_SEARCH = "microsoft_purview.mailbox.audit.search"


@dataclass(frozen=True, slots=True)
class MicrosoftPurviewMailInvestigationConnector:
    reader: MicrosoftPurviewExchangeAuditReader
    boundaries: ClientBoundaryRepository
    audit: AuditSink

    provider_name = "microsoft_purview"
    capabilities = frozenset({PURVIEW_MAILBOX_AUDIT_SEARCH})

    def _boundary(self, context: ConnectorContext):
        client_id = str(context.client_id or "").strip()
        if not client_id:
            raise ConnectorAuthorizationError(
                "A governed client is required for Microsoft mail audit investigation."
            )
        boundary = self.boundaries.find_active_for_client(
            client_id=client_id,
            provider=MICROSOFT_MAIL_INVESTIGATION_BOUNDARY_PROVIDER,
        )
        if boundary is None or boundary.status is not BoundaryStatus.VALIDATED:
            raise ConnectorAuthorizationError(
                "A validated Microsoft mail-investigation client boundary is required."
            )
        if boundary.profile != "mail-investigation-read":
            raise ConnectorAuthorizationError(
                "The Microsoft client boundary is not approved for mail investigation."
            )
        return boundary

    def execute(self, request: ConnectorRequest) -> ConnectorResult:
        require_capability(request, self.capabilities)
        if "tenant_id" in request.arguments:
            raise ConnectorAuthorizationError(
                "Microsoft tenant selection is derived from the governed client boundary."
            )
        boundary = self._boundary(request.context)
        mailbox = str(request.arguments.get("mailbox") or "").strip().casefold()
        if not mailbox or "@" not in mailbox:
            raise ValueError("an exact mailbox address is required")

        operations = request.arguments.get("operations")
        normalized_operations = (
            tuple(str(item) for item in operations)
            if isinstance(operations, (list, tuple))
            else (
                "Move",
                "MoveToDeletedItems",
                "SoftDelete",
                "HardDelete",
                "Update",
                "UpdateInboxRules",
                "MailItemsAccessed",
            )
        )

        self.audit.record(
            "connector.requested",
            request.context,
            {
                "provider": self.provider_name,
                "operation": request.context.capability,
                "mailbox": mailbox,
                "tenant_id": boundary.external_tenant_id,
            },
        )
        data = self.reader.search_mailbox_events(
            microsoft_tenant_id=boundary.external_tenant_id,
            mailbox=mailbox,
            start=str(request.arguments.get("start") or ""),
            end=str(request.arguments.get("end") or ""),
            subject=(
                str(request.arguments["subject"])
                if request.arguments.get("subject") is not None
                else None
            ),
            internet_message_id=(
                str(request.arguments["internet_message_id"])
                if request.arguments.get("internet_message_id") is not None
                else None
            ),
            operations=normalized_operations,
            maximum_records=int(request.arguments.get("maximum_records", 500)),
            correlation_id=request.context.correlation_id,
        )
        self.audit.record(
            "connector.completed",
            request.context,
            {
                "provider": self.provider_name,
                "operation": request.context.capability,
                "mailbox": mailbox,
                "query_status": data.get("query_status"),
                "count": data.get("count"),
            },
        )
        return ConnectorResult(
            capability=request.context.capability,
            provider=self.provider_name,
            data=data,
        )
