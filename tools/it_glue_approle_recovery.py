#!/usr/bin/env python3
"""One-provider, local Owner-operated IT Glue read AppRole identity recovery.

Source-only. No MCP/remote invocation, no generic root worker, no unattended timer.
Use only after independently reviewed/authorized native release has installed
this byte-identical source in the root trust directory and closed successfully.
"""
from __future__ import annotations

import argparse
import getpass
import hashlib
import hmac
import importlib.util
import json
import os
import pwd
import re
import stat
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

# Pinned provider/role/secret scope. Do not make these caller controlled.
PROVIDER = "it_glue.readonly"
ROLE = "jason-itglue-read"
API_SECRET = "secret/data/connectors/it-glue/production/read-only"
SOURCE_DIR = Path("/opt/jason/bootstrap/secrets/openbao/itglue-read-approle")
ROOT_INSTALL = Path("/usr/local/lib/jason/it_glue_approle_recovery.py")
CURRENT = Path("/opt/jason/current")
RECORDS = Path("/var/lib/jason/openclaw/release-manager/records")
RECEIPT_DIR = Path("/var/lib/jason/openclaw/identity-lifecycle/it-glue-read")
SHA = re.compile(r"[0-9a-f]{40}\Z")
APPROVAL_REF = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{15,159}\Z")
OWNER_PROOF_VERIFIER = Path("/usr/local/lib/jason/owner_signed_release.py")
OWNER_PUBLIC_KEY = Path("/etc/jason-owner-release/verified-owner-public-key.json")
PROCESSED = Path("/var/lib/jason/openclaw/release-manager/owner-approval-requests-processed")
FREEZE = Path("/var/lib/jason/openclaw/release-manager/production-deployment-freeze")
CHALLENGE = "AUTHORIZE IT GLUE READ APPROLE ROTATION AND BOUNDED RUNTIME REFRESH"


class ItGlueIdentityError(RuntimeError):
    """Sanitized failure that carries no SecretID, RoleID, or provider API key."""


@dataclass(frozen=True, slots=True)
class SecretFile:
    path: Path
    value: str
    mode: int
    uid: int
    gid: int


def _protected(path: Path) -> SecretFile:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0
                or info.st_mode & 0o022):
            raise ItGlueIdentityError("protected identity permissions invalid")
        with os.fdopen(fd, "r", encoding="utf-8", closefd=False) as fh:
            value = fh.read().strip()
        if not value or len(value) > 2048 or any(ord(ch) < 33 for ch in value):
            raise ItGlueIdentityError("protected identity value invalid")
        return SecretFile(path, value, stat.S_IMODE(info.st_mode), info.st_uid, info.st_gid)
    finally:
        os.close(fd)


def _write_private(original: SecretFile, replacement: str) -> None:
    """Atomic and fsynced single-file replacement preserving existing owner/mode."""
    path = original.path
    directory = path.parent
    parent = os.stat(directory, follow_symlinks=False)
    current = os.lstat(path)
    if (not stat.S_ISDIR(parent.st_mode) or parent.st_uid != 0
            or parent.st_mode & 0o022
            or not stat.S_ISREG(current.st_mode) or current.st_uid != original.uid
            or current.st_gid != original.gid or stat.S_IMODE(current.st_mode) != original.mode):
        raise ItGlueIdentityError("protected source changed before replacement")
    if not isinstance(replacement, str) or not replacement.strip() or len(replacement) > 2048:
        raise ItGlueIdentityError("replacement SecretID invalid")
    observed = _protected(path)
    if not hmac.compare_digest(observed.value, original.value):
        raise ItGlueIdentityError("PROTECTED_SECRET_ID_CHANGED")
    fd, name = tempfile.mkstemp(prefix=".itglue-identity-", dir=directory)
    try:
        os.fchmod(fd, original.mode)
        os.fchown(fd, original.uid, original.gid)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(replacement)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(name, path)
        dir_fd = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    finally:
        if os.path.lexists(name):
            os.unlink(name)


def _verify_installed_source(expected_sha: str) -> Path:
    if os.geteuid() != 0:
        raise ItGlueIdentityError("LOCAL_ROOT_SESSION_REQUIRED")
    if ROOT_INSTALL.is_symlink() or Path(__file__).resolve() != ROOT_INSTALL:
        raise ItGlueIdentityError("ROOT_INSTALLED_REVIEWED_CODE_REQUIRED")
    for path in (ROOT_INSTALL, ROOT_INSTALL.parent, ROOT_INSTALL.parent.parent):
        item = os.lstat(path)
        if item.st_uid != 0 or item.st_mode & 0o022:
            raise ItGlueIdentityError("ROOT_TRUST_PARENT_UNSAFE")
    if not SHA.fullmatch(expected_sha):
        raise ItGlueIdentityError("EXACT_RELEASE_SHA_REQUIRED")
    if CURRENT.resolve(strict=True).name != expected_sha:
        raise ItGlueIdentityError("CURRENT_PRODUCTION_SOURCE_MISMATCH")
    reviewed = CURRENT / "tools" / "it_glue_approle_recovery.py"
    if hashlib.sha256(reviewed.read_bytes()).digest() != hashlib.sha256(ROOT_INSTALL.read_bytes()).digest():
        raise ItGlueIdentityError("ROOT_INSTALLED_SOURCE_SHA_MISMATCH")
    record = RECORDS / ("release-" + expected_sha[:16] + ".json")
    if record.is_symlink():
        raise ItGlueIdentityError("ROOT_RELEASE_RECORD_UNTRUSTED")
    info = record.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
        raise ItGlueIdentityError("ROOT_RELEASE_RECORD_PERMISSIONS_UNSAFE")
    data = json.loads(record.read_text(encoding="utf-8"))
    _verify_historical_signed_release(data, expected_sha)
    return record


def _load_pinned_owner_verifier():
    verifier_path = OWNER_PROOF_VERIFIER
    rootmeta = os.lstat(verifier_path)
    if (not stat.S_ISREG(rootmeta.st_mode) or rootmeta.st_uid != 0
            or rootmeta.st_mode & 0o022 or verifier_path.is_symlink()):
        raise ItGlueIdentityError("ROOT_OWNER_PROOF_VERIFIER_UNTRUSTED")
    spec = importlib.util.spec_from_file_location(
        "_jason_root_owner_release_proof", verifier_path)
    if spec is None or spec.loader is None:
        raise ItGlueIdentityError("ROOT_OWNER_PROOF_VERIFIER_UNAVAILABLE")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, module.read_pinned_root_owner_public_key(OWNER_PUBLIC_KEY)


def _verify_historical_signed_release(record: Mapping[str, Any],
                                      expected_sha: str) -> None:
    """Validate a consumed, signed *release*, not authority for a new action.

    The release Owner signature is valid only for 15 minutes at issuance. We
    independently verify it at its recorded acceptance time, and require the
    current root-pinned freeze. A separate local Owner challenge gates the
    later AppRole mutation. Mutable owner_approval text alone is never trusted.
    """
    if record.get("state") != "closed":
        raise ItGlueIdentityError("RELEASE_NOT_CLOSED")
    candidate = record.get("release_candidate") or {}
    approval = record.get("owner_approval") or {}
    review = record.get("manual_scope_review") or {}
    manifest = record.get("release_manifest") or {}
    rollback = record.get("rollback_sha")
    release_id = "release-" + expected_sha[:16]
    if (candidate.get("candidate_sha") != expected_sha
            or approval.get("approved") is not True
            or approval.get("candidate_sha") != expected_sha
            or review.get("candidate_sha") != expected_sha
            or review.get("baseline_sha") != rollback
            or manifest.get("candidate_sha") != expected_sha
            or manifest.get("rollback_sha") != rollback
            or "tools/it_glue_approle_recovery.py" not in
               (record.get("changed_files") or [])):
        raise ItGlueIdentityError("EXACT_SIGNED_OWNER_RELEASE_NOT_PROVEN")
    request_file = PROCESSED / (release_id + ".json")
    if request_file.is_symlink():
        raise ItGlueIdentityError("OWNER_PROOF_SOURCE_UNSAFE")
    reqinfo = request_file.stat()
    if (not stat.S_ISREG(reqinfo.st_mode)
            or stat.S_IMODE(reqinfo.st_mode) != 0o600
            or reqinfo.st_size > 16384):
        raise ItGlueIdentityError("OWNER_PROOF_SOURCE_UNSAFE")
    request = json.loads(request_file.read_text(encoding="utf-8"))
    proof = request.get("signed_owner_proof") or {}
    if (request.get("release_id") != release_id
            or request.get("candidate_sha") != expected_sha
            or request.get("organization_id") != "aot"):
        raise ItGlueIdentityError("OWNER_PROOF_RELEASE_MISMATCH")
    module, public = _load_pinned_owner_verifier()
    scoped = {
        "expected_candidate_sha": expected_sha,
        "expected_rollback_sha": rollback,
        "expected_release_id": release_id,
        "expected_scope_sha256": review.get("scope_sha256"),
        "expected_manifest_sha256": hashlib.sha256(json.dumps(
            manifest, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False).encode("utf-8")).hexdigest(),
        "expected_freeze_sha256": hashlib.sha256(FREEZE.read_bytes()).hexdigest(),
    }
    try:
        recorded = datetime.fromisoformat(approval.get("recorded_at", ""))
        signed = module.verify_exact_owner_release(
            proof, public_key=public, at=recorded, **scoped)
    except Exception:
        raise ItGlueIdentityError("OWNER_PROOF_SIGNATURE_OR_BINDING_INVALID") from None
    if (approval.get("source") !=
            "authenticated_signed_mcp_owner:" + signed["approval_id"]
            or request.get("source") !=
            "authenticated_jason_mcp_owner:" + signed["approval_id"]
            or request.get("approved_by") != signed["owner_principal"]):
        raise ItGlueIdentityError("OWNER_PROOF_IDENTITY_MISMATCH")


def _call(api: Callable[..., Mapping[str, Any]], path: str, *, method: str,
          token: str | None = None, payload: Mapping[str, Any] | None = None,
          allow_empty: bool = False) -> Mapping[str, Any]:
    try:
        result = api(path, method=method, token=token, payload=payload,
                     allow_empty=allow_empty)
        if not isinstance(result, Mapping):
            raise TypeError("invalid OpenBao result")
        return result
    except Exception:
        # Providers may return raw authorization errors; never emit them.
        raise ItGlueIdentityError("OPENBAO_" + method + "_FAILED") from None


def _api_readback(api: Callable[..., Mapping[str, Any]], role_id: str,
                  secret_id: str) -> bool:
    try:
        login = _call(api, "auth/approle/login", method="POST",
                      payload={"role_id": role_id, "secret_id": secret_id})
        token = str((login.get("auth") or {}).get("client_token") or "")
        if not token:
            return False
        try:
            result = _call(api, API_SECRET, method="GET", token=token)
            fields = ((result.get("data") or {}).get("data") or {})
            return isinstance(fields.get("api_key"), str) and bool(fields["api_key"].strip())
        finally:
            # Never print or retain issued token.
            try:
                _call(api, "auth/token/revoke-self", method="POST",
                      token=token, payload={}, allow_empty=True)
            except ItGlueIdentityError:
                pass
    except ItGlueIdentityError:
        return False


def rotate_once(api: Callable[..., Mapping[str, Any]], *, admin_token: str,
                role: SecretFile, old: SecretFile) -> Mapping[str, Any]:
    """Generate one new SecretID, validate login/KV, then stage at source.

    No direct provider API calls, no service restart, no implicit retries.
    The existing root boot-recovery timer performs staged binding reconciliation.
    """
    observed = _call(api, f"auth/approle/role/{ROLE}/role-id",
                     method="GET", token=admin_token)
    verified_role = str((observed.get("data") or {}).get("role_id") or "")
    if not verified_role or not hmac.compare_digest(verified_role, role.value):
        raise ItGlueIdentityError("IT_GLUE_ROLE_ID_MISMATCH")
    if _api_readback(api, role.value, old.value):
        return {
            "status": "already_valid", "provider": PROVIDER,
            "secret_id_rotated": False, "provider_api_key_changed": False,
            "runtime_refresh_needed": False,
        }
    created = _call(api, f"auth/approle/role/{ROLE}/secret-id", method="POST",
                    token=admin_token, payload={"ttl": "2160h", "num_uses": 0})
    new_sid = str((created.get("data") or {}).get("secret_id") or "")
    accessor = str((created.get("data") or {}).get("secret_id_accessor") or "")
    if not new_sid or not accessor:
        raise ItGlueIdentityError("REPLACEMENT_SECRET_ID_MISSING")
    if not _api_readback(api, role.value, new_sid):
        # Best-effort cancel of unused new identity; never touch existing one.
        try:
            _call(api, f"auth/approle/role/{ROLE}/secret-id-accessor/destroy",
                  method="POST", token=admin_token,
                  payload={"secret_id_accessor": accessor}, allow_empty=True)
        except ItGlueIdentityError:
            pass
        raise ItGlueIdentityError("NEW_APPROLE_LOGIN_OR_KV_DENIED")
    try:
        _write_private(old, new_sid)
    except Exception:
        # No protected-file change should leave an unused new SID active.
        try:
            _call(api, f"auth/approle/role/{ROLE}/secret-id-accessor/destroy",
                  method="POST", token=admin_token,
                  payload={"secret_id_accessor": accessor}, allow_empty=True)
        except ItGlueIdentityError:
            pass
        raise
    confirmed = _protected(old.path)
    if not hmac.compare_digest(confirmed.value, new_sid):
        raise ItGlueIdentityError("SOURCE_SECRET_ID_READBACK_MISMATCH")
    return {
        "status": "source_rotated", "provider": PROVIDER,
        "secret_id_rotated": True, "provider_api_key_changed": False,
        "openbao_login_and_kv_verified": True, "old_identity_revocation_deferred": True,
        "runtime_refresh_needed": True, "secret_values_exposed": False,
    }


def _receipt_file(revision: str) -> Path:
    return RECEIPT_DIR / ("recovery-" + revision[:16] + ".json")


def _claim(revision: str, approval_ref: str) -> Path:
    """Claim one attempt *before* creating the provider SecretID.

    If anything after the claim is ambiguous, an authenticated root operator
    must investigate/reconcile; no blind re-issue or duplicate request.
    """
    RECEIPT_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    parent = RECEIPT_DIR.stat()
    if parent.st_uid != 0 or parent.st_mode & 0o077:
        raise ItGlueIdentityError("RECEIPT_DIRECTORY_UNSAFE")
    final = _receipt_file(revision)
    payload = {
        "schema_version": "1.0", "provider": PROVIDER,
        "source_sha": revision, "approval_reference": approval_ref,
        "at": datetime.now(timezone.utc).isoformat(),
        "status": "claimed", "secret_values_exposed": False,
    }
    fd = os.open(final, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                 getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, sort_keys=True)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        directory_fd = os.open(RECEIPT_DIR, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        return final
    except Exception:
        # Any uncertain outcome is a durable claim, not permission to retry.
        raise


def _complete(claim: Path, evidence: Mapping[str, Any]) -> None:
    original = json.loads(claim.read_text(encoding="utf-8"))
    info = os.lstat(claim)
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or
            stat.S_IMODE(info.st_mode) != 0o600 or
            original.get("status") != "claimed" or
            original.get("provider") != PROVIDER):
        raise ItGlueIdentityError("RECOVERY_CLAIM_DRIFT")
    record = {
        **original, **evidence, "status": "pending_governed_provider_read",
        "root_stage_verified_at": datetime.now(timezone.utc).isoformat(),
    }
    fd, tmp = tempfile.mkstemp(prefix=".itglue-receipt-", dir=claim.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(record, fh, sort_keys=True)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, 0o600)
        os.chown(tmp, 0, 0)
        os.replace(tmp, claim)
        directory_fd = os.open(claim.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if os.path.lexists(tmp):
            os.unlink(tmp)



def _trusted_openbao_client():
    """Import only an exact source-matching root-pinned OpenBao client.

    Python -I deliberately does not consult PYTHONPATH or the script's
    writable checkout. A missing root-pinned helper fails closed.
    """
    helper = ROOT_INSTALL.parent / "provider_secret_provision.py"
    approved = CURRENT / "tools" / "provider_secret_provision.py"
    if helper.is_symlink() or not helper.is_file():
        raise ItGlueIdentityError("ROOT_PINNED_OPENBAO_CLIENT_MISSING")
    meta = helper.stat()
    if meta.st_uid != 0 or meta.st_mode & 0o022:
        raise ItGlueIdentityError("ROOT_PINNED_OPENBAO_CLIENT_UNSAFE")
    if not hmac.compare_digest(
        hashlib.sha256(helper.read_bytes()).digest(),
        hashlib.sha256(approved.read_bytes()).digest(),
    ):
        raise ItGlueIdentityError("ROOT_PINNED_OPENBAO_CLIENT_MISMATCH")
    spec = importlib.util.spec_from_file_location(
        "_jason_itglue_root_openbao_client", helper)
    if spec is None or spec.loader is None:
        raise ItGlueIdentityError("ROOT_PINNED_OPENBAO_CLIENT_INVALID")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Local Owner-governed IT Glue READ AppRole recovery")
    p.add_argument("--source-sha", required=True)
    p.add_argument("--check-only", action="store_true")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--approval-reference")
    args = p.parse_args(argv)
    try:
        if args.apply == args.check_only:
            raise ItGlueIdentityError("SPECIFY_EXACTLY_ONE_MODE")
        _verify_installed_source(args.source_sha)
        role = _protected(SOURCE_DIR / "role-id")
        old = _protected(SOURCE_DIR / "secret-id")
        if args.check_only:
            print(json.dumps({"status": "source_verified", "provider": PROVIDER,
                              "source_sha": args.source_sha,
                              "credential_values_exposed": False}, sort_keys=True))
            return 0
        if (os.getenv("SUDO_USER") != "al" or not sys.stdin.isatty()
                or not args.approval_reference
                or not APPROVAL_REF.fullmatch(args.approval_reference)):
            raise ItGlueIdentityError("LOCAL_OWNER_AND_EXACT_APPROVAL_REQUIRED")
        if _receipt_file(args.source_sha).exists():
            raise ItGlueIdentityError("ONE_SHOT_RECOVERY_ALREADY_USED")
        if input("Type exact local approval challenge: ").strip() != CHALLENGE:
            raise ItGlueIdentityError("LOCAL_EXACT_ACTION_APPROVAL_FAILED")
        openbao_client = _trusted_openbao_client()
        api_request = openbao_client.api_request
        admin_login = openbao_client.admin_login
        revoke_admin_token = openbao_client.revoke_admin_token
        addr = "http://127.0.0.1:8200"
        password = getpass.getpass("OpenBao administrator password (local only): ")
        try:
            token = admin_login(addr, "al-admin", password)
        finally:
            password = ""
        try:
            # Durable claim after administrator authentication, but before
            # ANY provider identity creation/rotation. Never auto retry.
            claim = _claim(args.source_sha, args.approval_reference)
            def request(path, **kwargs):
                return api_request(addr, path, **kwargs)
            result = rotate_once(request, admin_token=token, role=role, old=old)
            _complete(claim, result)
        finally:
            revoke_admin_token(addr, token)
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception as exc:
        # Do not propagate provider exceptions (may include sensitive payloads).
        label = str(exc) if isinstance(exc, ItGlueIdentityError) else (
            "INTERNAL_" + type(exc).__name__)
        print("DENIED: " + label, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
