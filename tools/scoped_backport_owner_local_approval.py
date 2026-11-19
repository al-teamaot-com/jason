#!/usr/bin/env python3
"""Exact, interactive Entra OAuth Owner approval for an eligible scoped release.

Runs ONLY as the pre-existing 'al' service operator from a root-owned pinned
installation. No Teams requirement. No password, token, private key, or OTP
is printed or written. It signs one exact already staged offer and then exits.

This is a future authenticated Owner option until the dedicated MCP action is
installed. It cannot approve the uninstalled source engineering itself.
"""
from __future__ import annotations
from datetime import datetime, timezone
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import pwd
import stat
import sys
import time
from uuid import uuid4

INSTALL_ROOT = Path("/usr/local/lib/jason/scoped-backport")
INSTALLED = INSTALL_ROOT / "tools/scoped_backport_owner_local_approval.py"
if Path(__file__).resolve() == INSTALLED:
    sys.path.insert(0, str(INSTALL_ROOT))

from implementation.kernel.signed_owner_release import (
    EXACT_OWNER_OAUTH_SUBJECTS, TID, read_pinned_root_owner_public_key,
    read_service_owner_signing_key, issue_exact_owner_release,
    verify_exact_owner_release,
)
from tools.scoped_backport_release import validate_offer, deny, ScopedBackportDenied

AUTH = Path("/var/lib/jason/authority/scoped-backport-release")
VERIFIER = Path("/usr/local/lib/jason/owner_signer_recovery.py")
VERIFIER_SHA256 = "24d3632a4b0aa60851a1c82ccb15539eb823dd26afa5a1a2cc8c7afc54d72153"
SIGNER = Path("/var/lib/jason/runtime-secrets/owner-release/private_key")
TRUST = Path("/etc/jason-owner-release/verified-owner-public-key.json")
DECISION = "APPROVE-EXACT-SCOPED-BACKPORT-RELEASE"


def installed() -> None:
    if (Path(__file__).resolve(strict=True) != INSTALLED
            or not sys.flags.isolated or os.geteuid() != pwd.getpwnam("al").pw_uid
            or INSTALLED.is_symlink() or INSTALLED.stat().st_uid != 0
            or INSTALLED.stat().st_mode & 0o022):
        deny("OWNER_AUTHENTICATION_INSTALLED_OPERATOR_REQUIRED")
    verifier = VERIFIER.lstat()
    if (VERIFIER.is_symlink() or not stat.S_ISREG(verifier.st_mode)
            or verifier.st_uid != 0 or verifier.st_mode & 0o022
            or sha256(VERIFIER.read_bytes()).hexdigest() != VERIFIER_SHA256):
        deny("PINNED_OWNER_JWT_VERIFIER_CHANGED")


def _safe_public(name: str, release_id: str) -> dict:
    if name not in ("offers", "eligibility") or not release_id.startswith("release-"):
        deny("OWNER_SOURCE_OUT_OF_SCOPE")
    folder = AUTH / name
    user = pwd.getpwnam("al")
    if (folder.is_symlink() or not folder.is_dir()
            or folder.stat().st_uid != user.pw_uid
            or stat.S_IMODE(folder.stat().st_mode) != 0o700):
        deny("OWNER_OFFER_DIR_UNTRUSTED")
    p = folder / (release_id + ".json")
    if p.is_symlink() or not p.is_file():
        deny("OWNER_OFFER_MISSING")
    m = p.stat()
    if (m.st_uid != user.pw_uid or stat.S_IMODE(m.st_mode) != 0o600
            or m.st_size > 32768):
        deny("OWNER_OFFER_METADATA")
    data = json.loads(p.read_text())
    if not isinstance(data, dict):
        deny("OWNER_OFFER_NOT_OBJECT")
    return data


def authenticated_owner() -> str:
    # This audited root-owned helper performs signed JWT issuer/audience,
    # tenant, expiry, MFA-capable Entra OAuth and Owner account verification.
    spec = importlib.util.spec_from_file_location(
        "aot_scoped_owner_pinned_verifier", VERIFIER)
    if spec is None or spec.loader is None:
        deny("OWNER_JWT_VERIFIER_NOT_IMPORTABLE")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if (module.TENANT != TID or module.CLIENT_ID !=
            "9b9996e9-5c34-48b7-948c-f44f89352f89"
            or module.SCOPE !=
            "https://mcp-jason.teamaot.com/mcp/Jason.Read"
            or frozenset(module.OWNERS) != frozenset(EXACT_OWNER_OAUTH_SUBJECTS)):
        deny("OWNER_JWT_VERIFIER_POLICY_CHANGED")
    authority = "https://login.microsoftonline.com/" + TID + "/oauth2/v2.0/"
    challenge = module._form(authority + "devicecode", {
        "client_id": module.CLIENT_ID,
        "scope": module.SCOPE,
    })
    if not all(isinstance(challenge.get(k), str) for k in (
            "device_code", "user_code", "verification_uri")):
        deny("OWNER_DEVICE_CODE_UNAVAILABLE")
    seconds = min(600, int(challenge.get("expires_in") or 0))
    if seconds < 60:
        deny("OWNER_DEVICE_CODE_TOO_SHORT")
    print("OWNER_SIGN_IN_URL=" + challenge["verification_uri"], flush=True)
    print("OWNER_SIGN_IN_CODE=" + challenge["user_code"], flush=True)
    deadline = time.monotonic() + seconds
    interval = max(5, min(20, int(challenge.get("interval") or 5)))
    oid = None
    while time.monotonic() < deadline:
        time.sleep(interval)
        result = module._form(authority + "token", {
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "client_id": module.CLIENT_ID,
            "device_code": challenge["device_code"],
        })
        if isinstance(result.get("access_token"), str):
            oid = module.jwt_owner(result["access_token"])
            break
        if result.get("error") == "slow_down":
            interval = min(20, interval + 5)
        elif result.get("error") != "authorization_pending":
            deny("OWNER_OAUTH_REJECTED")
    if oid not in EXACT_OWNER_OAUTH_SUBJECTS:
        deny("OWNER_OAUTH_IDENTITY_NOT_VERIFIED")
    return oid


def approve(release_id: str) -> dict:
    installed()
    offer = validate_offer(_safe_public("offers", release_id))
    eligibility = _safe_public("eligibility", release_id)
    if (offer["release_id"] != release_id
            or eligibility.get("status") !=
            "native_scoped_preproduction_eligible_not_approved"
            or eligibility.get("release_id") != release_id
            or eligibility.get("candidate_sha") != offer["candidate_sha"]
            or eligibility.get("scope_sha256") != offer["scope_sha256"]
            or eligibility.get("manifest_sha256") != offer["manifest_sha256"]
            or eligibility.get("freeze_sha256") != offer["freeze_sha256"]):
        deny("OWNER_EXACT_ELIGIBLE_OFFER_REQUIRED")
    folder = AUTH / "owner-approvals"
    if folder.is_symlink() or not folder.is_dir():
        deny("OWNER_APPROVAL_SPOOL_MISSING")
    target = folder / (release_id + ".json")
    if target.exists() or target.is_symlink():
        deny("OWNER_PROOF_ALREADY_EXISTS")
    print("EXACT_ACTION=scoped_backport_release_one_time", flush=True)
    for name in ("release_id", "candidate_sha", "rollback_sha",
                 "scope_sha256", "manifest_sha256", "freeze_sha256"):
        print(name.upper() + "=" + str(offer[name]), flush=True)
    print("TENANT=" + str(offer["tenant_id"]), flush=True)
    print("PROVIDER_MUTATIONS_APPROVED=false", flush=True)
    oid = authenticated_owner()
    if input("Type " + DECISION + " to sign only this exact release: ").strip() != DECISION:
        deny("OWNER_EXACT_RELEASE_DECISION_NOT_CONFIRMED")
    from cryptography.hazmat.primitives import serialization
    trusted = read_pinned_root_owner_public_key(TRUST)
    signer = read_service_owner_signing_key(SIGNER)
    raw = trusted.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw)
    mine = signer.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw)
    if raw != mine:
        deny("SERVICE_SIGNER_AND_ROOT_TRUST_MISMATCH")
    signature = issue_exact_owner_release(
        approval_id="owner-mcp-" + uuid4().hex,
        release_id=offer["release_id"],
        candidate_sha=offer["candidate_sha"],
        rollback_sha=offer["rollback_sha"],
        scope_sha256=offer["scope_sha256"],
        manifest_sha256=offer["manifest_sha256"],
        freeze_sha256=offer["freeze_sha256"],
        verified_tenant_id=TID, verified_owner_oid=oid,
        verified_principal=EXACT_OWNER_OAUTH_SUBJECTS[oid],
        verified_organization_id="aot", confirmed_decision="approve",
        at=datetime.now(timezone.utc), private_key=signer)
    verify_exact_owner_release(
        signature, public_key=trusted,
        expected_candidate_sha=offer["candidate_sha"],
        expected_rollback_sha=offer["rollback_sha"],
        expected_release_id=offer["release_id"],
        expected_scope_sha256=offer["scope_sha256"],
        expected_manifest_sha256=offer["manifest_sha256"],
        expected_freeze_sha256=offer["freeze_sha256"],
        at=datetime.now(timezone.utc))
    record = {
        "schema_version": "1.0", "release_id": release_id,
        "candidate_sha": offer["candidate_sha"],
        "manifest_sha256": offer["manifest_sha256"],
        "standing_authority": False,
        "signed_owner_proof": signature,
        "provider_mutations_approved": False,
    }
    raw = json.dumps(record, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return {
        "status": "owner_exact_signed_release_proof_queued_not_deployed",
        "release_id": release_id,
        "candidate_sha": offer["candidate_sha"],
        "owner_principal": EXACT_OWNER_OAUTH_SUBJECTS[oid],
        "approval_id": signature["payload"]["approval_id"],
        "production_deployment": False,
        "provider_mutations_approved": False,
    }


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-id", required=True)
    args = parser.parse_args()
    print(json.dumps(approve(args.release_id), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
