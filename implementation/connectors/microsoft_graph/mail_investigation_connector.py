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

from .mailbox_reader import MicrosoftGraphMailboxReader
from .service_catalog import MICROSOFT_MAIL_INVESTIGATION_BOUNDARY_PROVIDER


MAIL_INVESTIGATION_MESSAGE_SEARCH = "microsoft_graph.mail_investigation.message.search"
MAIL_INVESTIGATION_MESSAGE_READ = "microsoft_graph.mail_investigation.message.read"
MAIL_INVESTIGATION_FOLDER_SEARCH = "microsoft_graph.mail_investigation.folder.search"
MAIL_INVESTIGATION_FOLDER_READ = "microsoft_graph.mail_investigation.folder.read"


@dataclass(frozen=True, slots=True)
class MicrosoftGraphMailInvestigationConnector:
    reader: MicrosoftGraphMailboxReader
    boundaries: ClientBoundaryRepository
    audit: AuditSink

    provider_name = "microsoft_graph"
    capabilities = frozenset(
        {
            MAIL_INVESTIGATION_MESSAGE_SEARCH,
            MAIL_INVESTIGATION_MESSAGE_READ,
            MAIL_INVESTIGATION_FOLDER_SEARCH,
            MAIL_INVESTIGATION_FOLDER_READ,
        }
    )

    def _boundary(self, context: ConnectorContext):
        client_id = str(context.client_id or "").strip()
        if not client_id:
            raise ConnectorAuthorizationError(
                "A governed client is required for Microsoft mail investigation."
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

    @staticmethod
    def _mailbox(request: ConnectorRequest) -> str:
        mailbox = str(request.arguments.get("mailbox") or "").strip().casefold()
        if not mailbox or "@" not in mailbox:
            raise ValueError("an exact mailbox address is required")
        if "tenant_id" in request.arguments or "organization" in request.arguments:
            raise ConnectorAuthorizationError(
                "Microsoft tenant selection is derived from the governed client boundary."
            )
        return mailbox

    def execute(self, request: ConnectorRequest) -> ConnectorResult:
        require_capability(request, self.capabilities)
        boundary = self._boundary(request.context)
        mailbox = self._mailbox(request)
        capability = request.context.capability

        self.audit.record(
            "connector.requested",
            request.context,
            {
                "provider": self.provider_name,
                "operation": capability,
                "mailbox": mailbox,
                "tenant_id": boundary.external_tenant_id,
            },
        )

        if capability == MAIL_INVESTIGATION_MESSAGE_SEARCH:
            data = self.reader.search_messages(
                microsoft_tenant_id=boundary.external_tenant_id,
                mailbox=mailbox,
                maximum_records=int(request.arguments.get("page_size", 25)),
                sender=(
                    str(request.arguments["sender"])
                    if request.arguments.get("sender") is not None
                    else None
                ),
                received_after=(
                    str(request.arguments["received_after"])
                    if request.arguments.get("received_after") is not None
                    else None
                ),
                received_before=(
                    str(request.arguments["received_before"])
                    if request.arguments.get("received_before") is not None
                    else None
                ),
            )
        elif capability == MAIL_INVESTIGATION_MESSAGE_READ:
            data = self.reader.read_message(
                microsoft_tenant_id=boundary.external_tenant_id,
                mailbox=mailbox,
                message_id=str(request.arguments.get("message_id") or ""),
            )
        elif capability == MAIL_INVESTIGATION_FOLDER_SEARCH:
            data = self.reader.search_folder_messages(
                microsoft_tenant_id=boundary.external_tenant_id,
                mailbox=mailbox,
                folder=str(request.arguments.get("folder") or ""),
                maximum_records=int(request.arguments.get("page_size", 50)),
                sender=(
                    str(request.arguments["sender"])
                    if request.arguments.get("sender") is not None
                    else None
                ),
                received_after=(
                    str(request.arguments["received_after"])
                    if request.arguments.get("received_after") is not None
                    else None
                ),
                received_before=(
                    str(request.arguments["received_before"])
                    if request.arguments.get("received_before") is not None
                    else None
                ),
            )
        else:
            data = self.reader.read_folder(
                microsoft_tenant_id=boundary.external_tenant_id,
                mailbox=mailbox,
                folder_id=str(request.arguments.get("folder_id") or ""),
            )

        self.audit.record(
            "connector.completed",
            request.context,
            {
                "provider": self.provider_name,
                "operation": capability,
                "mailbox": mailbox,
            },
        )
        return ConnectorResult(
            capability=capability,
            provider=self.provider_name,
            data=data,
        )
