#!/usr/bin/env python3
"""Narrow, one-use PMv4 Stage A0 root-trust bootstrap.

This deliberately installs only the six hash-pinned root files and two empty
ledger directories in the signed exact-action plan. The executable must first
be copied into the fixed /run root-only staging directory and independently
matched to the reviewed hash before running. No standalone/root authority is
conferred on the stage, and no release, service or provider is changed.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tarfile
import time

SHA = "7b42ce983896711525de4c7955bf9fc43ac003d0"
LKG = "d1b8c196dadd4b672ec8ba47075f27bb61c98d63"
BUNDLE_SHA = "40ce2e9380c3864fcdcf42346a5857896db1c63cbf07b68e95ed9ae56a36761b"
PLAN_SHA = "49be6d4177ed33bdeae7fc27aa0f89f10fc0d45809220efbdb43543dc5805ff1"
SCOPE_SHA = "0ed4b2f8e65fd95a2890bac106ab03b5962d6cb73437fc8a2f869cde50c5ba37"
FREEZE_SHA = "bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f"
HOLD_SHA = "11f0f78904236c36ebd1aeee58f52fcecba035bce33d15ce323b36d36ad5a5a0"
VERIFIER_SHA = "f50eea90102d9a1de82b3753ec8d0cd225280d385ac7a658ae2c2a303934a0e3"
MCP_IMAGE = "sha256:b2f74bf1513568f6c9df7a2ffa764b1a5f43303c8317702741d646f223db1477"
RUNTIME_IMAGE = "sha256:c43f9f7364a4b2b16bdec261fa35db2b861eabe959ba818f689582bbb1b7d132"
APPROVED_ACTION = "pmv4-stage-a0-initial-root-trust-v1"
ARCHIVE = Path("/srv/jason/archive")
PLAN = ARCHIVE / ("pmv4-stage-a0-initial-root-trust-plan-" + SHA + ".json")
BUNDLE = ARCHIVE / ("pmv4-stage-a0-initial-root-trust-" + SHA + ".tar")
PROOF = ARCHIVE / ("pmv4-stage-a0-root-trust-OWNER-APPROVAL-" + SHA + ".json")
VERIFIER = Path("/usr/local/lib/jason/owner_signed_release.py")
ROOT_PUB = Path("/etc/jason-owner-release/verified-owner-public-key.json")
RELEASE = Path("/var/lib/jason/openclaw/release-manager")
READBACK = RELEASE / "protected-readback"
LOCK = RELEASE / "production-transaction.lock"
JOURNAL = RELEASE / "protected-transitions" / ("pmv4-a0-initial-root-trust-" + SHA + ".json")
STAGING = Path("/run/jason-pmv4-a0-root-trust-7b42ce983896")
STAGED_EXECUTABLE = STAGING / "installer.py"
REQUIRED_MODES = {
    "/usr/local/lib/jason/pmv4_stage_a0_issuer_activation.py": 0o444,
    "/usr/local/lib/jason/pmv4_stage_a0_sparse_source.py": 0o444,
    "/usr/local/lib/jason/pmv4_stage_a0_sparse_root_stage.py": 0o444,
    "/usr/local/lib/jason/pmv4_shadow_ci.py": 0o444,
    "/etc/jason-owner-release/pmv4-stage-a0-issuer-activation.json": 0o400,
    "/etc/jason-owner-release/pmv4-stage-a0-sparse-root-stage.json": 0o400,
}
REQUIRED_DIRS = {
    "/etc/jason-owner-release/pmv4-stage-a0-issuer-ledger",
    "/etc/jason-owner-release/pmv4-stage-a0-sparse-root-stage-ledger",
}


class Denied(RuntimeError):
    pass


def must(condition: bool, message: str) -> None:
    if not condition:
        raise Denied(message)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def read_bounded(path: Path, maximum: int, expected: str | None = None) -> bytes:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        metadata = os.fstat(fd)
        must(stat.S_ISREG(metadata.st_mode) and metadata.st_nlink == 1 and metadata.st_size <= maximum,
             "UNTRUSTED_SOURCE_OBJECT")
        data = os.read(fd, maximum + 1)
        must(len(data) == metadata.st_size, "SOURCE_FILE_CHANGED")
        if expected:
            must(sha(data) == expected, "PINNED_SOURCE_HASH_CHANGED")
        return data
    finally:
        os.close(fd)


def root_owned_file(path: Path, *, mode: int | None = None) -> None:
    metadata = path.lstat()
    must(stat.S_ISREG(metadata.st_mode) and metadata.st_uid == 0 and metadata.st_nlink == 1,
         "ROOT_FILE_OWNERSHIP_OR_TYPE_INVALID")
    must(metadata.st_mode & 0o022 == 0, "ROOT_FILE_WRITABLE")
    if mode is not None:
        must(stat.S_IMODE(metadata.st_mode) == mode, "ROOT_FILE_MODE_INVALID")


def check_trusted_execution() -> None:
    must(os.geteuid() == 0, "LOCAL_ROOT_SESSION_REQUIRED")
    path = Path(__file__)
    must(path == STAGED_EXECUTABLE and not path.is_symlink(), "ROOT_STAGING_PATH_NOT_PINNED")
    folder = path.parent.lstat()
    must(stat.S_ISDIR(folder.st_mode) and folder.st_uid == 0
         and stat.S_IMODE(folder.st_mode) == 0o700, "ROOT_STAGE_NOT_PRIVATE")
    root_owned_file(path, mode=0o400)
    root_owned_file(VERIFIER)
    must(sha(read_bounded(VERIFIER, 100_000)) == VERIFIER_SHA, "TRUSTED_VERIFIER_CHANGED")


def load_verifier():
    spec = importlib.util.spec_from_file_location("pinned_owner_verifier_a0", VERIFIER)
    must(spec is not None and spec.loader is not None, "ROOT_VERIFIER_LOAD_FAILED")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_exact_package() -> tuple[dict, dict[str, bytes]]:
    plan = json.loads(read_bounded(PLAN, 20_000, PLAN_SHA))
    signed_scope = plan.get("plan_sha256")
    must(signed_scope == SCOPE_SHA and sha(canonical({k:v for k,v in plan.items() if k != "plan_sha256"})) == SCOPE_SHA,
         "PLAN_SCOPE_MISMATCH")
    must(plan.get("action") == APPROVED_ACTION and plan.get("commit_sha") == SHA
         and plan.get("existing_lkg_sha") == LKG and plan.get("freeze_sha256") == FREEZE_SHA
         and plan.get("promotion_hold_sha256") == HOLD_SHA
         and plan.get("production_install_authorized") is False
         and plan.get("requires_separate_exact_owner_approval") is True,
         "PLAN_ACTION_BINDING_MISMATCH")
    files = plan.get("new_root_files")
    dirs = plan.get("new_root_directories")
    must(isinstance(files, list) and isinstance(dirs, list)
         and len(files) == 6 and len(dirs) == 2,
         "PLAN_OBJECT_COUNT_INVALID")
    must({row["destination"] for row in files} == set(REQUIRED_MODES)
         and {row["path"] for row in dirs} == REQUIRED_DIRS,
         "PLAN_UNEXPECTED_TARGET")
    for row in files:
        must(row["mode"] == format(REQUIRED_MODES[row["destination"]], "04o")
             and row["uid"] == row["gid"] == 0
             and row["bundle_member"] == row["destination"].lstrip("/")
             and row["size"] <= 100_000,
             "PLAN_FILE_METADATA_INVALID")
    for row in dirs:
        must(row["mode"] == "0700" and row["uid"] == row["gid"] == 0,
             "PLAN_DIRECTORY_METADATA_INVALID")
    for item in plan["preexisting_root_trust"]:
        root_owned_file(Path(item["path"]))
        must(sha(read_bounded(Path(item["path"]), 100_000)) == item["sha256"],
             "ROOT_EXISTING_TRUST_CHANGED")

    tar_bytes = read_bounded(BUNDLE, 2_000_000, BUNDLE_SHA)
    content = {}
    with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:") as tar:
        members = tar.getmembers()
        must(len(members) == 9, "PACKAGE_MEMBER_COUNT_INVALID")
        observed = set()
        expected = set(row["bundle_member"] for row in files) | set(x.lstrip("/") for x in REQUIRED_DIRS) | {"_metadata/reviewed-exact-action.json"}
        for item in members:
            must(item.name in expected and item.name not in observed,
                 "PACKAGE_PATH_EXTRA_OR_DUPLICATE")
            observed.add(item.name)
            must(item.uid == item.gid == 0 and item.mtime == 0
                 and not item.issym() and not item.islnk() and not item.isdev(),
                 "PACKAGE_UNSAFE_METADATA")
            if item.name == "_metadata/reviewed-exact-action.json":
                must(item.isfile() and item.mode == 0o400
                     and tar.extractfile(item).read() == canonical(plan) + b"\n",
                     "PACKAGE_PLAN_CHANGED")
            elif item.isdir():
                must(item.isdir() and item.mode == 0o700,
                     "PACKAGE_DIRECTORY_INVALID")
            else:
                row = next(x for x in files if x["bundle_member"] == item.name)
                blob = tar.extractfile(item).read()
                must(item.isfile() and item.mode == int(row["mode"], 8)
                     and item.size == row["size"] and sha(blob) == row["sha256"],
                     "PACKAGE_FILE_INVALID")
                content[row["destination"]] = blob
        must(observed == expected, "PACKAGE_OBJECTS_MISSING")
    return plan, content


def verify_signed_approval(plan: dict) -> dict:
    proof = json.loads(read_bounded(PROOF, 20_000))
    must(set(proof) == {"schema_version", "action", "scope_sha256", "source_sha",
                            "rollback_sha", "bundle_sha256", "signed_owner_proof", "status"},
         "PROOF_ENVELOPE_FIELDS_INVALID")
    must(proof["schema_version"] == "1.0" and proof["action"] == APPROVED_ACTION
         and proof["scope_sha256"] == SCOPE_SHA and proof["source_sha"] == SHA
         and proof["rollback_sha"] == LKG and proof["bundle_sha256"] == BUNDLE_SHA
         and proof["status"] == "AUTHENTICATED_APPROVAL_NOT_PRODUCTION_INSTALL",
         "PROOF_ENVELOPE_SCOPE_INVALID")
    module = load_verifier()
    key = module.read_pinned_root_owner_public_key(ROOT_PUB, require_root_owned=True)
    payload = module.verify_exact_owner_release(
        proof["signed_owner_proof"], public_key=key,
        at=datetime.now(timezone.utc), expected_candidate_sha=SHA,
        expected_rollback_sha=LKG, expected_release_id="release-" + SHA[:16],
        expected_scope_sha256=SCOPE_SHA,
        expected_manifest_sha256=sha(canonical(plan)),
        expected_freeze_sha256=FREEZE_SHA,
    )
    must(payload["approval_id"].startswith("owner-mcp-") and payload["one_release_only"] is True,
         "PROOF_NO_ONE_SHOT_APPROVAL")
    return {"approval_id": payload["approval_id"], "proof_sha256": sha(canonical(proof))}


def preflight_production() -> None:
    must(Path("/opt/jason/current").resolve(strict=True).name == LKG, "PRODUCTION_LKG_CHANGED")
    must(sha(read_bounded(RELEASE / "production-deployment-freeze", 10_000)) == FREEZE_SHA,
         "PRODUCTION_FREEZE_CHANGED")
    must(sha(read_bounded(RELEASE / "auto-promotion-incident-hold", 10_000)) == HOLD_SHA,
         "PRODUCTION_HOLD_CHANGED")
    control = json.loads(read_bounded(READBACK / "production-control-state.json", 50_000))
    drift = json.loads(read_bounded(READBACK / "production-drift.json", 50_000))
    breaker = control.get("circuit_breaker") or {}
    must(breaker.get("state") == "closed" and breaker.get("revalidated_revision") == LKG,
         "PRODUCTION_BREAKER_NOT_ROOT_CLOSED")
    must(drift.get("status") == "pass" and drift.get("problems") == [],
         "PRODUCTION_DRIFT_NOT_PASS")
    observed = datetime.fromisoformat(drift["observed_at"].replace("Z", "+00:00"))
    age = (datetime.now(timezone.utc) - observed).total_seconds()
    must(observed.tzinfo is not None and 0 <= age <= 180, "PRODUCTION_DRIFT_STALE")
    health_path = Path("/var/lib/jason/openclaw/operational-health.json")
    health = json.loads(read_bounded(health_path, 40_000))
    health_age = time.time() - health_path.stat().st_mtime
    must(0 <= health_age <= 600 and health.get("full_proof_age_seconds", 999999) <= 86400,
         "PRODUCTION_AUTHORITY_HEALTH_STALE")
    must(health.get("status") == "pass" and health.get("full_proof_status") == "pass"
         and health.get("snapshot_source_exit_code") == 0 and health.get("failures") == [],
         "PRODUCTION_AUTHORITY_HEALTH_NOT_PASS")
    unit = subprocess.run(["/usr/bin/systemctl", "show", "jason-openclaw-authority-health.service",
                           "--property=Result", "--property=ExecMainStatus"],
                          text=True, capture_output=True, check=True, timeout=12)
    outcome = dict(s.split("=", 1) for s in unit.stdout.splitlines() if "=" in s)
    must(outcome.get("Result") == "success" and outcome.get("ExecMainStatus") == "0",
         "PRODUCTION_AUTHORITY_ONESHOT_FAILED")
    docker = json.loads(subprocess.check_output(
        ["/usr/bin/docker", "inspect", "jason-mcp-pilot", "jason-runtime"], timeout=16, text=True))
    must(len(docker) == 2 and docker[0]["Image"] == MCP_IMAGE and docker[1]["Image"] == RUNTIME_IMAGE,
         "PRODUCTION_IMAGES_CHANGED")
    must(docker[0]["State"]["Running"] and docker[1]["State"]["Health"]["Status"] == "healthy",
         "PRODUCTION_RUNTIME_UNHEALTHY")
    must("JASON_PMV4_STAGE_A0_ISSUER_ENABLED=false" in docker[0]["Config"]["Env"],
         "ISSUER_MUST_REMAIN_DISABLED")


def check_absent() -> None:
    must(not JOURNAL.exists() and not JOURNAL.is_symlink(), "ROOT_TRUST_ACTION_ALREADY_CLAIMED")
    for target in [*REQUIRED_MODES, *REQUIRED_DIRS]:
        p = Path(target)
        must(not p.exists() and not p.is_symlink(), "ROOT_TRUST_TARGET_NOT_EMPTY")
        parent = p.parent.lstat()
        must(stat.S_ISDIR(parent.st_mode) and parent.st_uid == 0
             and not (parent.st_mode & 0o022), "ROOT_TRUST_PARENT_UNTRUSTED")


def fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def audit_write(record: dict, *, first: bool) -> None:
    parent = JOURNAL.parent.lstat()
    must(stat.S_ISDIR(parent.st_mode) and parent.st_uid == 0
         and not (parent.st_mode & 0o022), "ROOT_AUDIT_PARENT_INVALID")
    if first:
        fd = os.open(JOURNAL, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            data = canonical(record) + b"\n"
            must(os.write(fd, data) == len(data), "ROOT_AUDIT_INITIAL_WRITE_FAILED")
            os.fsync(fd)
        finally:
            os.close(fd)
        fsync_dir(JOURNAL.parent)
    else:
        root_owned_file(JOURNAL, mode=0o600)
        stage = JOURNAL.parent / (JOURNAL.name + ".pending-" + str(os.getpid()))
        fd = os.open(stage, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            data = canonical(record) + b"\n"
            must(os.write(fd, data) == len(data), "ROOT_AUDIT_REWRITE_FAILED")
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(stage, JOURNAL)
        fsync_dir(JOURNAL.parent)


def publish_targets(plan: dict, content: dict[str, bytes], audit: dict) -> None:
    created_files: list[tuple[Path, int, int, bytes]] = []
    created_dirs: list[tuple[Path, int]] = []
    try:
        for row in sorted(plan["new_root_directories"], key=lambda r:r["path"]):
            path = Path(row["path"])
            os.mkdir(path, 0o700)
            meta = path.lstat()
            must(meta.st_uid == 0 and stat.S_IMODE(meta.st_mode) == 0o700, "AUDIT_DIRECTORY_READBACK_FAILED")
            created_dirs.append((path, meta.st_ino))
            fsync_dir(path.parent)
        for row in sorted(plan["new_root_files"], key=lambda r:r["destination"]):
            path = Path(row["destination"])
            raw = content[str(path)]
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
            try:
                metadata = os.fstat(fd)
                os.fchmod(fd, int(row["mode"], 8))
                created_files.append((path, metadata.st_ino, int(row["mode"], 8), raw))
                must(os.write(fd, raw) == len(raw), "ROOT_OBJECT_SHORT_WRITE")
                os.fsync(fd)
            finally:
                os.close(fd)
            fsync_dir(path.parent)
        verify_installed(plan, content)
        preflight_production()  # independent post-readback; no service changes permitted
        audit["status"] = "verified_installed"
        audit["installed_files"] = len(created_files)
        audit["installed_directories"] = len(created_dirs)
        audit["verified_at"] = datetime.now(timezone.utc).isoformat()
        audit_write(audit, first=False)
    except BaseException as original:
        unsafe = []
        for path, inode, mode, original_bytes in reversed(created_files):
            try:
                meta = path.lstat()
                observed_bytes = path.read_bytes()
                if (not stat.S_ISREG(meta.st_mode) or meta.st_ino != inode or meta.st_uid != 0
                        or stat.S_IMODE(meta.st_mode) != mode
                        or not original_bytes.startswith(observed_bytes)):
                    unsafe.append(str(path))
                else:
                    path.unlink()
                    fsync_dir(path.parent)
            except OSError:
                unsafe.append(str(path))
        for path, inode in reversed(created_dirs):
            try:
                meta = path.lstat()
                if (not stat.S_ISDIR(meta.st_mode) or meta.st_ino != inode or meta.st_uid != 0
                        or stat.S_IMODE(meta.st_mode) != 0o700 or next(path.iterdir(), None) is not None):
                    unsafe.append(str(path))
                else:
                    path.rmdir()
                    fsync_dir(path.parent)
            except OSError:
                unsafe.append(str(path))
        audit["status"] = "rollback_requires_review" if unsafe else "verified_empty_rollback"
        audit["failure_type"] = type(original).__name__
        audit["rollback_foreign_or_unverifiable_count"] = len(unsafe)
        audit["verified_at"] = datetime.now(timezone.utc).isoformat()
        audit_write(audit, first=False)
        if unsafe:
            raise Denied("ROOT_TRUST_INSTALL_FAILED_AND_ROLLBACK_REQUIRES_REVIEW") from original
        raise Denied("ROOT_TRUST_INSTALL_FAILED_ROLLBACK_VERIFIED") from original


def verify_installed(plan: dict, content: dict[str, bytes]) -> None:
    for pathstr, raw in content.items():
        path = Path(pathstr)
        root_owned_file(path, mode=REQUIRED_MODES[pathstr])
        must(path.read_bytes() == raw, "ROOT_INSTALLED_FILE_HASH_DRIFT")
    for target in REQUIRED_DIRS:
        p = Path(target)
        meta = p.lstat()
        must(stat.S_ISDIR(meta.st_mode) and meta.st_uid == 0
             and stat.S_IMODE(meta.st_mode) == 0o700
             and next(p.iterdir(), None) is None, "ROOT_INSTALLED_AUDIT_DIR_NOT_EMPTY")


def execute() -> None:
    check_trusted_execution()
    # The existing release lock protects the entire proof consumption and install.
    metadata = LOCK.lstat()
    must(stat.S_ISREG(metadata.st_mode) and metadata.st_nlink == 1 and metadata.st_uid == 1000
         and not (metadata.st_mode & 0o002), "RELEASE_TRANSACTION_LOCK_UNTRUSTED")
    lock = os.open(LOCK, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise Denied("RELEASE_TRANSACTION_BUSY") from exc
        plan, content = parse_exact_package()
        preflight_production()
        check_absent()
        approval = verify_signed_approval(plan)
        # The journal claims the one-use exact Owner decision BEFORE any install.
        audit = {"schema_version": "1.0", "action": APPROVED_ACTION,
                 "approval_id": approval["approval_id"],
                 "proof_sha256": approval["proof_sha256"],
                 "source_sha": SHA, "rollback_sha": LKG,
                 "bundle_sha256": BUNDLE_SHA, "scope_sha256": SCOPE_SHA,
                 "freeze_sha256": FREEZE_SHA, "hold_sha256": HOLD_SHA,
                 "status": "signed_owner_approval_consumed_install_started",
                 "created_at": datetime.now(timezone.utc).isoformat()}
        audit_write(audit, first=True)
        publish_targets(plan, content, audit)
        print("PMV4_A0_INITIAL_ROOT_TRUST=VERIFIED")
        print("EXACT_ROOT_FILES=6")
        print("EXACT_ROOT_EMPTY_AUDIT_DIRECTORIES=2")
        print("PRODUCTION_MCP_RUNTIME_UNCHANGED=true")
        print("PRODUCTION_FREEZE_HOLD_UNCHANGED=true")
        print("OWNER_PROOF_CONSUMED=" + approval["approval_id"])
    finally:
        os.close(lock)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", required=True)
    args = parser.parse_args()
    try:
        execute()
        return 0
    except Exception as exc:
        print("PMV4_A0_ROOT_TRUST=DENIED " + type(exc).__name__ + ":" + str(exc)[:140], file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
