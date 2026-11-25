"""Root-published successor receipt reader; strictly read-only.

This program never grants authority or starts units. A separately approved
native transaction publishes the exact receipt only after retiring the old
user triggers. The current Stage E acceptance is independently preserved.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
import subprocess

ROOT = Path("/usr/local/lib/jason/pmv4-e-engineering-manager")
ENTRY = ROOT / "manager_guard.py"
RECEIPT = Path("/etc/jason-owner-release/pmv4-e/engineering-manager-system-authorized.json")
STAGE_E = RECEIPT.with_name("replacement-retirement-accepted.json")
STAGE_E_SHA256 = "a74d159851ca82cd1d94e996ee9469cc7ad923046d36f642c341a8a90fd20141"
LKG = "d1b8c196dadd4b672ec8ba47075f27bb61c98d63"
PARALLEL_RESULT = "e0fab889ba182db3092cfe55296dce66d27264834cfcaf1dd638f2b9d85f16be"
TIMERS = ("jason-pmv4-engineering.timer", "jason-self-heal-watchdog.timer")
SERVICES = tuple(x.replace(".timer", ".service") for x in TIMERS)
UNITS = TIMERS + SERVICES
ARTIFACTS = {
    "release_manager_host_runner.py": None,
    "pmv4_e_engineering_manager_client.py": None,
    "jason_self_heal_watchdog.py": None,
    "owner_approved_development_worker.py": "856eee72496931ca58d24997ba5c2ff172c81b74186b277b24efe238a414de27",
    "dependency_conflict_service.py": "517c6fd03033b13c1bfc2b3c261257fd9f5dcc3a281b1095872e7a19c920a8fa",
    "development-concurrency-scopes.json": "5d01893673c054b0f1636fffef8ad58c684e9352ef4b9136dcc2f33476e32423",
    "isolated_service_common.py": "b13b333e8463b2e32011872f4c82f0698ae7db001aaee8b28c089cd4dd110992",
}
ACTION = "RELOCATE-EXACT-PMV4-ENGINEERING-AND-WATCHDOG-MANAGERS"


class Denied(PermissionError):
    pass


def need(ok, why):
    if not ok:
        raise Denied("ENGINEERING_MANAGER_" + why)


def digest(raw):
    return sha256(raw).hexdigest()


def exact(value, size):
    return isinstance(value, str) and re.fullmatch("[0-9a-f]{" + str(size) + "}", value) is not None


def root_directory(path):
    meta = path.lstat()
    need(path.resolve() == path and stat.S_ISDIR(meta.st_mode) and meta.st_uid == meta.st_gid == 0
         and not meta.st_mode & 0o022, "DIRECTORY_CUSTODY")


def read(path, uid, mode=None):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as f:
        m = os.fstat(f.fileno())
        need(stat.S_ISREG(m.st_mode) and m.st_uid == m.st_gid == uid
             and m.st_nlink == 1 and not m.st_mode & 0o022
             and (mode is None or stat.S_IMODE(m.st_mode) == mode)
             and 0 < m.st_size <= 2000000, "FILE_CUSTODY")
        raw = f.read(2000001)
    need(len(raw) == m.st_size, "FILE_CHANGED")
    return raw


def validate_receipt(row):
    fields = {"schema_version", "action", "status", "candidate_sha", "rollback_sha",
              "scope_sha256", "approval_sha256", "stage_e_sha256", "parallel_result_sha256",
              "effective_policy_sha256", "guard_sha256", "unit_sha256", "artifact_sha256", "accepted_at"}
    need(isinstance(row, dict) and set(row) == fields and row["schema_version"] == "1.0"
         and row["action"] == ACTION and row["status"] == "accepted"
         and exact(row["candidate_sha"], 40) and row["rollback_sha"] == LKG
         and row["candidate_sha"] != LKG and row["stage_e_sha256"] == STAGE_E_SHA256
         and row["parallel_result_sha256"] == PARALLEL_RESULT
         and all(exact(row[k], 64) for k in ("scope_sha256", "approval_sha256",
                                            "effective_policy_sha256", "guard_sha256")),
         "RECEIPT_IDENTITY")
    for field, keys in (("unit_sha256", UNITS), ("artifact_sha256", ARTIFACTS)):
        need(isinstance(row[field], dict) and set(row[field]) == set(keys)
             and all(exact(x, 64) for x in row[field].values()), "EXACT_HASH_SET")
    need(all(row["artifact_sha256"][name] == pin for name, pin in ARTIFACTS.items() if pin),
         "PARALLEL_APPROVED_ARTIFACT_CHANGED")
    when = datetime.fromisoformat(row["accepted_at"])
    need(when.tzinfo is not None and when <= datetime.now(timezone.utc), "RECEIPT_TIME")
    return row


def properties(name, *, user):
    need(name in UNITS, "UNKNOWN_UNIT")
    cmd = ["/usr/bin/systemctl"]
    env = {"PATH": "/usr/bin:/bin", "HOME": "/home/al", "LANG": "C.UTF-8"}
    if user:
        cmd.append("--user")
        env.update(XDG_RUNTIME_DIR="/run/user/1000",
                   DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/1000/bus")
    args = ["LoadState", "ActiveState", "UnitFileState", "FragmentPath", "DropInPaths",
            "User", "Group", "NoNewPrivileges", "PrivateTmp", "ProtectSystem", "ProtectHome", "MainPID"]
    p = subprocess.run(cmd + ["show", name] + ["-p" + x for x in args],
                       capture_output=True, text=True, timeout=12, check=False, env=env)
    need(p.returncode in (0, 4), "SYSTEMD_READBACK_FAILED")
    values = dict(x.split("=", 1) for x in p.stdout.splitlines() if "=" in x)
    need("LoadState" in values and "ActiveState" in values, "SYSTEMD_READBACK_MISSING")
    return values


def verify_topology(query):
    for name in UNITS:
        old = query(name, user=True)
        need(old.get("LoadState") == "not-found" and old.get("ActiveState") == "inactive"
             and not old.get("FragmentPath") and not old.get("DropInPaths")
             and old.get("MainPID", "0") in ("", "0"), "OLD_USER_UNIT_NOT_RETIRED")
        new = query(name, user=False)
        need(new.get("LoadState") == "loaded" and new.get("FragmentPath") == "/etc/systemd/system/" + name
             and not new.get("DropInPaths"), "SYSTEM_UNIT_NOT_EXACT")
        if name in TIMERS:
            need(new.get("ActiveState") == "active" and new.get("UnitFileState") == "enabled",
                 "SYSTEM_TIMER_INACTIVE")
        else:
            need(new.get("ActiveState") in ("inactive", "activating", "active")
                 and all(new.get(k) == v for k, v in {
                     "User": "al", "Group": "al", "NoNewPrivileges": "yes",
                     "PrivateTmp": "yes", "ProtectSystem": "strict", "ProtectHome": "read-only",
                 }.items()), "SYSTEM_SERVICE_SANDBOX_CHANGED")


def verify_service_context(raw):
    # A UID check alone is insufficient; require the actual system-manager unit.
    paths = [line.split(":", 2)[-1] for line in raw.splitlines() if ":" in line]
    need(any(x == "/system.slice/" + service for x in paths for service in SERVICES),
         "NOT_IN_REVIEWED_SYSTEM_SERVICE")


def status(*, require_system=False):
    need(os.geteuid() == os.getegid() == 1000, "UNEXPECTED_SERVICE_ACCOUNT")
    for path in (ROOT, RECEIPT.parent, RECEIPT.parent.parent, Path("/etc/systemd/system")):
        root_directory(path)
    row = validate_receipt(json.loads(read(RECEIPT, 0, 0o444)))
    need(digest(read(STAGE_E, 0, 0o444)) == row["stage_e_sha256"], "ORIGINAL_STAGE_E_CHANGED")
    need(Path(__file__).resolve() == ENTRY and digest(read(ENTRY, 0, 0o444)) == row["guard_sha256"],
         "GUARD_CHANGED")
    need(Path("/opt/jason/current").resolve(strict=True).name == row["rollback_sha"], "RUNTIME_CHANGED")
    release = ROOT / "releases" / row["candidate_sha"]
    for path in (ROOT / "releases", release, release / "tools"):
        root_directory(path)
    artifacts = {}
    for name, expected in row["artifact_sha256"].items():
        saved = release / "tools" / name
        live = Path("/home/al/.local/lib/jason") / name
        need(digest(read(saved, 0, 0o444)) == expected
             and digest(read(live, 1000)) == expected, "ARTIFACT_CHANGED:" + name)
        artifacts[name] = {"source": str(saved), "sha256": expected}
    for name, expected in row["unit_sha256"].items():
        need(digest(read(Path("/etc/systemd/system") / name, 0, 0o644)) == expected,
             "UNIT_BYTES_CHANGED")
    verify_topology(properties)
    if require_system:
        verify_service_context(Path("/proc/self/cgroup").read_text())
    return {"status": "verified_system_manager", "candidate_sha": row["candidate_sha"],
            "rollback_sha": row["rollback_sha"], "scope_sha256": row["scope_sha256"],
            "system_timers": list(TIMERS), "artifact_sources": artifacts,
            "production_authority": False}


def main():
    p = argparse.ArgumentParser()
    choice = p.add_mutually_exclusive_group(required=True)
    choice.add_argument("--status", action="store_true")
    choice.add_argument("--require-system", action="store_true")
    a = p.parse_args()
    try:
        print(json.dumps(status(require_system=a.require_system), sort_keys=True))
        return 0
    except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError) as exc:
        print("DENIED:" + type(exc).__name__ + ":" + str(exc)[:180])
        return 255


if __name__ == "__main__":
    raise SystemExit(main())
