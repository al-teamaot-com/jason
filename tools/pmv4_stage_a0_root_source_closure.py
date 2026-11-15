#!/usr/bin/env python3
"""Exact, one-use Stage A0 immutable-source closure. Source-only until trusted installation.

This tool is NOT a generic privileged file writer.  Production execution requires
a separately reviewed root-owned installation of this exact module and an exact
root-owned policy, a fresh authenticated Owner decision, the original immutable
13-file source baseline, protected-main CI, the existing host release lock, and
unchanged production health/freeze/hold. Running from a mutable checkout denies.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import sys
import time
from typing import Any, Callable, Mapping

ACTION = "pmv4-stage-a0-root-source-closure-v1"
ROOT_SCRIPT = Path("/usr/local/lib/jason/pmv4_stage_a0_root_source_closure.py")
ROOT_STAGE = Path("/usr/local/lib/jason/pmv4_stage_a0_sparse_root_stage.py")
ROOT_SOURCE = Path("/usr/local/lib/jason/pmv4_stage_a0_sparse_source.py")
ROOT_CI = Path("/usr/local/lib/jason/pmv4_shadow_ci.py")
ROOT_VERIFIER = Path("/usr/local/lib/jason/owner_signed_release.py")
ROOT_OAUTH = Path("/usr/local/lib/jason/owner_signer_recovery.py")
POLICY = Path("/etc/jason-owner-release/pmv4-stage-a0-root-source-closure.json")
AUDIT = Path("/etc/jason-owner-release/pmv4-stage-a0-root-source-closure-ledger")
CANDIDATE = "7b42ce983896711525de4c7955bf9fc43ac003d0"
RELATIVE = "tools/pmv4_host_install_contract.py"
MISSING_SHA256 = "ca844feeb43aa624fb1a965571bfb30f554e24662b2837bb2efa8bfddbdfb5db"
ORIGINAL_SCOPE = "09e35bf812c3bedd61991af669ea9a80b0a0ff5948b1d1a6edb1d70c3332c27f"
PROPOSAL_SHA256 = "089f8706b61b70c9f31406204bb27fab0bde47bc8df56f13a274defb8b537381"
ZERO_WRITE_AUTHORITY_FROM_SOURCE = True
REQUIRED_POLICY = frozenset({
    "schema_version", "action", "one_shot", "candidate_sha", "lkg_sha",
    "file_path", "file_sha256", "original_scope_sha256", "proposal_sha256",
    "freeze_sha256", "promotion_hold_sha256", "mcp_image_sha256",
    "runtime_image_sha256", "script_sha256", "owner_authentication",
    "install_scope", "no_services_changed", "no_provider_writes",
})


class SourceClosureDenied(PermissionError):
    pass


def canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(dict(value), sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode()


def digest(raw: bytes) -> str:
    return sha256(raw).hexdigest()


def repair_scope(policy: Mapping[str, Any]) -> str:
    return digest(canonical({
        "action": ACTION, "source_revision": policy["candidate_sha"],
        "only_file": policy["file_path"], "file_sha256": policy["file_sha256"],
        "previous_scope": policy["original_scope_sha256"],
        "proposal_sha256": policy["proposal_sha256"],
        "rollback": "absent-file-only",
    }))


def _load_root(path: Path, name: str, stage: Any) -> Any:
    # The installed Stage A0 trust loader rejects operator-writable modules.
    return stage._load_trusted(path, name)


def trusted_policy(stage: Any) -> dict[str, Any]:
    obj = json.loads(stage.secure_root_read(POLICY, max_bytes=8192))
    if (not isinstance(obj, dict) or set(obj) != REQUIRED_POLICY
            or obj["schema_version"] != "1.0" or obj["action"] != ACTION
            or obj["one_shot"] is not True
            or obj["candidate_sha"] != CANDIDATE
            or obj["file_path"] != RELATIVE
            or obj["file_sha256"] != MISSING_SHA256
            or obj["original_scope_sha256"] != ORIGINAL_SCOPE
            or obj["proposal_sha256"] != PROPOSAL_SHA256
            or obj["owner_authentication"] != "fresh-entra-oauth-signed-exact-action"
            or obj["install_scope"] != "only-one-missing-root-owned-stage-a0-source"
            or obj["no_services_changed"] is not True
            or obj["no_provider_writes"] is not True):
        raise SourceClosureDenied("A0_CLOSURE_POLICY_SCOPE_DENIED")
    for name in ("lkg_sha",):
        if not isinstance(obj[name], str) or not re.fullmatch(r"[0-9a-f]{40}", obj[name]):
            raise SourceClosureDenied("A0_CLOSURE_POLICY_SHA_INVALID")
    for name in ("freeze_sha256", "promotion_hold_sha256", "script_sha256"):
        if not isinstance(obj[name], str) or not re.fullmatch(r"[0-9a-f]{64}", obj[name]):
            raise SourceClosureDenied("A0_CLOSURE_POLICY_DIGEST_INVALID")
    for name in ("mcp_image_sha256", "runtime_image_sha256"):
        if not isinstance(obj[name], str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", obj[name]):
            raise SourceClosureDenied("A0_CLOSURE_POLICY_IMAGE_INVALID")
    if digest(stage.secure_root_read(ROOT_SCRIPT, max_bytes=256000)) != obj["script_sha256"]:
        raise SourceClosureDenied("A0_CLOSURE_INSTALLED_SCRIPT_HASH_DRIFT")
    return obj


def exact_source_scopes(
    source: Any, stage: Any, policy: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], bytes]:
    blob = source.git_object(stage.REPO)
    prior = source.source_manifest(
        policy["candidate_sha"], blob,
        freeze_sha256=policy["freeze_sha256"],
        current_lkg=policy["lkg_sha"],
    )
    if (prior.get("scope_sha256") != ORIGINAL_SCOPE
            or len(prior.get("files", [])) != 13
            or RELATIVE in {f["path"] for f in prior["files"]}):
        raise SourceClosureDenied("A0_CLOSURE_PRIOR_SOURCE_SCOPE_DRIFT")
    missing = blob(policy["candidate_sha"], RELATIVE)
    if len(missing) != 9571 or digest(missing) != MISSING_SHA256:
        raise SourceClosureDenied("A0_CLOSURE_MISSING_GIT_BLOB_DRIFT")
    item = {"path": RELATIVE, "size": len(missing),
            "sha256": MISSING_SHA256, "mode": "0444", "uid": 0, "gid": 0}
    after = dict(prior)
    after["files"] = list(prior["files"]) + [item]
    if len({x["path"] for x in after["files"]}) != 14:
        raise SourceClosureDenied("A0_CLOSURE_DUPLICATE_SOURCE_PATH")
    return prior, after, missing


def verify_prior(stage: Any, root: Path, prior: Mapping[str, Any]) -> None:
    target = root / RELATIVE
    if target.exists() or target.is_symlink():
        raise SourceClosureDenied("A0_CLOSURE_MISSING_TARGET_NOT_ABSENT")
    stage.verify_staged_source(root, prior)


def _write_one_exact(
    target: Path, payload: bytes, *, after_write: Callable[[], None] | None = None,
    test_only: bool = False,
) -> None:
    """Exclusive immutable file creation, with inode-bound conditional rollback.

    Caller MUST hold the trusted host lock, check the signed Owner proof and
    journal a one-use attempt before invoking this helper in production.
    """
    if (target.name != Path(RELATIVE).name
            or target.parent.name != "tools"
            or target.exists() or target.is_symlink()
            or digest(payload) != MISSING_SHA256):
        raise SourceClosureDenied("A0_CLOSURE_EXACT_TARGET_OR_BLOB_DENIED")
    if not test_only:
        if (os.geteuid() != 0
                or target != Path("/opt/jason/releases") / CANDIDATE / RELATIVE):
            raise SourceClosureDenied("A0_CLOSURE_PRODUCTION_ROOT_REQUIRED")
    else:
        if not target.is_absolute() or not str(target).startswith("/tmp/"):
            raise SourceClosureDenied("A0_CLOSURE_TEST_TARGET_OUTSIDE_TEMP")
    parent = target.parent.lstat()
    if (not stat.S_ISDIR(parent.st_mode) or target.parent.is_symlink()
            or parent.st_mode & 0o022 or (not test_only and parent.st_uid != 0)):
        raise SourceClosureDenied("A0_CLOSURE_PARENT_UNTRUSTED")
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                 | getattr(os, "O_NOFOLLOW", 0), 0o600)
    inode = os.fstat(fd).st_ino
    created = True
    try:
        # Keep the original inode open until after verification/rollback.
        # Otherwise unlink+recreate could recycle its inode number, causing
        # conditional rollback to delete a foreign replacement.
        if not test_only:
            os.fchown(fd, 0, 0)
        os.fchmod(fd, 0o444)
        if os.write(fd, payload) != len(payload):
            raise SourceClosureDenied("A0_CLOSURE_PARTIAL_FILE_WRITE")
        os.fsync(fd)
        if after_write:
            after_write()
        meta = target.lstat()
        if (target.is_symlink() or not stat.S_ISREG(meta.st_mode)
                or meta.st_ino != inode or meta.st_nlink != 1
                or stat.S_IMODE(meta.st_mode) != 0o444
                or (not test_only and (meta.st_uid, meta.st_gid) != (0, 0))
                or digest(target.read_bytes()) != MISSING_SHA256):
            raise SourceClosureDenied("A0_CLOSURE_CREATED_SOURCE_READBACK_FAILED")
        created = False
    finally:
        if created:
            try:
                meta = target.lstat()
            except FileNotFoundError:
                meta = None
            # Only remove the inode this transaction created. Never touch a
            # replaced path, symlink, or hard-linked foreign object.
            if (meta is not None and stat.S_ISREG(meta.st_mode)
                    and not target.is_symlink() and meta.st_ino == inode
                    and meta.st_dev == os.fstat(fd).st_dev
                    and meta.st_nlink == 1 and (test_only or meta.st_uid == 0)):
                target.unlink()
        os.close(fd)


def fresh_exact_owner(stage: Any, oauth: Any, policy: Mapping[str, Any]) -> str:
    """Existing Entra Owner identity; no Teams, new signer, or approval plane."""
    entry = "https://login.microsoftonline.com/" + oauth.TENANT + "/oauth2/v2.0/"
    challenge = oauth._form(entry + "devicecode", {
        "client_id": oauth.CLIENT_ID, "scope": oauth.SCOPE,
    })
    if not all(isinstance(challenge.get(k), str)
               for k in ("device_code", "user_code", "verification_uri")):
        raise SourceClosureDenied("A0_CLOSURE_OWNER_OAUTH_NOT_AVAILABLE")
    duration = min(int(challenge.get("expires_in", 0)), 600)
    if duration < 60:
        raise SourceClosureDenied("A0_CLOSURE_OWNER_OAUTH_TOO_SHORT")
    print("EXACT_ACTION=" + ACTION, flush=True)
    print("ONLY_SOURCE_SHA=" + policy["candidate_sha"], flush=True)
    print("ONLY_FILE=" + RELATIVE, flush=True)
    print("FILE_SHA256=" + MISSING_SHA256, flush=True)
    print("NO_RUNTIME_OR_MCP_REPLACEMENT=true", flush=True)
    print("BROWSER_VERIFICATION_URL=" + challenge["verification_uri"], flush=True)
    print("SIGN_IN_CODE=" + challenge["user_code"], flush=True)
    interval = max(5, min(20, int(challenge.get("interval", 5))))
    deadline = time.monotonic() + duration
    while time.monotonic() < deadline:
        time.sleep(interval)
        token = oauth._form(entry + "token", {
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "client_id": oauth.CLIENT_ID, "device_code": challenge["device_code"],
        })
        if isinstance(token.get("access_token"), str):
            owner = oauth.jwt_owner(token["access_token"])
            phrase = "APPROVE-EXACT-PMV4-A0-ONE-FILE-ROOT-CLOSURE"
            if input("Confirm ONLY the shown file with " + phrase + ": ").strip() != phrase:
                raise SourceClosureDenied("A0_CLOSURE_OWNER_EXACT_CONSENT_DENIED")
            return owner
        if token.get("error") == "slow_down":
            interval = min(20, interval + 5)
        elif token.get("error") != "authorization_pending":
            raise SourceClosureDenied("A0_CLOSURE_OWNER_OAUTH_DENIED")
    raise SourceClosureDenied("A0_CLOSURE_OWNER_OAUTH_EXPIRED")


def execute() -> None:
    # Protect against running a checkout or manual root Python as a release.
    if (os.geteuid() != 0 or sys.flags.isolated != 1
            or Path(__file__).resolve(strict=True) != ROOT_SCRIPT):
        raise SourceClosureDenied("A0_CLOSURE_TRUSTED_ROOT_INSTALL_REQUIRED")
    if ROOT_STAGE.is_symlink():
        raise SourceClosureDenied("A0_CLOSURE_TRUSTED_ROOT_STAGE_MISSING")
    spec = importlib.util.spec_from_file_location("a0_closure_existing_root", ROOT_STAGE)
    if spec is None or spec.loader is None:
        raise SourceClosureDenied("A0_CLOSURE_TRUSTED_STAGE_LOAD_DENIED")
    stage = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(stage)
    stage.secure_root_read(ROOT_STAGE, max_bytes=256000)
    policy = trusted_policy(stage)
    audit_stat = AUDIT.lstat()
    if (AUDIT.is_symlink() or audit_stat.st_uid != 0
            or stat.S_IMODE(audit_stat.st_mode) != 0o700
            or any(AUDIT.iterdir())):
        raise SourceClosureDenied("A0_CLOSURE_AUDIT_ALREADY_CLAIMED_OR_UNSAFE")
    source = _load_root(ROOT_SOURCE, "a0_closure_source", stage)
    ci = _load_root(ROOT_CI, "a0_closure_ci", stage)
    verifier = _load_root(ROOT_VERIFIER, "a0_closure_verifier", stage)
    oauth = _load_root(ROOT_OAUTH, "a0_closure_oauth", stage)
    oauth.trusted_signer()
    before = stage.protected_preflight(policy)
    if not stage.protected_ci_as_operator(ci, CANDIDATE):
        raise SourceClosureDenied("A0_CLOSURE_PROTECTED_MAIN_CI_DENIED")
    prior, after, missing = exact_source_scopes(source, stage, policy)
    root = stage.RELEASES / CANDIDATE
    verify_prior(stage, root, prior)
    owner_oid = fresh_exact_owner(stage, oauth, policy)
    # The existing pinned Ed25519 signer binds the exact new repair scope and
    # entire immutable policy to the one-use, short-lived Owner release proof.
    auth_policy = dict(policy, sparse_scope_sha256=repair_scope(policy))
    proof = stage.signed_stage_owner_proof(auth_policy, owner_oid, verifier)
    with stage.existing_host_lock():
        if (trusted_policy(stage) != policy or stage.protected_preflight(policy) != before
                or not stage.protected_ci_as_operator(ci, CANDIDATE)):
            raise SourceClosureDenied("A0_CLOSURE_PRODUCTION_CHANGED_AFTER_CONSENT")
        prior, after, missing = exact_source_scopes(source, stage, policy)
        verify_prior(stage, root, prior)
        attempt = AUDIT / (ACTION + ".attempt.json")
        stage._write_root(attempt, canonical({
            "schema_version": "1.0", "action": ACTION,
            "candidate_sha": CANDIDATE, "file": RELATIVE,
            "file_sha256": MISSING_SHA256,
            "scope_sha256": repair_scope(policy),
            "signed_owner_proof": proof,
            "state": "one_use_claimed_before_root_write",
        }) + b"\n")
        result = {"schema_version": "1.0", "action": ACTION,
                  "candidate_sha": CANDIDATE, "status": "failed"}
        try:
            def verify_before_commit() -> None:
                # Keep the created inode OPEN while verifying the exact full
                # fourteen-file closure and protected production state.
                # Any failure here rolls back only our own inode inside
                # _write_one_exact, never a replacement or foreign object.
                stage.verify_staged_source(root, after)
                if stage.protected_preflight(policy) != before:
                    raise SourceClosureDenied("A0_CLOSURE_PRODUCTION_CHANGED_AFTER_WRITE")
            _write_one_exact(root / RELATIVE, missing,
                             after_write=verify_before_commit)
            result["status"] = "verified"
            result["installed_file_sha256"] = MISSING_SHA256
            result["source_file_count"] = 14
        except Exception:
            # The in-flight helper conditionally rolls back if its postflight
            # refuses. An audit failure AFTER helper return is fail-closed for
            # independent forensic review; never unconditionally unlink.
            result["status"] = "requires_review"
            raise
        finally:
            result["verified_at"] = datetime.now(timezone.utc).isoformat()
            stage._write_root(AUDIT / (ACTION + ".result.json"),
                              canonical(result) + b"\n")
    print("PMV4_STAGE_A0_ROOT_SOURCE_CLOSURE=VERIFIED")
    print("CURRENT_PRODUCTION_POINTER_CHANGED=false")
    print("RUNTIME_OR_MCP_REPLACED=false")


def main() -> int:
    parser = argparse.ArgumentParser()
    choices = parser.add_mutually_exclusive_group(required=True)
    choices.add_argument("--inspect", action="store_true")
    choices.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    try:
        if args.inspect:
            print(json.dumps({
                "action": ACTION, "candidate_sha": CANDIDATE, "only_file": RELATIVE,
                "file_sha256": MISSING_SHA256, "source_only": True,
                "production_mutation_authorized": False,
            }, sort_keys=True))
        else:
            execute()
        return 0
    except (SourceClosureDenied, OSError, ValueError) as exc:
        print("PMV4_A0_ROOT_CLOSURE=DENIED " + type(exc).__name__ +
              ":" + str(exc)[:180], file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
