#!/usr/bin/env python3
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any, Iterator, Mapping, Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
IMPLEMENTATION_ROOT = REPOSITORY_ROOT / "implementation"
RUNTIME_SOURCE = IMPLEMENTATION_ROOT / "runtime_service" / "src"
for source in (IMPLEMENTATION_ROOT, RUNTIME_SOURCE):
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))

from connectors.autotask.impersonating_connector import AUTOTASK_REQUESTER_AUTH_MODE_ENV
from connectors.autotask.mutation_connector import AutotaskMutationConnector
from connectors.core.contracts import ConnectorContext, ConnectorRequest
from connectors.core.http_transport import UrlLibJsonHttpTransport
from connectors.core.openbao_secrets import OpenBaoSecretResolver
from orchestrator.teams_identity_binding_sqlite import (
    DirectoryEnrichedMicrosoftIdentityBindingResolver,
    SQLiteMicrosoftIdentityBindingStore,
)
from jason_runtime.microsoft_directory import build_microsoft_directory_runtime


DEFAULT_OPENBAO_URL = "http://127.0.0.1:8200"
DEFAULT_BINDINGS_DB = Path("/var/lib/jason/openclaw/teams-identity-bindings.sqlite3")
DEFAULT_MICROSOFT_BOUNDARY_DB = Path("/var/lib/jason/authority/client-boundaries.sqlite3")
DEFAULT_MICROSOFT_ROLE_ID_PATH = Path(
    "/run/jason-secrets/openbao/microsoft-graph/role_id"
)
DEFAULT_MICROSOFT_SECRET_ID_PATH = Path(
    "/run/jason-secrets/openbao/microsoft-graph/secret_id"
)
DEFAULT_AUTOTASK_WRITE_ROLE_ID_PATH = Path(
    "/opt/jason/bootstrap/secrets/openbao/autotask-write-approle/role-id"
)
DEFAULT_AUTOTASK_WRITE_SECRET_ID_PATH = Path(
    "/opt/jason/bootstrap/secrets/openbao/autotask-write-approle/secret-id"
)

_APPROVED_OPERATIONS = (
    "autotask.ticket.create",
    "autotask.ticket.update",
    "autotask.ticket.note.create",
    "autotask.ticket.note.update",
)

_EXPECTED_METHOD = {
    "autotask.ticket.create": "POST",
    "autotask.ticket.update": "PATCH",
    "autotask.ticket.note.create": "POST",
    "autotask.ticket.note.update": "PATCH",
}


class SanitizedAudit:
    """Record event names only; credentials and provider payloads are discarded."""

    def __init__(self) -> None:
        self.events: list[str] = []

    def record(self, event_type: str, context: ConnectorContext, details: Mapping[str, Any]) -> None:
        del context, details
        self.events.append(str(event_type))


class ReadOnlyReadinessTransport:
    """Hard transport guard: readiness may issue GET requests only.

    The mutation connector is used only to compile and preflight the exact future
    mutation. The returned POST/PATCH request is never dispatched. Even if future
    refactoring accidentally attempted to dispatch it through this transport, the
    transport fails closed before provider I/O.
    """

    def __init__(self, delegate=None) -> None:
        self._delegate = delegate or UrlLibJsonHttpTransport()
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
        normalized_method = str(method).strip().upper()
        if normalized_method != "GET":
            raise PermissionError("AUTOTASK_READINESS_PROVIDER_WRITE_BLOCKED")

        entity_information = url.rstrip("/").endswith("/entityInformation")
        self.calls.append(
            {
                "method": normalized_method,
                "zone_information": url.rstrip("/").endswith("/v1.0/zoneInformation"),
                "resource_lookup": url.rstrip("/").endswith("/V1.0/Resources/query"),
                "entity_information": entity_information,
                "impersonation_header_present": "ImpersonationResourceId" in headers,
                "request_body_present": json is not None,
            }
        )
        return self._delegate.request(
            method=normalized_method,
            url=url,
            headers=headers,
            params=params,
            json=None,
            timeout_seconds=timeout_seconds,
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run a credential-safe, provider-backed, read-only readiness probe for "
            "the governed Autotask Ticket/TicketNote mutation foundation."
        )
    )
    parser.add_argument("--principal-id", required=True)
    parser.add_argument("--correlation-id", required=True)
    parser.add_argument("--evidence-output", type=Path, required=True)
    parser.add_argument("--bindings-db", type=Path, default=DEFAULT_BINDINGS_DB)
    parser.add_argument(
        "--microsoft-boundary-db",
        type=Path,
        default=DEFAULT_MICROSOFT_BOUNDARY_DB,
    )
    parser.add_argument(
        "--microsoft-role-id-path",
        type=Path,
        default=DEFAULT_MICROSOFT_ROLE_ID_PATH,
    )
    parser.add_argument(
        "--microsoft-secret-id-path",
        type=Path,
        default=DEFAULT_MICROSOFT_SECRET_ID_PATH,
    )
    parser.add_argument("--expected-principal-email")
    parser.add_argument(
        "--role-id-path",
        type=Path,
        default=DEFAULT_AUTOTASK_WRITE_ROLE_ID_PATH,
    )
    parser.add_argument(
        "--secret-id-path",
        type=Path,
        default=DEFAULT_AUTOTASK_WRITE_SECRET_ID_PATH,
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
    expected_email = str(args.expected_principal_email or "").strip()
    if expected_email and (
        "@" not in expected_email
        or expected_email.startswith("@")
        or expected_email.endswith("@")
    ):
        raise ValueError("expected-principal-email must be a valid address when supplied")
    return _destination(args.evidence_output)


def _synthetic_payload(operation: str) -> Mapping[str, Any]:
    # These values are compilation-only and are never sent to Autotask. They are
    # intentionally not real record identifiers.
    if operation == "autotask.ticket.create":
        return {"companyID": 1, "title": "JASON_READINESS_NOT_SENT"}
    if operation == "autotask.ticket.update":
        return {"id": 1}
    if operation == "autotask.ticket.note.create":
        return {"ticketID": 1, "description": "JASON_READINESS_NOT_SENT"}
    if operation == "autotask.ticket.note.update":
        return {"id": 1}
    raise ValueError("AUTOTASK_READINESS_OPERATION_NOT_APPROVED")


def _request(
    operation: str,
    *,
    principal_id: str,
    correlation_id: str,
) -> ConnectorRequest:
    return ConnectorRequest(
        context=ConnectorContext(
            correlation_id=correlation_id,
            principal_id=principal_id,
            organization_id="aot",
            client_id=None,
            capability=operation,
            mode="execute",
        ),
        arguments={"payload": _synthetic_payload(operation)},
    )


def _resolver(args: argparse.Namespace) -> OpenBaoSecretResolver:
    return OpenBaoSecretResolver(
        base_url=str(args.openbao_url).strip(),
        role_id_path=args.role_id_path.expanduser().resolve(),
        secret_id_path=args.secret_id_path.expanduser().resolve(),
    )


def _verify_binding(
    args: argparse.Namespace,
) -> tuple[SQLiteMicrosoftIdentityBindingStore, DirectoryEnrichedMicrosoftIdentityBindingResolver]:
    store = SQLiteMicrosoftIdentityBindingStore(args.bindings_db.expanduser().resolve())
    base_binding = store.find_active_by_jason_identity(
        jason_identity_id=str(args.principal_id).strip()
    )
    if base_binding is None:
        store.close()
        raise PermissionError("TRUSTED_PRINCIPAL_BINDING_NOT_UNIQUE")

    directory_runtime = build_microsoft_directory_runtime(
        boundary_db=args.microsoft_boundary_db.expanduser().resolve(),
        openbao_url=str(args.openbao_url).strip(),
        role_id_path=args.microsoft_role_id_path.expanduser().resolve(),
        secret_id_path=args.microsoft_secret_id_path.expanduser().resolve(),
        transport=UrlLibJsonHttpTransport(),
    )
    enriched = DirectoryEnrichedMicrosoftIdentityBindingResolver(
        bindings=store,
        directory=directory_runtime.directory,
    )
    resolved = enriched.find_active_by_jason_identity(
        jason_identity_id=str(args.principal_id).strip()
    )
    if resolved is None or not str(resolved.email_address or "").strip():
        store.close()
        raise PermissionError("TRUSTED_PRINCIPAL_DIRECTORY_EMAIL_UNAVAILABLE")

    expected_email = str(args.expected_principal_email or "").strip().casefold()
    if expected_email and str(resolved.email_address).strip().casefold() != expected_email:
        store.close()
        raise PermissionError("TRUSTED_PRINCIPAL_DIRECTORY_EMAIL_MISMATCH")

    return store, enriched


@contextmanager
def _impersonated_mode() -> Iterator[None]:
    previous = os.environ.get(AUTOTASK_REQUESTER_AUTH_MODE_ENV)
    os.environ[AUTOTASK_REQUESTER_AUTH_MODE_ENV] = "impersonated"
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(AUTOTASK_REQUESTER_AUTH_MODE_ENV, None)
        else:
            os.environ[AUTOTASK_REQUESTER_AUTH_MODE_ENV] = previous


def _probe_operation(
    args: argparse.Namespace,
    *,
    bindings,
    operation: str,
) -> Mapping[str, Any]:
    if operation not in _APPROVED_OPERATIONS:
        raise ValueError("AUTOTASK_READINESS_OPERATION_NOT_APPROVED")

    transport = ReadOnlyReadinessTransport()
    audit = SanitizedAudit()
    resolver = _resolver(args)
    connector = AutotaskMutationConnector(
        secrets=resolver,
        transport=transport,
        audit=audit,
        bindings=bindings,
    )
    request = _request(
        operation,
        principal_id=str(args.principal_id).strip(),
        correlation_id=f"{str(args.correlation_id).strip()}-{operation.rsplit('.', 1)[-1]}",
    )

    credentials = dict(resolver.resolve("autotask.write", request.context))
    try:
        with _impersonated_mode():
            prepared = connector.prepare_request(request, credentials)
    finally:
        credentials.clear()

    expected_method = _EXPECTED_METHOD[operation]
    if prepared.method != expected_method:
        raise RuntimeError("AUTOTASK_READINESS_COMPILED_METHOD_UNEXPECTED")
    if any(str(call["method"]) != "GET" for call in transport.calls):
        raise RuntimeError("AUTOTASK_READINESS_NON_READ_PROVIDER_CALL_OBSERVED")

    entity_calls = [call for call in transport.calls if bool(call["entity_information"])]
    resource_calls = [call for call in transport.calls if bool(call["resource_lookup"])]
    if len(entity_calls) != 1 or not bool(entity_calls[0]["impersonation_header_present"]):
        raise RuntimeError("AUTOTASK_READINESS_IMPERSONATED_PREFLIGHT_NOT_PROVEN")
    if len(resource_calls) != 1:
        raise RuntimeError("AUTOTASK_READINESS_REQUESTER_LOOKUP_NOT_UNIQUE_PATH")

    return {
        "operation": operation,
        "compiled_mutation_method": expected_method,
        "compiled_mutation_dispatched": False,
        "provider_get_count": len(transport.calls),
        "requester_resource_lookup_count": len(resource_calls),
        "impersonated_entity_information_count": len(entity_calls),
        "impersonation_header_applied": True,
        "preflight_permitted": True,
    }


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
                    "credential_logical_name": "autotask.write",
                    "probe_operations": list(_APPROVED_OPERATIONS),
                    "provider_calls_allowed": ["GET"],
                    "compiled_mutation_dispatched": False,
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

    if not args.role_id_path.expanduser().resolve().is_file() or not args.secret_id_path.expanduser().resolve().is_file():
        raise PermissionError("AUTOTASK_WRITE_APPROle_ARTIFACTS_UNAVAILABLE")

    store, bindings = _verify_binding(args)
    try:
        results = [
            _probe_operation(
                args,
                bindings=bindings,
                operation=operation,
            )
            for operation in _APPROVED_OPERATIONS
        ]

        observed_at = datetime.now(timezone.utc).isoformat()
        evidence = {
            "schema_version": "1.0",
            "provider": "autotask",
            "observed_at": observed_at,
            "provider_backed": True,
            "read_only_probe": True,
            "provider_writes": False,
            "credential_logical_name": "autotask.write",
            "credential_values_printed": False,
            "credential_values_persisted": False,
            "trusted_principal_binding_unique": True,
            "trusted_principal_email_present": True,
            "trusted_principal_email_source": "microsoft_graph",
            "principal_identity_printed": False,
            "principal_identity_persisted": False,
            "autotask_resource_id_printed": False,
            "autotask_resource_id_persisted": False,
            "operations": results,
            "all_four_preflights_permitted": all(
                bool(result["preflight_permitted"]) for result in results
            ),
            "compiled_mutations_dispatched": False,
            "provider_payload_printed": False,
            "provider_payload_persisted": False,
            "hosted_model_used": False,
            "durable_activation_mutated": False,
            "authority_mutated": False,
            "status": "pass",
        }
        _write(destination, evidence)
        return destination
    finally:
        store.close()


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        output = run(args)
    except Exception as exc:
        parser.exit(1, f"DENIED: {type(exc).__name__}: {exc}\n")
    if args.live_read:
        print("PASS: read-only Autotask mutation readiness completed.")
        print(f"Evidence: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
