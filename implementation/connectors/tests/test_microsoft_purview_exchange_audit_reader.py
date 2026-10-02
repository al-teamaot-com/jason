from connectors.microsoft_purview.exchange_audit_reader import (
    MicrosoftPurviewExchangeAuditReader,
)


class Tokens:
    def access_token_for_tenant(self, *, microsoft_tenant_id):
        assert microsoft_tenant_id == "f7054323-d52b-4863-8c2f-1898f0b6077c"
        return "token"


class Transport:
    def __init__(self):
        self.calls = []

    def request(self, **kwargs):
        self.calls.append(kwargs)
        url = kwargs["url"]
        if kwargs["method"] == "POST":
            return {"id": "q-1", "status": "notStarted"}
        if url.endswith("/queries/q-1"):
            return {"id": "q-1", "status": "succeeded"}
        return {
            "value": [
                {
                    "id": "event-1",
                    "createdDateTime": "2026-10-01T14:00:00Z",
                    "operation": "MoveToDeletedItems",
                    "userPrincipalName": "delegate@teamaot.com",
                    "clientIp": "192.0.2.10",
                    "service": "Exchange",
                    "auditData": {
                        "MailboxOwnerUPN": "lori@teamaot.com",
                        "ClientInfoString": "Client=OneOutlook",
                        "AffectedItems": [
                            {
                                "InternetMessageId": "<message@example>",
                                "Subject": "Toner Delivery Follow-Up",
                                "ParentFolder": {"Path": "\\Inbox"},
                            }
                        ],
                    },
                }
            ]
        }


def test_purview_reader_correlates_target_mailbox_and_message():
    transport = Transport()
    reader = MicrosoftPurviewExchangeAuditReader(
        tokens=Tokens(),
        transport=transport,
        sleeper=lambda _: None,
    )
    result = reader.search_mailbox_events(
        microsoft_tenant_id="f7054323-d52b-4863-8c2f-1898f0b6077c",
        mailbox="lori@teamaot.com",
        start="2026-09-30T00:00:00Z",
        end="2026-10-02T00:00:00Z",
        subject="Toner Delivery Follow-Up",
        internet_message_id="<message@example>",
        correlation_id="corr-1",
    )
    assert result["complete"] is True
    assert result["count"] == 1
    event = result["items"][0]
    assert event["operation"] == "MoveToDeletedItems"
    assert event["actor"] == "delegate@teamaot.com"
    assert event["mailbox_owner"] == "lori@teamaot.com"


def test_purview_reader_uses_exchange_service_filter_and_bounded_operations():
    transport = Transport()
    reader = MicrosoftPurviewExchangeAuditReader(
        tokens=Tokens(),
        transport=transport,
        sleeper=lambda _: None,
    )
    reader.search_mailbox_events(
        microsoft_tenant_id="f7054323-d52b-4863-8c2f-1898f0b6077c",
        mailbox="lori@teamaot.com",
        start="2026-09-30T00:00:00Z",
        end="2026-10-02T00:00:00Z",
        correlation_id="corr-1",
    )
    create = transport.calls[0]["json"]
    assert create["serviceFilter"] == "Exchange"
    assert "HardDelete" in create["operationFilters"]
    assert "MoveToDeletedItems" in create["operationFilters"]
