"""Licensed AOT Owner may inspect exact preprod status, never administer it."""
from types import SimpleNamespace
import pytest
from jason_mcp import server

TENANT = "f7054323-d52b-4863-8c2f-1898f0b6077c"
OWNER_OID = "bee80bdc-ffb0-4c50-b453-c09d4d411f5f"
OWNER_PRINCIPAL = "person-entra-bee80bdcffb04c50b453c09d4d411f5f"


def configure(monkeypatch, *, principal=OWNER_PRINCIPAL, oid=OWNER_OID,
              tenant=TENANT, assurance="entra-oauth-bearer", client_id=None):
    monkeypatch.setattr(server, "_authenticated_write_identity",
                        lambda: (principal, "aot", assurance, client_id))
    monkeypatch.setattr(server, "approval_owner_identities",lambda:frozenset({"person-al"}))
    monkeypatch.setattr(server,"get_access_token",
                        lambda: SimpleNamespace(claims={"tid":tenant,"oid":oid}))


def test_current_licensed_owner_may_inspect_only_status(monkeypatch):
    configure(monkeypatch)
    principal, organization=server._preprod_observe_status_owner()
    assert principal==OWNER_PRINCIPAL
    assert organization=="aot"
    # Separate grant administration MUST remain bound to person-al admin,
    # not to the licensed Owner's read-only status authorization.
    with pytest.raises(PermissionError, match="AUTHORITY_GRANT_ADMIN_OWNER_REQUIRED"):
        server._authority_admin_owner()


@pytest.mark.parametrize("changes",[
    {"tenant":"11111111-1111-1111-1111-111111111111"},
    {"oid":"22222222-2222-2222-2222-222222222222"},
    {"principal":"person-other"},
    {"assurance":"unverified"},
    {"client_id":"1158"},
])
def test_client_scoped_cross_tenant_or_unverified_identity_fails_closed(monkeypatch,changes):
    configure(monkeypatch,**changes)
    with pytest.raises(PermissionError):
        server._preprod_observe_status_owner()
