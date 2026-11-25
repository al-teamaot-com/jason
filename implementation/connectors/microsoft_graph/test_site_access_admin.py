from dataclasses import dataclass
import pytest
from connectors.microsoft_graph.site_access_registry import SharePointSiteAccess
from connectors.microsoft_graph.site_access_admin import GovernedSiteAccessAdministration

TENANT = "f7054323-d52b-4863-8c2f-1898f0b6077c"

@dataclass
class Auth:
    allowed: bool = False
    def can_change_site_access(self, **kw):
        assert kw["tenant_id"] == TENANT
        assert kw["authenticated_principal"] == "verified-owner"
        return self.allowed

def test_owner_authorization_and_exact_revision_required(tmp_path):
    registry = SharePointSiteAccess(str(tmp_path/"access.db"), tenant_id=TENANT)
    registry.discover([{"tenant_id":TENANT, "site_id":"site",
        "name":"Accounting", "web_url":"https://absolnet.sharepoint.com/sites/AOTAccountingDocuments"}])
    service = GovernedSiteAccessAdministration(registry,Auth(False))
    kw={"authenticated_principal":"verified-owner","site_id":"site",
        "enabled":True,"approval_reference":"exact-approved-action","expected_revision":1}
    with pytest.raises(PermissionError):service.change_site_access(**kw)
    assert registry.sites()[0]["enabled"]==0
    service = GovernedSiteAccessAdministration(registry,Auth(True))
    result = service.change_site_access(**kw)
    assert result["enabled"]==1 and result["revision"]==2
    with pytest.raises(ValueError):service.change_site_access(**kw)

def test_anonymous_actor_denied(tmp_path):
    registry = SharePointSiteAccess(str(tmp_path/"access.db"), tenant_id=TENANT)
    service = GovernedSiteAccessAdministration(registry,Auth(True))
    with pytest.raises(PermissionError):
        service.change_site_access(authenticated_principal="",site_id="site",
            enabled=True,approval_reference="exact",expected_revision=1)
