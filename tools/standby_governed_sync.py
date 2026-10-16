#!/usr/bin/env python3
"""Governed, compare-and-swap Azure standby ref writer. GitHub stays primary."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Callable
from tools.standby_safe_ref_plan import plan

ZERO = "0" * 40
EXPECTED = {"active_provider": "github", "standby_provider": "azure-devops",
            "mirroring_enabled": True, "failover_state": "inactive"}


class MirrorBlocked(RuntimeError):
    pass


def approved_authority(path: Path) -> None:
    """External operator-controlled authority; no implicit authorization."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise MirrorBlocked("missing or unreadable external mirroring authority") from exc
    if any(data.get(key) != expected for key, expected in EXPECTED.items()):
        raise MirrorBlocked("GitHub-primary mirroring authority not enabled")


def build_updates(github: dict, azure: dict, ancestor: Callable) -> tuple[list, dict]:
    result = plan(github, azure, ancestor)
    if not result["ready"]:
        raise MirrorBlocked("conflicting refs: no synchronization authorized")
    updates = []
    for row in result["add_only"]:
        updates.append({"name": row["ref"], "oldObjectId": ZERO, "newObjectId": row["new"]})
    for row in result["fast_forward_only"]:
        updates.append({"name": row["ref"], "oldObjectId": row["expected_old"],
                        "newObjectId": row["new"]})
    return updates, result


def apply_cas(github: dict, read_azure: Callable, ancestor: Callable,
              ref_update: Callable, authority_path: Path, independent_verify: Callable) -> dict:
    """Never replan after a failed CAS; never overwrite Azure-only refs."""
    approved_authority(authority_path)
    before = read_azure()
    updates, result = build_updates(github, before, ancestor)
    approved_authority(authority_path)
    if read_azure() != before:
        raise MirrorBlocked("Azure refs changed since plan; refusing stale updates")
    if updates:
        outcomes = ref_update(updates)
        if not isinstance(outcomes, list) or len(outcomes) != len(updates):
            raise MirrorBlocked("Azure ref update response missing or incomplete")
        if any(not item.get("success") for item in outcomes):
            raise MirrorBlocked("one or more Azure CAS ref updates failed; inspect before retry")
    after = independent_verify()
    if not isinstance(after, dict):
        raise MirrorBlocked("independent Azure readback unavailable")
    if any(after.get(name) != sha for name, sha in github.items()):
        raise MirrorBlocked("GitHub source refs do not match Azure readback")
    if any(after.get(name) != sha for name, sha in before.items() if name not in github):
        raise MirrorBlocked("Azure-only preservation failed")
    return {"verified": True, "applied_count": len(updates),
            "preserved_azure_only": len(result["preserve_azure_only"])}


def azure_ref_payload(updates: list) -> list:
    """Azure Git Refs Update API uses optimistic oldObjectId compare-and-swap."""
    return updates
