import json
from pathlib import Path
import pytest
from tools import sharepoint_grafana_install as installer

DASH = {"uid": installer.DASHBOARD_UID, "title": "Jason SharePoint Site Access",
        "panels": [{"id": 1, "type": "text"}]}
TOKEN = "long-secret-exactly-32-or-more-characters"


def test_preflight_never_mutates_existing_grafana(monkeypatch, tmp_path):
    path = tmp_path/"dashboard.json"
    path.write_text(json.dumps(DASH))
    calls = []
    def fake(base, credential, method, path, payload=None):
        calls.append((method, path))
        if path == "/api/health": return 200, {"database": "ok"}
        if path == "/api/plugins/volkovlabs-form-panel/settings":
            return 200, {"enabled": True}
        if path == "/api/folders":
            return 200, [{"title": "Jason", "uid": "folder-jason"}]
        return 404, None
    monkeypatch.setattr(installer, "_request", fake)
    output=installer.provision("http://localhost:3000", "grafana-admin-token",
                              TOKEN,path,apply=False)
    assert output["status"]=="preflight"
    assert all(method=="GET" for method, _ in calls)


def test_apply_creates_only_approved_uids_and_reads_back(monkeypatch, tmp_path):
    path = tmp_path/"dashboard.json"
    path.write_text(json.dumps(DASH))
    changes = []
    def fake(base, credential, method, path, payload=None):
        if method != "GET":
            changes.append((method,path,payload))
            return 200, {"status": "success"}
        if path == "/api/health":return 200,{}
        if path == "/api/plugins/volkovlabs-form-panel/settings":return 200,{"enabled":True}
        if path == "/api/folders":return 200,[{"title":"Jason","uid":"folder-jason"}]
        if path.endswith("/"+installer.DATASOURCE_UID):
            return (200,{"uid":installer.DATASOURCE_UID,
                         "type":"yesoreyeram-infinity-datasource",
                         "url":installer.DATASOURCE_TARGET}) if changes else (404,None)
        if path.endswith("/"+installer.DASHBOARD_UID):
            return (200,{"dashboard":{"uid":installer.DASHBOARD_UID}}) if changes else (404,None)
        raise AssertionError(path)
    monkeypatch.setattr(installer,"_request",fake)
    output=installer.provision("http://localhost:3000","grafana-admin",TOKEN,path,apply=True)
    assert output["status"]=="verified"
    assert [x[1] for x in changes]==["/api/datasources","/api/dashboards/db"]
    assert changes[1][2]["folderUid"]=="folder-jason"
    assert changes[0][2]["uid"]==installer.DATASOURCE_UID


def test_wrong_dashboard_uid_fails_before_api_mutation(tmp_path):
    path=tmp_path/"dashboard.json"
    path.write_text(json.dumps({**DASH,"uid":"other"}))
    with pytest.raises(ValueError):
        installer.provision("http://localhost:3000","token",TOKEN,path,apply=True)
