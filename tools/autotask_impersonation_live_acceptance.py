#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
IMPLEMENTATION_ROOT = REPOSITORY_ROOT / "implementation"
RUNTIME_SOURCE = IMPLEMENTATION_ROOT / "runtime_service" / "src"
for source in (IMPLEMENTATION_ROOT, RUNTIME_SOURCE):
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))

from connectors.autotask.impersonating_connector import AutotaskImpersonatingConnector
from connectors.core.contracts import ConnectorContext, ConnectorRequest, ConnectorTransportError
from connectors.core.http_transport import UrlLibJsonHttpTransport
from connectors.core.openbao_secrets import OpenBaoSecretResolver
from orchestrator.teams_identity_binding_sqlite import SQLiteMicrosoftIdentityBindingStore


DEFAULT_OPENBAO_URL = "http://127.0.0.1:8200"
DEFAULT_BINDINGS_DB = Path("/var/lib/jason/openclaw/teams-identity-bindings.sqlite3")
DEFAULT_AUTOTASK_ROLE_ID_PATH = Path(
    "/run/jason-secrets/openbao/autotask/role_id"
)
DEFAULT_AUTOTASK_SECRET_ID_PATH = Path(
    "/run/jason-secrets/openbao/autotask/secret_id"
)
_IMPOSSIBLE_RESOURCE_ID = 9223372036854775807


class SanitizedAudit:
    """Record event names only; provider evidence and credentials are discarded."""

    def __init__(self) -> None:
        self.events: list[str] = []

    def record(self, event_type: str, context: ConnectorContext, details: Mapping[str, Any]) -> None:
        del context, details
        self.events.append(str(event_type))


class ObservingTransport:
    """Observe only safe transport facts while delegating the real request."""

    def __init__(self) -> None:
        self._delegate = UrlLibJsonHttpTransport()
        self.calls: list[dict[str, object]] = []

    def request(
        self,
        *,
        method: str,
        url: str,
        headers: Mapping[str, str],
        params: Mapping[str, Any] | None = None,
        json: Mapping[str, Any] | None = None,
        timeout_seconds: float = 30.0,
    ) -> Mapping[str, Any]:
        self.calls.append(
            {
                "method": method.upper().strip(),
                "resource_lookup": url.rstrip("/").endswith("/V1.0/Resources/query"),
                "ticket_query": url.rstrip("/").endswith("/V1.0/Tickets/query"),
                "company_query": url.rstrip("/").endswith("/V1.0/Companies/query"),
                "impersonation_header_present": "ImpersonationResourceId" in headers,
            }
        )
        return self._delegate.request(
            method=method,
            url=url,
            headers=headers,
            params=params,
            json=json,
            timeout_seconds=timeout_seconds,
        )


class InvalidImpersonationConnector(AutotaskImpersonatingConnector):
    """Negative control: send an impossible resource ID without exposing a real ID."""

    def _resolve_impersonation_resource_id(self, *, prepared, email: str) -> int:
        del prepared, email
        return _IMPOSSIBLE_RESOURCE_ID


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run bounded read-only provider-backed acceptance for Autotask resource "
            "impersonation without printing provider records, identities, IDs, or secrets."
        )
    )
    parser.add_argument("--principal-id", required=True)
    parser.add_argument("--correlation-id", required=True)
    parser.add_argument("--evidence-output", type=Path, required=True)
    parser.add_argument("--bindings-db", type=Path, default=DEFAULT_BINDINGS_DB)
    parser.add_argument(
        "--role-id-path",
        type=Path,
        default=DEFAULT_AUTOTASK_ROLE_ID_PATH,
    )
    parser.add_argument(
        "--secret-id-path",
        type=Path,
        default=DEFAULT_AUTOTASK_SECRET_ID_PATH,
    )
    parser.add_argument("--openbao-url", default=DEFAULT_OPENBAO_URL)
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--live-read", action="store_true")
    return parser


def _destination(path: Path) -> Path:
    target = path.expanduser().resolve()
    if target.exists():
        raise FileExistsError("Evidence output already exists; overwrite is denied.")
    try:
        target.relative_to(REPOSITORY_ROOT.resolve())
    except ValueError:
        return target
    raise ValueError("Acceptance evidence must be written outside the repository.")


def _validate(args: argparse.Namespace) -> Path:
    if args.check_only == args.live_read:
        raise PermissionError("Choose exactly one mode: --check-only or --live-read.")
    for label, value in {
        "principal-id": args.principal_id,
        "correlation-id": args.correlation_id,
        "openbao-url": args.openbao_url,
    }.items():
        if not str(value).strip():
            raise ValueError(f"{label} must be non-empty")
    return _destination(args.evidence_output)


def _query(capability: str, *, principal_id: str, correlation_id: str) -> ConnectorRequest:
    provider_capability = {
        "autotask.ticket.search": "Tickets",
        "autotask.company.search": "Companies",
    }[capability]
    del provider_capability
    search = json.dumps(
        {
            "MaxRecords": 1,
            "IncludeFields": ["id"],
            "filter": [{"op": "gt", "field": "id", "value": 0}],
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    return ConnectorRequest(
        context=ConnectorContext(
            correlation_id=correlation_id,
            principal_id=principal_id,
            organization_id="aot",
            client_id=None,
            capability=capability,
            mode="observe",
        ),
        arguments={"search": search},
    )


def _resolver(args: argparse.Namespace) -> OpenBaoSecretResolver:
    return OpenBaoSecretResolver(
        base_url=str(args.openbao_url).strip(),
        role_id_path=args.role_id_path.expanduser().resolve(),
        secret_id_path=args.secret_id_path.expanduser().resolve(),
    )


def _verify_binding(args: argparse.Namespace) -> SQLiteMicrosoftIdentityBindingStore:
    store = SQLiteMicrosoftIdentityBindingStore(args.bindings_db.expanduser().resolve())
    binding = store.find_active_by_jason_identity(
        jason_identity_id=str(args.principal_id).strip()
    )
    if binding is None or not str(binding.email_address or "").strip():
        store.close()
        raise PermissionError("TRUSTED_PRINCIPAL_BINDING_NOT_UNIQUE_OR_EMAIL_MISSING")
    return store


def _run_negative_control(
    args: argparse.Namespace,
    *,
    bindings,
) -> tuple[bool, int | None, int]:
    transport = ObservingTransport()
    connector = InvalidImpersonationConnector(
        secrets=_resolver(args),
        transport=transport,
        audit=SanitizedAudit(),
        bindings=bindings,
    )
    try:
        connector.execute(
            _query(
                "autotask.ticket.search",
                principal_id=str(args.principal_id).strip(),
                correlation_id=f"{str(args.correlation_id).strip()}-invalid-control",
            )
        )
    except ConnectorTransportError as exc:
        target_calls = [call for call in transport.calls if bool(call["ticket_query"])]
        provider_target_observed = (
            len(target_calls) == 1
            and bool(target_calls[0]["impersonation_header_present"])
        )
        provider_http_response_observed = exc.status_code is not None
        return (
            provider_target_observed and provider_http_response_observed,
            exc.status_code,
            len(target_calls),
        )
    return False, None, 0


def _run_valid_probe(args: argparse.Namespace, *, bindings, capability: str) -> tuple[bool, int, int]:
    transport = ObservingTransport()
    audit = SanitizedAudit()
    connector = AutotaskImpersonatingConnector(
        secrets=_resolver(args),
        transport=transport,
        audit=audit,
        bindings=bindings,
    )
    result = connector.execute(
        _query(
            capability,
            principal_id=str(args.principal_id).strip(),
            correlation_id=f"{str(args.correlation_id).strip()}-{capability.rsplit('.', 2)[-2]}",
        )
    )
    del result
    target_kind = "ticket_query" if capability == "autotask.ticket.search" else "company_query"
    target_calls = [call for call in transport.calls if bool(call[target_kind])]
    applied = (
        len(target_calls) == 1
        and bool(target_calls[0]["impersonation_header_present"])
    )
    resource_lookups = sum(1 for call in transport.calls if bool(call["resource_lookup"]))
    return applied, resource_lookups, len(audit.events)


def _write(destination: Path, payload: Mapping[str, Any]) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(json.dumps(dict(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    temporary.replace(destination)


def run(args: argparse.Namespace) -> Path | None:
    destination = _validate(args)
    if args.check_only:
        print(
            json.dumps(
                {
                    "provider": "autotask",
                    "probe_operations": ["ticket.search", "company.search"],
                    "negative_control": "impossible_impersonation_resource_id",
                    "provider_write": False,
                    "provider_payload_printed": False,
                    "credential_value_printed": False,
                    "hosted_model_used": False,
                    "network_contacted": False,
                    "status": "credential_safe_preflight",
                },
                indent=2,
                sort_keys=True,
            )
        )
        return None

    bindings = _verify_binding(args)
    try:
        (
            negative_rejected,
            negative_status,
            negative_target_request_count,
        ) = _run_negative_control(args, bindings=bindings)
        if not negative_rejected:
            raise PermissionError(
                "AUTOTASK_IMPERSONATION_NEGATIVE_CONTROL_NOT_PROVIDER_REJECTED"
            )

        ticket_applied, ticket_resource_lookups, ticket_audit_events = _run_valid_probe(
            args,
            bindings=bindings,
            capability="autotask.ticket.search",
        )
        company_applied, company_resource_lookups, company_audit_events = _run_valid_probe(
            args,
            bindings=bindings,
            capability="autotask.company.search",
        )
        if not ticket_applied or not company_applied:
            raise RuntimeError("AUTOTASK_IMPERSONATION_HEADER_NOT_APPLIED")

        observed_at = datetime.now(timezone.utc).isoformat()
        evidence = {
            "schema_version": "1.1",
            "provider": "autotask",
            "observed_at": observed_at,
            "provider_backed": True,
            "read_only": True,
            "provider_writes": False,
            "trusted_principal_binding_unique": True,
            "trusted_principal_email_present": True,
            "principal_identity_printed": False,
            "principal_identity_persisted": False,
            "autotask_resource_id_printed": False,
            "autotask_resource_id_persisted": False,
            "negative_impersonation_control_rejected": True,
            "negative_control_provider_http_response_observed": True,
            "negative_control_target_request_observed": negative_target_request_count == 1,
            "negative_control_target_request_count": negative_target_request_count,
            "negative_control_http_status": negative_status,
            "ticket_search_impersonation_header_applied": ticket_applied,
            "company_search_impersonation_header_applied": company_applied,
            "ticket_resource_lookup_count": ticket_resource_lookups,
            "company_resource_lookup_count": company_resource_lookups,
            "ticket_audit_event_count": ticket_audit_events,
            "company_audit_event_count": company_audit_events,
            "provider_payload_printed": False,
            "provider_payload_persisted": False,
            "provider_credentials_printed": False,
            "provider_credentials_persisted": False,
            "hosted_model_used": False,
            "durable_activation_mutated": False,
            "authority_mutated": False,
            "status": "pass",
        }
        _write(destination, evidence)
        return destination
    finally:
        bindings.close()


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        output = run(args)
    except Exception as exc:
        parser.exit(1, f"DENIED: {type(exc).__name__}: {exc}\n")
    if args.live_read:
        print("PASS: bounded Autotask requester-impersonation acceptance completed.")
        print(f"Evidence: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
