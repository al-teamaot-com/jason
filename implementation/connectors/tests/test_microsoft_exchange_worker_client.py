import pytest

from connectors.microsoft_exchange.worker_client import (
    EXCHANGE_READ_WORKER_URL,
    ExchangeReadWorkerClient,
    ExchangeWorkerProtocolError,
)


class Transport:
    def __init__(self, response=None):
        self.response = response or {"ok": True, "data": {"items": []}}
        self.calls = []

    def request(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def client(transport=None):
    return ExchangeReadWorkerClient(
        transport=transport or Transport(),
        worker_token="internal-token",
    )


def test_trace_search_posts_typed_operation_to_fixed_worker_url():
    transport = Transport()
    result = client(transport).execute(
        microsoft_tenant_id="f7054323-d52b-4863-8c2f-1898f0b6077c",
        organization="absolnet.onmicrosoft.com",
        operation="message_trace.search",
        exchange_access_token="exo-token",
        arguments={
            "sender": "admin@teamaot.com",
            "subject": "Toner Delivery Follow-Up",
            "start": "2026-09-30T00:00:00Z",
            "end": "2026-10-01T00:00:00Z",
        },
        correlation_id="corr-1",
    )
    assert result == {"items": []}
    call = transport.calls[0]
    assert call["url"] == EXCHANGE_READ_WORKER_URL
    assert call["method"] == "POST"
    assert call["json"]["operation"] == "message_trace.search"
    assert call["json"]["organization"] == "absolnet.onmicrosoft.com"
    assert call["json"]["exchange_access_token"] == "exo-token"
    assert call["headers"]["Authorization"] == "Bearer internal-token"


@pytest.mark.parametrize(
    "operation",
    [
        "powershell.execute",
        "Get-Mailbox",
        "mailbox.delete",
        "mailbox.rule.create",
        "message.move",
    ],
)
def test_arbitrary_or_mutating_operations_are_rejected(operation):
    with pytest.raises(ExchangeWorkerProtocolError, match="not allowlisted"):
        client().execute(
            microsoft_tenant_id="f7054323-d52b-4863-8c2f-1898f0b6077c",
            organization="absolnet.onmicrosoft.com",
            operation=operation,
            exchange_access_token="exo-token",
            arguments={},
            correlation_id="corr-1",
        )


def test_operation_rejects_extra_arguments_that_could_be_command_injection():
    with pytest.raises(ExchangeWorkerProtocolError, match="unsupported arguments"):
        client().execute(
            microsoft_tenant_id="f7054323-d52b-4863-8c2f-1898f0b6077c",
            organization="absolnet.onmicrosoft.com",
            operation="mailbox.forwarding.read",
            exchange_access_token="exo-token",
            arguments={"mailbox": "lori@teamaot.com", "script": "Remove-Mailbox *"},
            correlation_id="corr-1",
        )


@pytest.mark.parametrize(
    "organization",
    ["teamaot.com", "x@absolnet.onmicrosoft.com", "../absolnet.onmicrosoft.com"],
)
def test_organization_must_be_validated_onmicrosoft_domain_shape(organization):
    with pytest.raises(ExchangeWorkerProtocolError):
        client().execute(
            microsoft_tenant_id="f7054323-d52b-4863-8c2f-1898f0b6077c",
            organization=organization,
            operation="mailbox.transport_rules.read",
            exchange_access_token="exo-token",
            arguments={},
            correlation_id="corr-1",
        )
