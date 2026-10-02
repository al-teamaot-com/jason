from dataclasses import dataclass
from datetime import datetime, timezone

import pytest

from connectors.core.contracts import ConnectorContext, ConnectorRequest
from connectors.microsoft_exchange.connector import (
    MAILBOX_FORWARDING_READ,
    MESSAGE_TRACE_SEARCH,
    MicrosoftExchangeReadConnector,
)
from kernel.client_boundaries import BoundaryStatus, ClientBoundary


class Worker:
    def __init__(self):
        self.calls = []

    def execute(self, **kwargs):
        self.calls.append(kwargs)
        return {"items": [], "count": 0}


class Tokens:
    def access_token_for_tenant(self, *, microsoft_tenant_id):
        assert microsoft_tenant_id == "f7054323-d52b-4863-8c2f-1898f0b6077c"
        return "exo-token"


class Audit:
    def record(self, *args, **kwargs):
        pass


class Boundaries:
    def __init__(self, boundary):
        self.boundary = boundary
        self.calls = []

    def find_active_for_client(self, *, client_id: str, provider: str):
        self.calls.append((client_id, provider))
        return self.boundary


def boundary(profile="mail-investigation-read", scopes=("exchange_org:absolnet.onmicrosoft.com",)):
    return ClientBoundary(
        id="boundary-1",
        client_id="0",
        provider="microsoft_365_mail_investigation",
        external_tenant_id="f7054323-d52b-4863-8c2f-1898f0b6077c",
        primary_domain="teamaot.com",
        profile=profile,
        application_id="app-1",
        status=BoundaryStatus.VALIDATED,
        consent_transaction_id="tx-1",
        created_at=datetime.now(timezone.utc),
        external_scope_ids=scopes,
    )


def context(capability, client_id="0"):
    return ConnectorContext(
        correlation_id="corr-1",
        principal_id="tech-1",
        organization_id="aot",
        client_id=client_id,
        capability=capability,
        mode="observe",
    )


def test_connector_derives_tenant_and_exchange_domain_from_client_boundary():
    worker = Worker()
    connector = MicrosoftExchangeReadConnector(
        worker=worker,
        exchange_tokens=Tokens(),
        boundaries=Boundaries(boundary()),
        audit=Audit(),
    )
    connector.execute(
        ConnectorRequest(
            context=context(MAILBOX_FORWARDING_READ),
            arguments={"mailbox": "lori@teamaot.com"},
        )
    )
    call = worker.calls[0]
    assert call["microsoft_tenant_id"] == "f7054323-d52b-4863-8c2f-1898f0b6077c"
    assert call["organization"] == "absolnet.onmicrosoft.com"
    assert call["operation"] == "mailbox.forwarding.read"
    assert call["exchange_access_token"] == "exo-token"


def test_conversation_cannot_override_tenant_or_exchange_organization():
    connector = MicrosoftExchangeReadConnector(
        worker=Worker(),
        exchange_tokens=Tokens(),
        boundaries=Boundaries(boundary()),
        audit=Audit(),
    )
    with pytest.raises(Exception, match="derived from the governed client boundary"):
        connector.execute(
            ConnectorRequest(
                context=context(MESSAGE_TRACE_SEARCH),
                arguments={
                    "tenant_id": "00000000-0000-0000-0000-000000000000",
                    "organization": "evil.onmicrosoft.com",
                    "start": "2026-09-30T00:00:00Z",
                    "end": "2026-10-01T00:00:00Z",
                },
            )
        )


def test_connector_requires_mail_investigation_profile():
    connector = MicrosoftExchangeReadConnector(
        worker=Worker(),
        exchange_tokens=Tokens(),
        boundaries=Boundaries(boundary(profile="directory-read")),
        audit=Audit(),
    )
    with pytest.raises(Exception, match="not approved for mail investigation"):
        connector.execute(
            ConnectorRequest(
                context=context(MAILBOX_FORWARDING_READ),
                arguments={"mailbox": "lori@teamaot.com"},
            )
        )


def test_connector_requires_exchange_organization_binding():
    connector = MicrosoftExchangeReadConnector(
        worker=Worker(),
        exchange_tokens=Tokens(),
        boundaries=Boundaries(boundary(scopes=())),
        audit=Audit(),
    )
    with pytest.raises(Exception, match="does not contain an Exchange organization"):
        connector.execute(
            ConnectorRequest(
                context=context(MAILBOX_FORWARDING_READ),
                arguments={"mailbox": "lori@teamaot.com"},
            )
        )
