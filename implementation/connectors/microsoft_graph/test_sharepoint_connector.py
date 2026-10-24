from dataclasses import dataclass, field
import pytest

from connectors.core.contracts import (
    ConnectorAuthorizationError, ConnectorContext, ConnectorRequest,
)
from connectors.microsoft_graph.sharepoint_connector import GovernedSharePointConnector
from connectors.microsoft_graph.sharepoint_reader import MicrosoftGraphSharePointReader

TENANT = "f7054323-d52b-4863-8c2f-1898f0b6077c"

@dataclass
class Binding:
    status: str = "active"
    client_id: str = "client-aot"
    microsoft_tenant_id: str = TENANT

@dataclass
class Bindings:
    bound: object = field(default_factory=Binding)
    def find_active_by_jason_identity(self, *, jason_identity_id):
        assert jason_identity_id == "owner-1"
        return self.bound

@dataclass
class Authorizer:
    allow: bool = True
    calls: list = field(default_factory=list)
    def authorized(self, **kwargs):
        self.calls.append(kwargs)
        return self.allow

@dataclass
class Audit:
    calls: list = field(default_factory=list)
    def record(self, *args):
        self.calls.append(args)

class Tokens:
    def access_token_for_tenant(self, *, microsoft_tenant_id):
        assert microsoft_tenant_id == TENANT
        return "synthetic"

@dataclass
class Transport:
    calls: list = field(default_factory=list)
    def request(self, **kwargs):
        self.calls.append(kwargs)
        return {"value": [{"id":"drive-id"}]}
    def request_bytes(self, **kwargs):
        self.calls.append(kwargs)
        return b""

def make_connector(allow=True, binding=None):
    t = Transport()
    a = Authorizer(allow)
    audit = Audit()
    conn = GovernedSharePointConnector(
        reader=MicrosoftGraphSharePointReader(Tokens(), t),
        bindings=Bindings(binding if binding is not None else Binding()),
        authorizer=a, audit=audit)
    return conn, t, a, audit

def context(capability="knowledge.library.search", client_id="client-aot"):
    return ConnectorContext(
        correlation_id="test-id", principal_id="owner-1",
        organization_id="aot", client_id=client_id, capability=capability)

def test_authorized_library_read_uses_tenant_binding():
    c,t,a,audit = make_connector()
    result = c.execute(ConnectorRequest(context=context(),arguments={"site_id":"site-id"}))
    assert result.data["count"] == 1
    assert a.calls[0]["tenant_id"] == TENANT
    assert a.calls[0]["client_id"] == "client-aot"
    assert t.calls[0]["method"] == "GET"
    assert [i[0] for i in audit.calls] == ["connector.requested","connector.completed"]

def test_unauthorized_call_does_not_contact_provider():
    c,t,a,audit = make_connector(allow=False)
    with pytest.raises(ConnectorAuthorizationError):
        c.execute(ConnectorRequest(context=context(),arguments={"site_id":"other-site"}))
    assert not t.calls and not audit.calls

def test_wrong_client_boundary_fails_closed():
    c,t,a,audit = make_connector()
    with pytest.raises(ConnectorAuthorizationError):
        c.execute(ConnectorRequest(context=context(client_id="other-client"),arguments={"site_id":"site-id"}))
    assert not t.calls and not a.calls and not audit.calls

@pytest.mark.parametrize("selectors", [
    {"site_id":"site-id", "tenant_id":TENANT},
    {"site_id":"site-id", "token":"fake"},
    {"site_id":"site-id", "url":"https://graph.microsoft.com"},
    {},
])
def test_rejects_untrusted_graph_selector_keys(selectors):
    c,t,a,audit = make_connector()
    with pytest.raises(ValueError):
        c.execute(ConnectorRequest(context=context(),arguments=selectors))
    assert not t.calls and not a.calls and not audit.calls

def test_mismatched_identity_binding_fails_closed():
    c,t,a,audit = make_connector(binding=Binding(status="revoked"))
    with pytest.raises(ConnectorAuthorizationError):
        c.execute(ConnectorRequest(context=context(),arguments={"site_id":"site-id"}))
    assert not t.calls and not a.calls and not audit.calls

def test_document_content_requires_specific_authorization():
    c,t,a,audit = make_connector(allow=False)
    with pytest.raises(ConnectorAuthorizationError):
        c.execute(ConnectorRequest(
            context=context("knowledge.document.content.read"),
            arguments={"site_id":"site-id", "drive_id":"drive-id", "item_id":"item-id"}))
    assert not t.calls
    assert a.calls[0]["operation"] == "knowledge.document.content.read"
    assert a.calls[0]["item_id"] == "item-id"
