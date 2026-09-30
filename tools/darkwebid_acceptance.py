#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
IMPLEMENTATION = REPO_ROOT / "implementation"
if str(IMPLEMENTATION) not in sys.path:
    sys.path.insert(0, str(IMPLEMENTATION))

from connectors.core.contracts import ConnectorContext, ConnectorRequest
from connectors.core.openbao_secrets import OpenBaoSecretResolver
from connectors.darkwebid.connector import DarkWebIdConnector


class Audit:
    def __init__(self) -> None:
        self.events = []

    def record(self, event_type, context, details) -> None:
        self.events.append((event_type, dict(details)))


class UnusedTransport:
    def request(self, **kwargs):
        raise RuntimeError("unexpected generic transport use")


def main() -> int:
    context = ConnectorContext(
        correlation_id="corr-darkwebid-acceptance-20260930",
        principal_id="operator-acceptance",
        organization_id="aot",
        client_id=None,
        capability="darkwebid.organization.search",
        mode="observe",
    )
    resolver = OpenBaoSecretResolver(
        base_url="http://127.0.0.1:8200",
        role_id_path=Path(
            "/var/lib/jason/runtime-secrets/openbao/darkwebid-approle/role-id"
        ),
        secret_id_path=Path(
            "/var/lib/jason/runtime-secrets/openbao/darkwebid-approle/secret-id"
        ),
    )
    audit = Audit()
    connector = DarkWebIdConnector(
        secrets=resolver,
        transport=UnusedTransport(),
        audit=audit,
    )
    result = connector.execute(ConnectorRequest(context, {"page": 0, "limit": 200}))
    data = result.data
    items = data.get("list", []) if isinstance(data, dict) else []
    first_keys = []
    if items and isinstance(items[0], dict):
        first_keys = sorted(str(key) for key in items[0].keys())
    print(
        json.dumps(
            {
                "status": "pass",
                "provider": result.provider,
                "capability": result.capability,
                "records_returned": len(items),
                "top_level_fields": sorted(str(key) for key in data.keys()),
                "first_record_fields": first_keys,
                "audit_events": len(audit.events),
                "secret_values_printed": False,
                "provider_mutation_attempted": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
