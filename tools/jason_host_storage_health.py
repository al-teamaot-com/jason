"""Fail-closed, read-only host storage check for Jason's existing five-minute watchdog.

Production root and separate archive volume are explicitly checked. Uses
statvfs (same root-user-reserved-block semantics as df Use%) and inode capacity.
No file removal, Docker action, provider call, restart or notification is made.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any, Mapping

POLICY_PATH = Path(__file__).resolve().parents[1] / "config/operations/host-storage-capacity-v1.json"
ALLOWED_MOUNTS = {"root": "/", "archive": "/srv/jason/archive"}
GIB = 1024 ** 3


def read_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema_version") != "1.0":
        raise ValueError("host storage monitoring schema invalid")
    if data.get("monitoring_mode") != "read_only" or data.get("remediation") != "ticket_or_owner_approval_required":
        raise ValueError("host storage monitoring must remain read-only and governed")
    expected = [{"id": name, "path": target, "must_be_mount": True} for name, target in ALLOWED_MOUNTS.items()]
    if data.get("mounts") != expected:
        raise ValueError("monitored production mounts differ from reviewed allowlist")
    checks = (
        ("warning_used_percent", "critical_used_percent"),
        ("warning_inode_used_percent", "critical_inode_used_percent"),
    )
    for low, high in checks:
        a, b = data.get(low), data.get(high)
        if type(a) not in (int, float) or type(b) not in (int, float) or not (0 < a < b < 100):
            raise ValueError("storage usage thresholds are invalid")
    low, high = data.get("critical_available_gib"), data.get("warning_available_gib")
    if type(low) not in (int, float) or type(high) not in (int, float) or not (0 < low < high < 1024):
        raise ValueError("storage free-space thresholds are invalid")
    return data


def storage_capacity_failures(
    *, policy_path: Path = POLICY_PATH,
    statvfs=None, ismount=None,
) -> tuple[list[str], dict[str, Any]]:
    """One filesystem = one stable failure id, supporting idempotent incidents.

    Unreadable/missing data is unknown/degraded, never treated as healthy.
    The evidence contains quantities, never any customer file names.
    """
    statvfs = statvfs or os.statvfs
    ismount = ismount or os.path.ismount
    try:
        policy = read_policy(policy_path)
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return ["host_storage_monitor_unavailable:policy"], {
            "status": "unknown", "policy": str(policy_path), "mounts": {},
        }

    results: dict[str, dict[str, Any]] = {}
    failures: list[str] = []
    for spec in policy["mounts"]:
        name, path = spec["id"], spec["path"]
        entry: dict[str, Any] = {"path": path, "state": "unknown"}
        results[name] = entry
        try:
            if not ismount(path):
                failures.append("host_storage_mount_missing:" + name)
                entry["reason"] = "required_mount_not_mounted"
                continue
            stats = statvfs(path)
            blocksize = int(stats.f_frsize or stats.f_bsize)
            blocks, free_blocks, avail_blocks = int(stats.f_blocks), int(stats.f_bfree), int(stats.f_bavail)
            if (blocksize <= 0 or blocks <= 0 or free_blocks < 0
                    or avail_blocks < 0 or free_blocks > blocks or avail_blocks > free_blocks):
                raise ValueError("invalid filesystem capacity counters")
            used_bytes = (blocks - free_blocks) * blocksize
            available_bytes = avail_blocks * blocksize
            effective = used_bytes + available_bytes
            if effective <= 0:
                raise ValueError("invalid allocatable filesystem capacity")
            used_pct = (100.0 * used_bytes / effective)
            inode_total, inode_free = int(stats.f_files), int(stats.f_ffree)
            if inode_total < 0 or inode_free < 0 or inode_free > inode_total:
                raise ValueError("invalid inode counters")
            inode_used_pct = (100.0 * (inode_total - inode_free) / inode_total) if inode_total else None
            available_gib = available_bytes / GIB
            reasons: list[str] = []
            severe = (
                used_pct >= policy["critical_used_percent"]
                or available_gib < policy["critical_available_gib"]
                or (inode_used_pct is not None and inode_used_pct >= policy["critical_inode_used_percent"])
            )
            warning = (
                used_pct >= policy["warning_used_percent"]
                or available_gib < policy["warning_available_gib"]
                or (inode_used_pct is not None and inode_used_pct >= policy["warning_inode_used_percent"])
            )
            if used_pct >= policy["warning_used_percent"]:
                reasons.append("filesystem_occupancy")
            if available_gib < policy["warning_available_gib"]:
                reasons.append("allocatable_free_bytes")
            if inode_used_pct is not None and inode_used_pct >= policy["warning_inode_used_percent"]:
                reasons.append("inode_exhaustion")
            state = "critical" if severe else ("warning" if warning else "healthy")
            entry.update({
                "state": state,
                "used_percent": round(used_pct, 2),
                "available_gib": round(available_gib, 2),
                "used_gib": round(used_bytes / GIB, 2),
                "total_gib": round(blocks * blocksize / GIB, 2),
                "inode_used_percent": round(inode_used_pct, 2) if inode_used_pct is not None else None,
                "reasons": reasons,
            })
            if state != "healthy":
                failures.append("host_storage_capacity_" + state + ":" + name)
        except (OSError, TypeError, ValueError, OverflowError):
            entry["reason"] = "storage_probe_failed"
            failures.append("host_storage_probe_unavailable:" + name)
    return sorted(set(failures)), {"status": "degraded" if failures else "healthy", "mounts": results}


if __name__ == "__main__":
    failures, evidence = storage_capacity_failures()
    print(json.dumps({"failures": failures, "evidence": evidence}, sort_keys=True))
    raise SystemExit(0 if not failures else 2)
