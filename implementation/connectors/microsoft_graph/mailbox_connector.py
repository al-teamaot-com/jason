from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet

from connectors.core.contracts import (
    AuditSink,
    ConnectorAuthorizationError,
    ConnectorContext,
    ConnectorRequest,
    ConnectorResult,
    require_capability,
)

from .mailbox_reader import MicrosoftGraphMailboxReader


@dataclass(frozen=True, slots=True)
class MicrosoftGraphMailboxConnector:
    metadata_reader: MicrosoftGraphMailboxReader
    content_reader: MicrosoftGraphMailboxReader
    bindings: object
    approved_mailboxes: FrozenSet[str]
    audit: AuditSink

    provider_name = "microsoft_graph"
    capabilities = frozenset(
        {
            "microsoft_graph.mail.message.search",
            "microsoft_graph.mail.message.read",
            "microsoft_graph.mail.attachment.search",
        }
    )

    def _tenant(self, context: ConnectorContext) -> str:
        binding = self.bindings.find_active_by_jason_identity(
            jason_identity_id=context.principal_id
        )
        if (
            binding is None
            or str(getattr(binding, "status", "") or "").strip() != "active"
        ):
            raise ConnectorAuthorizationError(
                "A unique active Microsoft identity binding is required."
            )
        tenant = str(
            getattr(binding, "microsoft_tenant_id", "") or ""
        ).strip()
        if not tenant:
            raise ConnectorAuthorizationError(
                "The Microsoft identity binding does not identify a tenant."
            )
        return tenant

    def _mailbox(self, request: ConnectorRequest, *, require_full_read: bool) -> str:
        mailbox = str(request.arguments.get("mailbox") or "").strip().casefold()
        if not mailbox or "@" not in mailbox:
            raise ValueError("an exact mailbox address is required")
        if require_full_read:
            approved = {value.strip().casefold() for value in self.approved_mailboxes}
            if mailbox not in approved:
                raise ConnectorAuthorizationError(
                    "The requested mailbox is not approved for governed full-content mail read."
                )
        return mailbox

    def execute(self, request: ConnectorRequest) -> ConnectorResult:
        require_capability(request, self.capabilities)
        tenant = self._tenant(request.context)
        capability = request.context.capability
        mailbox = self._mailbox(
            request,
            require_full_read=(capability != "microsoft_graph.mail.message.search"),
        )

        self.audit.record(
            "connector.requested",
            request.context,
            {
                "provider": self.provider_name,
                "operation": request.context.capability,
                "mailbox": mailbox,
            },
        )

        if capability == "microsoft_graph.mail.message.search":
            data = self.metadata_reader.search_messages(
                microsoft_tenant_id=tenant,
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
        elif capability == "microsoft_graph.mail.message.read":
            data = self.content_reader.read_message(
                microsoft_tenant_id=tenant,
                mailbox=mailbox,
                message_id=str(request.arguments.get("message_id") or ""),
            )
        else:
            data = self.content_reader.attachment_metadata(
                microsoft_tenant_id=tenant,
                mailbox=mailbox,
                message_id=str(request.arguments.get("message_id") or ""),
                maximum_records=int(request.arguments.get("page_size", 25)),
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
