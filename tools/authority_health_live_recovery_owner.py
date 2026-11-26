#!/usr/bin/env python3
"""Independent UID-1000 Entra Owner authentication and one-use release signature.

Never executes root mutations, creates a waiver or clears the production breaker.
The immutable root runner verifies this proof independently before it can act.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys
import time
import uuid

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ACTION = "owner-authority-health-relocated-audit-oneuse-20261117"
CONFIRM = "APPROVE-EXACT-RELOCATED-AUDIT-ROOT-HEALTH-REPAIR"
OWNER_LIB = Path("/usr/local/lib/jason/owner_signed_release.py")
OWNER_SHA = "f50eea90102d9a1de82b3753ec8d0cd225280d385ac7a658ae2c2a303934a0e3"
OAUTH_LIB = Path("/usr/local/lib/jason/owner_signer_recovery.py")
OAUTH_SHA = "24d3632a4b0aa60851a1c82ccb15539eb823dd26afa5a1a2cc8c7afc54d72153"
PRIVATE = Path("/var/lib/jason/runtime-secrets/owner-release/private_key")
PUBLIC = Path("/etc/jason-owner-release/verified-owner-public-key.json")
FREEZE = Path("/var/lib/jason/openclaw/release-manager/production-deployment-freeze")
LKG = "d1b8c196dadd4b672ec8ba47075f27bb61c98d63"


class Denied(PermissionError):
    pass


def need(ok: bool, message: str) -> None:
    if not ok:
        raise Denied(message)


def digest(raw: bytes) -> str:
    from hashlib import sha256
    return sha256(raw).hexdigest()


def canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode()


def trusted(path: Path, expected: str, name: str):
    info = path.lstat()
    need(not path.is_symlink() and stat.S_ISREG(info.st_mode)
         and info.st_uid == 0 and info.st_nlink == 1
         and info.st_mode & 0o022 == 0
         and digest(path.read_bytes()) == expected, "PINNED_OWNER_LIBRARY_DRIFT")
    spec = importlib.util.spec_from_file_location(name, path)
    need(spec and spec.loader, "PINNED_LIBRARY_UNAVAILABLE")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def preflight(directory: Path):
    need(os.geteuid() == 1000, "UID1000_OWNER_REQUIRED")
    need(directory.parent == Path("/home/al/.local/share/jason")
         and directory.name.startswith("authority-health-live-root-")
         and directory.is_dir() and not directory.is_symlink(),
         "OWNER_REVIEW_DIRECTORY_UNTRUSTED")
    d = directory.lstat()
    need(d.st_uid == 1000 and stat.S_IMODE(d.st_mode) == 0o700,
         "OWNER_REVIEW_DIRECTORY_PERMISSIONS")
    manifest_path = directory / "manifest.json"
    info = manifest_path.lstat()
    need(info.st_uid == 1000 and stat.S_IMODE(info.st_mode) == 0o400
         and not manifest_path.is_symlink(), "OWNER_PLAN_UNTRUSTED")
    manifest = json.loads(manifest_path.read_bytes())
    need(manifest["schema_version"] == "1.0"
         and manifest["action"] == ACTION
         and manifest["rollback_sha"] == LKG
         and manifest["requires_owner_signature"] is True
         and manifest["provider_mutations"] == 0
         and manifest["financial_scheduler_activation"] is False
         and manifest["one_use"] is True
         and manifest["full_scan_seconds"] == 5400,
         "OWNER_ACTION_SCOPE_DRIFT")
    unsigned = dict(manifest)
    unsigned.pop("scope_sha256")
    need(manifest["scope_sha256"] == digest(canonical(unsigned)),
         "OWNER_SCOPE_HASH_CHANGED")
    need(digest(FREEZE.read_bytes()) == manifest["freeze_sha256"],
         "PRODUCTION_FREEZE_CHANGED")
    need(Path("/opt/jason/current").resolve(strict=True).name == LKG,
         "PRODUCTION_LKG_CHANGED")
    expected = set(manifest["files_sha256"]) | {"manifest.json"}
    actual = {p.name for p in directory.iterdir()}
    need(actual == expected, "OWNER_ACTION_ALREADY_PROVED_OR_EXTRA_FILES")
    for name, known in manifest["files_sha256"].items():
        p = directory / name
        meta = p.lstat()
        need(meta.st_uid == 1000 and stat.S_IMODE(meta.st_mode) == 0o400
             and not p.is_symlink() and digest(p.read_bytes()) == known,
             "OWNER_SOURCE_BUNDLE_DRIFT")
    signer = trusted(OWNER_LIB, OWNER_SHA, "owner_release_issuer")
    auth = trusted(OAUTH_LIB, OAUTH_SHA, "owner_oauth_issuer")
    rawmeta = PRIVATE.lstat()
    need(rawmeta.st_uid == 1000 and stat.S_IMODE(rawmeta.st_mode) == 0o400
         and not PRIVATE.is_symlink() and rawmeta.st_size == 32,
         "OWNER_PRIVATE_SIGNER_UNTRUSTED")
    private = Ed25519PrivateKey.from_private_bytes(PRIVATE.read_bytes())
    pub = signer.read_pinned_root_owner_public_key(PUBLIC, require_root_owned=True)
    need(signer.public_key_sha256(pub) ==
         signer.public_key_sha256(private.public_key()),
         "PINNED_OWNER_PUBLIC_SIGNER_MISMATCH")
    return manifest, signer, auth, private


def authenticate(auth, manifest: dict) -> str:
    endpoint = ("https://login.microsoftonline.com/" + auth.TENANT +
                "/oauth2/v2.0/")
    challenge = auth._form(endpoint + "devicecode", {
        "client_id": auth.CLIENT_ID, "scope": auth.SCOPE})
    need(all(isinstance(challenge.get(k), str) for k in
             ("device_code", "user_code", "verification_uri")),
         "ENTRA_DEVICE_CODE_UNAVAILABLE")
    ttl = min(600, int(challenge.get("expires_in", 0)))
    need(ttl >= 60, "ENTRA_DEVICE_CODE_TOO_SHORT")
    print("EXACT_OWNER_ACTION=" + ACTION, flush=True)
    print("EXACT_SOURCE=" + manifest["source_sha"], flush=True)
    print("EXACT_SCOPE_SHA256=" + manifest["scope_sha256"], flush=True)
    print("NO_PRODUCTION_MUTATIONS_UNTIL_ROOT_PROOF_VERIFICATION=True", flush=True)
    print("READ_ONLY_FULL_INTEGRITY_LIMIT_SECONDS=5400", flush=True)
    print("BROWSER_VERIFICATION_URL=" + challenge["verification_uri"], flush=True)
    print("SIGN_IN_CODE=" + challenge["user_code"], flush=True)
    end = time.monotonic() + ttl
    interval = max(5, min(20, int(challenge.get("interval", 5))))
    while time.monotonic() < end:
        response = auth._form(endpoint + "token", {
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "client_id": auth.CLIENT_ID,
            "device_code": challenge["device_code"]})
        if isinstance(response.get("access_token"), str):
            oid = auth.jwt_owner(response["access_token"])
            response = None
            typed = input("Type " + CONFIRM + " to authorize this exact action: ")
            need(typed.strip() == CONFIRM, "OWNER_EXACT_CONFIRMATION_MISSING")
            return oid
        if response.get("error") == "slow_down":
            interval = min(20, interval + 5)
        else:
            need(response.get("error") == "authorization_pending",
                 "ENTRA_OWNER_AUTHORIZATION_DENIED")
        time.sleep(interval)
    raise Denied("ENTRA_OWNER_CHALLENGE_EXPIRED")


def issue(directory: Path) -> dict:
    manifest, signer, auth, private = preflight(directory)
    oid = authenticate(auth, manifest)
    principal = signer.EXACT_OWNER_OAUTH_SUBJECTS.get(oid)
    need(principal is not None, "AUTHENTICATED_OWNER_SUBJECT_NOT_PINNED")
    proof = signer.issue_exact_owner_release(
        approval_id="owner-mcp-" + uuid.uuid4().hex,
        release_id="release-" + manifest["source_sha"][:16],
        candidate_sha=manifest["source_sha"],
        rollback_sha=LKG,
        scope_sha256=manifest["scope_sha256"],
        manifest_sha256=digest(canonical(manifest)),
        freeze_sha256=manifest["freeze_sha256"],
        verified_tenant_id=signer.TID,
        verified_owner_oid=oid,
        verified_principal=principal,
        verified_organization_id="aot",
        confirmed_decision="approve",
        at=datetime.now(timezone.utc),
        private_key=private,
    )
    signer.verify_exact_owner_release(
        proof, public_key=private.public_key(),
        expected_candidate_sha=manifest["source_sha"],
        expected_rollback_sha=LKG,
        expected_release_id="release-" + manifest["source_sha"][:16],
        expected_scope_sha256=manifest["scope_sha256"],
        expected_manifest_sha256=digest(canonical(manifest)),
        expected_freeze_sha256=manifest["freeze_sha256"],
        at=datetime.now(timezone.utc),
    )
    signed = {
        "schema_version": "1.0", "action": ACTION,
        "manifest_sha256": digest(canonical(manifest)),
        "signed_owner_proof": proof,
    }
    p = directory / "owner-proof.json"
    fd = os.open(p, os.O_WRONLY | os.O_EXCL | os.O_CREAT |
                 getattr(os, "O_NOFOLLOW", 0), 0o400)
    with os.fdopen(fd, "wb") as handle:
        handle.write(json.dumps(signed, sort_keys=True).encode() + b"\n")
        handle.flush()
        os.fsync(handle.fileno())
    print("AUTHENTICATED_SIGNED_ONE_USE_OWNER_PROOF=VERIFIED")
    print("ROOT_EXECUTION=NOT_PERFORMED")
    return signed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--packet", type=Path, required=True)
    ap.add_argument("--check-only", action="store_true")
    ap.add_argument("--approve", action="store_true")
    args = ap.parse_args()
    need(args.check_only != args.approve, "MODE_REQUIRED")
    if args.check_only:
        info, _, _, _ = preflight(args.packet)
        print("OWNER_ISSUER_PREFLIGHT=PASS")
        print("SOURCE_SHA=" + info["source_sha"])
        print("OWNER_APPROVAL=NOT_REQUESTED")
    else:
        issue(args.packet)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("OWNER_LIVE_AUDIT_APPROVAL=DENIED " + type(exc).__name__ +
              ":" + (str(exc)[:130] if isinstance(exc, Denied)
                      else "SENSITIVE_DETAILS_REDACTED"), file=sys.stderr)
        raise SystemExit(2)
