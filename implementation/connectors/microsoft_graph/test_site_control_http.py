import json
import threading
from http.server import HTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from connectors.microsoft_graph.site_access_admin import GovernedSiteAccessAdministration
from connectors.microsoft_graph.site_access_registry import SharePointSiteAccess
from connectors.microsoft_graph.site_control_http import make_handler

TENANT = "f7054323-d52b-4863-8c2f-1898f0b6077c"
TOKEN = "test-secret-token-should-be-long-enough-for-acceptance"


class OwnerAuthorization:
    def can_change_site_access(self, **kwargs):
        return kwargs["authenticated_principal"] == "owner@example.com"


@pytest.fixture()
def server(tmp_path):
    registry = SharePointSiteAccess(str(tmp_path / "sites.db"), tenant_id=TENANT)
    registry.discover([{"tenant_id": TENANT, "site_id": "site-1",
                        "name": "AOT Accounting", "web_url": "https://absolnet.sharepoint.com/sites/AOTAccountingDocuments"}])
    admin = GovernedSiteAccessAdministration(registry, OwnerAuthorization())
    handler = make_handler(
        administration=admin, service_token=TOKEN,
        allowed_grafana_owners=frozenset({"owner@example.com"}),
        approval_verifier=lambda actor, site, enabled: actor == "owner@example.com" and site == "site-1",
    )
    httpd = HTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_port}", registry
    httpd.shutdown()
    thread.join(timeout=2)
    httpd.server_close()


def call(base, path, *, token=TOKEN, owner="owner@example.com", payload=None):
    headers = {"Authorization": f"Bearer {token}", "X-Grafana-User": owner}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    request = Request(base + path, data=None if payload is None else json.dumps(payload).encode(),
                      headers=headers, method="POST" if payload is not None else "GET")
    try:
        with urlopen(request, timeout=2) as result:
            return result.status, json.load(result)
    except HTTPError as error:
        return error.code, json.load(error)


def test_authentication_is_fail_closed(server):
    base, registry = server
    assert call(base, "/sharepoint-control/sites", token="invalid")[0] == 403
    assert call(base, "/sharepoint-control/sites", owner="unapproved@example.com")[0] == 403
    assert call(base, "/sharepoint-control/sites")[1]["sites"][0]["enabled"] == 0


def test_owner_toggles_without_deployment_and_gets_live_readback(server):
    base, registry = server
    payload = {"site_id": "site-1", "enabled": True,
               "expected_revision": 1, "reason": "Grafana approval"}
    status, body = call(base, "/sharepoint-control/site-access", payload=payload)
    assert status == 200 and body["site"]["enabled"] == 1
    assert registry.sites()[0]["enabled"] == 1
    assert call(base, "/sharepoint-control/site-access", payload=payload)[0] == 409
    payload.update(enabled=False, expected_revision=2)
    status, body = call(base, "/sharepoint-control/site-access", payload=payload)
    assert status == 200 and body["site"]["enabled"] == 0


def test_caller_cannot_supply_extra_authority(server):
    base, registry = server
    status, _ = call(base, "/sharepoint-control/site-access",
                     payload={"site_id": "site-1", "enabled": True, "expected_revision": 1,
                              "reason": "try", "tenant_id": "other"})
    assert status == 409
    assert registry.sites()[0]["enabled"] == 0
