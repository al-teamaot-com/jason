from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from connectors.autotask.connector import AutotaskConnector
from connectors.core.contracts import ConnectorContext, ConnectorRequest
from connectors.core.http_transport import UrlLibJsonHttpTransport
from connectors.core.openbao_secrets import OpenBaoSecretResolver
from connectors.dnsfilter.connector import (
    DNSFILTER_PROFILE,
    DNSFILTER_PROVIDER,
    DnsFilterConnector,
)
from kernel.client_boundaries import (
    BoundaryStatus,
    ClientBoundary,
    SQLiteClientBoundaryRepository,
    SQLiteClientBoundaryStore,
)

DEFAULT_BOUNDARY_DB = Path("/var/lib/jason/authority/client-boundaries.sqlite3")
DEFAULT_ALIAS_FILE = Path("/app/config/dnsfilter-client-aliases.json")
DEFAULT_AUTOTASK_ROLE = Path("/run/jason-secrets/openbao/autotask/role_id")
DEFAULT_AUTOTASK_SECRET = Path("/run/jason-secrets/openbao/autotask/secret_id")
DEFAULT_DNSFILTER_ROLE = Path("/run/jason-secrets/openbao/dnsfilter/role_id")
DEFAULT_DNSFILTER_SECRET = Path("/run/jason-secrets/openbao/dnsfilter/secret_id")


class ReconciliationError(RuntimeError):
    pass


class _SilentAudit:
    def record(self, *args: Any, **kwargs: Any) -> None:
        return None


def normalize_name(value: object) -> str:
    text = str(value or "").casefold().replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def load_aliases(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    aliases = raw.get("aliases", {})
    if not isinstance(aliases, Mapping):
        raise ReconciliationError("DNSFilter alias file must contain an aliases object.")
    result: dict[str, str] = {}
    for name, company_id in aliases.items():
        try:
            normalized_id = str(int(company_id))
        except (TypeError, ValueError) as exc:
            raise ReconciliationError("DNSFilter alias company IDs must be integers.") from exc
        if int(normalized_id) < 0:
            raise ReconciliationError("DNSFilter alias company IDs must be non-negative.")
        result[normalize_name(name)] = normalized_id
    return result


def choose_company(
    site_name: str,
    companies: list[Mapping[str, Any]],
    aliases: Mapping[str, str],
) -> tuple[Mapping[str, Any] | None, str]:
    if normalize_name(site_name) == normalize_name("AOT Office"):
        return {"id": 0, "companyName": "Atlantic Office Machines", "isActive": True}, "aot-self"

    active = [item for item in companies if item.get("isActive") is not False]
    by_id = {str(item.get("id")): item for item in active}
    alias_id = aliases.get(normalize_name(site_name))
    if alias_id is not None:
        item = by_id.get(alias_id)
        return (item, "alias") if item is not None else (None, "alias-target-unavailable")

    exact = [
        item for item in active
        if normalize_name(item.get("companyName")) == normalize_name(site_name)
    ]
    if len(exact) == 1:
        return exact[0], "normalized-exact"
    if len(exact) > 1:
        return None, "ambiguous-exact"
    return None, "unmatched"


def _context(capability: str) -> ConnectorContext:
    return ConnectorContext(
        correlation_id=f"corr_dnsfilter_boundary_reconcile_{uuid4().hex}",
        principal_id="operator-boundary-reconciler",
        organization_id="aot",
        client_id=None,
        capability=capability,
        mode="observe",
    )


def _resolver(role: Path, secret: Path) -> OpenBaoSecretResolver:
    return OpenBaoSecretResolver(
        base_url=os.getenv("JASON_OPENBAO_URL", "http://openbao:8200"),
        role_id_path=role,
        secret_id_path=secret,
    )


def fetch_autotask_companies(
    *,
    role_id_path: Path,
    secret_id_path: Path,
) -> list[Mapping[str, Any]]:
    connector = AutotaskConnector(
        _resolver(role_id_path, secret_id_path),
        UrlLibJsonHttpTransport(),
        _SilentAudit(),
    )
    companies: list[Mapping[str, Any]] = []
    after_id = 0
    for _ in range(20):
        filters: list[dict[str, Any]] = [{"op": "exist", "field": "id"}]
        if after_id:
            filters.append({"op": "gt", "field": "id", "value": after_id})
        search = json.dumps(
            {"MaxRecords": 500, "filter": filters},
            separators=(",", ":"),
        )
        result = connector.execute(
            ConnectorRequest(
                context=_context("autotask.company.search"),
                arguments={"search": search},
            )
        ).data
        items = result.get("items", [])
        if not isinstance(items, list):
            raise ReconciliationError("Autotask company search returned an invalid shape.")
        page = [item for item in items if isinstance(item, Mapping)]
        companies.extend(page)
        if len(page) < 500:
            break
        observed_ids = [int(item["id"]) for item in page if str(item.get("id", "")).isdigit()]
        if not observed_ids:
            raise ReconciliationError("Autotask company pagination could not prove a continuation ID.")
        next_after = max(observed_ids)
        if next_after <= after_id:
            raise ReconciliationError("Autotask company pagination did not advance.")
        after_id = next_after
    else:
        raise ReconciliationError("Autotask company reconciliation exceeded the bounded page limit.")
    return companies


def fetch_dnsfilter_sites(
    *,
    role_id_path: Path,
    secret_id_path: Path,
    boundary_db: Path,
) -> tuple[str, list[Mapping[str, Any]]]:
    store = SQLiteClientBoundaryStore(boundary_db)
    try:
        repo = SQLiteClientBoundaryRepository(store)
        boundary = repo.find_active_for_client(client_id="0", provider=DNSFILTER_PROVIDER)
        if boundary is None or boundary.status is not BoundaryStatus.VALIDATED:
            raise ReconciliationError("A validated AOT DNSFilter master boundary is required.")
        organization_id = str(int(boundary.external_tenant_id))
        connector = DnsFilterConnector(
            _resolver(role_id_path, secret_id_path),
            UrlLibJsonHttpTransport(),
            _SilentAudit(),
            repo,
        )
        result = connector.execute(
            ConnectorRequest(
                context=_context("dnsfilter.network.search"),
                arguments={"company_id": 0, "page_number": 1, "page_size": 500},
            )
        ).data
    finally:
        store.close()
    items = result.get("data", [])
    if not isinstance(items, list):
        raise ReconciliationError("DNSFilter site search returned an invalid shape.")
    return organization_id, [item for item in items if isinstance(item, Mapping)]


def apply_scope(
    repo: SQLiteClientBoundaryRepository,
    *,
    company_id: str,
    organization_id: str,
    network_id: str,
    apply: bool,
) -> str:
    existing = repo.find_active_for_client(
        client_id=company_id,
        provider=DNSFILTER_PROVIDER,
    )
    if existing is not None:
        if existing.status is not BoundaryStatus.VALIDATED:
            raise ReconciliationError("Existing DNSFilter boundary is not validated.")
        if existing.external_tenant_id != organization_id:
            raise ReconciliationError("Existing DNSFilter boundary points to a different organization.")
        if existing.profile != DNSFILTER_PROFILE:
            raise ReconciliationError("Existing DNSFilter boundary uses an unapproved profile.")
        scopes = tuple(sorted(set(existing.external_scope_ids) | {network_id}, key=int))
        if scopes == existing.external_scope_ids:
            return "already-mapped"
        if apply:
            repo.replace(replace(existing, external_scope_ids=scopes))
        return "scope-added" if apply else "would-add-scope"

    if not apply:
        return "would-create"
    now = datetime.now(timezone.utc)
    pending = ClientBoundary(
        id=f"bnd_dnsfilter_{uuid4().hex}",
        client_id=company_id,
        provider=DNSFILTER_PROVIDER,
        external_tenant_id=organization_id,
        primary_domain=f"autotask-{company_id}.invalid",
        profile=DNSFILTER_PROFILE,
        application_id="dnsfilter-management-api",
        status=BoundaryStatus.PENDING,
        consent_transaction_id=f"dnsfilter_reconcile_{uuid4().hex}",
        created_at=now,
        consented_at=now,
        external_scope_ids=(network_id,),
    )
    repo.add(pending)
    repo.replace(
        replace(
            pending,
            status=BoundaryStatus.VALIDATED,
            validated_at=now,
        )
    )
    return "created"


def reconcile(args: argparse.Namespace) -> dict[str, Any]:
    aliases = load_aliases(args.alias_file)
    companies = fetch_autotask_companies(
        role_id_path=args.autotask_role_id_path,
        secret_id_path=args.autotask_secret_id_path,
    )
    organization_id, sites = fetch_dnsfilter_sites(
        role_id_path=args.dnsfilter_role_id_path,
        secret_id_path=args.dnsfilter_secret_id_path,
        boundary_db=args.boundary_db,
    )

    summary: dict[str, Any] = {
        "status": "pass",
        "apply": bool(args.apply),
        "organization_id": organization_id,
        "autotask_company_count": len(companies),
        "dnsfilter_site_count": len(sites),
        "mapped": [],
        "unresolved": [],
        "conflicts": [],
        "secret_values_printed": False,
    }
    store = SQLiteClientBoundaryStore(args.boundary_db)
    try:
        repo = SQLiteClientBoundaryRepository(store)
        for site in sites:
            network_id = str(int(site.get("id")))
            site_name = str((site.get("attributes") or {}).get("name") or "").strip()
            company, method = choose_company(site_name, companies, aliases)
            if company is None:
                summary["unresolved"].append(
                    {"site": site_name, "network_id": network_id, "reason": method}
                )
                continue
            company_id = str(int(company["id"]))
            try:
                action = apply_scope(
                    repo,
                    company_id=company_id,
                    organization_id=organization_id,
                    network_id=network_id,
                    apply=bool(args.apply),
                )
            except Exception as exc:
                summary["conflicts"].append(
                    {
                        "site": site_name,
                        "network_id": network_id,
                        "company_id": company_id,
                        "reason": str(exc),
                    }
                )
                continue
            summary["mapped"].append(
                {
                    "site": site_name,
                    "network_id": network_id,
                    "company_id": company_id,
                    "company_name": company.get("companyName"),
                    "match_method": method,
                    "action": action,
                }
            )
    finally:
        store.close()

    if summary["conflicts"]:
        summary["status"] = "conflict"
    elif summary["unresolved"]:
        summary["status"] = "partial"
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Reconcile Autotask companies to DNSFilter client network boundaries."
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--boundary-db", type=Path, default=DEFAULT_BOUNDARY_DB)
    parser.add_argument("--alias-file", type=Path, default=DEFAULT_ALIAS_FILE)
    parser.add_argument("--autotask-role-id-path", type=Path, default=DEFAULT_AUTOTASK_ROLE)
    parser.add_argument("--autotask-secret-id-path", type=Path, default=DEFAULT_AUTOTASK_SECRET)
    parser.add_argument("--dnsfilter-role-id-path", type=Path, default=DEFAULT_DNSFILTER_ROLE)
    parser.add_argument("--dnsfilter-secret-id-path", type=Path, default=DEFAULT_DNSFILTER_SECRET)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = reconcile(args)
    except Exception as exc:
        print(json.dumps({"status": "denied", "reason": str(exc), "secret_values_printed": False}))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] in {"pass", "partial"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
