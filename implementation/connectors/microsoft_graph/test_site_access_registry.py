import sqlite3
import pytest
from connectors.microsoft_graph.site_access_registry import SharePointSiteAccess

TENANT = "f7054323-d52b-4863-8c2f-1898f0b6077c"

def site(site_id="site-1", tenant_id=TENANT):
    return {"site_id": site_id, "tenant_id": tenant_id,
            "name": "AOT Accounting", "web_url": "https://example.sharepoint.com/sites/aot"}

def test_daily_discovery_creates_disabled_and_is_idempotent(tmp_path):
    r = SharePointSiteAccess(str(tmp_path / "sites.db"), tenant_id=TENANT)
    assert r.discover([site()]) == 1
    assert r.sites()[0]["enabled"] == 0
    assert r.discover([site()]) == 1
    assert r.sites()[0]["revision"] == 1
    with pytest.raises(PermissionError):
        r.require_site_access(tenant_id=TENANT, site_id="site-1")
    assert r.last_discovery()["success"] == 1

def test_toggle_effective_immediately_and_preserved_on_discovery(tmp_path):
    path = str(tmp_path / "sites.db")
    r = SharePointSiteAccess(path, tenant_id=TENANT)
    r.discover([site()])
    assert r.set_enabled(site_id="site-1", enabled=True, actor="owner",
                         approval_reference="approved-A", expected_revision=1) == 2
    r.require_site_access(tenant_id=TENANT, site_id="site-1")
    r.discover([site()])
    SharePointSiteAccess(path, tenant_id=TENANT).require_site_access(
        tenant_id=TENANT, site_id="site-1")
    assert r.sites()[0]["revision"] == 2
    assert r.set_enabled(site_id="site-1", enabled=False, actor="owner",
                         approval_reference="approved-B", expected_revision=2) == 3
    with pytest.raises(PermissionError):
        r.require_site_access(tenant_id=TENANT, site_id="site-1")
    with pytest.raises(ValueError):
        r.set_enabled(site_id="site-1", enabled=True, actor="owner",
                      approval_reference="stale", expected_revision=1)

def test_unknown_site_and_cross_tenant_fail_closed(tmp_path):
    r = SharePointSiteAccess(str(tmp_path / "sites.db"), tenant_id=TENANT)
    with pytest.raises(PermissionError):
        r.require_site_access(tenant_id=TENANT, site_id="missing")
    with pytest.raises(PermissionError):
        r.discover([site(tenant_id="other-tenant")])
    assert r.sites() == []

def test_partial_failed_scan_cannot_register_or_enable_site(tmp_path):
    r = SharePointSiteAccess(str(tmp_path / "sites.db"), tenant_id=TENANT)
    with pytest.raises(ValueError):
        r.discover([site(), {"tenant_id": TENANT, "site_id": ""}])
    assert r.sites() == []
    r.discovery_failed("Graph throttled")
    assert r.last_discovery()["success"] == 0
    assert r.sites() == []

def test_scans_do_not_reset_existing_site_decisions(tmp_path):
    r = SharePointSiteAccess(str(tmp_path / "sites.db"), tenant_id=TENANT)
    r.discover([site("a"),site("b")])
    r.set_enabled(site_id="a", enabled=True, actor="owner",
                  approval_reference="change-1", expected_revision=1)
    r.discover([site("a"),site("b"),site("c")])
    states = {s["site_id"]: s["enabled"] for s in r.sites()}
    assert states == {"a": 1, "b": 0, "c": 0}
    with sqlite3.connect(r.path) as db:
        assert db.execute("SELECT COUNT(*) FROM sharepoint_site_audit").fetchone()[0] == 4
