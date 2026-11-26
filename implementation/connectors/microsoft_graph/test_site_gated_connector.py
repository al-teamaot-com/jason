from dataclasses import dataclass, field
import pytest

from connectors.core.contracts import ConnectorContext, ConnectorRequest
from connectors.microsoft_graph.site_access_registry import SharePointSiteAccess
from connectors.microsoft_graph.site_gated_connector import SiteGatedSharePointConnector

TENANT = "f7054323-d52b-4863-8c2f-1898f0b6077c"

@dataclass
class Delegate:
    calls: list = field(default_factory=list)
    provider_name: str = "microsoft_graph"
    capabilities: frozenset = frozenset({"knowledge.library.search"})

    def _tenant(self, context):
        assert context.principal_id == "jason-service"
        return TENANT

    def execute(self, request):
        self.calls.append(request)
        return "provider-result"

def request(site="site-1"):
    return ConnectorRequest(
        context=ConnectorContext(correlation_id="gate-test",
            principal_id="jason-service", organization_id="aot",
            client_id="client-aot", capability="knowledge.library.search"),
        arguments={"site_id":site})

def test_new_site_denied_then_owner_toggle_applies_immediately(tmp_path):
    registry = SharePointSiteAccess(str(tmp_path/"access.db"),tenant_id=TENANT)
    registry.discover([{"tenant_id":TENANT,"site_id":"site-1",
                        "name":"Accounting","web_url":"https://example.sharepoint.com"}])
    delegate=Delegate()
    gated=SiteGatedSharePointConnector(delegate,registry)
    with pytest.raises(PermissionError): gated.execute(request())
    assert delegate.calls==[]
    registry.set_enabled(site_id="site-1",enabled=True,actor="owner",
                         approval_reference="approval-1",expected_revision=1)
    assert gated.execute(request())=="provider-result"
    registry.set_enabled(site_id="site-1",enabled=False,actor="owner",
                         approval_reference="approval-2",expected_revision=2)
    with pytest.raises(PermissionError): gated.execute(request())
    assert len(delegate.calls)==1

def test_unknown_site_never_contacted(tmp_path):
    registry = SharePointSiteAccess(str(tmp_path/"access.db"),tenant_id=TENANT)
    delegate=Delegate()
    gated=SiteGatedSharePointConnector(delegate,registry)
    with pytest.raises(PermissionError): gated.execute(request("unknown"))
    assert not delegate.calls
