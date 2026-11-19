#!/usr/bin/env python3
"""Preflight and exact-scope Grafana provisioner for Jason SharePoint controls.

Default mode reads only. --apply additionally requires an exact source commit
and a separately provisioned authenticated Grafana service-account token.
Never displays secret bytes. Never modifies unrelated datasource/dashboard UIDs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

DATASOURCE_UID = "jason-sharepoint-control"
DASHBOARD_UID = "jason-sharepoint-site-access"
DATASOURCE_TARGET = "http://jason-sharepoint-site-control:9582"


def _request(base: str, credential: str, method: str, path: str,
             payload: dict | None = None):
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req = Request(base.rstrip("/") + path, data=body,
                  headers={"Authorization": "Bearer " + credential,
                           "Accept": "application/json",
                           "Content-Type": "application/json"},
                  method=method)
    try:
        with urlopen(req, timeout=15) as r:
            return r.status, json.load(r)
    except HTTPError as exc:
        if exc.code == 404:
            return 404, None
        raise RuntimeError("Grafana API rejected exact-scope operation: HTTP " + str(exc.code))


def provision(base: str, credential: str, control_token: str,
              dashboard_path: Path, *, apply: bool) -> dict:
    if not credential.strip() or len(control_token.strip()) < 32:
        raise ValueError("Grafana service credentials are not provisioned")
    dashboard = json.loads(dashboard_path.read_text())
    if dashboard.get("uid") != DASHBOARD_UID:
        raise ValueError("Unexpected Grafana dashboard UID")
    if not isinstance(dashboard.get("panels"), list) or not dashboard["panels"]:
        raise ValueError("Grafana page is incomplete")

    health, _ = _request(base, credential, "GET", "/api/health")
    if health != 200:
        raise RuntimeError("Grafana health check failed")
    plugin_status, plugin = _request(
        base, credential, "GET", "/api/plugins/volkovlabs-form-panel/settings")
    if plugin_status != 200 or not plugin:
        raise RuntimeError("Required Grafana form panel is unavailable")
    folders_status, folders = _request(base, credential, "GET", "/api/folders")
    if folders_status != 200 or not isinstance(folders, list):
        raise RuntimeError("Grafana folder metadata unavailable")
    approved_folders = [folder for folder in folders
                        if folder.get("title") == "Jason" and folder.get("uid")]
    if len(approved_folders) != 1:
        raise PermissionError("Exact Jason dashboard folder not established")
    folder_uid = approved_folders[0]["uid"]
    _, current_ds = _request(base, credential, "GET",
                             "/api/datasources/uid/" + DATASOURCE_UID)
    _, current_dashboard = _request(base, credential, "GET",
                                    "/api/dashboards/uid/" + DASHBOARD_UID)
    if current_ds is not None and (
        current_ds.get("type") != "yesoreyeram-infinity-datasource"
        or current_ds.get("url") != DATASOURCE_TARGET
    ):
        raise PermissionError("Existing datasource UID is owned by a different target")
    if current_dashboard is not None:
        current = current_dashboard.get("dashboard") or {}
        if current.get("uid") != DASHBOARD_UID:
            raise PermissionError("Dashboard identity mismatch")

    if not apply:
        return {"status": "preflight", "grafana_available": True,
                "datasource_exists": current_ds is not None,
                "dashboard_exists": current_dashboard is not None,
                "changed": False}

    ds_payload = {
        "name": "Jason SharePoint Site Control",
        "uid": DATASOURCE_UID,
        "type": "yesoreyeram-infinity-datasource",
        "access": "proxy",
        "url": DATASOURCE_TARGET,
        "jsonData": {"httpHeaderName1": "Authorization", "global_queries": []},
        "secureJsonData": {"httpHeaderValue1": "Bearer " + control_token.strip()},
        "isDefault": False,
    }
    if current_ds is None:
        _request(base, credential, "POST", "/api/datasources", ds_payload)
    else:
        _request(base, credential, "PUT",
                 "/api/datasources/uid/" + DATASOURCE_UID, ds_payload)
    # Grafana's own dashboard API provisions immediately, without restarting
    # the existing Grafana or any Jason runtime container.
    _request(base, credential, "POST", "/api/dashboards/db", {
        "dashboard": dashboard,
        "overwrite": current_dashboard is not None,
        "folderUid": folder_uid,
        "message": "Approved isolated Jason SharePoint access dashboard",
    })
    _, readback_ds = _request(base, credential, "GET",
                              "/api/datasources/uid/" + DATASOURCE_UID)
    _, readback_dash = _request(base, credential, "GET",
                                "/api/dashboards/uid/" + DASHBOARD_UID)
    if (not readback_ds or readback_ds.get("url") != DATASOURCE_TARGET
            or not readback_dash
            or (readback_dash.get("dashboard") or {}).get("uid") != DASHBOARD_UID):
        raise RuntimeError("Grafana exact-scope provisioning readback failed")
    return {"status": "verified", "datasource_uid": DATASOURCE_UID,
            "dashboard_uid": DASHBOARD_UID, "changed": True}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-sha", default="")
    args = parser.parse_args()
    source_root = Path(__file__).resolve().parent.parent
    if args.apply:
        actual = subprocess.check_output(
            ["git", "-C", str(source_root), "rev-parse", "HEAD"],
            text=True).strip()
        if not args.expected_sha or args.expected_sha != actual:
            raise PermissionError("Exact approved release commit SHA mismatch")
    credential = Path(os.environ["JASON_GRAFANA_API_TOKEN_FILE"]).read_text().strip()
    control_token = Path(os.environ["JASON_SHAREPOINT_GRAFANA_TOKEN_FILE"]).read_text().strip()
    result = provision(
        os.environ.get("JASON_GRAFANA_URL", "http://127.0.0.1:3000"),
        credential, control_token,
        source_root / "infrastructure/showcase/grafana/dashboards/jason-sharepoint-site-access.json",
        apply=args.apply,
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
