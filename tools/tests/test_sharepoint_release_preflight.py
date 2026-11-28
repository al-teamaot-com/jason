import sqlite3
from tools.sharepoint_release_preflight import APP, SP, TENANT, collect
import pytest


def test_absent_credentials_and_client_boundary_block(tmp_path):
    result = collect(boundary_db=tmp_path/"missing.db",
        role_id=tmp_path/"role", secret_id=tmp_path/"secret",
        grafana_user_header=False, runtime_read_registered=False)
    assert result["status"]=="blocked"
    assert not result["production_changed"]
    assert len(result["blockers"])==6


@pytest.mark.parametrize("client,tenant,app,principal,offboarded,expected", [
    ("client-aot-internal", TENANT, APP, SP, None, True),
    ("other-client", TENANT, APP, SP, None, False),
    ("client-aot-internal", "other-tenant", APP, SP, None, False),
    ("client-aot-internal", TENANT, "other-app", SP, None, False),
    ("client-aot-internal", TENANT, APP, "other-principal", None, False),
    ("client-aot-internal", TENANT, APP, SP, "2026-11-27", False),
])
def test_exact_active_boundary(tmp_path, client, tenant, app, principal, offboarded, expected):
    db=tmp_path/"boundaries.db"
    with sqlite3.connect(db) as cx:
        cx.execute("""CREATE TABLE client_boundaries(provider TEXT, profile TEXT,
            status TEXT, validated_at TEXT, application_id TEXT,
            service_principal_id TEXT, client_id TEXT, external_tenant_id TEXT, offboarded_at TEXT)""")
        cx.execute("""INSERT INTO client_boundaries VALUES(?,?,?,?,?,?,?,?,?)""",
                   ("microsoft_graph_sharepoint","sharepoint-read","validated",
                    "2026-11-19T10:00:00Z",app,principal,client,tenant,offboarded))
    result=collect(boundary_db=db,role_id=tmp_path/"missing-role",
                   secret_id=tmp_path/"missing-secret",grafana_user_header=True,
                   runtime_read_registered=True)
    assert result["checks"]["validated_sharepoint_client_boundary"] is expected
    assert result["status"]=="blocked"
