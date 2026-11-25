from connectors.microsoft_graph.aot_site_document_policy import AotSharePointSiteDocumentAuthorizer
from connectors.microsoft_graph.site_access_registry import SharePointSiteAccess
TENANT = "f7054323-d52b-4863-8c2f-1898f0b6077c"

class ContentRelease:
    def authorized(self, **kw):
        return kw["item_id"] == "allowed-document"

def test_metadata_requires_enabled_site_and_specific_aot_service(tmp_path):
    r = SharePointSiteAccess(str(tmp_path/"sites.db"), tenant_id=TENANT)
    r.discover([{"tenant_id": TENANT, "site_id": "site",
                 "name": "AOT", "web_url": "https://absolnet.sharepoint.com/sites/AOTAccountingDocuments"}])
    p = AotSharePointSiteDocumentAuthorizer(r, frozenset({"jason-service"}),ContentRelease())
    request={"principal_id":"jason-service","organization_id":"aot",
             "client_id":None,"tenant_id":TENANT,"site_id":"site",
             "drive_id":"drive","item_id":"file"}
    assert not p.authorized(operation="knowledge.document.search",**request)
    r.set_enabled(site_id="site",enabled=True,actor="owner",
                  approval_reference="site-enable",expected_revision=1)
    assert p.authorized(operation="knowledge.document.search",**request)
    assert p.authorized(operation="knowledge.library.search",**request)
    assert not p.authorized(operation="knowledge.document.content.read",**request)
    assert p.authorized(operation="knowledge.document.content.read",
                        **{**request,"item_id":"allowed-document"})
    assert not p.authorized(operation="knowledge.document.search",
                            **{**request,"principal_id":"another-user"})
    assert not p.authorized(operation="knowledge.document.search",
                            **{**request,"tenant_id":"other-tenant"})
