"""Read the root-authorized manager routing without issuing authority."""
from __future__ import annotations
import json
from pathlib import Path
import re
import stat
import subprocess

RECEIPT = Path("/etc/jason-owner-release/pmv4-e/engineering-manager-system-authorized.json")
GUARD = Path("/usr/local/lib/jason/pmv4-e-engineering-manager/manager_guard.py")
SYSTEM_TIMERS = ["jason-pmv4-engineering.timer", "jason-self-heal-watchdog.timer"]
ARTIFACTS = {"release_manager_host_runner.py", "jason_self_heal_watchdog.py",
             "pmv4_e_engineering_manager_client.py",
             "owner_approved_development_worker.py", "dependency_conflict_service.py",
             "development-concurrency-scopes.json", "isolated_service_common.py"}


def read_routing():
    try:
        RECEIPT.lstat()
    except FileNotFoundError:
        # Presence of a staged native successor is never interpreted as a
        # legacy acceptance. Old code is retained until the bounded cutover.
        if GUARD.exists() or GUARD.is_symlink():
            raise PermissionError("ENGINEERING_MANAGER_SUCCESSOR_RECEIPT_MISSING")
        return None
    m = GUARD.lstat()
    d = GUARD.parent.lstat()
    if not (GUARD.resolve() == GUARD and stat.S_ISREG(m.st_mode) and m.st_uid == m.st_gid == 0
            and m.st_nlink == 1 and stat.S_IMODE(m.st_mode) == 0o444
            and stat.S_ISDIR(d.st_mode) and d.st_uid == d.st_gid == 0 and not d.st_mode & 0o022):
        raise PermissionError("ENGINEERING_MANAGER_SUCCESSOR_GUARD_UNTRUSTED")
    p = subprocess.run(["/usr/bin/python3", "-I", "-B", str(GUARD), "--status"],
                       capture_output=True, text=True, timeout=100, check=False)
    if p.returncode or len(p.stdout) > 20000:
        raise PermissionError("ENGINEERING_MANAGER_SUCCESSOR_GUARD_DENIED")
    j = json.loads(p.stdout)
    if not (isinstance(j, dict) and j.get("status") == "verified_system_manager"
            and j.get("system_timers") == SYSTEM_TIMERS and j.get("production_authority") is False
            and all(isinstance(j.get(k), str) and re.fullmatch("[0-9a-f]{40}", j[k])
                    for k in ("candidate_sha", "rollback_sha"))
            and set(j.get("artifact_sources", {})) == ARTIFACTS):
        raise PermissionError("ENGINEERING_MANAGER_SUCCESSOR_PROOF_INVALID")
    root = GUARD.parent / "releases" / j["candidate_sha"] / "tools"
    for name, row in j["artifact_sources"].items():
        if not (isinstance(row, dict) and row.get("source") == str(root / name)
                and isinstance(row.get("sha256"), str) and re.fullmatch("[0-9a-f]{64}", row["sha256"])):
            raise PermissionError("ENGINEERING_MANAGER_ARTIFACT_PROOF_INVALID")
    return j
