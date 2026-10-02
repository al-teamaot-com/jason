from dataclasses import dataclass
from datetime import datetime, timezone

import pytest

from connectors.core.contracts import ConnectorContext, ConnectorRequest
from connectors.microsoft_graph.mail_investigation_connector import (
    MAIL_INVESTIGATION_FOLDER_SEARCH,
    MAIL_INVESTIGATION_MESSAGE_SEARCH,
    MicrosoftGraphMailInvestigationConnector,
)
from kernel.client_boundaries import BoundaryStatus, ClientBoundary


class Reader:
    def __init__(self):
        self.calls = []

    def search_messages(self, **kwargs):
        self.calls.append(("messages", kwargs))
        return {"items": [], "count": 0, "mailbox": kwargs["mailbox"]}

    def search_folder_messages(self, **kwargs):
        self.calls.append(("folder", kwargs))
        return {
            "items": [],
            "count": 0,
            "mailbox": kwargs["mailbox"],
            "folder": kwargs["folder"],
        }

    def read_message(self, **kwargs):
        self.calls.append(("read_message", kwargs))
        return {"item": {"id": kwargs["message_id"]}}

    def read_folder(self, **kwargs):
        self.calls.append(("read_folder", kwargs))
        return {"folder": {"id": kwargs["folder_id"]}}


class Audit:
    def record(self, *args, **kwargs):
        pass


class Boundaries:
    def __init__(self, item):
        self.item = item

    def find_active_for_client(self, *, client_id, provider):
        assert provider == "microsoft_365_mail_investigation"
        assert client_id == "client-7"
        return self.item


def boundary(profile="mail-investigation-read"):
    return ClientBoundary(
        id="boundary-7",
        client_id="client-7",
        provider="microsoft_365_mail_investigation",
        external_tenant_id="f7054323-d52b-4863-8c2f-1898f0b6077c",
        primary_domain="client.example",
        profile=profile,
        application_id="14d82eec-204b-4c2f-b7e8-296a70dab67e",
        status=BoundaryStatus.VALIDATED,
        consent_transaction_id="tx-7",
        created_at=datetime.now(timezone.utc),
    )


def context(capability):
    return ConnectorContext(
        correlation_id="corr-7",
        principal_id="tech-7",
        organization_id="aot",
        client_id="client-7",
        capability=capability,
        mode="observe",
    )


def test_client_mail_search_uses_boundary_tenant_not_user_input():
    reader = Reader()
    connector = MicrosoftGraphMailInvestigationConnector(
        reader=reader,
        boundaries=Boundaries(boundary()),
        audit=Audit(),
    )
    connector.execute(
        ConnectorRequest(
            context=context(MAIL_INVESTIGATION_MESSAGE_SEARCH),
            arguments={"mailbox": "user@client.example", "page_size": 10},
        )
    )
    _, call = reader.calls[0]
    assert call["microsoft_tenant_id"] == "f7054323-d52b-4863-8c2f-1898f0b6077c"
    assert call["mailbox"] == "user@client.example"


def test_folder_search_is_typed_and_bounded_to_reader_contract():
    reader = Reader()
    connector = MicrosoftGraphMailInvestigationConnector(
        reader=reader,
        boundaries=Boundaries(boundary()),
        audit=Audit(),
    )
    result = connector.execute(
        ConnectorRequest(
            context=context(MAIL_INVESTIGATION_FOLDER_SEARCH),
            arguments={
                "mailbox": "user@client.example",
                "folder": "deleteditems",
                "page_size": 20,
            },
        )
    )
    assert result.data["folder"] == "deleteditems"
    assert reader.calls[0][1]["folder"] == "deleteditems"


def test_client_mail_connector_rejects_tenant_override():
    connector = MicrosoftGraphMailInvestigationConnector(
        reader=Reader(),
        boundaries=Boundaries(boundary()),
        audit=Audit(),
    )
    with pytest.raises(Exception, match="derived from the governed client boundary"):
        connector.execute(
            ConnectorRequest(
                context=context(MAIL_INVESTIGATION_MESSAGE_SEARCH),
                arguments={
                    "mailbox": "user@client.example",
                    "tenant_id": "00000000-0000-0000-0000-000000000000",
                },
            )
        )


def test_client_mail_connector_requires_investigation_profile():
    connector = MicrosoftGraphMailInvestigationConnector(
        reader=Reader(),
        boundaries=Boundaries(boundary(profile="directory-read")),
        audit=Audit(),
    )
    with pytest.raises(Exception, match="not approved for mail investigation"):
        connector.execute(
            ConnectorRequest(
                context=context(MAIL_INVESTIGATION_MESSAGE_SEARCH),
                arguments={"mailbox": "user@client.example"},
            )
        )
