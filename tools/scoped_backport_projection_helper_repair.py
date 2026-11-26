#!/usr/bin/env python3
"""One-use Owner-authenticated installation of a missing native Docker helper.

The root-installed deploy_live_container.py imports its pmv4_mcp_projection.py
sibling at module import. The approved installer accidentally omitted that
sibling; native stage therefore failed closed before creating eligibility.

This correction modifies ONLY the isolated root release-control installation,
its private SHA policy, and matching public attestation. It never modifies
production containers, their images, PMv4 services, AppRoles, provider state,
the frozen production policy or release approvals.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import argparse
import json
import os
from pathlib import Path
import pwd
import re
import stat
import subprocess
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from tools import scoped_backport_four_unit_drift_reconcile as base

OLD_MAIN = "24651789b5fc8ee79d46b54151ac36280e83efad"
OLD_REVIEWED = "0baeb8155758b04537bdca425b4578d13324efb0"
ROOT_DIR = Path("/usr/local/lib/jason/scoped-backport")
HOST_PATH = ROOT_DIR / "tools/scoped_backport_native_host.py"
MODULE_PATH = ROOT_DIR / "tools/pmv4_mcp_projection.py"
DEPLOY_PATH = ROOT_DIR / "tools/deploy_live_container.py"
ROOT_POLICY = Path("/etc/jason-owner-release/scoped-backport-installed.json")
PUBLIC = Path("/etc/jason-owner-release/scoped-backport-public-attestation.json")
ROOT_AUDIT = Path("/etc/jason-owner-release/scoped-backport-projection-dependency-repair")
ACTION = "INSTALL-SCOPED-BACKPORT-PINNED-PROJECTION-DEPENDENCY-V1"
CONFIRM = "APPROVE-SCOPED-BACKPORT-PROJECTION-DEPENDENCY-V1"
SCOPE_PATHS = (
    "tools/scoped_backport_projection_helper_repair.py",
    "tools/scoped_backport_native_host.py",
    "tools/scoped_backport_root_install.py",
    "tools/pmv4_mcp_projection.py",
    "tools/scoped_backport_four_unit_drift_reconcile.py",
)
HEX40 = re.compile(r"^[0-9a-f]{40}$")


def need(ok: bool, reason: str) -> None:
    if not ok:
        raise base.DriftCorrectionDenied("SCOPED_PROJECTION_" + reason)


def git(*args: str) -> bytes:
    p = subprocess.run(
        ["git", "-c", "safe.directory=" + str(REPO), "-C", str(REPO), *args],
        capture_output=True, timeout=30, check=False,
    )
    need(p.returncode == 0, "REVIEWED_GIT_UNAVAILABLE")
    return p.stdout


def source_verified(source_sha: str, reviewed_sha: str) -> None:
    """Pinned reviewed bytes remain valid after unrelated protected-main merges."""
    need(bool(HEX40.fullmatch(source_sha)) and
         bool(HEX40.fullmatch(reviewed_sha)), "SOURCE_SHA_INVALID")
    need(git("rev-parse", "HEAD").decode().strip() == source_sha,
         "LOCAL_SOURCE_SHA_CHANGED")
    need(git("status", "--porcelain") == b"", "SOURCE_WORKTREE_DIRTY")
    need(git("remote", "get-url", "origin").decode().strip() in {
        "https://github.com/al-teamaot-com/jason",
        "https://github.com/al-teamaot-com/jason.git",
    }, "SOURCE_ORIGIN_NOT_AOT")
    remote = git("ls-remote", "origin", "refs/heads/main").decode().strip().split()
    need(len(remote) == 2 and HEX40.fullmatch(remote[0])
         and remote[1] == "refs/heads/main",
         "LATEST_PROTECTED_MAIN_UNAVAILABLE")
    for ancestor, child in ((source_sha, remote[0]),
                            (reviewed_sha, source_sha),
                            (OLD_MAIN, source_sha)):
        p = subprocess.run(
            ["git", "-c", "safe.directory=" + str(REPO), "-C", str(REPO),
             "merge-base", "--is-ancestor", ancestor, child],
            capture_output=True, timeout=20, check=False)
        need(p.returncode == 0, "PROTECTED_SOURCE_LINEAGE_CHANGED")
    for relative in SCOPE_PATHS:
        source_file = REPO / relative
        need(not source_file.is_symlink() and source_file.is_file(),
             "REVIEWED_SOURCE_PATH_NOT_REGULAR")
        current = source_file.read_bytes()
        need(current == git("show", source_sha + ":" + relative)
             == git("show", reviewed_sha + ":" + relative)
             == git("show", remote[0] + ":" + relative),
             "CI_REVIEWED_PROJECTION_BYTES_CHANGED")
    # Root's previously reviewed control code and release scope must be
    # unchanged; this repair may not silently replace a different release.
    for relative in (
        "tools/scoped_backport_native_root.py",
        "tools/scoped_backport_release.py",
        "tools/scoped_backport_release_request.py",
        "tools/deploy_live_container.py",
        "config/scoped-backport-m365-release.json",
    ):
        need(git("show", OLD_MAIN + ":" + relative)
             == git("show", source_sha + ":" + relative)
             == git("show", remote[0] + ":" + relative),
             "EXISTING_NATIVE_RELEASE_SCOPE_CHANGED")
    base.require_ci_green(reviewed_sha)


def upgrade_policy(old: dict, *, source_sha: str,
                   reviewed_sha: str, host: bytes,
                   projection: bytes) -> dict:
    need(isinstance(old, dict) and old.get("schema_version") == "1.0"
         and old.get("profile") == "governed-scoped-backport-v1"
         and old.get("trusted_source_sha") == OLD_MAIN
         and old.get("reviewed_ci_sha") == OLD_REVIEWED
         and old.get("no_global_owner_elevation") is True
         and old.get("native_root_control_supported") is True
         and old.get("automatic_rollback_recovery_installed") is True
         and old.get("exact_signed_owner_approval_required") is True
         and "native_mcp_projection_sha256" not in old,
         "PREVIOUS_ROOT_POLICY_NOT_EXACT")
    expected_fields = set(base.ROOT_PATCH.keys())
    need(expected_fields == {
        "tools/scoped_backport_release.py",
        "tools/scoped_backport_native_root.py"
    }, "PREVIOUS_CORRECTION_SCOPE_CHANGED")
    new = dict(old)
    new["trusted_source_sha"] = source_sha
    new["reviewed_ci_sha"] = reviewed_sha
    new["native_host_sha256"] = sha256(host).hexdigest()
    new["native_mcp_projection_sha256"] = sha256(projection).hexdigest()
    return new


def inspect(*, source_sha: str, reviewed_sha: str) -> dict:
    need(os.geteuid() == 0 and os.environ.get("SUDO_USER") == "al",
         "AUTHENTICATED_LOCAL_SUDO_REQUIRED")
    source_verified(source_sha, reviewed_sha)
    installed = base.root_json(ROOT_POLICY)
    old_private = base.read_root(ROOT_POLICY)
    old_public = base.read_root(PUBLIC, mode=0o644)
    need(json.loads(old_public) == base.public_attestation(installed),
         "INSTALLED_PUBLIC_ATTESTATION_DRIFT")
    host_before = base.read_root(HOST_PATH, mode=0o444, maxsize=1_000_000)
    deploy_before = base.read_root(DEPLOY_PATH, mode=0o444, maxsize=1_000_000)
    need(sha256(host_before).hexdigest() == installed["native_host_sha256"]
         and sha256(deploy_before).hexdigest() == installed["native_deploy_sha256"]
         and host_before == git("show", OLD_MAIN + ":tools/scoped_backport_native_host.py")
         and deploy_before == git("show", OLD_MAIN + ":tools/deploy_live_container.py"),
         "INSTALLED_SOURCE_NOT_ORIGINAL_REVIEWED")
    need(not MODULE_PATH.exists() and not MODULE_PATH.is_symlink(),
         "PROJECTION_MODULE_ALREADY_PRESENT")
    projection = (REPO / "tools/pmv4_mcp_projection.py").read_bytes()
    host_after = (REPO / "tools/scoped_backport_native_host.py").read_bytes()
    policy_after = upgrade_policy(
        installed, source_sha=source_sha, reviewed_sha=reviewed_sha,
        host=host_after, projection=projection)
    private_after = (json.dumps(policy_after, sort_keys=True, indent=2)+"\n").encode()
    public_after = (json.dumps(base.public_attestation(policy_after),
                               sort_keys=True, indent=2)+"\n").encode()
    # It is a native code packaging correction; root breaker, health,
    # external images and production freeze must already be independently OK.
    control = base.root_json(base.ROOT_CONTROL)
    drift = base.root_json(base.ROOT_DRIFT)
    need((control.get("circuit_breaker") or {}).get("state") == "closed"
         and ((control.get("last_known_good") or {}).get("manifest") or {}).get("revision")
            == base.ROLLBACK_SHA,
         "PROTECTED_BREAKER_OR_LKG_NOT_VERIFIED")
    need(drift.get("status") == "pass" and drift.get("problems") == [],
         "INDEPENDENT_DRIFT_NOT_CLEAN")
    observed = datetime.fromisoformat(drift["observed_at"].replace("Z", "+00:00"))
    age = (datetime.now(timezone.utc) - observed).total_seconds()
    need(0 <= age <= 180, "DRIFT_EVIDENCE_STALE")
    freeze = sha256(base.FREEZE.read_bytes()).hexdigest()
    need(freeze == base.FREEZE_SHA256, "PRODUCTION_FREEZE_CHANGED")
    hold_sha = sha256(base.HOLD.read_bytes()).hexdigest()
    before_containers = base.live_snapshot()
    for folder in (base.SCOPED_REQUESTS, base.SCOPED_TRANSACTIONS,
                   base.SCOPED_OFFERS):
        need(folder.is_dir() and not folder.is_symlink()
             and not any(folder.iterdir()), "NATIVE_RELEASE_ALREADY_ACTIVE")
    for service in (base.SCOPED_TIMER, base.SCOPED_PATH):
        result = subprocess.run(["systemctl", "is-active", service],
                                capture_output=True, timeout=10)
        need(result.stdout.strip() == b"active",
             "SCOPED_LISTENER_NOT_ACTIVE")
    base.ensure_scoped_oneshots_quiescent()
    plan = {
        "schema_version": "1.0", "action": ACTION,
        "source_sha": source_sha, "reviewed_ci_sha": reviewed_sha,
        "old_trusted_source_sha": OLD_MAIN,
        "installed_module": str(MODULE_PATH),
        "module_sha256": sha256(projection).hexdigest(),
        "installed_native_host": str(HOST_PATH),
        "native_host_sha256_before": sha256(host_before).hexdigest(),
        "native_host_sha256_after": sha256(host_after).hexdigest(),
        "root_policy_sha256_before": sha256(old_private).hexdigest(),
        "root_policy_sha256_after": sha256(private_after).hexdigest(),
        "public_attestation_sha256_before": sha256(old_public).hexdigest(),
        "public_attestation_sha256_after": sha256(public_after).hexdigest(),
        "freeze_sha256": freeze, "hold_sha256": hold_sha,
        "rollback_revision": base.ROLLBACK_SHA,
        "paused_scoped_listeners_only": list((base.SCOPED_PATH, base.SCOPED_TIMER)),
        "standing_authority": False, "provider_writes": False,
        "production_promotion": False, "core_service_restarts": False,
        "unfreeze": False, "automatic_exact_rollback": True,
    }
    plan["scope_sha256"] = sha256(base.canonical(plan)).hexdigest()
    return {
        "plan": plan, "old_private": old_private,
        "new_private": private_after, "old_public": old_public,
        "new_public": public_after, "host_before": host_before,
        "host_after": host_after, "projection": projection,
        "containers": before_containers
    }


def create_root_module(data: bytes) -> None:
    need(not MODULE_PATH.exists() and not MODULE_PATH.is_symlink(),
         "PROJECTION_MODULE_ALREADY_PRESENT")
    fd = os.open(MODULE_PATH, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o444)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chown(MODULE_PATH, 0, 0)
        os.chmod(MODULE_PATH, 0o444)
        need(base.read_root(MODULE_PATH, mode=0o444) == data,
             "ROOT_PROJECTION_FILE_READBACK_FAILED")
        directory_fd = os.open(MODULE_PATH.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        pass


def remove_only_reviewed_module(data: bytes) -> None:
    need(base.read_root(MODULE_PATH, mode=0o444) == data,
         "FOREIGN_PROJECTION_MODULE_PREVENTS_ROLLBACK")
    os.unlink(MODULE_PATH)
    directory_fd = os.open(MODULE_PATH.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def apply(*, source_sha: str, reviewed_sha: str) -> dict:
    first = inspect(source_sha=source_sha, reviewed_sha=reviewed_sha)
    plan = first["plan"]
    print("ACTION=" + ACTION, flush=True)
    print("SOURCE_SHA=" + source_sha, flush=True)
    print("REVIEWED_CI_SHA=" + reviewed_sha, flush=True)
    print("MISSING_HELPER_SHA256=" + plan["module_sha256"], flush=True)
    print("ROOT_HOST_SHA256_AFTER=" + plan["native_host_sha256_after"], flush=True)
    print("ROOT_POLICY_SHA256_BEFORE=" + plan["root_policy_sha256_before"], flush=True)
    print("ROOT_POLICY_SHA256_AFTER=" + plan["root_policy_sha256_after"], flush=True)
    print("EXACT_SCOPE_SHA256=" + plan["scope_sha256"], flush=True)
    print("RUNTIME_MCP_TICKET_CORE_RESTARTS=0; GRAPH_POST=false; UNFREEZE=false", flush=True)
    need(sys.stdin.isatty() and sys.stdout.isatty(),
         "OWNER_LOCAL_TTY_REQUIRED")
    owner_oid = base.owner_sign_in()
    decision = input("Type " + CONFIRM + " to approve ONLY this helper repair: ")
    need(decision.strip() == CONFIRM, "EXACT_OWNER_CONSENT_NOT_GIVEN")
    second = inspect(source_sha=source_sha, reviewed_sha=reviewed_sha)
    need(first == second, "ROOT_SCOPE_CHANGED_AFTER_OWNER_AUTH")
    if not ROOT_AUDIT.exists():
        ROOT_AUDIT.mkdir(mode=0o700)
        os.chown(ROOT_AUDIT, 0, 0)
        os.chmod(ROOT_AUDIT, 0o700)
    need(ROOT_AUDIT.is_dir() and not ROOT_AUDIT.is_symlink()
         and ROOT_AUDIT.stat().st_uid == 0
         and stat.S_IMODE(ROOT_AUDIT.stat().st_mode) == 0o700,
         "AUDIT_BOUNDARY_UNTRUSTED")
    attempted = ROOT_AUDIT / (source_sha + ".attempt.json")
    completed = ROOT_AUDIT / (source_sha + ".complete.json")
    need(not attempted.exists() and not completed.exists(),
         "OWNER_APPROVAL_ALREADY_CONSUMED")
    base.audit_once(attempted, {
        "schema_version": "1.0", "status": "one_use_exact_owner_approval_consumed",
        "source_sha": source_sha, "reviewed_sha": reviewed_sha,
        "action": ACTION, "scope_sha256": plan["scope_sha256"],
        "owner_oid": owner_oid, "tenant": base.TENANT,
        "recorded_at": datetime.now(timezone.utc).isoformat()
    })
    changes = [
        (HOST_PATH, first["host_before"], first["host_after"], 0o444),
        (ROOT_POLICY, first["old_private"], first["new_private"], 0o600),
        (PUBLIC, first["old_public"], first["new_public"], 0o644),
    ]
    changed = []
    created = False
    listeners_paused = False
    success = False
    try:
        with base.production_lock():
            need(base.live_snapshot() == first["containers"],
                 "PROTECTED_PRODUCTION_CHANGED_UNDER_LOCK")
            need(sha256(base.FREEZE.read_bytes()).hexdigest() == plan["freeze_sha256"],
                 "FREEZE_CHANGED_UNDER_LOCK")
            listeners_paused = True
            base.listener_action("stop")
            base.ensure_scoped_oneshots_quiescent()
            created = True
            create_root_module(first["projection"])
            for path, before, after, mode in changes:
                changed.append((path, before, after, mode))
                base.atomic_exact_root_file(path, before, after, mode)
        base.listener_action("start")
        listeners_paused = False
        # No release request, restart, image swap or provider write in these
        # two independent executable/root-trust readbacks.
        # The original root handler invokes the deploy CLI with ordinary
        # python3 (not -I), allowing a root-owned sibling import. Testing
        # with -I would remove the script directory and create a false fail.
        exe = subprocess.run(
            ["/usr/bin/python3", "-E", str(DEPLOY_PATH), "--help"],
            capture_output=True, timeout=15)
        need(exe.returncode == 0 and b"--preflight" in exe.stdout,
             "INSTALLED_NATIVE_DEPLOY_IMPORT_STILL_MISSING")
        worker = subprocess.run(
            ["/usr/bin/python3", "-I",
             str(ROOT_DIR / "tools/scoped_backport_native_root.py"), "--drain"],
            capture_output=True, timeout=45)
        need(worker.returncode == 0, "NEW_ROOT_SHA_POLICY_NOT_ATTESTED")
        need(base.live_snapshot() == first["containers"]
             and sha256(base.FREEZE.read_bytes()).hexdigest() == plan["freeze_sha256"]
             and sha256(base.HOLD.read_bytes()).hexdigest() == plan["hold_sha256"],
             "PROTECTED_PRODUCTION_CHANGED")
        success = True
    finally:
        if not success:
            with base.production_lock():
                base.restore_attempted_root_files(changed)
                if created and MODULE_PATH.exists():
                    remove_only_reviewed_module(first["projection"])
            if listeners_paused:
                base.listener_action("start")
    # Stage diagnostics must never consume or issue Owner release approval.
    try:
        probe = subprocess.run(
            ["/usr/bin/python3", "-I",
             str(ROOT_DIR / "tools/scoped_backport_native_root.py"),
             "--probe-stage"],
            capture_output=True, timeout=150)
        probe_doc = json.loads(probe.stdout)
        safe_status = (probe_doc.get("status") if probe.returncode == 0 else
                       probe_doc.get("denial_code"))
        if not isinstance(safe_status, str) or not re.fullmatch(
                r"[A-Za-z0-9_]{4,110}", safe_status):
            safe_status = "SCOPED_PROJECTION_PROBE_RESULT_INVALID"
    except (OSError, ValueError, AttributeError, subprocess.TimeoutExpired):
        safe_status = "SCOPED_PROJECTION_PROBE_RESULT_UNREADABLE"
    base.audit_once(completed, {
        "schema_version": "1.0", "status": "installed_root_projection_dependency_attested",
        "source_sha": source_sha, "reviewed_sha": reviewed_sha,
        "scope_sha256": plan["scope_sha256"],
        "root_policy_sha256": plan["root_policy_sha256_after"],
        "owner_oid": owner_oid, "read_only_stage_probe": safe_status,
        "provider_writes": False, "release_approval_issued": False,
        "production_containers_replaced": False,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    })
    return {
        "status": "installed_root_projection_dependency_attested",
        "scope_sha256": plan["scope_sha256"], "source_sha": source_sha,
        "native_read_only_stage_probe": safe_status,
        "production_containers_changed": False, "provider_writes": False,
        "release_approved": False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--reviewed-ci-sha", required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true")
    group.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    # --check still uses root-protected readback, never mutates or asks OAuth.
    if args.check:
        doc = inspect(source_sha=args.source_sha, reviewed_sha=args.reviewed_ci_sha)
        print(json.dumps({"status": "verified_exact_projection_helper_repair_preflight",
                          "plan": doc["plan"], "production_mutations": False},
                         sort_keys=True, indent=2))
    else:
        print(json.dumps(apply(source_sha=args.source_sha,
                               reviewed_sha=args.reviewed_ci_sha),
                         sort_keys=True))


if __name__ == "__main__":
    main()
