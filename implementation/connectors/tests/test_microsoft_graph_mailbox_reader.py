from dataclasses import dataclass

import pytest

from connectors.core.contracts import ConnectorContext, ConnectorRequest
from connectors.microsoft_graph.mailbox_connector import MicrosoftGraphMailboxConnector
from connectors.microsoft_graph.mailbox_reader import MicrosoftGraphMailboxReader


class Tokens:
    def access_token_for_tenant(self, *, microsoft_tenant_id: str) -> str:
        assert microsoft_tenant_id == "tenant-1"
        return "token"


class Transport:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def request(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class Audit:
    def record(self, *args, **kwargs):
        pass


@dataclass
class Binding:
    microsoft_tenant_id: str = "tenant-1"
    status: str = "active"


class Bindings:
    def find_active_by_jason_identity(self, *, jason_identity_id: str):
        assert jason_identity_id == "person-al"
        return Binding()


def context(capability: str) -> ConnectorContext:
    return ConnectorContext(
        correlation_id="corr-1",
        principal_id="person-al",
        organization_id="aot",
        client_id=None,
        capability=capability,
        mode="observe",
    )


def test_search_messages_is_bounded_and_projects_safe_metadata():
    transport = Transport({
        "value": [{
            "id": "msg-1",
            "subject": "PO 123 shipped",
            "from": {"emailAddress": {"address": "vendor@example.com"}},
            "receivedDateTime": "2026-09-20T12:00:00Z",
            "sentDateTime": "2026-09-20T11:59:00Z",
            "hasAttachments": True,
            "internetMessageId": "<x@example.com>",
            "conversationId": "conv-1",
        }]
    })
    reader = MicrosoftGraphMailboxReader(tokens=Tokens(), transport=transport)
    result = reader.search_messages(
        microsoft_tenant_id="tenant-1",
        mailbox="buyer@teamaot.com",
        maximum_records=10,
        sender="vendor@example.com",
        received_after="2026-09-19T00:00:00Z",
    )
    assert result["count"] == 1
    assert result["items"][0]["subject"] == "PO 123 shipped"
    call = transport.calls[0]
    assert call["method"] == "GET"
    assert "/users/buyer%40teamaot.com/messages" in call["url"]
    assert call["params"]["$top"] == 10
    assert "from/emailAddress/address eq" in call["params"]["$filter"]


def test_read_message_requires_exact_durable_message():
    transport = Transport({
        "id": "msg-1",
        "subject": "ETA update",
        "from": {"emailAddress": {"address": "vendor@example.com"}},
        "body": {"contentType": "text", "content": "ETA is Sep 30"},
        "bodyPreview": "ETA is Sep 30",
    })
    reader = MicrosoftGraphMailboxReader(tokens=Tokens(), transport=transport)
    result = reader.read_message(
        microsoft_tenant_id="tenant-1",
        mailbox="buyer@teamaot.com",
        message_id="msg-1",
    )
    assert result["item"]["id"] == "msg-1"
    assert result["item"]["body"] == "ETA is Sep 30"


def test_attachment_search_exposes_metadata_not_content():
    transport = Transport({
        "value": [{
            "id": "att-1",
            "name": "packing-slip.pdf",
            "contentType": "application/pdf",
            "size": 1200,
            "isInline": False,
        }]
    })
    reader = MicrosoftGraphMailboxReader(tokens=Tokens(), transport=transport)
    result = reader.attachment_metadata(
        microsoft_tenant_id="tenant-1",
        mailbox="buyer@teamaot.com",
        message_id="msg-1",
    )
    assert result["content_exposed"] is False
    assert result["items"][0]["name"] == "packing-slip.pdf"


def test_connector_fails_closed_for_unapproved_mailbox():
    reader = MicrosoftGraphMailboxReader(tokens=Tokens(), transport=Transport({"value": []}))
    connector = MicrosoftGraphMailboxConnector(
        reader=reader,
        bindings=Bindings(),
        approved_mailboxes=frozenset({"buyer@teamaot.com"}),
        audit=Audit(),
    )
    with pytest.raises(Exception, match="not approved"):
        connector.execute(ConnectorRequest(
            context=context("microsoft_graph.mail.message.search"),
            arguments={"mailbox": "other@teamaot.com"},
        ))


def test_connector_allows_exact_approved_mailbox():
    reader = MicrosoftGraphMailboxReader(tokens=Tokens(), transport=Transport({"value": []}))
    connector = MicrosoftGraphMailboxConnector(
        reader=reader,
        bindings=Bindings(),
        approved_mailboxes=frozenset({"buyer@teamaot.com"}),
        audit=Audit(),
    )
    result = connector.execute(ConnectorRequest(
        context=context("microsoft_graph.mail.message.search"),
        arguments={"mailbox": "buyer@teamaot.com", "page_size": 5},
    ))
    assert result.data["mailbox"] == "buyer@teamaot.com"
    assert result.data["count"] == 0
