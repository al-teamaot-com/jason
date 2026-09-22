#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import os
import sys
import urllib.parse
import uuid
from pathlib import Path

sys.path.insert(0, "/app/implementation")

from connectors.core.contracts import ConnectorContext
from connectors.core.openbao_secrets import OpenBaoSecretResolver

def main() -> int:
    resolver = OpenBaoSecretResolver(
        base_url="http://127.0.0.1:8200",
        role_id_path=Path("/secrets/role-id"),
        secret_id_path=Path("/secrets/secret-id"),
    )
    context = ConnectorContext(
        correlation_id=f"kfs-collector:{uuid.uuid4()}",
        principal_id="svc-jason-kfs-collector",
        organization_id="aot",
        client_id=None,
        capability="print.collect.snapshot",
        mode="observe",
    )
    secret = dict(resolver.resolve("kyocera_kfs.readonly", context))
    db_password = Path("/dbsecret/postgres_password").read_text(encoding="utf-8").strip()
    if not db_password:
        raise RuntimeError("Local KFS database password is empty.")
    database_url = (
        "postgresql://kfs_collector:"
        + urllib.parse.quote(db_password, safe="")
        + "@127.0.0.1:5432/kfs_collector"
    )

    os.environ.update(
        {
            "KFS_BASE_URL": secret["api_url"],
            "KFS_REQUEST_FROM": secret["request_from"],
            "KFS_REQUEST_TO": secret["request_to"],
            "KFS_AUTH_TOKEN": secret["authorization"],
            "KFS_USERNAME": secret["kfs_username"],
            "KFS_PASSWORD": secret["kfs_password"],
            "DATABASE_URL": database_url,
            "KFS_SOURCE": "Jason KFS Collector",
            "KFS_OUTPUT_ROOT": "/out",
        }
    )
    secret.clear()
    db_password = ""
    database_url = ""

    collector_path = Path("/collector/kfs_collector.py")
    spec = importlib.util.spec_from_file_location("jason_kfs_collector", collector_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load KFS collector.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return int(module.main([]))


if __name__ == "__main__":
    raise SystemExit(main())
