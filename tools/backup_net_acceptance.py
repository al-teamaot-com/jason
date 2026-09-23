#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from connectors.backup_net.connector import BackupNetConnector
from connectors.core.contracts import ConnectorContext, ConnectorRequest
from connectors.core.openbao_secrets import OpenBaoSecretResolver
from kernel.client_boundaries import (
    BoundaryStatus,
    ClientBoundary,
    InMemoryClientBoundaryRepository,
)

COMPANY_ID = "1627"
CUSTOMER_ID = "08ded7d7-e1b5-427d-83d7-874e6c699471"
CUSTOMER_NAME = "Deborah Gittens Virtuol Designs LLC"
ASSET_NAME = "DGV-50859"


class Audit:
    def __init__(self):
        self.events = []
    def record(self, event_type, context, details):
        self.events.append({"event_type": event_type, "details": dict(details)})


class UnusedTransport:
    def request(self, **kwargs):
        raise RuntimeError("unexpected generic transport use")


def ctx(capability: str) -> ConnectorContext:
    return ConnectorContext(
        correlation_id="corr_backupnet_acceptance_20260923",
        principal_id="operator-acceptance",
        organization_id="aot",
        client_id=COMPANY_ID,
        capability=capability,
        mode="observe",
    )


def main() -> int:
    repo = InMemoryClientBoundaryRepository()
    now = datetime.now(timezone.utc)
    repo.add(
        ClientBoundary(
            id="acceptance-backupnet-1627",
            client_id=COMPANY_ID,
            provider="backup_net",
            external_tenant_id=CUSTOMER_ID,
            primary_domain="virtuoldesigns.com",
            profile="endpoint-backup-read",
            application_id="uniview-public-api",
            status=BoundaryStatus.VALIDATED,
            consent_transaction_id="controlled-acceptance-20260923",
            created_at=now,
            consented_at=now,
            validated_at=now,
        )
    )

    resolver = OpenBaoSecretResolver(
        base_url="http://openbao:8200",
        role_id_path=Path("/run/jason-secrets/openbao/backup-net/role_id"),
        secret_id_path=Path("/run/jason-secrets/openbao/backup-net/secret_id"),
    )
    audit = Audit()
    connector = BackupNetConnector(
        secrets=resolver,
        transport=UnusedTransport(),
        audit=audit,
        boundaries=repo,
    )

    asset = connector.execute(
        ConnectorRequest(
            ctx("backup_net.endpoint_asset.search"),
            {"company_id": 1627, "name": ASSET_NAME, "page_size": 10},
        )
    ).data
    items = asset.get("items") if isinstance(asset, dict) else []
    exact = [
        x for x in items or []
        if isinstance(x, dict) and str(x.get("name") or "").casefold() == ASSET_NAME.casefold()
    ]
    if len(exact) != 1:
        raise SystemExit("DENIED: exact governed asset proof failed")
    a = exact[0]

    backups = connector.execute(
        ConnectorRequest(
            ctx("backup_net.backup.search"),
            {"company_id": 1627, "page_size": 10, "order_direction": "desc"},
        )
    ).data
    backup_items = backups.get("items") if isinstance(backups, dict) else []

    alerts = connector.execute(
        ConnectorRequest(
            ctx("backup_net.backupiq_alert.search"),
            {
                "company_id": 1627,
                "type": "alert",
                "asset_name": ASSET_NAME,
                "page_size": 10,
                "order_direction": "desc",
            },
        )
    ).data
    alert_items = alerts.get("items") if isinstance(alerts, dict) else []

    print(json.dumps({
        "status": "pass",
        "company_id": COMPANY_ID,
        "customer_id": CUSTOMER_ID,
        "customer_name": CUSTOMER_NAME,
        "asset": {
            "id": a.get("id"),
            "name": a.get("name"),
            "status": a.get("status"),
            "backupEnabled": a.get("backupEnabled"),
            "lastSuccessfulBackupTimestamp": a.get("lastSuccessfulBackupTimestamp"),
            "lastOnlineTimestamp": a.get("lastOnlineTimestamp"),
            "storageUsedBytes": a.get("storageUsedBytes"),
            "os": a.get("os"),
        },
        "backup_records_returned": len(backup_items or []),
        "backupiq_alerts_for_asset_returned": len(alert_items or []),
        "audit_events": len(audit.events),
        "all_requests_boundary_validated": all(
            e["details"].get("customer_boundary_validated") is True
            for e in audit.events
            if e["event_type"] in {"connector.requested", "connector.completed"}
        ),
        "secret_values_printed": False,
        "production_boundary_written": False,
    }, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
