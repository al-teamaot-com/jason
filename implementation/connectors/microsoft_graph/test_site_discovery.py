from dataclasses import dataclass, field
import pytest
from connectors.microsoft_graph.site_discovery import SharePointSiteDiscovery
from connectors.microsoft_graph.site_access_registry import SharePointSiteAccess

TENANT="f7054323-d52b-4863-8c2f-1898f0b6077c"
SITE={"id":"absolnet.sharepoint.com,aaa,bbb","name":"AOT Accounting",
      "webUrl":"https://absolnet.sharepoint.com/sites/AOTAccountingDocuments",
      "siteCollection":{"hostName":"absolnet.sharepoint.com"}}
NEXT="https://graph.microsoft.com/v1.0/sites/oneDrive.getAllSites?$skiptoken=ABC"

class Tokens:
    def access_token_for_tenant(self, *, microsoft_tenant_id):
        assert microsoft_tenant_id == TENANT
        return "synthetic-app-token"

@dataclass
class Transport:
    responses: list
    calls: list = field(default_factory=list)
    def request(self, **kw):
        self.calls.append(kw)
        result=self.responses.pop(0)
        if isinstance(result, Exception): raise result
        return result

def make(tmp_path, responses):
    r=SharePointSiteAccess(str(tmp_path/"sites.db"),tenant_id=TENANT)
    tr=Transport(list(responses))
    return SharePointSiteDiscovery(TENANT, Tokens(), tr, r),r,tr

def test_multi_page_discovery_new_sites_disabled(tmp_path):
    d,r,tr=make(tmp_path,[{"value":[SITE],"@odata.nextLink":NEXT},
                          {"value":[{**SITE,"id":"second","name":"Sales",
                                      "webUrl":"https://absolnet.sharepoint.com/sites/Sales"}]}])
    assert d.run()==2
    assert len(r.sites())==2 and all(x["enabled"]==0 for x in r.sites())
    assert tr.calls[1]["url"]==NEXT
    assert all(x["method"]=="GET" for x in tr.calls)

def test_graph_failure_does_not_commit_partial_site_list(tmp_path):
    d,r,tr=make(tmp_path,[{"value":[SITE],"@odata.nextLink":NEXT},
                          RuntimeError("Graph throttling")])
    with pytest.raises(RuntimeError):d.run()
    assert r.sites()==[]
    assert r.last_discovery()["success"]==0

def test_untrusted_nextlink_denied_without_request(tmp_path):
    d,r,tr=make(tmp_path,[{"value":[SITE],
        "@odata.nextLink":"https://evil.example/v1.0/sites/getAllSites"}])
    with pytest.raises(Exception):d.run()
    assert len(tr.calls)==1 and r.sites()==[]

def test_daily_scan_never_reenables_disabled_or_changes_existing_switch(tmp_path):
    d,r,tr=make(tmp_path,[{"value":[SITE]}])
    d.run()
    r.set_enabled(site_id=SITE["id"],enabled=True,actor="owner",
                  approval_reference="exact-1",expected_revision=1)
    d2,r,tr2=make(tmp_path,[{"value":[SITE]}])
    d2.run()
    assert r.sites()[0]["enabled"]==1
