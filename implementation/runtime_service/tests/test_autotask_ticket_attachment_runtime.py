from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

import pytest

from connectors.core.contracts import ConnectorContext, ConnectorRequest
from kernel.capabilities import CapabilityLifecycle, CapabilityRegistryService, InMemoryCapabilityRegistry
from kernel.execution_providers import ExecutionProviderRegistryService, InMemoryExecutionProviderRegistry
from jason_runtime.autotask_ticket_attachment import (
    AUTOTASK_TICKET_ATTACHMENT_PROFILE,
    AUTOTASK_TICKET_ATTACHMENT_PROFILE_ENV,
    AUTOTASK_TICKET_ATTACHMENT_PROVIDER,
    AutotaskTicketAttachmentConnector,
    register_autotask_ticket_attachment_runtime_foundation,
)
from orchestrator.provider_mutation_capability_catalog import SERVICE_TICKET_ATTACHMENT_CREATE


class Secrets:
    def resolve(self, logical_name, context):
        del context
        assert logical_name == "autotask.write"
        return {
            "username": "write@example.invalid",
            "secret": "synthetic",
            "integration_code": "synthetic-code",
        }


class Audit:
    def __init__(self): self.events=[]
    def record(self, event_type, context, details):
        del context
        self.events.append((event_type, dict(details)))


@dataclass(frozen=True)
class Binding:
    jason_identity_id: str = "person-al"
    email_address: str = "al@example.com"


class Bindings:
    def find_active_by_jason_identity(self, *, jason_identity_id):
        return Binding() if jason_identity_id == "person-al" else None


class Transport:
    def __init__(self, *, ticket_company=333):
        self.ticket_company=ticket_company
        self.requests=[]
        self.encoded=base64.b64encode(b"bounded attachment evidence").decode()
    def request(self, *, method, url, headers, params=None, json=None, timeout_seconds=30.0):
        self.requests.append({"method":method,"url":url,"headers":dict(headers),"params":params,"json":json})
        if url.endswith("/v1.0/zoneInformation"):
            return {"url":"https://webservices3.autotask.net/atservicesrest/"}
        if url.endswith("/V1.0/Resources/query"):
            return {"items":[{"id":77,"email":"al@example.com","isActive":True}]}
        if url.endswith("/V1.0/TicketAttachments/entityInformation"):
            return {"userAccessForCreate":1}
        if url.endswith("/V1.0/TicketAttachments/entityInformation/fields"):
            return {"fields":[{"name":"publish","picklistValues":[
                {"label":"All Autotask Users","value":1},
                {"label":"Internal Users Only","value":2},
                {"label":"Internal & Co-Managed","value":4},
            ]}]}
        if url.endswith("/V1.0/Tickets/query"):
            return {"item":{"id":140000,"companyID":self.ticket_company}}
        if method == "POST" and url.endswith("/V1.0/Tickets/140000/Attachments"):
            return {"itemId":555}
        if method == "GET" and url.endswith("/V1.0/Tickets/140000/Attachments/555"):
            return {"items":[{
                "id":555,"ticketID":140000,"publish":2,
                "fullPath":"evidence.txt","title":"Evidence",
                "data":self.encoded,
            }]}
        raise AssertionError(f"unexpected request {method} {url}")


def request(encoded: str) -> ConnectorRequest:
    return ConnectorRequest(
        context=ConnectorContext(
            correlation_id="corr-attachment",
            principal_id="person-al",
            organization_id="aot",
            client_id=None,
            capability="autotask.ticket.attachment.create",
            mode="execute",
        ),
        arguments={
            "company_id":333,"ticket_id":140000,"file_name":"evidence.txt",
            "title":"Evidence","visibility":"internal","data_base64":encoded,
        },
    )


@pytest.fixture(autouse=True)
def enabled(monkeypatch):
    monkeypatch.setenv("JASON_AUTOTASK_MUTATION_ENABLED","true")


def connector(transport):
    return AutotaskTicketAttachmentConnector(
        secrets=Secrets(), transport=transport, audit=Audit(), bindings=Bindings()
    )


def test_attachment_profile_dormant_until_explicit_activation(monkeypatch):
    monkeypatch.delenv(AUTOTASK_TICKET_ATTACHMENT_PROFILE_ENV, raising=False)
    capabilities=CapabilityRegistryService(registry=InMemoryCapabilityRegistry())
    providers=ExecutionProviderRegistryService(registry=InMemoryExecutionProviderRegistry())
    state=register_autotask_ticket_attachment_runtime_foundation(
        capabilities=capabilities,providers=providers,now=datetime.now(timezone.utc)
    )
    assert state.enabled is False
    assert capabilities.get(capability_name=SERVICE_TICKET_ATTACHMENT_CREATE,version="1.0").lifecycle_status is CapabilityLifecycle.BUILDING


def test_attachment_profile_activates_exact_single_capability(monkeypatch):
    monkeypatch.setenv(AUTOTASK_TICKET_ATTACHMENT_PROFILE_ENV,AUTOTASK_TICKET_ATTACHMENT_PROFILE)
    capabilities=CapabilityRegistryService(registry=InMemoryCapabilityRegistry())
    providers=ExecutionProviderRegistryService(registry=InMemoryExecutionProviderRegistry())
    state=register_autotask_ticket_attachment_runtime_foundation(
        capabilities=capabilities,providers=providers,now=datetime.now(timezone.utc)
    )
    assert state.enabled is True
    assert state.capability_names == (SERVICE_TICKET_ATTACHMENT_CREATE,)
    assert providers.get(AUTOTASK_TICKET_ATTACHMENT_PROVIDER).capabilities == frozenset({SERVICE_TICKET_ATTACHMENT_CREATE})


def test_execution_plan_contains_digest_manifest_not_base64():
    transport=Transport(); encoded=transport.encoded
    prepared=connector(transport).prepare_governed_execution(request(encoded))
    assert prepared.payload["sha256"]
    assert prepared.payload["size_bytes"] == len(b"bounded attachment evidence")
    assert "data" not in prepared.payload and "data_base64" not in prepared.payload
    assert encoded not in repr(prepared.payload)
    assert all(call["method"] != "POST" for call in transport.requests)


def test_ticket_company_mismatch_fails_before_provider_post():
    transport=Transport(ticket_company=311)
    with pytest.raises(PermissionError, match="TICKET_COMPANY_MISMATCH"):
        connector(transport).prepare_governed_execution(request(transport.encoded))
    assert all(call["method"] != "POST" for call in transport.requests)


def test_successful_attachment_post_and_exact_readback_are_verified_and_sanitized():
    transport=Transport(); c=connector(transport)
    prepared=c.prepare_governed_execution(request(transport.encoded))
    result=c.execute_governed_execution(prepared)
    assert result.data["itemId"] == 555
    assert result.data["jasonVerification"]["readbackVerified"] is True
    assert result.data["jasonVerification"]["companyId"] == 333
    assert "data" not in result.data and "data_base64" not in result.data
    posts=[call for call in transport.requests if call["method"] == "POST"]
    assert len(posts) == 1
    assert posts[0]["json"]["data"] == transport.encoded
    assert posts[0]["headers"]["ImpersonationResourceId"] == "77"


def test_internal_visibility_resolution_ignores_internal_and_comanaged():
    transport=Transport(); c=connector(transport)
    prepared=c.prepare_governed_execution(request(transport.encoded))
    assert prepared.payload["publish"] == 2
    assert prepared.symbolic_resolutions == {"visibility":"2"}
