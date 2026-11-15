#!/usr/bin/env python3
"""Unprivileged Entra Owner exact consent for one PMv4 source closure trust bootstrap.

Does not run sudo, install root files, or grant standing authority.
Requires an interactive local UID1000 Owner terminal for authentication.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys
import time
import uuid
from typing import Any, Mapping

SOURCE_SHA = "7b42ce983896711525de4c7955bf9fc43ac003d0"
LKG = "d1b8c196dadd4b672ec8ba47075f27bb61c98d63"
ACTION = "pmv4-stage-a0-root-source-closure-bootstrap-v1"
PLAN_SHA = "25e68eaee841791b5b857d59eef543691225ff9ea7d38fc9477eff69957e4564"
SCOPE_SHA = "e5515b5e0d5243c5e18c3118fcc0c39580535c7e0da31525390c141e1aa298cb"
FREEZE_SHA = "bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f"
HOLD_SHA = "11f0f78904236c36ebd1aeee58f52fcecba035bce33d15ce323b36d36ad5a5a0"
ARCHIVE = Path("/srv/jason/archive")
PLAN = ARCHIVE / "pmv4-a0-closure-bootstrap-plan-7b42.json"
PROOF = ARCHIVE / "pmv4-a0-closure-bootstrap-OWNER-PROOF-7b42.json"
SIGNER = Path("/var/lib/jason/runtime-secrets/owner-release/private_key")
VERIFIER = Path("/usr/local/lib/jason/owner_signed_release.py")
OWNER_OAUTH = Path("/usr/local/lib/jason/owner_signer_recovery.py")
ROOT_PIN = Path("/etc/jason-owner-release/verified-owner-public-key.json")
FREEZE = Path("/var/lib/jason/openclaw/release-manager/production-deployment-freeze")
HOLD = Path("/var/lib/jason/openclaw/release-manager/auto-promotion-incident-hold")
CONFIRM = "APPROVE-EXACT-PMV4-A0-CLOSURE-BOOTSTRAP"


class OwnerDenied(PermissionError):
    pass


def must(value: bool, code: str) -> None:
    if not value:
        raise OwnerDenied(code)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(dict(value), sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode()


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    must(spec is not None and spec.loader is not None, "OWNER_LIBRARY_UNAVAILABLE")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify_reviewed_plan(*, allow_proof: bool = False) -> dict[str, Any]:
    must(os.geteuid() == 1000, "OWNER_LOCAL_SERVICE_UID_REQUIRED")
    raw = PLAN.read_bytes()
    must(sha(raw) == PLAN_SHA, "OWNER_EXACT_PLAN_DIGEST_CHANGED")
    plan = json.loads(raw)
    scope = plan.get("scope_sha256")
    must(scope == SCOPE_SHA and sha(canonical({
        k: v for k, v in plan.items() if k != "scope_sha256"
    })) == SCOPE_SHA, "OWNER_EXACT_BOOTSTRAP_SCOPE_CHANGED")
    must(plan.get("action") == ACTION and plan.get("source_sha") == SOURCE_SHA
         and plan.get("lkg_sha") == LKG
         and plan.get("freeze_sha256") == FREEZE_SHA
         and plan.get("hold_sha256") == HOLD_SHA
         and plan.get("one_shot") is True
         and plan.get("owner_authentication") == "fresh-entra-oauth-ed25519-exact-action"
         and plan.get("production_install_authorized") is False
         and len(plan.get("files", [])) == 2,
         "OWNER_EXACT_BOOTSTRAP_CONTRACT_CHANGED")
    must(sha(FREEZE.read_bytes()) == FREEZE_SHA
         and sha(HOLD.read_bytes()) == HOLD_SHA
         and Path("/opt/jason/current").resolve(strict=True).name == LKG,
         "OWNER_PROTECTED_PRODUCTION_STATE_CHANGED")
    for row in plan["files"]:
        path = Path(row["source"])
        st = path.lstat()
        must(st.st_uid == 1000 and stat.S_ISREG(st.st_mode)
             and st.st_nlink == 1 and stat.S_IMODE(st.st_mode) == 0o600
             and path.parent == ARCHIVE
             and len(path.read_bytes()) == row["size"]
             and sha(path.read_bytes()) == row["sha256"],
             "OWNER_BOOTSTRAP_SOURCE_BYTES_CHANGED")
        dest = Path(row["destination"])
        must(not dest.exists() and not dest.is_symlink(),
             "OWNER_BOOTSTRAP_ROOT_TARGET_ALREADY_EXISTS")
    directory = Path(plan["one_directory"])
    must(not directory.exists() and not directory.is_symlink(),
         "OWNER_BOOTSTRAP_LEDGER_ALREADY_EXISTS")
    if not allow_proof:
        must(not PROOF.exists() and not PROOF.is_symlink(),
             "OWNER_BOOTSTRAP_APPROVAL_ALREADY_PUBLISHED")
    return plan


def authenticate_exact_owner(oauth) -> str:
    endpoint = "https://login.microsoftonline.com/" + oauth.TENANT + "/oauth2/v2.0/"
    challenge = oauth._form(endpoint + "devicecode", {
        "client_id": oauth.CLIENT_ID, "scope": oauth.SCOPE,
    })
    must(all(isinstance(challenge.get(x), str)
             for x in ("device_code", "user_code", "verification_uri")),
         "OWNER_DEVICE_AUTHORIZATION_UNAVAILABLE")
    duration = min(int(challenge.get("expires_in", 0)), 600)
    must(duration >= 60, "OWNER_AUTHENTICATION_DURATION_INVALID")
    print("EXACT_ACTION=" + ACTION, flush=True)
    print("REVIEWED_SOURCE_SHA=" + SOURCE_SHA, flush=True)
    print("ONE_HELPER_ONE_POLICY_ONE_EMPTY_LEDGER=true", flush=True)
    print("NO_RUNTIME_MCP_OR_TICKET_CHANGES=true", flush=True)
    print("BROWSER_VERIFICATION_URL=" + challenge["verification_uri"], flush=True)
    print("SIGN_IN_CODE=" + challenge["user_code"], flush=True)
    interval = max(5, min(20, int(challenge.get("interval", 5))))
    stop = time.monotonic() + duration
    while time.monotonic() < stop:
        time.sleep(interval)
        token = oauth._form(endpoint + "token", {
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "client_id": oauth.CLIENT_ID, "device_code": challenge["device_code"],
        })
        if isinstance(token.get("access_token"), str):
            identity = oauth.jwt_owner(token["access_token"])
            phrase = input("Type " + CONFIRM + " to approve ONLY the listed root bootstrap: ")
            must(phrase.strip() == CONFIRM, "OWNER_EXACT_CONFIRMATION_REQUIRED")
            return identity
        if token.get("error") == "slow_down":
            interval = min(20, interval + 5)
        elif token.get("error") != "authorization_pending":
            raise OwnerDenied("OWNER_ENTRA_AUTHENTICATION_DENIED")
    raise OwnerDenied("OWNER_ENTRA_AUTHENTICATION_EXPIRED")


def verify_signed_proof(plan: Mapping[str, Any]) -> str:
    record = json.loads(PROOF.read_bytes())
    must(set(record) == {
        "schema_version", "action", "source_sha", "rollback_sha",
        "scope_sha256", "manifest_sha256", "signed_owner_proof", "status",
    }, "OWNER_PROOF_FIELDS_CHANGED")
    must(record["action"] == ACTION and record["source_sha"] == SOURCE_SHA
         and record["rollback_sha"] == LKG
         and record["scope_sha256"] == SCOPE_SHA
         and record["manifest_sha256"] == sha(canonical(plan))
         and record["status"] == "SIGNED_OWNER_EXACT_APPROVAL_NO_INSTALL",
         "OWNER_PROOF_BINDING_CHANGED")
    verifier = load(VERIFIER, "a0_closure_owner_verifier")
    verifier.verify_exact_owner_release(
        record["signed_owner_proof"],
        public_key=verifier.read_pinned_root_owner_public_key(ROOT_PIN),
        at=datetime.now(timezone.utc),
        expected_candidate_sha=SOURCE_SHA,
        expected_rollback_sha=LKG,
        expected_release_id="release-" + SOURCE_SHA[:16],
        expected_scope_sha256=SCOPE_SHA,
        expected_manifest_sha256=sha(canonical(plan)),
        expected_freeze_sha256=FREEZE_SHA,
    )
    return str(record["signed_owner_proof"]["payload"]["approval_id"])


def main() -> int:
    parser = argparse.ArgumentParser()
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--check-only", action="store_true")
    modes.add_argument("--authorize", action="store_true")
    modes.add_argument("--verify-proof", action="store_true")
    args = parser.parse_args()
    try:
        plan = verify_reviewed_plan(allow_proof=args.verify_proof)
        print("EXACT_BOOTSTRAP_PLAN_AND_SOURCE=VERIFIED", flush=True)
        if args.check_only:
            print("ROOT_WRITES=ZERO; OWNER_APPROVAL_ISSUED=false")
            return 0
        if args.verify_proof:
            print("EXACT_OWNER_APPROVAL_ID=" + verify_signed_proof(plan))
            return 0
        must(sys.stdin.isatty(), "OWNER_LOCAL_INTERACTIVE_TERMINAL_REQUIRED")
        oauth = load(OWNER_OAUTH, "a0_closure_owner_auth")
        verifier = load(VERIFIER, "a0_closure_owner_signer")
        owner_oid = authenticate_exact_owner(oauth)
        must(owner_oid in verifier.EXACT_OWNER_OAUTH_SUBJECTS,
             "OWNER_OAUTH_SUBJECT_NOT_APPROVED")
        must(verify_reviewed_plan() == plan, "OWNER_PRODUCTION_CHANGED_DURING_AUTH")
        private_key = verifier.read_service_owner_signing_key(SIGNER)
        now = datetime.now(timezone.utc)
        proof = verifier.issue_exact_owner_release(
            approval_id="owner-mcp-" + uuid.uuid4().hex,
            release_id="release-" + SOURCE_SHA[:16],
            candidate_sha=SOURCE_SHA, rollback_sha=LKG,
            scope_sha256=SCOPE_SHA, manifest_sha256=sha(canonical(plan)),
            freeze_sha256=FREEZE_SHA,
            verified_tenant_id=verifier.TID,
            verified_owner_oid=owner_oid,
            verified_principal=verifier.EXACT_OWNER_OAUTH_SUBJECTS[owner_oid],
            verified_organization_id="aot",
            confirmed_decision="approve", at=now, private_key=private_key,
        )
        verifier.verify_exact_owner_release(
            proof, public_key=verifier.read_pinned_root_owner_public_key(ROOT_PIN),
            at=now, expected_candidate_sha=SOURCE_SHA, expected_rollback_sha=LKG,
            expected_release_id="release-" + SOURCE_SHA[:16],
            expected_scope_sha256=SCOPE_SHA,
            expected_manifest_sha256=sha(canonical(plan)),
            expected_freeze_sha256=FREEZE_SHA,
        )
        record = {
            "schema_version": "1.0", "action": ACTION,
            "source_sha": SOURCE_SHA, "rollback_sha": LKG,
            "scope_sha256": SCOPE_SHA,
            "manifest_sha256": sha(canonical(plan)),
            "signed_owner_proof": proof,
            "status": "SIGNED_OWNER_EXACT_APPROVAL_NO_INSTALL",
        }
        fd = os.open(PROOF, os.O_CREAT | os.O_EXCL | os.O_WRONLY
                     | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            raw = canonical(record) + b"\n"
            must(os.write(fd, raw) == len(raw), "OWNER_PROOF_SHORT_WRITE")
            os.fsync(fd)
        finally:
            os.close(fd)
        print("ONE_USE_EXACT_OWNER_SIGNATURE=VERIFIED_AND_RECORDED")
        print("ROOT_INSTALL_PERFORMED=false")
        return 0
    except (OwnerDenied, ValueError, OSError) as exc:
        print("PMV4_A0_CLOSURE_OWNER=DENIED " + type(exc).__name__
              + ":" + str(exc)[:150], file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
