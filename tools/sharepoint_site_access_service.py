#!/usr/bin/env python3
"""Dedicated Jason SharePoint site discovery/control component.

No delegated user token, no provider mutation, no direct access to other Jason
components. Release Manager must provision exact app boundary and control token
before scheduling/serving this component.
"""
from __future__ import annotations

import argparse
import os
from http.server import ThreadingHTTPServer
from pathlib import Path

from connectors.core.http_transport import UrlLibJsonHttpTransport
from connectors.microsoft_graph.site_access_admin import GovernedSiteAccessAdministration
from connectors.microsoft_graph.site_access_registry import SharePointSiteAccess
from connectors.microsoft_graph.site_control_http import make_handler
from jason_runtime.microsoft_sharepoint import (
    build_microsoft_sharepoint_runtime,
    build_sharepoint_site_management,
    require_validated_sharepoint_service_boundary,
)
from kernel.client_boundaries import SQLiteClientBoundaryRepository


class OwnerSiteAuthority:
    def __init__(self, approved_owners: frozenset[str]):
        self.owners = approved_owners

    def can_change_site_access(self, *, authenticated_principal, tenant_id,
                               site_id, desired_enabled, approval_reference):
        return bool(authenticated_principal in self.owners
                    and isinstance(site_id, str) and site_id
                    and isinstance(approval_reference, str) and approval_reference.strip())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("discover", "serve"))
    args = parser.parse_args()
    tenant = os.environ["JASON_SHAREPOINT_AOT_TENANT_ID"].strip()
    boundary_db = Path(os.environ["JASON_SHAREPOINT_BOUNDARY_DB"])
    state_db = Path(os.environ["JASON_SHAREPOINT_SITE_ACCESS_DB"])
    transport = UrlLibJsonHttpTransport()
    runtime = build_microsoft_sharepoint_runtime(
        boundary_db=boundary_db,
        openbao_url=os.environ["JASON_OPENBAO_URL"],
        role_id_path=Path(os.environ["JASON_SHAREPOINT_OPENBAO_ROLE_ID_PATH"]),
        secret_id_path=Path(os.environ["JASON_SHAREPOINT_OPENBAO_SECRET_ID_PATH"]),
        transport=transport,
    )
    require_validated_sharepoint_service_boundary(
        boundaries=SQLiteClientBoundaryRepository(runtime.store),
        tenant_id=tenant,
        expected_client_id="client-aot-internal",
        expected_domain="teamaot.com",
    )
    manager = build_sharepoint_site_management(
        runtime=runtime, tenant_id=tenant, state_db=state_db, transport=transport,
        allowed_sharepoint_hosts=frozenset(
            h.strip().casefold() for h in
            os.environ['JASON_SHAREPOINT_AOT_HOSTNAMES'].split(',') if h.strip()
        ),
    )
    if args.action == "discover":
        count = manager.daily_discovery.run()
        print("SHAREPOINT_DISCOVERY_SUCCEEDED sites_seen=" + str(count))
        return 0

    owners = frozenset(
        value.strip().casefold() for value in
        os.environ["JASON_SHAREPOINT_GRAFANA_OWNER_USERS"].split(",")
        if value.strip()
    )
    # Secret never logged; service startup fails closed if it is missing/short.
    token = Path(os.environ["JASON_SHAREPOINT_GRAFANA_TOKEN_FILE"]).read_text(
        encoding="utf-8").strip()
    authority = OwnerSiteAuthority(owners)
    administration = GovernedSiteAccessAdministration(
        registry=manager.site_access, authorization=authority,
    )
    handler = make_handler(
        administration=administration, service_token=token,
        allowed_grafana_owners=owners,
        approval_verifier=lambda actor, site, enabled: (
            actor in owners and bool(site.strip()) and type(enabled) is bool
        ),
    )
    bind = os.environ.get("JASON_SHAREPOINT_CONTROL_BIND", "127.0.0.1")
    port = int(os.environ.get("JASON_SHAREPOINT_CONTROL_PORT", "9582"))
    ThreadingHTTPServer((bind, port), handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
