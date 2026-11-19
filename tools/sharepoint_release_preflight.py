#!/usr/bin/env python3
"""Read-only release readiness evidence for Jason's independent SharePoint service.

Does not authenticate to Graph, read secret content, install, restart, or approve.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


def collect(*, boundary_db: Path, role_id: Path, secret_id: Path,
            grafana_user_header: bool, runtime_read_registered: bool) -> dict:
    checks = {}
    for key, path in (
        ("sharepoint_approle_role_id_present", role_id),
        ("sharepoint_approle_secret_id_present", secret_id),
    ):
        try:
            checks[key] = path.is_file()
        except OSError:
            # Root-protected credentials may exist but are unreadable to this
            # unprivileged preflight; never report unverified presence as PASS.
            checks[key] = False
    checks["validated_sharepoint_client_boundary"] = False
    checks["boundary_db_readable"] = False
    if boundary_db.is_file():
        try:
            with sqlite3.connect(f"file:{boundary_db}?mode=ro", uri=True) as db:
                rows = db.execute(
                    """SELECT count(*) FROM client_boundaries
                       WHERE provider='microsoft_graph_sharepoint'
                         AND profile='sharepoint-read'
                         AND status='validated'
                         AND validated_at IS NOT NULL
                         AND application_id IS NOT NULL
                         AND service_principal_id IS NOT NULL""").fetchone()
                checks["boundary_db_readable"] = True
                checks["validated_sharepoint_client_boundary"] = rows[0] > 0
        except (sqlite3.Error, OSError):
            pass
    checks["grafana_authenticated_user_header_enabled"] = bool(grafana_user_header)
    checks["governed_sharepoint_runtime_capabilities_active"] = bool(runtime_read_registered)
    blocked = [key for key, ok in checks.items() if not ok]
    return {
        "status": "preproduction_ready" if not blocked else "blocked",
        "mode": "read_only_no_secret_values",
        "checks": checks,
        "blockers": blocked,
        "production_changed": False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--boundary-db", type=Path,
                        default=Path("/var/lib/jason/authority/client-boundaries.sqlite3"))
    parser.add_argument("--role-id", type=Path,
                        default=Path("/opt/jason/bootstrap/secrets/openbao/microsoft-graph-sharepoint-read-approle/role-id"))
    parser.add_argument("--secret-id", type=Path,
                        default=Path("/opt/jason/bootstrap/secrets/openbao/microsoft-graph-sharepoint-read-approle/secret-id"))
    parser.add_argument("--grafana-user-header-enabled", action="store_true")
    parser.add_argument("--runtime-read-registered", action="store_true")
    a=parser.parse_args()
    print(json.dumps(collect(boundary_db=a.boundary_db, role_id=a.role_id,
                             secret_id=a.secret_id,
                             grafana_user_header=a.grafana_user_header_enabled,
                             runtime_read_registered=a.runtime_read_registered),
                     indent=2,sort_keys=True))


if __name__ == "__main__":
    main()
