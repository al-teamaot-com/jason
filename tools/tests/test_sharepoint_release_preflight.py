import sqlite3
from tools.sharepoint_release_preflight import collect


def test_absent_credentials_and_client_boundary_block(tmp_path):
    result = collect(boundary_db=tmp_path/"missing.db",
        role_id=tmp_path/"role", secret_id=tmp_path/"secret",
        grafana_user_header=False, runtime_read_registered=False)
    assert result["status"]=="blocked"
    assert not result["production_changed"]
    assert len(result["blockers"])==6


def test_existing_app_boundary_does_not_satisfy_missing_credentials(tmp_path):
    db=tmp_path/"boundaries.db"
    with sqlite3.connect(db) as cx:
        cx.execute("""CREATE TABLE client_boundaries(provider TEXT, profile TEXT,
            status TEXT, validated_at TEXT, application_id TEXT,
            service_principal_id TEXT)""")
        cx.execute("""INSERT INTO client_boundaries VALUES(?,?,?,?,?,?)""",
                   ("microsoft_graph_sharepoint","sharepoint-read","validated",
                    "2026-11-19T10:00:00Z","app-id","service-id"))
    result=collect(boundary_db=db,role_id=tmp_path/"missing-role",
                   secret_id=tmp_path/"missing-secret",grafana_user_header=True,
                   runtime_read_registered=True)
    assert result["checks"]["validated_sharepoint_client_boundary"] is True
    assert result["status"]=="blocked"
