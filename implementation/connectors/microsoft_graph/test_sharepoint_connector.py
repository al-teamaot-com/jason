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
        if jason_identity_id != "owner-1":
            return None
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



@dataclass
class AotServiceBinding:
    status: str = "active"
    organization_id: str = "aot"
    jason_identity_id: str = "jason-kfs-evidence-service"
    microsoft_tenant_id: str = TENANT
    profile: str = "aot-approved-document-read"


@dataclass
class OrganizationBindings:
    binding: object = field(default_factory=AotServiceBinding)
    calls: list = field(default_factory=list)

    def find_active_by_jason_service_identity(self, *, jason_identity_id, organization_id):
        self.calls.append((jason_identity_id, organization_id))
        return self.binding


class FakeDocumentReader:
    def __init__(self):
        self.calls = []

    def read_metadata(self, **kwargs):
        self.calls.append(("metadata", kwargs))
        return {"id": kwargs["item_id"], "site_id": kwargs["site_id"],
                "drive_id": kwargs["drive_id"], "name": "AOT Copier Log.xlsx"}

    def read_bytes(self, **kwargs):
        self.calls.append(("content", kwargs))
        return b"test approved evidence"


def org_context(operation="knowledge.document.metadata.read", organization_id="aot",
                principal_id="jason-kfs-evidence-service", client_id=None):
    return ConnectorContext(
        correlation_id="kfs-evidence-qa", principal_id=principal_id,
        organization_id=organization_id, client_id=client_id,
        capability=operation,
    )


def make_service_connector(*, org_binding=None, allow=True):
    reader = FakeDocumentReader()
    authorizer = Authorizer(allow)
    audit = Audit()
    bindings = OrganizationBindings(org_binding if org_binding is not None else AotServiceBinding())
    connector = GovernedSharePointConnector(
        reader=reader, bindings=Bindings(), authorizer=authorizer,
        audit=audit, organization_bindings=bindings,
    )
    return connector, reader, authorizer, audit, bindings


def test_aot_workload_can_read_one_authorized_document_metadata():
    connector, reader, authorizer, audit, bindings = make_service_connector()
    result = connector.execute(ConnectorRequest(
        context=org_context(),
        arguments={"site_id": "approved-aot-site", "drive_id": "approved-drive",
                   "item_id": "approved-copier-file"},
    ))
    assert result.data["item"]["id"] == "approved-copier-file"
    assert bindings.calls == [("jason-kfs-evidence-service", "aot")]
    assert authorizer.calls[0]["client_id"] is None
    assert authorizer.calls[0]["tenant_id"] == TENANT
    assert authorizer.calls[0]["operation"] == "knowledge.document.metadata.read"
    assert reader.calls[0][0] == "metadata"
    assert len(audit.calls) == 2


def test_aot_workload_content_requires_specific_document_release():
    connector, reader, authorizer, audit, _ = make_service_connector(allow=False)
    with pytest.raises(ConnectorAuthorizationError):
        connector.execute(ConnectorRequest(
            context=org_context("knowledge.document.content.read"),
            arguments={"site_id": "site", "drive_id": "drive", "item_id": "document"},
        ))
    assert authorizer.calls[0]["operation"] == "knowledge.document.content.read"
    assert reader.calls == [] and audit.calls == []


@pytest.mark.parametrize("profile_update", [
    {"status": "revoked"},
    {"organization_id": "another-org"},
    {"jason_identity_id": "another-service"},
    {"profile": "mail-read"},
    {"microsoft_tenant_id": ""},
])
def test_aot_workload_binding_fail_closed(profile_update):
    from dataclasses import replace
    bound = replace(AotServiceBinding(), **profile_update)
    connector, reader, authorizer, audit, _ = make_service_connector(org_binding=bound)
    with pytest.raises(ConnectorAuthorizationError):
        connector.execute(ConnectorRequest(
            context=org_context(),
            arguments={"site_id": "site", "drive_id": "drive", "item_id": "document"},
        ))
    assert reader.calls == [] and authorizer.calls == [] and audit.calls == []


def test_aot_workload_never_inherits_non_aot_organization_scope():
    connector, reader, authorizer, audit, _ = make_service_connector()
    with pytest.raises(ConnectorAuthorizationError):
        connector.execute(ConnectorRequest(
            context=org_context(organization_id="client-org"),
            arguments={"site_id": "site", "drive_id": "drive", "item_id": "document"},
        ))
    assert reader.calls == [] and authorizer.calls == [] and audit.calls == []


@pytest.mark.parametrize("operation,arguments", [
    ("knowledge.library.search", {"site_id": "site"}),
    ("knowledge.document.search", {"site_id": "site", "drive_id": "drive"}),
])
def test_aot_document_service_cannot_enumerate_libraries_or_arbitrary_files(operation, arguments):
    connector, reader, authorizer, audit, _ = make_service_connector()
    with pytest.raises(ConnectorAuthorizationError, match="may not enumerate"):
        connector.execute(ConnectorRequest(context=org_context(operation), arguments=arguments))
    assert reader.calls == [] and authorizer.calls == [] and audit.calls == []


def test_aot_service_role_cannot_override_client_bound_principal():
    connector, reader, authorizer, audit, _ = make_service_connector()
    with pytest.raises(ConnectorAuthorizationError):
        connector.execute(ConnectorRequest(
            context=org_context(client_id="some-client"),
            arguments={"site_id": "site", "drive_id": "drive", "item_id": "document"},
        ))
    assert reader.calls == [] and authorizer.calls == [] and audit.calls == []
