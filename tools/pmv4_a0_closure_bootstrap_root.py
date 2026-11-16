#!/usr/bin/env python3
"""One-use exact root-trust bootstrap for the reviewed Stage A0 closure helper.

Root execution ONLY from a pre-reviewed, root-owned 0400 /run private stage.
One exact helper, one exact policy and one empty audit directory. No runtime,
MCP, protected-main, freeze, ticket, provider or promotion mutations.
The existing root lock and pinned Ed25519 owner verifier remain authoritative.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
from typing import Any, Mapping

SOURCE_SHA = "8c2064193d74cc41b52369681febbc0a74fa96f7"
LKG = "d1b8c196dadd4b672ec8ba47075f27bb61c98d63"
ACTION = "pmv4-stage-a0-root-source-closure-bootstrap-v1"
PLAN_SHA = "a4ea1463435fdeff50c9ae2e2322b899a22987f3fcac6b313f220834d01138f3"
SCOPE_SHA = "9e36a199cda7a176e893a17fdfeeedfb3782dce3f705886e29deed5867bf2837"
FREEZE_SHA = "bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f"
HOLD_SHA = "11f0f78904236c36ebd1aeee58f52fcecba035bce33d15ce323b36d36ad5a5a0"
MCP_IMAGE = "sha256:b2f74bf1513568f6c9df7a2ffa764b1a5f43303c8317702741d646f223db1477"
RUNTIME_IMAGE = "sha256:c43f9f7364a4b2b16bdec261fa35db2b861eabe959ba818f689582bbb1b7d132"
VERIFIER_SHA = "f50eea90102d9a1de82b3753ec8d0cd225280d385ac7a658ae2c2a303934a0e3"
ARCHIVE = Path("/srv/jason/archive")
PLAN = ARCHIVE / "pmv4-a0-closure-bootstrap-plan-8c20.json"
PROOF = ARCHIVE / "pmv4-a0-closure-bootstrap-OWNER-PROOF-8c20.json"
RELEASE = Path("/var/lib/jason/openclaw/release-manager")
LOCK = RELEASE / "production-transaction.lock"
CONTROL = RELEASE / "production-control-state.json"
DRIFT = RELEASE / "production-drift.json"
FREEZE = RELEASE / "production-deployment-freeze"
HOLD = RELEASE / "auto-promotion-incident-hold"
VERIFIER = Path("/usr/local/lib/jason/owner_signed_release.py")
ROOT_PIN = Path("/etc/jason-owner-release/verified-owner-public-key.json")
STAGE = Path("/run/jason-pmv4-a0-closure-bootstrap-8c20")
STAGED = STAGE / "installer.py"
LEDGER = Path("/etc/jason-owner-release/pmv4-stage-a0-root-source-closure-ledger")
JOURNAL = RELEASE / "protected-transitions/pmv4-a0-root-source-closure-bootstrap-8c20.json"
FILES = {
    "/usr/local/lib/jason/pmv4_stage_a0_root_source_closure.py":
        ("pmv4-a0-root-source-closure-8c20.py", "69a7fa57916290295f3f085f35a0fafa67c51110e2ce8dcc2b1b886ca5ed0e4d", 16909, 0o444),
    "/etc/jason-owner-release/pmv4-stage-a0-root-source-closure.json":
        ("pmv4-a0-root-source-closure-policy-8c20.json", "1af604a3e8b9459dfda7e5c617126378a3c58bc77f6a1819a6389eb8c1ff5079", 1206, 0o400),
}


class BootstrapDenied(PermissionError):
    pass


def must(condition: bool, code: str) -> None:
    if not condition:
        raise BootstrapDenied(code)


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical(obj: Mapping[str, Any]) -> bytes:
    return json.dumps(dict(obj), sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode()


def read_bounded(path: Path, maximum: int, expected: str | None = None,
                 *, uid: int | None = None, mode: int | None = None) -> bytes:
    must(not path.is_symlink(), "CLOSURE_BOOTSTRAP_SOURCE_SYMLINK_DENIED")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        m = os.fstat(fd)
        must(stat.S_ISREG(m.st_mode) and m.st_nlink == 1
             and 0 <= m.st_size <= maximum, "CLOSURE_BOOTSTRAP_SOURCE_NOT_REGULAR")
        if uid is not None:
            must(m.st_uid == uid, "CLOSURE_BOOTSTRAP_SOURCE_UID_DENIED")
        if mode is not None:
            must(stat.S_IMODE(m.st_mode) == mode, "CLOSURE_BOOTSTRAP_SOURCE_MODE_DENIED")
        raw = os.read(fd, maximum + 1)
        must(len(raw) == m.st_size, "CLOSURE_BOOTSTRAP_SOURCE_CHANGED")
        if expected is not None:
            must(digest(raw) == expected, "CLOSURE_BOOTSTRAP_SOURCE_HASH_DRIFT")
        return raw
    finally:
        os.close(fd)


def trusted_execution() -> None:
    must(os.geteuid() == 0 and sys.flags.isolated == 1
         and Path(__file__).absolute() == STAGED and not STAGED.is_symlink(),
         "CLOSURE_BOOTSTRAP_TRUSTED_LOCAL_ROOT_REQUIRED")
    m = STAGE.lstat()
    must(stat.S_ISDIR(m.st_mode) and m.st_uid == 0 and m.st_gid == 0
         and stat.S_IMODE(m.st_mode) == 0o700,
         "CLOSURE_BOOTSTRAP_PRIVATE_ROOT_STAGE_REQUIRED")
    read_bounded(STAGED, 100000, uid=0, mode=0o400)
    read_bounded(VERIFIER, 100000, expected=VERIFIER_SHA, uid=0)
    must(not LEDGER.exists() and not LEDGER.is_symlink()
         and not JOURNAL.exists() and not JOURNAL.is_symlink(),
         "CLOSURE_BOOTSTRAP_ACTION_ALREADY_CLAIMED")


def validate_plan() -> tuple[dict[str, Any], dict[str, bytes]]:
    plan = json.loads(read_bounded(PLAN, 8000, expected=PLAN_SHA, uid=1000, mode=0o600))
    must(isinstance(plan, dict), "CLOSURE_BOOTSTRAP_PLAN_INVALID")
    scope = plan.get("scope_sha256")
    unsigned = {k: v for k, v in plan.items() if k != "scope_sha256"}
    must(scope == SCOPE_SHA and digest(canonical(unsigned)) == SCOPE_SHA,
         "CLOSURE_BOOTSTRAP_SCOPE_CHANGED")
    must(plan.get("schema_version") == "1.0"
         and plan.get("action") == ACTION
         and plan.get("source_sha") == SOURCE_SHA
         and plan.get("lkg_sha") == LKG
         and plan.get("freeze_sha256") == FREEZE_SHA
         and plan.get("hold_sha256") == HOLD_SHA
         and plan.get("runtime_image") == RUNTIME_IMAGE
         and plan.get("mcp_image") == MCP_IMAGE
         and plan.get("one_shot") is True
         and plan.get("production_install_authorized") is False
         and plan.get("approved_before_execution") is False
         and plan.get("owner_authentication") == "fresh-entra-oauth-ed25519-exact-action"
         and plan.get("one_directory") == str(LEDGER)
         and plan.get("journal") == str(JOURNAL)
         and plan.get("no_runtime_or_mcp_replacement") is True
         and plan.get("no_freeze_or_hold_mutation") is True
         and isinstance(plan.get("files"), list)
         and len(plan["files"]) == 2, "CLOSURE_BOOTSTRAP_PLAN_NOT_EXACT")
    rows = {entry.get("destination"): entry for entry in plan["files"]}
    must(set(rows) == set(FILES), "CLOSURE_BOOTSTRAP_FILE_SCOPE_CHANGED")
    blobs = {}
    for dest, (name, expected, size, mode) in FILES.items():
        entry = rows[dest]
        must(entry == {
            "source": str(ARCHIVE / name), "destination": dest,
            "sha256": expected, "size": size, "mode": format(mode, "04o"),
            "uid": 0, "gid": 0,
        }, "CLOSURE_BOOTSTRAP_FILE_METADATA_CHANGED")
        blobs[dest] = read_bounded(ARCHIVE / name, size, expected=expected,
                                   uid=1000, mode=0o600)
    return plan, blobs


def load_verifier():
    spec = importlib.util.spec_from_file_location("a0_closure_bootstrap_trusted_owner", VERIFIER)
    must(spec is not None and spec.loader is not None,
         "CLOSURE_BOOTSTRAP_VERIFIER_UNAVAILABLE")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def verify_owner(plan: Mapping[str, Any]) -> dict[str, Any]:
    row = json.loads(read_bounded(PROOF, 15000, uid=1000, mode=0o600))
    must(set(row) == {
        "schema_version", "action", "source_sha", "rollback_sha",
        "scope_sha256", "manifest_sha256", "signed_owner_proof", "status",
    } and row["schema_version"] == "1.0"
        and row["action"] == ACTION
        and row["source_sha"] == SOURCE_SHA
        and row["rollback_sha"] == LKG
        and row["scope_sha256"] == SCOPE_SHA
        and row["manifest_sha256"] == digest(canonical(plan))
        and row["status"] == "SIGNED_OWNER_EXACT_APPROVAL_NO_INSTALL",
        "CLOSURE_BOOTSTRAP_SIGNED_ENVELOPE_INVALID")
    verifier = load_verifier()
    proof = verifier.verify_exact_owner_release(
        row["signed_owner_proof"],
        public_key=verifier.read_pinned_root_owner_public_key(
            ROOT_PIN, require_root_owned=True,
        ), at=datetime.now(timezone.utc),
        expected_candidate_sha=SOURCE_SHA,
        expected_rollback_sha=LKG,
        expected_release_id="release-" + SOURCE_SHA[:16],
        expected_scope_sha256=SCOPE_SHA,
        expected_manifest_sha256=digest(canonical(plan)),
        expected_freeze_sha256=FREEZE_SHA,
    )
    must(proof["one_release_only"] is True and proof["standing_authority"] is False
         and proof["approval_id"].startswith("owner-mcp-"),
         "CLOSURE_BOOTSTRAP_OWNER_PROOF_NOT_ONE_USE")
    return {"approval_id": proof["approval_id"], "proof_sha256": digest(canonical(row))}


def readback() -> dict[str, str]:
    must(Path("/opt/jason/current").resolve(strict=True).name == LKG,
         "CLOSURE_BOOTSTRAP_LKG_CHANGED")
    must(digest(read_bounded(FREEZE, 10000)) == FREEZE_SHA
         and digest(read_bounded(HOLD, 10000)) == HOLD_SHA,
         "CLOSURE_BOOTSTRAP_FREEZE_OR_HOLD_CHANGED")
    control = json.loads(read_bounded(CONTROL, 200000))
    drift = json.loads(read_bounded(DRIFT, 200000))
    breaker = control.get("circuit_breaker", {})
    must(breaker.get("state") == "closed"
         and drift.get("status") == "pass"
         and drift.get("problems") == [],
         "CLOSURE_BOOTSTRAP_PRODUCTION_INTEGRITY_NOT_PASS")
    at = datetime.fromisoformat(str(drift.get("observed_at", "")).replace("Z", "+00:00"))
    age = (datetime.now(timezone.utc) - at).total_seconds()
    must(at.tzinfo is not None and -10 <= age <= 180,
         "CLOSURE_BOOTSTRAP_DRIFT_STALE")
    repo = "/home/al/.local/lib/jason/engineering-source-repo"
    revision = subprocess.check_output(
        ["git", "-c", "safe.directory=" + repo, "-C", repo,
         "rev-parse", "origin/main"],
        timeout=15, text=True).strip()
    must(revision == SOURCE_SHA, "CLOSURE_BOOTSTRAP_PROTECTED_MAIN_CHANGED")
    containers = json.loads(subprocess.check_output(
        ["docker", "inspect", "jason-runtime", "jason-mcp-pilot"],
        text=True, timeout=20))
    must(len(containers) == 2 and containers[0]["Image"] == RUNTIME_IMAGE
         and containers[1]["Image"] == MCP_IMAGE
         and containers[0]["State"]["Health"]["Status"] == "healthy"
         and containers[1]["State"]["Running"],
         "CLOSURE_BOOTSTRAP_PROTECTED_IMAGES_CHANGED")
    return {
        "lkg": LKG, "freeze": FREEZE_SHA, "hold": HOLD_SHA,
        "runtime_id": containers[0]["Id"], "mcp_id": containers[1]["Id"],
    }


def require_empty() -> None:
    for obj in (LEDGER, *[Path(x) for x in FILES]):
        must(not obj.exists() and not obj.is_symlink(),
             "CLOSURE_BOOTSTRAP_TARGET_ALREADY_EXISTS")
        meta = obj.parent.lstat()
        must(stat.S_ISDIR(meta.st_mode) and meta.st_uid == 0
             and not (meta.st_mode & 0o022),
             "CLOSURE_BOOTSTRAP_PARENT_NOT_ROOT_TRUSTED")


def fsync_parent(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                 | getattr(os, "O_NOFOLLOW", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


@contextmanager
def production_lock():
    fd = os.open(LOCK, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        m = os.fstat(fd)
        must(stat.S_ISREG(m.st_mode) and m.st_uid == 1000
             and m.st_nlink == 1 and not (m.st_mode & 0o002),
             "CLOSURE_BOOTSTRAP_LOCK_UNTRUSTED")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise BootstrapDenied("CLOSURE_BOOTSTRAP_RELEASE_BUSY") from exc
        yield
    finally:
        os.close(fd)


def audit_write(data: Mapping[str, Any], *, first: bool) -> None:
    parent = JOURNAL.parent.lstat()
    must(stat.S_ISDIR(parent.st_mode) and parent.st_uid == 0
         and not (parent.st_mode & 0o022), "CLOSURE_BOOTSTRAP_JOURNAL_PARENT_UNTRUSTED")
    raw = canonical(data) + b"\n"
    if first:
        out = JOURNAL
    else:
        out = JOURNAL.parent / (JOURNAL.name + ".tmp-" + str(os.getpid()))
    fd = os.open(out, os.O_CREAT | os.O_EXCL | os.O_WRONLY
                 | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        must(os.write(fd, raw) == len(raw), "CLOSURE_BOOTSTRAP_JOURNAL_SHORT_WRITE")
        os.fsync(fd)
    finally:
        os.close(fd)
    if not first:
        os.replace(out, JOURNAL)
    fsync_parent(JOURNAL.parent)


def verify_targets(blobs: Mapping[str, bytes]) -> None:
    info = LEDGER.lstat()
    must(stat.S_ISDIR(info.st_mode) and (info.st_uid, info.st_gid) == (0, 0)
         and stat.S_IMODE(info.st_mode) == 0o700
         and next(LEDGER.iterdir(), None) is None,
         "CLOSURE_BOOTSTRAP_LEDGER_NOT_EMPTY")
    for dest, (name, expected, size, mode) in FILES.items():
        raw = read_bounded(Path(dest), size, expected=expected, uid=0, mode=mode)
        must(raw == blobs[dest], "CLOSURE_BOOTSTRAP_ROOT_CONTENT_DRIFT")


def publish(blobs: Mapping[str, bytes], before: Mapping[str, str],
            *, after_step=None) -> None:
    created = []
    held_fds = []
    try:
        os.mkdir(LEDGER, 0o700)
        info = LEDGER.lstat()
        created.append((LEDGER, info.st_ino, info.st_dev, 0o700, None))
        os.chown(LEDGER, 0, 0)
        fsync_parent(LEDGER.parent)
        if after_step:
            after_step("created_ledger")
        for dest, (_, expected, size, mode) in sorted(FILES.items()):
            path = Path(dest)
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                         | getattr(os, "O_NOFOLLOW", 0), 0o600)
            held_fds.append(fd)
            info = os.fstat(fd)
            raw = blobs[dest]
            # Claim the new inode immediately, before any metadata or write
            # that might fail, so a partial file can always be recovered.
            created.append((path, info.st_ino, info.st_dev, mode, raw))
            os.fchown(fd, 0, 0)
            os.fchmod(fd, mode)
            must(os.write(fd, raw) == len(raw), "CLOSURE_BOOTSTRAP_SHORT_WRITE")
            os.fsync(fd)
            fsync_parent(path.parent)
            if after_step:
                after_step(dest)
        verify_targets(blobs)
        must(readback() == dict(before), "CLOSURE_BOOTSTRAP_PRODUCTION_CHANGED")
    except BaseException as original:
        unsafe = []
        for path, inode, dev, mode, raw in reversed(created):
            try:
                info = path.lstat()
                if (path.is_symlink() or info.st_ino != inode
                        or info.st_dev != dev or info.st_uid != 0):
                    unsafe.append(str(path))
                elif raw is not None:
                    observed = path.read_bytes()
                    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                            or stat.S_IMODE(info.st_mode) not in (0o600, mode)
                            or not raw.startswith(observed)):
                        unsafe.append(str(path))
                    else:
                        path.unlink()
                        fsync_parent(path.parent)
                elif (not stat.S_ISDIR(info.st_mode)
                      or stat.S_IMODE(info.st_mode) != 0o700
                      or next(path.iterdir(), None) is not None):
                    unsafe.append(str(path))
                else:
                    path.rmdir()
                    fsync_parent(path.parent)
            except OSError:
                unsafe.append(str(path))
        if unsafe:
            raise BootstrapDenied("CLOSURE_BOOTSTRAP_ROLLBACK_REQUIRES_REVIEW") from original
        raise BootstrapDenied("CLOSURE_BOOTSTRAP_ROLLBACK_TO_ABSENCE_VERIFIED") from original
    finally:
        # Holding each newly created inode open through readback and recovery
        # prevents an unlink/recreate attacker from reusing its inode number.
        for fd in held_fds:
            os.close(fd)


def execute() -> None:
    trusted_execution()
    with production_lock():
        plan, blobs = validate_plan()
        before = readback()
        require_empty()
        approval = verify_owner(plan)
        attempt = {
            "schema_version": "1.0", "action": ACTION,
            "candidate_sha": SOURCE_SHA, "rollback_sha": LKG,
            "scope_sha256": SCOPE_SHA, **approval,
            "status": "one_use_owner_claimed_before_root_mutation",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        audit_write(attempt, first=True)
        outcome = dict(attempt, status="needs_review")
        try:
            publish(blobs, before)
            outcome["status"] = "verified"
            outcome["installed_files"] = 2
            outcome["installed_empty_audit_directories"] = 1
        except Exception as exc:
            outcome["failure"] = type(exc).__name__ + ":" + str(exc)[:120]
            raise
        finally:
            outcome["verified_at"] = datetime.now(timezone.utc).isoformat()
            audit_write(outcome, first=False)
        print("PMV4_A0_EXACT_CLOSURE_ROOT_TRUST=VERIFIED")
        print("PRODUCTION_RUNTIME_OR_MCP_CHANGED=false")
        print("PRODUCTION_FREEZE_OR_HOLD_CHANGED=false")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", required=True)
    parser.parse_args()
    try:
        execute()
        return 0
    except (BootstrapDenied, OSError, ValueError, subprocess.SubprocessError) as exc:
        print("PMV4_A0_CLOSURE_BOOTSTRAP=DENIED "
              + type(exc).__name__ + ":" + str(exc)[:160], file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
