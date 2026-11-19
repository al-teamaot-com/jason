#!/usr/bin/env python3
"""Preflight and establish Jason's dedicated SharePoint client boundary.

The read-only default verifies the OpenBao certificate identity with an app-only
Graph site enumeration and never writes the production boundary database. --apply
persists one validated boundary only after those checks pass. It does not deploy,
restart, grant Graph permissions, read document contents, or enable any site.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
import re
from pathlib import Path
import secrets
import sqlite3
import subprocess
import sys
import tempfile
from typing import Mapping
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "implementation"))

from connectors.core.http_transport import UrlLibJsonHttpTransport
from connectors.core.openbao_secrets import OpenBaoSecretResolver
from connectors.microsoft_graph.openbao_credentials import OpenBaoMicrosoftCredentialSource
from connectors.microsoft_graph.site_access_registry import SharePointSiteAccess
from connectors.microsoft_graph.site_discovery import SharePointSiteDiscovery
from connectors.microsoft_graph.tenant_tokens import GovernedTenantApplicationTokenProvider
from connectors.microsoft_graph.token import MsalCertificateTokenProvider, default_msal_application_factory
from kernel.client_boundaries import (
    BoundaryStatus, ClientBoundary, ClientBoundaryService,
    InMemoryClientBoundaryRepository, OnboardingStateService,
    SQLiteClientBoundaryRepository, SQLiteClientBoundaryStore,
    SQLiteOnboardingTransactionRepository,
)

PROVIDER = "microsoft_graph_sharepoint"
PROFILE = "sharepoint-read"
APPROVAL_SCOPE = "aot-sharepoint-client-boundary-create-only"
DEFAULT_DB = Path("/var/lib/jason/authority/client-boundaries.sqlite3")
AUDIT_DIR = Path("/var/lib/jason/authority")
AUDIT_FILE = AUDIT_DIR / "sharepoint-client-boundary-bootstrap.jsonl"


class BootstrapDenied(RuntimeError):
    pass


def token_claims(token: str) -> Mapping[str, object]:
    parts = token.split(".")
    if len(parts) != 3:
        raise BootstrapDenied("GRAPH_ACCESS_TOKEN_FORMAT_INVALID")
    try:
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        value = json.loads(base64.urlsafe_b64decode(payload).decode("utf-8"))
    except Exception as exc:
        raise BootstrapDenied("GRAPH_ACCESS_TOKEN_CLAIMS_INVALID") from exc
    if not isinstance(value, dict):
        raise BootstrapDenied("GRAPH_ACCESS_TOKEN_CLAIMS_INVALID")
    return value


def validate_claims(claims: Mapping[str, object], *, tenant: str, app: str,
                    service_principal: str) -> None:
    roles = claims.get("roles")
    if (str(claims.get("tid", "")).lower() != tenant.lower()
            or str(claims.get("appid", claims.get("azp", ""))).lower() != app.lower()
            or str(claims.get("oid", "")).lower() != service_principal.lower()
            or not isinstance(roles, list) or "Sites.Read.All" not in roles):
        raise BootstrapDenied("GRAPH_TOKEN_IDENTITY_OR_SITES_READ_ALL_MISMATCH")


def _settings():
    tenant = str(UUID(os.environ["JASON_SHAREPOINT_AOT_TENANT_ID"]))
    app = str(UUID(os.environ["JASON_SHAREPOINT_APPLICATION_ID"]))
    service_principal = str(UUID(os.environ["JASON_SHAREPOINT_SERVICE_PRINCIPAL_ID"]))
    domain = os.environ["JASON_SHAREPOINT_AOT_DOMAIN"].strip().casefold()
    client = os.environ.get("JASON_SHAREPOINT_CLIENT_ID", "client-aot-internal").strip()
    thumb = "".join(ch for ch in os.environ["JASON_SHAREPOINT_EXPECTED_CERT_THUMBPRINT"]
                    if ch.isalnum()).upper()
    hosts = frozenset(x.strip().casefold() for x in
                      os.environ["JASON_SHAREPOINT_AOT_HOSTNAMES"].split(",") if x.strip())
    if (not domain or not client or len(thumb) not in {40, 64}
            or not re.fullmatch(r"[A-F0-9]+", thumb) or not hosts):
        raise BootstrapDenied("SHAREPOINT_IDENTITY_CONFIGURATION_INVALID")
    if any(not h.endswith(".sharepoint.com") for h in hosts):
        raise BootstrapDenied("SHAREPOINT_HOST_ALLOWLIST_INVALID")
    credential_dir = Path(os.environ.get(
        "JASON_SHAREPOINT_APPROLE_HOST_DIR",
        "/opt/jason/bootstrap/secrets/openbao/microsoft-graph-sharepoint-read-approle",
    ))
    role_id = Path(os.environ.get("JASON_SHAREPOINT_OPENBAO_ROLE_ID_PATH",
                                  str(credential_dir / "role-id")))
    secret_id = Path(os.environ.get("JASON_SHAREPOINT_OPENBAO_SECRET_ID_PATH",
                                    str(credential_dir / "secret-id")))
    return tenant, app, service_principal, domain, client, thumb, hosts, role_id, secret_id


def _production_signature() -> tuple[str, ...]:
    state = []
    for name in ("jason-runtime", "jason-mcp-pilot"):
        result = subprocess.run(
            ["docker", "inspect", name, "--format", "{{.Image}}|{{.State.Running}}"],
            check=True, capture_output=True, text=True, timeout=15,
        ).stdout.strip()
        if not result.endswith("|true"):
            raise BootstrapDenied("PRODUCTION_RUNTIME_NOT_HEALTHY")
        state.append(name + "=" + result)
    return tuple(state)


def _probe(*, tenant: str, app: str, service_principal: str, domain: str,
           client: str, expected_thumb: str, hosts: frozenset[str],
           role_id: Path, secret_id: Path) -> int:
    boundaries = InMemoryClientBoundaryRepository()
    provisional = ClientBoundary(
        id="sharepoint-boundary-read-preflight",
        client_id=client, provider=PROVIDER, external_tenant_id=tenant,
        primary_domain=domain, profile=PROFILE, application_id=app,
        service_principal_id=service_principal, status=BoundaryStatus.VALIDATED,
        consent_transaction_id="sharepoint-read-preflight",
        created_at=datetime.now(timezone.utc), consented_at=datetime.now(timezone.utc),
        validated_at=datetime.now(timezone.utc),
    )
    boundaries.add(provisional)
    resolver = OpenBaoSecretResolver(
        base_url=os.environ.get("JASON_OPENBAO_URL", "http://127.0.0.1:8200"),
        role_id_path=role_id, secret_id_path=secret_id,
    )
    credentials = OpenBaoMicrosoftCredentialSource(secrets=resolver)
    credential = credentials.resolve("microsoft_graph.sharepoint_read")
    if credential.certificate_thumbprint.upper() != expected_thumb:
        raise BootstrapDenied("OPENBAO_CERTIFICATE_THUMBPRINT_MISMATCH")
    import ssl
    der = ssl.PEM_cert_to_DER_cert(credential.certificate_pem)
    digest = hashlib.sha1(der).hexdigest().upper()
    actual_thumb = (digest if len(expected_thumb) == 40
                    else hashlib.sha256(der).hexdigest().upper())
    if actual_thumb != expected_thumb:
        raise BootstrapDenied("OPENBAO_CERTIFICATE_FINGERPRINT_MISMATCH")
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import serialization
        cert = x509.load_pem_x509_certificate(credential.certificate_pem.encode("ascii"))
        key = serialization.load_pem_private_key(credential.private_key_pem.encode("ascii"), password=None)
        public = {"encoding": serialization.Encoding.DER,
                  "format": serialization.PublicFormat.SubjectPublicKeyInfo}
        if key.public_key().public_bytes(**public) != cert.public_key().public_bytes(**public):
            raise BootstrapDenied("OPENBAO_CERTIFICATE_KEY_PAIR_MISMATCH")
    except BootstrapDenied:
        raise
    except Exception as exc:
        raise BootstrapDenied("OPENBAO_CERTIFICATE_CRYPTOGRAPHIC_CHECK_FAILED") from exc

    token_provider = MsalCertificateTokenProvider(
        boundaries=boundaries, credentials=credentials,
        application_factory=default_msal_application_factory,
        logical_secret="microsoft_graph.sharepoint_read",
        provider_name=PROVIDER, profile_name=PROFILE,
    )
    token = token_provider.acquire_for_client(
        client_id=client, correlation_id="sharepoint-client-boundary-preflight",
    )
    validate_claims(token_claims(token.access_token), tenant=tenant, app=app,
                    service_principal=service_principal)
    tenant_tokens = GovernedTenantApplicationTokenProvider(
        boundaries=boundaries, tokens=token_provider,
        provider_name=PROVIDER, profile_name=PROFILE,
    )
    transport = UrlLibJsonHttpTransport()
    with tempfile.TemporaryDirectory(prefix="jason-sharepoint-boundary-") as tmp:
        registry = SharePointSiteAccess(str(Path(tmp) / "sites.sqlite3"), tenant_id=tenant)
        discovery = SharePointSiteDiscovery(
            tenant_id=tenant, tokens=tenant_tokens, transport=transport,
            registry=registry, allowed_sharepoint_hosts=hosts,
        )
        return discovery.run()


def _persist(*, db_path: Path, tenant: str, app: str, service_principal: str,
             domain: str, client: str, approval_reference: str) -> str:
    if os.geteuid() != 0 or os.environ.get("SUDO_USER") != "al":
        raise BootstrapDenied("BOUNDARY_WRITE_REQUIRES_AUTHENTICATED_AL_SUDO")
    if approval_reference != APPROVAL_SCOPE:
        raise BootstrapDenied("EXACT_SHAREPOINT_BOUNDARY_APPROVAL_SCOPE_REQUIRED")
    store = SQLiteClientBoundaryStore(db_path)
    boundaries = SQLiteClientBoundaryRepository(store)
    current = boundaries.find_active_for_client(client_id=client, provider=PROVIDER)
    if current:
        if (current.status is BoundaryStatus.VALIDATED
                and current.external_tenant_id == tenant
                and current.application_id == app
                and current.service_principal_id == service_principal
                and current.profile == PROFILE
                and current.primary_domain.casefold() == domain.casefold()):
            store.close()
            return "already_validated"
        store.close()
        raise BootstrapDenied("EXISTING_SHAREPOINT_BOUNDARY_CONFLICT")
    transactions = SQLiteOnboardingTransactionRepository(store)
    states = OnboardingStateService(signing_key=secrets.token_bytes(32), transactions=transactions)
    service = ClientBoundaryService(
        boundaries=boundaries, transactions=transactions, state_service=states,
    )
    now = datetime.now(timezone.utc)
    transaction, signed = service.begin_onboarding(
        client_id=client, provider=PROVIDER, primary_domain=domain,
        profile=PROFILE, application_id=app,
        correlation_id="sharepoint-boundary-" + secrets.token_hex(8),
    )
    pending = service.complete_onboarding(
        state=signed.value, external_tenant_id=tenant, consented_at=now,
        service_principal_id=service_principal,
    )
    validated = service.mark_validated(boundary_id=pending.id, validated_at=now)
    if (validated.status is not BoundaryStatus.VALIDATED
            or validated.consent_transaction_id != transaction.id):
        store.close()
        raise BootstrapDenied("SHAREPOINT_BOUNDARY_READBACK_FAILED")
    store.close()
    return "created_and_validated"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--boundary-db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--approval-reference", default="")
    args = parser.parse_args()
    actual = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
    dirty = subprocess.check_output(["git", "-C", str(ROOT), "status", "--porcelain"], text=True).strip()
    if args.expected_sha != actual or dirty:
        raise BootstrapDenied("SOURCE_SHA_MISMATCH_OR_DIRTY")
    tenant, app, sp, domain, client, thumb, hosts, role_id, secret_id = _settings()
    before = _production_signature() if args.apply else ()
    sites = _probe(tenant=tenant, app=app, service_principal=sp, domain=domain,
                   client=client, expected_thumb=thumb, hosts=hosts,
                   role_id=role_id, secret_id=secret_id)
    if not args.apply:
        print(json.dumps({"status":"preflight_pass","app_only_graph_read":True,
                          "sites_seen":sites,"boundary_changed":False,
                          "secret_values_printed":False}, sort_keys=True))
        return 0
    if not args.approval_reference:
        raise BootstrapDenied("EXACT_SHAREPOINT_BOUNDARY_APPROVAL_REFERENCE_REQUIRED")
    db_path = args.boundary_db
    if not db_path.is_file():
        raise BootstrapDenied("CLIENT_BOUNDARY_DATABASE_NOT_FOUND")
    mode = db_path.stat().st_mode & 0o777
    if mode & 0o077:
        raise BootstrapDenied("CLIENT_BOUNDARY_DATABASE_PERMISSIONS_UNSAFE")
    if AUDIT_DIR.is_symlink() or not AUDIT_DIR.is_dir():
        raise BootstrapDenied("AUDIT_DIRECTORY_UNTRUSTED")
    audit_dir_stat = AUDIT_DIR.stat()
    if audit_dir_stat.st_uid != 0 or audit_dir_stat.st_mode & 0o077:
        raise BootstrapDenied("AUDIT_DIRECTORY_PERMISSIONS_UNSAFE")
    if AUDIT_FILE.is_symlink():
        raise BootstrapDenied("AUDIT_FILE_SYMLINK_DENIED")
    event = {
        "at_utc": datetime.now(timezone.utc).isoformat(),
        "event": "sharepoint_client_boundary_validation",
        "approval_scope": APPROVAL_SCOPE,
        "approval_reference": args.approval_reference,
        "source_sha": actual, "sites_seen": sites,
        "production_code_deployed": False, "service_restarted": False,
    }
    boundary_result = _persist(
        db_path=db_path, tenant=tenant, app=app, service_principal=sp,
        domain=domain, client=client, approval_reference=args.approval_reference,
    )
    event["boundary_result"] = boundary_result
    fd = os.open(AUDIT_FILE, os.O_WRONLY | os.O_CREAT | os.O_APPEND
                 | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as stream:
        info = os.fstat(stream.fileno())
        if not __import__("stat").S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o077:
            raise BootstrapDenied("AUDIT_FILE_PERMISSIONS_UNSAFE")
        stream.write(json.dumps(event, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    if _production_signature() != before:
        raise BootstrapDenied("PRODUCTION_RUNTIME_CHANGED_DURING_BOUNDARY_SETUP")
    print(json.dumps({"status":"boundary_validated","sites_seen":sites,
                      "boundary_result":boundary_result,
                      "audit_recorded":True,"production_runtime_changed":False,
                      "secret_values_printed":False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BootstrapDenied as exc:
        print("SHAREPOINT_BOUNDARY_BOOTSTRAP=BLOCKED")
        print("BLOCKER_CODE=" + str(exc))
        raise SystemExit(2)
    except Exception as exc:
        print("SHAREPOINT_BOUNDARY_BOOTSTRAP=FAILED")
        print("FAILURE_CLASS=" + type(exc).__name__)
        raise SystemExit(3)
