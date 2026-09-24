#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from uuid import UUID, uuid4

from connectors.backup_net.client import BackupNetClient
from connectors.core.contracts import ConnectorContext
from connectors.core.openbao_secrets import OpenBaoSecretResolver
from kernel.client_boundaries import (
    BoundaryStatus,
    ClientBoundary,
    SQLiteClientBoundaryRepository,
    SQLiteClientBoundaryStore,
)

DEFAULT_OPENBAO_URL = "http://openbao:8200"
DEFAULT_ROLE_ID_PATH = Path("/run/jason-secrets/openbao/backup-net/role_id")
DEFAULT_SECRET_ID_PATH = Path("/run/jason-secrets/openbao/backup-net/secret_id")
DEFAULT_BOUNDARY_DB = Path("/var/lib/jason/authority/client-boundaries.sqlite3")


class BoundaryDiscoveryError(RuntimeError):
    pass


def _items(value: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    raw = value.get("items")
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, Mapping)]


def _exact_customer(client: BackupNetClient, name: str) -> tuple[str, str]:
    response = client.get(
        "/v1/customers",
        {"name": name, "page_number": 1, "page_size": 10},
    )
    matches = [
        item for item in _items(response)
        if str(item.get("name") or "").strip().casefold() == name.casefold()
    ]
    if len(matches) != 1:
        raise BoundaryDiscoveryError(
            f"Expected exactly one exact Backup.net customer match; found {len(matches)}."
        )
    customer_id = str(matches[0].get("id") or "").strip()
    try:
        customer_id = str(UUID(customer_id))
    except ValueError as exc:
        raise BoundaryDiscoveryError(
            "Backup.net returned an invalid customer UUID."
        ) from exc
    return customer_id, str(matches[0].get("name") or "").strip()


def _exact_asset(
    client: BackupNetClient,
    *,
    customer_id: str,
    asset_name: str,
) -> Mapping[str, Any]:
    response = client.get(
        "/api/epb/v1/assets",
        {
            "customer_id": customer_id,
            "name": asset_name,
            "page_number": 1,
            "page_size": 10,
        },
    )
    matches = [
        item for item in _items(response)
        if str(item.get("name") or "").strip().casefold() == asset_name.casefold()
    ]
    if len(matches) != 1:
        raise BoundaryDiscoveryError(
            f"Expected exactly one exact Endpoint Backup asset match; found {len(matches)}."
        )
    asset = matches[0]
    observed_customer = str(asset.get("customerId") or "").strip()
    try:
        observed_customer = str(UUID(observed_customer))
    except ValueError as exc:
        raise BoundaryDiscoveryError(
            "Endpoint Backup asset returned an invalid customer UUID."
        ) from exc
    if observed_customer != customer_id:
        raise BoundaryDiscoveryError(
            "Endpoint Backup asset customer UUID does not match the customer lookup."
        )
    return asset


def _prove_empty_asset_inventory(
    client: BackupNetClient,
    *,
    customer_id: str,
) -> dict[str, Any]:
    response = client.get(
        "/api/epb/v1/assets",
        {
            "customer_id": customer_id,
            "page_number": 1,
            "page_size": 1,
        },
    )
    items = _items(response)
    if items:
        raise BoundaryDiscoveryError(
            "Endpoint Backup assets exist for this customer; exact asset proof is required."
        )
    return {"inventory_empty": True}


def _safe_asset_summary(asset: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": asset.get("id"),
        "name": asset.get("name"),
        "customerName": asset.get("customerName"),
        "status": asset.get("status"),
        "backupEnabled": asset.get("backupEnabled"),
        "lastSuccessfulBackupTimestamp": asset.get("lastSuccessfulBackupTimestamp"),
        "lastOnlineTimestamp": asset.get("lastOnlineTimestamp"),
        "storageUsedBytes": asset.get("storageUsedBytes"),
        "os": asset.get("os"),
    }


def _persist_boundary(
    *,
    db_path: Path,
    company_id: str,
    customer_id: str,
    primary_domain: str,
) -> tuple[str, bool]:
    store = SQLiteClientBoundaryStore(db_path)
    try:
        repo = SQLiteClientBoundaryRepository(store)
        existing = repo.find_active_for_client(
            client_id=company_id,
            provider="backup_net",
        )
        if existing is not None:
            if (
                existing.status is BoundaryStatus.VALIDATED
                and existing.external_tenant_id == customer_id
                and existing.profile == "endpoint-backup-read"
            ):
                return existing.id, False
            raise BoundaryDiscoveryError(
                "An active Backup.net boundary already exists for this Autotask company."
            )

        other = repo.find_active_for_external_tenant(
            provider="backup_net",
            external_tenant_id=customer_id,
        )
        if other is not None:
            raise BoundaryDiscoveryError(
                "The Backup.net customer UUID is already mapped to another client."
            )

        now = datetime.now(timezone.utc)
        pending = ClientBoundary(
            id=f"bnd_{uuid4().hex}",
            client_id=company_id,
            provider="backup_net",
            external_tenant_id=customer_id,
            primary_domain=primary_domain,
            profile="endpoint-backup-read",
            application_id="uniview-public-api",
            status=BoundaryStatus.PENDING,
            consent_transaction_id=f"manual_backup_net_validation_{uuid4().hex}",
            created_at=now,
            consented_at=now,
        )
        repo.add(pending)
        validated = replace(
            pending,
            status=BoundaryStatus.VALIDATED,
            validated_at=now,
        )
        repo.replace(validated)
        return validated.id, True
    finally:
        store.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Discover and optionally persist one exact Autotask -> Backup.net "
            "customer boundary using customer-name and Endpoint Backup asset proof."
        )
    )
    parser.add_argument("--company-id", required=True)
    parser.add_argument("--customer-name", required=True)
    proof = parser.add_mutually_exclusive_group(required=True)
    proof.add_argument("--asset-name")
    proof.add_argument("--allow-empty-customer", action="store_true")
    parser.add_argument("--primary-domain", required=True)
    parser.add_argument("--openbao-url", default=DEFAULT_OPENBAO_URL)
    parser.add_argument("--role-id-path", type=Path, default=DEFAULT_ROLE_ID_PATH)
    parser.add_argument("--secret-id-path", type=Path, default=DEFAULT_SECRET_ID_PATH)
    parser.add_argument("--boundary-db", type=Path, default=DEFAULT_BOUNDARY_DB)
    parser.add_argument("--apply", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        company_id = str(int(args.company_id))
    except (TypeError, ValueError) as exc:
        raise SystemExit("DENIED: company-id must be a non-negative integer") from exc
    if int(company_id) < 0:
        raise SystemExit("DENIED: company-id must be a non-negative integer")

    context = ConnectorContext(
        correlation_id=f"corr_backup_boundary_{uuid4().hex}",
        principal_id="operator-boundary-provisioner",
        organization_id="aot",
        client_id=None,
        capability="backup_net.customer.boundary.discover",
        mode="observe",
    )
    resolver = OpenBaoSecretResolver(
        base_url=args.openbao_url,
        role_id_path=args.role_id_path,
        secret_id_path=args.secret_id_path,
    )
    secret_values = dict(resolver.resolve("backup_net.readonly", context))
    try:
        client = BackupNetClient(secret_values)
        customer_id, customer_name = _exact_customer(client, args.customer_name.strip())
        if args.asset_name:
            asset_proof = _safe_asset_summary(
                _exact_asset(
                    client,
                    customer_id=customer_id,
                    asset_name=args.asset_name.strip(),
                )
            )
        else:
            asset_proof = _prove_empty_asset_inventory(
                client,
                customer_id=customer_id,
            )
    finally:
        secret_values.clear()

    result: dict[str, Any] = {
        "status": "pass",
        "company_id": company_id,
        "customer_name": customer_name,
        "customer_id": customer_id,
        "asset_proof": asset_proof,
        "boundary_applied": False,
        "secret_values_printed": False,
    }

    if args.apply:
        boundary_id, created = _persist_boundary(
            db_path=args.boundary_db,
            company_id=company_id,
            customer_id=customer_id,
            primary_domain=args.primary_domain.strip().lower(),
        )
        result["boundary_id"] = boundary_id
        result["boundary_applied"] = True
        result["boundary_created"] = created

    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BoundaryDiscoveryError as exc:
        raise SystemExit(f"DENIED: {exc}") from exc
