#!/usr/bin/env python3
"""Owner-operated, exact-scope AOT group-admin credential/boundary bootstrap.

Configuration-only: never deploy code, restart services or POST to Graph.
Uses existing OpenBao provisioning and Kernel boundary repository contracts.
Requires a *local* authenticated sudo session plus OpenBao admin password.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import getpass
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import ssl
import subprocess
import sys
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "implementation"))
sys.path.insert(0, str(ROOT))

from connectors.core.http_transport import UrlLibJsonHttpTransport
from connectors.core.openbao_secrets import OpenBaoSecretResolver
from connectors.microsoft_graph.group_executor import MicrosoftGroupBoundaryValidator
from connectors.microsoft_graph.group_preflight import MicrosoftGroupTenantPreflight
from connectors.microsoft_graph.openbao_credentials import OpenBaoMicrosoftCredentialSource
from connectors.microsoft_graph.token import MsalCertificateTokenProvider, default_msal_application_factory
from kernel.client_boundaries import (
    BoundaryStatus, ClientBoundary, InMemoryClientBoundaryRepository,
    SQLiteClientBoundaryRepository, SQLiteClientBoundaryStore,
)
from tools.provider_secret_provision import (
    PROVIDERS, ProvisionError, admin_login, api_request, configure_read_approle,
    provider_policy_text, revoke_admin_token, write_provider_secret,
)

CLIENT = "client-aot-internal"
TENANT = "f7054323-d52b-4863-8c2f-1898f0b6077c"
DOMAIN = "teamaot.com"
PROFILES = {
    "read": {
        "provider": "microsoft_graph_group_read", "profile": "group-read",
        "application_id": "bb8f8e09-f851-4e0d-9c4a-95ff36d34b9a",
        "service_principal_id": "92191ddb-36dc-40f8-9b22-a070f68ff1e3",
        "thumbprint": "AB1EAD35B802F170BDFB7531637E923039B2F983",
    },
    "write": {
        "provider": "microsoft_graph_group_write", "profile": "group-write",
        "application_id": "6583ee4b-5aa7-4c82-a46e-472f03a4c467",
        "service_principal_id": "b15da46c-31f9-41a4-bb80-4d5eab615f81",
        "thumbprint": "C020401DAB7CF05BFEFE84024AA323913D903885",
    },
}
STAGING = Path("/home/al/.local/share/jason-credential-staging/m365-group-apps-20261112")
DB = Path("/var/lib/jason/authority/client-boundaries.sqlite3")
MANIFEST = ROOT / "config/microsoft_graph/pilots/aot-group-admin-20261112.json"
RECEIPT = Path("/var/lib/jason/authority/m365-group-identity-bootstrap-20261112.json")
EVENT_LOG = Path("/var/lib/jason/authority/m365-group-identity-bootstrap-20261112.events.jsonl")
OPENBAO = "http://127.0.0.1:8200"
PRODUCTION_RUNTIME_SHA = "d1b8c196dadd4b672ec8ba47075f27bb61c98d63"
APPROVAL = "owner-chat-2026-11-12-aot-group-read-and-write-secret-and-boundary-only"
RUNTIME_ACCESS_APPROVAL = "aot-m365-group-app-role-runtime-files-four-only"
RUNTIME_ACCESS_RECEIPT = Path(
    "/var/lib/jason/authority/m365-group-runtime-approle-access-20261112.json"
)


class BootstrapDenied(RuntimeError):
    pass


def source_sha() -> str:
    sha = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    changes = subprocess.run(
        ["git", "-C", str(ROOT), "status", "--porcelain"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    if changes:
        raise BootstrapDenied("SOURCE_WORKTREE_NOT_CLEAN")
    return sha


def _check_runtime_unchanged() -> None:
    """Read-only health and revision guard: refuse config writes during release drift."""
    try:
        runtime = subprocess.run(
            ["docker", "inspect", "jason-runtime",
             "--format", "{{.Image}}|{{.State.Running}}"],
            check=True, capture_output=True, text=True, timeout=10,
        ).stdout.strip()
        image_id, running = runtime.split("|", 1)
        revision = subprocess.run(
            ["docker", "image", "inspect", image_id, "--format",
             '{{index .Config.Labels "org.opencontainers.image.revision"}}'],
            check=True, capture_output=True, text=True, timeout=10,
        ).stdout.strip()
        mcp = subprocess.run(
            ["docker", "inspect", "jason-mcp-pilot",
             "--format", "{{.State.Running}}"],
            check=True, capture_output=True, text=True, timeout=10,
        ).stdout.strip()
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        raise BootstrapDenied("PRODUCTION_RUNTIME_HEALTH_VERIFICATION_UNAVAILABLE") from exc
    if revision != PRODUCTION_RUNTIME_SHA or running != "true" or mcp != "true":
        raise BootstrapDenied("PRODUCTION_RUNTIME_DRIFT_OR_UNHEALTHY")


def _stage_values(role: str) -> dict[str, str]:
    directory = STAGING
    if not directory.is_dir() or directory.stat().st_mode & 0o077:
        raise BootstrapDenied("CERTIFICATE_STAGING_DIRECTORY_NOT_PRIVATE")
    keyfile = directory / (role + ".key.pem")
    certfile = directory / (role + ".cert.pem")
    for file in (keyfile, certfile):
        if not file.is_file() or file.stat().st_mode & 0o077:
            raise BootstrapDenied("CERTIFICATE_STAGING_FILE_NOT_PRIVATE")
    key = keyfile.read_text(encoding="ascii").strip()
    cert = certfile.read_text(encoding="ascii").strip()
    if "PRIVATE KEY" not in key or "BEGIN CERTIFICATE" not in cert:
        raise BootstrapDenied("CERTIFICATE_STAGING_FORMAT_INVALID")
    thumb = hashlib.sha1(ssl.PEM_cert_to_DER_cert(cert)).hexdigest().upper()
    if thumb != PROFILES[role]["thumbprint"]:
        raise BootstrapDenied("CERTIFICATE_STAGING_THUMBPRINT_MISMATCH")
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import serialization
        from datetime import timedelta
        cert_obj = x509.load_pem_x509_certificate(cert.encode("ascii"))
        key_obj = serialization.load_pem_private_key(key.encode("ascii"), password=None)
        public_format = {
            "encoding": serialization.Encoding.DER,
            "format": serialization.PublicFormat.SubjectPublicKeyInfo,
        }
        if (key_obj.public_key().public_bytes(**public_format)
                != cert_obj.public_key().public_bytes(**public_format)):
            raise BootstrapDenied("CERTIFICATE_PRIVATE_KEY_PAIR_MISMATCH")
        now = datetime.now(timezone.utc)
        if cert_obj.not_valid_before_utc > now or cert_obj.not_valid_after_utc < now + timedelta(days=30):
            raise BootstrapDenied("CERTIFICATE_VALIDITY_NOT_ACCEPTABLE")
    except BootstrapDenied:
        raise
    except Exception as error:
        raise BootstrapDenied("CERTIFICATE_STAGING_CRYPTOGRAPHIC_CHECK_FAILED") from error
    return {
        "private_key_pem": key, "certificate_pem": cert,
        "certificate_thumbprint": thumb, "generation": "sha1:" + thumb,
    }


def _manifest() -> Mapping[str, Any]:
    item = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if (item.get("client_id") != CLIENT or item.get("tenant_id") != TENANT
            or item.get("primary_domain") != DOMAIN
            or item.get("status") != "aot_lab_live_readonly_preflight_verified_release_pending"):
        raise BootstrapDenied("PILOT_MANIFEST_UNEXPECTED")
    for role in PROFILES:
        spec = PROFILES[role]
        configured = item["required_group_" + role]
        if (configured["provider"] != spec["provider"]
                or configured["profile"] != spec["profile"]
                or configured["application_id"] != spec["application_id"]
                or configured["service_principal_id"] != spec["service_principal_id"]
                or configured["public_certificate_sha1"] != spec["thumbprint"]
                or configured["certificate_uploaded"] is not True
                or not configured["administrator_consent"].startswith("granted_and_read_back_")):
            raise BootstrapDenied("PILOT_MANIFEST_IDENTITY_CONSENT_MISMATCH")
    return item


def _check_existing_rows() -> None:
    if not DB.is_file():
        raise BootstrapDenied("EXISTING_PRODUCTION_BOUNDARY_DB_NOT_FOUND")
    con = sqlite3.connect("file:" + str(DB) + "?mode=ro", uri=True)
    try:
        rows = con.execute(
            "SELECT client_id, provider, external_tenant_id, primary_domain, profile,"
            " application_id, service_principal_id, status"
            " FROM client_boundaries WHERE provider IN (?, ?)",
            tuple(PROFILES[r]["provider"] for r in ("read", "write")),
        ).fetchall()
    finally:
        con.close()
    provider_counts = {}
    for row in rows:
        provider_counts[row[1]] = provider_counts.get(row[1], 0) + 1
    if any(count > 1 for count in provider_counts.values()):
        raise BootstrapDenied("MULTIPLE_GROUP_BOUNDARY_ROWS_REQUIRES_REVIEW")
    for (client, provider, tenant, domain, profile, app, principal, status) in rows:
        expected = next((p for p in PROFILES.values() if p["provider"] == provider), None)
        if (expected is None or client != CLIENT or tenant != TENANT or domain != DOMAIN
                or profile != expected["profile"] or app != expected["application_id"]
                or principal != expected["service_principal_id"]
                or status != BoundaryStatus.VALIDATED.value):
            raise BootstrapDenied("EXISTING_GROUP_BOUNDARY_REQUIRES_MANUAL_REVIEW")


def _existing_secret(address: str, token: str, role: str) -> Mapping[str, str] | None:
    spec = PROVIDERS["microsoft_graph_group_" + role]
    try:
        result = api_request(address, str(spec["secret_path"]), method="GET", token=token)
    except ProvisionError as exc:
        if "HTTP 404" in str(exc):
            return None
        raise
    fields = result.get("data", {}).get("data")
    if not isinstance(fields, dict):
        raise BootstrapDenied("OPENBAO_EXISTING_SECRET_INVALID")
    return fields


def _check_approle_preexisting(address: str, token: str, role: str) -> None:
    """Fail closed if the target named policy/AppRole is already nonstandard."""
    spec = PROVIDERS["microsoft_graph_group_" + role]
    directory = Path(spec["credential_dir"])
    if directory.exists():
        required = ("role-id", "secret-id", "credential-metadata.json")
        for item in required:
            p = directory / item
            if not p.is_file() or p.stat().st_mode & 0o077:
                raise BootstrapDenied("EXISTING_GROUP_APPROLE_CREDENTIAL_DIR_UNSAFE")
    for api_path, label in (
        ("sys/policies/acl/" + str(spec["policy_name"]), "policy"),
        ("auth/approle/role/" + str(spec["role_name"]), "role"),
    ):
        try:
            response = api_request(address, api_path, method="GET", token=token)
        except ProvisionError as exc:
            if "HTTP 404" in str(exc):
                continue
            raise
        data = response.get("data")
        if not isinstance(data, Mapping):
            raise BootstrapDenied("EXISTING_GROUP_APPROLE_CONFIGURATION_INVALID")
        if label == "policy":
            if str(data.get("policy", "")).strip() != provider_policy_text(
                "microsoft_graph_group_" + role).strip():
                raise BootstrapDenied("EXISTING_GROUP_APPROLE_POLICY_CONFLICT")
        elif (data.get("bind_secret_id") is not True
                or data.get("token_no_default_policy") is not True
                or data.get("token_policies") != [str(spec["policy_name"])]
                or data.get("token_type") != "service"):
            raise BootstrapDenied("EXISTING_GROUP_APPROLE_ROLE_CONFLICT")


def _audit_event(event: str, *, source: str, details: Mapping[str, str] | None = None) -> None:
    """Append bounded, non-secret operator evidence with root-only permissions."""
    allowed = {
        "OPENBAO_ADMIN_AUTHENTICATED", "OPENBAO_IDENTITY_STORED",
        "OPENBAO_CREDENTIALS_AND_GRAPH_READ_VALIDATED",
        "TENANT_BOUNDARIES_VALIDATED", "BOOTSTRAP_COMPLETE",
        "BOOTSTRAP_BLOCKED",
    }
    if event not in allowed:
        raise BootstrapDenied("AUDIT_EVENT_UNREGISTERED")
    record = {
        "event": event,
        "approval_reference": APPROVAL,
        "source_sha": source,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "operator": "sudo:al",
        "tenant_id": TENANT,
        "client_id": CLIENT,
    }
    if details:
        if set(details) - {"role", "stage", "failure_class"}:
            raise BootstrapDenied("AUDIT_DETAILS_NOT_ALLOWLISTED")
        record.update(details)
    data = (json.dumps(record, sort_keys=True) + "\n").encode("utf-8")
    fd = os.open(EVENT_LOG, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        info = os.stat(EVENT_LOG)
        if info.st_mode & 0o077 or (os.getuid() == 0 and info.st_uid != 0):
            raise BootstrapDenied("AUDIT_LOG_OWNER_OR_PERMISSIONS_NOT_PRIVATE")
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)


def _approle_tokens(repo, address: str):
    from pathlib import Path
    results = {}
    for role in ("read", "write"):
        spec = PROVIDERS["microsoft_graph_group_" + role]
        credential_dir = Path(spec["credential_dir"])
        resolver = OpenBaoSecretResolver(
            base_url=address,
            role_id_path=credential_dir / "role-id",
            secret_id_path=credential_dir / "secret-id",
        )
        credential = OpenBaoMicrosoftCredentialSource(secrets=resolver).resolve(
            "microsoft_graph.group_" + role)
        if credential.certificate_thumbprint.upper() != PROFILES[role]["thumbprint"]:
            raise BootstrapDenied("PRODUCTION_VAULT_CERTIFICATE_MISMATCH")
        tokens = MsalCertificateTokenProvider(
            boundaries=repo, credentials=OpenBaoMicrosoftCredentialSource(secrets=resolver),
            application_factory=default_msal_application_factory,
            logical_secret="microsoft_graph.group_" + role,
            provider_name=PROFILES[role]["provider"],
            profile_name=PROFILES[role]["profile"],
        )
        results[role] = tokens
    return results


def _ephemeral_boundaries():
    repo = InMemoryClientBoundaryRepository()
    now = datetime.now(timezone.utc)
    for role, spec in PROFILES.items():
        repo.add(ClientBoundary(
            id="aot-bootstrap-verified-" + role,
            client_id=CLIENT, provider=spec["provider"],
            external_tenant_id=TENANT, primary_domain=DOMAIN,
            profile=spec["profile"], application_id=spec["application_id"],
            status=BoundaryStatus.VALIDATED, consent_transaction_id=APPROVAL,
            created_at=now, consented_at=now, validated_at=now,
            service_principal_id=spec["service_principal_id"],
        ))
    return repo


def _persist_boundaries() -> dict[str, str]:
    # Production boundary DB is owned by the Jason runtime user, not root.
    # Perform the canonical repository write as the DB's existing owner so
    # SQLite lock/journal files retain the correct ownership and do not disrupt
    # active ticket processing. Root privileges are restored only after close.
    original_uid = os.geteuid()
    original_gid = os.getegid()
    owner_uid, owner_gid = DB.stat().st_uid, DB.stat().st_gid
    changed_identity = os.getuid() == 0 and original_uid == 0 and owner_uid != 0
    if changed_identity:
        os.setegid(owner_gid)
        os.seteuid(owner_uid)
    try:
        return _persist_boundaries_as_owner()
    finally:
        if changed_identity:
            os.seteuid(original_uid)
            os.setegid(original_gid)


def _persist_boundaries_as_owner() -> dict[str, str]:
    store = SQLiteClientBoundaryStore(DB)
    result: dict[str, str] = {}
    try:
        repo = SQLiteClientBoundaryRepository(store)
        now = datetime.now(timezone.utc)
        for role, spec in PROFILES.items():
            provider = spec["provider"]
            existing = repo.find_active_for_client(client_id=CLIENT, provider=provider)
            if existing is not None:
                if (existing.status != BoundaryStatus.VALIDATED
                        or existing.external_tenant_id != TENANT
                        or existing.application_id != spec["application_id"]
                        or existing.profile != spec["profile"]
                        or existing.service_principal_id != spec["service_principal_id"]):
                    raise BootstrapDenied("EXISTING_BOUNDARY_CONFLICT")
                result[role] = existing.id
                continue
            other = repo.find_active_for_external_tenant(provider=provider, external_tenant_id=TENANT)
            if other is not None:
                raise BootstrapDenied("BOUNDARY_TENANT_ALIAS_CONFLICT")
            item = ClientBoundary(
                id="bnd_aot_m365_groups_" + role + "_20261112",
                client_id=CLIENT, provider=provider, external_tenant_id=TENANT,
                primary_domain=DOMAIN, profile=spec["profile"],
                application_id=spec["application_id"], status=BoundaryStatus.VALIDATED,
                consent_transaction_id=APPROVAL,
                created_at=now, consented_at=now, validated_at=now,
                service_principal_id=spec["service_principal_id"],
            )
            repo.add(item)
            readback = repo.get(item.id)
            if readback != item:
                raise BootstrapDenied("PERSISTED_BOUNDARY_READBACK_FAILED")
            result[role] = item.id
        validator = MicrosoftGroupBoundaryValidator(repo)
        scope = validator.require_scope(client_id=CLIENT)
        if (scope.tenant_id != TENANT or scope.read_application_id != PROFILES["read"]["application_id"]
                or scope.write_application_id != PROFILES["write"]["application_id"]):
            raise BootstrapDenied("PERSISTED_BOUNDARY_PAIR_MISMATCH")
        return result
    finally:
        store.close()


def _verify_bootstrap_receipt() -> None:
    """Require exact prior owner-authenticated bootstrap evidence; no Graph action."""
    if RECEIPT.is_symlink() or not RECEIPT.is_file():
        raise BootstrapDenied("M365_RUNTIME_ACCESS_BOOTSTRAP_RECEIPT_MISSING")
    info = RECEIPT.stat()
    if info.st_uid != 0 or info.st_mode & 0o077:
        raise BootstrapDenied("M365_RUNTIME_ACCESS_BOOTSTRAP_RECEIPT_UNTRUSTED")
    try:
        doc = json.loads(RECEIPT.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise BootstrapDenied("M365_RUNTIME_ACCESS_BOOTSTRAP_RECEIPT_MALFORMED") from error
    if (doc.get("approval_reference") != APPROVAL
            or doc.get("client_id") != CLIENT
            or doc.get("tenant_id") != TENANT
            or doc.get("token_and_graph_read_preflight") != "pass"
            or doc.get("production_deployment") is not False
            or doc.get("graph_mutation") is not False
            or doc.get("app_ids") != {
                role: PROFILES[role]["application_id"] for role in PROFILES
            }):
        raise BootstrapDenied("M365_RUNTIME_ACCESS_BOOTSTRAP_RECEIPT_SCOPE_DRIFT")


def _runtime_access_sources() -> list[tuple[Path, int, int]]:
    """Return exact root-owned AppRole sources and original metadata; no content."""
    import stat
    result = []
    for role in ("read", "write"):
        directory = Path(PROVIDERS["microsoft_graph_group_" + role]["credential_dir"])
        if directory.is_symlink() or not directory.is_dir():
            raise BootstrapDenied("M365_RUNTIME_ACCESS_APPROLE_DIR_UNTRUSTED")
        meta = directory.stat()
        if meta.st_uid != 0 or meta.st_mode & 0o077:
            raise BootstrapDenied("M365_RUNTIME_ACCESS_APPROLE_DIR_UNTRUSTED")
        for name in ("role-id", "secret-id"):
            path = directory / name
            if path.is_symlink():
                raise BootstrapDenied("M365_RUNTIME_ACCESS_APPROLE_SYMLINK_DENIED")
            try:
                info = path.lstat()
            except OSError as error:
                raise BootstrapDenied("M365_RUNTIME_ACCESS_APPROLE_FILE_MISSING") from error
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0
                    or (info.st_gid, stat.S_IMODE(info.st_mode))
                        not in {(0, 0o600), (1000, 0o640)}
                    or info.st_size < 10 or info.st_size > 2048):
                raise BootstrapDenied("M365_RUNTIME_ACCESS_APPROLE_FILE_UNTRUSTED")
            result.append((path, info.st_gid, stat.S_IMODE(info.st_mode)))
    if len(result) != 4:
        raise BootstrapDenied("M365_RUNTIME_ACCESS_APPROLE_COUNT_INVALID")
    return result


def prepare_runtime_approle_access(*, apply: bool, approval_scope: str) -> None:
    """Owner-authenticated exact four-file permission projection. No key rotation."""
    import stat
    if os.geteuid() != 0 or os.environ.get("SUDO_USER") != "al":
        raise BootstrapDenied("M365_RUNTIME_ACCESS_REQUIRES_AUTHENTICATED_AL_SUDO")
    _verify_bootstrap_receipt()
    _check_runtime_unchanged()
    _check_existing_rows()
    items = _runtime_access_sources()
    if RUNTIME_ACCESS_RECEIPT.exists() or RUNTIME_ACCESS_RECEIPT.is_symlink():
        raise BootstrapDenied("M365_RUNTIME_ACCESS_ONE_SHOT_RECEIPT_EXISTS")
    print("RUNTIME_ACCESS_SCOPE=" + RUNTIME_ACCESS_APPROVAL)
    print("FILE_COUNT=4; EXCLUDES=GRAPH_POST,APP_CONSENT,OPENBAO_MUTATION,SERVICE_RESTART,PRODUCTION_UNFREEZE")
    if not apply:
        print("RUNTIME_ACCESS_PREFLIGHT=PASS; CHANGES=NONE")
        return
    if approval_scope != RUNTIME_ACCESS_APPROVAL:
        raise BootstrapDenied("M365_RUNTIME_ACCESS_EXACT_OWNER_APPROVAL_REQUIRED")
    if RUNTIME_ACCESS_RECEIPT.parent.is_symlink():
        raise BootstrapDenied("M365_RUNTIME_ACCESS_RECEIPT_PARENT_SYMLINK")
    # Open no-follow descriptors; validate all before changing any. Each descriptor
    # refers to the same inode across the bounded operation.
    opened = []
    changed = []
    try:
        for path, old_gid, old_mode in items:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0))
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0
                    or info.st_gid != old_gid
                    or stat.S_IMODE(info.st_mode) != old_mode):
                os.close(fd)
                raise BootstrapDenied("M365_RUNTIME_ACCESS_FILE_RACED")
            opened.append((fd, path, old_gid, old_mode))
        for fd, path, old_gid, old_mode in opened:
            if (old_gid, old_mode) != (1000, 0o640):
                # Record rollback BEFORE the first metadata mutation, so a
                # chgrp succeeding but a later chmod failing never leaves
                # behind partially widened access.
                changed.append((fd, old_gid, old_mode))
                os.fchown(fd, 0, 1000)
                os.fchmod(fd, 0o640)
        _check_runtime_unchanged()
        if any((os.fstat(fd).st_uid, os.fstat(fd).st_gid,
                stat.S_IMODE(os.fstat(fd).st_mode)) != (0, 1000, 0o640)
               for fd, _, _, _ in opened):
            raise BootstrapDenied("M365_RUNTIME_ACCESS_READBACK_FAILED")
        payload = {
            "schema_version": "1.0",
            "approved_scope": RUNTIME_ACCESS_APPROVAL,
            "operator_user": "al", "os_authentication": "sudo",
            "source_sha": source_sha(), "tenant_id": TENANT,
            "client_id": CLIENT, "file_count": 4,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "production_deployment": False, "service_restart": False,
            "graph_mutation": False, "production_unfreeze": False,
        }
        fd = os.open(RUNTIME_ACCESS_RECEIPT,
                     os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as output:
                json.dump(payload, output, indent=2, sort_keys=True)
                output.write("\n")
                output.flush()
                os.fsync(output.fileno())
        except BaseException:
            RUNTIME_ACCESS_RECEIPT.unlink(missing_ok=True)
            raise
    except BaseException:
        # No partial widening: restore all changed descriptors if audit fails.
        for fd, old_gid, old_mode in reversed(changed):
            os.fchmod(fd, old_mode)
            os.fchown(fd, 0, old_gid)
        raise
    finally:
        for fd, _, _, _ in opened:
            os.close(fd)
    print("M365_RUNTIME_ACCESS_PROJECTION=VERIFIED")
    print("READONLY_APPROLE_FILES=4; NO_CONTAINER_REPLACED=true")


def main() -> int:
    parser = argparse.ArgumentParser(description="AOT approved group credential + boundary operator bootstrap")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--prepare-runtime-access", action="store_true")
    parser.add_argument("--approval-scope", default="")
    parser.add_argument("--source-sha", required=True)
    args = parser.parse_args()
    if args.source_sha != source_sha():
        raise BootstrapDenied("SOURCE_SHA_NOT_EXACT")
    if args.prepare_runtime_access:
        prepare_runtime_approle_access(
            apply=args.apply,
            approval_scope=args.approval_scope,
        )
        return 0
    if args.approval_scope:
        raise BootstrapDenied("RUNTIME_ACCESS_SCOPE_NOT_VALID_FOR_ORIGINAL_BOOTSTRAP")
    _manifest()
    _check_runtime_unchanged()
    _check_existing_rows()
    # Precheck private staging material without emitting values.
    staged = {r: _stage_values(r) for r in PROFILES}
    print("SCOPE=AOT_M365_GROUP_READ_AND_WRITE_CONFIG_ONLY")
    print("SOURCE_SHA=" + args.source_sha)
    print("TARGET_TENANT=" + TENANT)
    print("APPROVAL_REFERENCE=" + APPROVAL)
    print("EXCLUDES=CODE_DEPLOYMENT,SERVICE_RESTART,GRAPH_POST,GROUP_MEMBERSHIP_MUTATION")
    if not args.apply:
        print("PREFLIGHT=PASS; CHANGES=NONE; USE --apply IN AUTHENTICATED OPERATOR SESSION")
        return 0
    if os.geteuid() != 0 or os.environ.get("SUDO_USER") != "al":
        raise BootstrapDenied("REQUIRES_AUTHENTICATED_LOCAL_AL_SUDO_OPERATOR")
    if RECEIPT.is_file():
        raise BootstrapDenied("EXISTING_AUDIT_RECEIPT_REQUIRES_REVIEW")
    password = getpass.getpass("OpenBao al-admin password (local terminal only): ")
    token = None
    status: dict[str, str] = {}
    try:
        token = admin_login(OPENBAO, "al-admin", password)
        password = ""
        _audit_event("OPENBAO_ADMIN_AUTHENTICATED", source=args.source_sha)
        # Abort all writes before mutation if any existing credential differs.
        existing = {r: _existing_secret(OPENBAO, token, r) for r in PROFILES}
        for role in PROFILES:
            _check_approle_preexisting(OPENBAO, token, role)
            if existing[role] is not None and existing[role] != staged[role]:
                raise BootstrapDenied("EXISTING_OPENBAO_CREDENTIAL_CONFLICT_" + role.upper())
        for role in ("read", "write"):
            provider = "microsoft_graph_group_" + role
            # The reviewed standard provisioning path writes the separate ACL/AppRole.
            state = configure_read_approle(address=OPENBAO, admin_token=token, provider=provider)
            status[role + "_approle"] = "created" if state["credentials_created"] else "verified_existing"
            if existing[role] is None:
                write_provider_secret(address=OPENBAO, admin_token=token, provider=provider,
                                      values=staged[role])
                status[role + "_kv"] = "created_cas0"
            else:
                status[role + "_kv"] = "verified_existing"
            _audit_event(
                "OPENBAO_IDENTITY_STORED", source=args.source_sha,
                details={"role": role, "stage": status[role + "_kv"]},
            )
    finally:
        password = ""
        if token:
            revoke_admin_token(OPENBAO, token)
    # Prove the actual production AppRole paths can access ONLY matching credentials
    # and Graph returns exact AOT app/tenant token, before durable boundary writes.
    repo = _ephemeral_boundaries()
    tokens = _approle_tokens(repo, OPENBAO)
    verification = MicrosoftGroupTenantPreflight(
        boundaries=MicrosoftGroupBoundaryValidator(repo),
        read_tokens=tokens["read"], write_tokens=tokens["write"],
        read_transport=UrlLibJsonHttpTransport(),
    ).inspect(client_id=CLIENT, correlation_id="aot-m365-production-config-preflight-20261112")
    if not (verification.read_identity_verified and verification.write_identity_verified
            and verification.group_read_verified and verification.user_read_verified
            and not verification.live_mutation_permitted):
        raise BootstrapDenied("LIVE_OPENBAO_BACKED_READ_PREFLIGHT_FAILED")
    _audit_event("OPENBAO_CREDENTIALS_AND_GRAPH_READ_VALIDATED", source=args.source_sha)
    _check_runtime_unchanged()
    boundary_ids = _persist_boundaries()
    _audit_event("TENANT_BOUNDARIES_VALIDATED", source=args.source_sha)
    _check_runtime_unchanged()
    receipt = {
        "approval_reference": APPROVAL,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "operator_user": "al",
        "os_authentication": "sudo",
        "openbao_admin_authentication": "verified_locally",
        "source_sha": args.source_sha,
        "client_id": CLIENT, "tenant_id": TENANT,
        "app_ids": {r: PROFILES[r]["application_id"] for r in PROFILES},
        "certificate_sha1": {r: PROFILES[r]["thumbprint"] for r in PROFILES},
        "boundary_ids": boundary_ids, "secret_and_approle_status": status,
        "token_and_graph_read_preflight": "pass",
        "production_deployment": False, "service_restart": False,
        "graph_mutation": False,
    }
    fd = os.open(RECEIPT, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(receipt, f, indent=2, sort_keys=True)
        f.write("\n")
    os.chmod(RECEIPT, 0o600)
    _audit_event("BOOTSTRAP_COMPLETE", source=args.source_sha)
    print("AOT_GROUP_CONFIGURATION_PROVISIONING=PASS")
    print("OPENBAO_GROUP_READ_WRITE_APPROLE=VERIFIED")
    print("OPENBAO_GROUP_READ_WRITE_SECRETS=VERIFIED")
    print("AOT_GROUP_READ_WRITE_BOUNDARIES=VALIDATED")
    print("GRAPH_SAFE_READ_PREFLIGHT=PASS")
    print("AUDIT_RECEIPT=" + str(RECEIPT))
    print("PRODUCTION_CODE_AND_GROUPS_UNCHANGED=TRUE")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (BootstrapDenied, ProvisionError) as exc:
        print("AOT_GROUP_CONFIGURATION_PROVISIONING=BLOCKED")
        print("BLOCKER_CODE=" + str(exc))
        raise SystemExit(2)
    except Exception as exc:
        print("AOT_GROUP_CONFIGURATION_PROVISIONING=FAILED")
        print("FAILURE_CLASS=" + type(exc).__name__)
        raise SystemExit(3)
