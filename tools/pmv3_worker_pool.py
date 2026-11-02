#!/usr/bin/env python3
"""Device-agnostic PMV3 engineering worker-pool planning.

This module is intentionally provider-neutral. Device enrollment is authoritative
outside the role manifest; this layer only admits exact enrolled role instances
that are also independently attested healthy for the current scheduling cycle.
It does not provision devices, grant shell authority, or deploy production.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

POOL_SCHEMA = "1.0"
UID_PATTERN = re.compile(r"[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}\Z")
ACTIVE_PHASES = {"running", "verifying"}


class WorkerPoolError(ValueError):
    pass


def role_ref(role_id: str, role_version: str) -> str:
    if not role_id or not role_version or "@" in role_id or "@" in role_version:
        raise WorkerPoolError("invalid worker role identity")
    return f"{role_id}@{role_version}"


def parse_role_ref(value: str) -> tuple[str, str]:
    role_id, sep, version = str(value).partition("@")
    if not sep or not role_id or not version or "@" in version:
        raise WorkerPoolError("invalid worker role reference")
    return role_id, version


def validate_pool(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise WorkerPoolError("worker pool must be an object")
    required = {
        "schema_version", "pool_id", "default_role", "assignment_strategy",
        "lease", "members", "governance",
    }
    if set(value) != required:
        raise WorkerPoolError("worker pool has missing or unknown keys")
    if value["schema_version"] != POOL_SCHEMA:
        raise WorkerPoolError("unsupported worker pool schema")
    if not isinstance(value["pool_id"], str) or not value["pool_id"].strip():
        raise WorkerPoolError("worker pool id required")
    parse_role_ref(value["default_role"])
    if value["assignment_strategy"] != "least_loaded_then_device_uid":
        raise WorkerPoolError("unsupported worker assignment strategy")

    lease = value["lease"]
    if not isinstance(lease, dict) or set(lease) != {
        "fencing", "checkpoint_required", "reassign_after_worker_loss"
    }:
        raise WorkerPoolError("invalid worker lease contract")
    if (lease["fencing"] != "stable_action_key_plus_worker_claim"
            or lease["checkpoint_required"] is not True
            or lease["reassign_after_worker_loss"] is not True):
        raise WorkerPoolError("unsafe worker lease contract")

    governance = value["governance"]
    if not isinstance(governance, dict) or set(governance) != {
        "direct_provider_access", "production_deploy_authority",
        "production_secrets_allowed", "new_device_requires_owner_enrollment"
    }:
        raise WorkerPoolError("invalid worker pool governance")
    if (governance["direct_provider_access"] is not False
            or governance["production_deploy_authority"] is not False
            or governance["production_secrets_allowed"] is not False
            or governance["new_device_requires_owner_enrollment"] is not True):
        raise WorkerPoolError("worker pool broadens authority")

    members = value["members"]
    if not isinstance(members, list):
        raise WorkerPoolError("worker pool members must be a list")
    seen: set[str] = set()
    for member in members:
        if not isinstance(member, dict) or set(member) != {
            "device_uid", "target_name", "provider", "enrollment_status",
            "role_instances"
        }:
            raise WorkerPoolError("invalid worker pool member")
        uid = str(member["device_uid"])
        if not UID_PATTERN.fullmatch(uid) or uid in seen:
            raise WorkerPoolError("invalid or duplicate worker device identity")
        seen.add(uid)
        if not isinstance(member["target_name"], str) or not member["target_name"].strip():
            raise WorkerPoolError("worker target name required")
        if member["provider"] != "datto_rmm":
            raise WorkerPoolError("unsupported worker device provider")
        if member["enrollment_status"] not in {"approved_not_activated", "active", "draining", "retired"}:
            raise WorkerPoolError("invalid worker enrollment status")
        roles = member["role_instances"]
        if not isinstance(roles, list) or not roles:
            raise WorkerPoolError("worker requires at least one role instance")
        role_seen: set[str] = set()
        for role in roles:
            if not isinstance(role, dict) or set(role) != {
                "role_id", "role_version", "max_concurrency"
            }:
                raise WorkerPoolError("invalid worker role instance")
            ref = role_ref(str(role["role_id"]), str(role["role_version"]))
            if ref in role_seen:
                raise WorkerPoolError("duplicate worker role instance")
            role_seen.add(ref)
            if not isinstance(role["max_concurrency"], int) or not 1 <= role["max_concurrency"] <= 64:
                raise WorkerPoolError("invalid worker role concurrency")
    return value


def load_pool(path: Path) -> dict[str, Any]:
    return validate_pool(json.loads(path.read_text(encoding="utf-8")))


def load_health(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise WorkerPoolError("worker health must be an object")
    return value


def _attested(entry: Mapping[str, Any], required_role: str) -> bool:
    roles = entry.get("attested_roles")
    return (
        entry.get("ready") is True
        and entry.get("draining") is not True
        and isinstance(roles, list)
        and required_role in roles
    )


def eligible_slots(
    pool: Mapping[str, Any],
    health: Mapping[str, Any],
    *,
    required_role: str | None = None,
) -> dict[str, int]:
    validated = validate_pool(dict(pool))
    required = required_role or str(validated["default_role"])
    parse_role_ref(required)
    slots: dict[str, int] = {}
    for member in validated["members"]:
        uid = str(member["device_uid"])
        if member["enrollment_status"] != "active":
            continue
        status = health.get(uid)
        if not isinstance(status, Mapping) or not _attested(status, required):
            continue
        capacity = 0
        for role in member["role_instances"]:
            if role_ref(str(role["role_id"]), str(role["role_version"])) == required:
                capacity += int(role["max_concurrency"])
        if capacity:
            slots[uid] = capacity
    return slots


def available_capacity(pool: Mapping[str, Any], health: Mapping[str, Any]) -> int:
    return sum(eligible_slots(pool, health).values())


def assignment_plan(
    candidates: Sequence[Mapping[str, Any]],
    state: Mapping[str, Any],
    pool: Mapping[str, Any],
    health: Mapping[str, Any],
    *,
    max_assignments: int | None = None,
) -> dict[str, dict[str, str]]:
    """Return deterministic fenced worker claims for runnable work.

    The planner never mutates work state. The caller persists the selected worker
    together with the ordinary PMV3 action claim before execution.
    """
    validated = validate_pool(dict(pool))
    default_role = str(validated["default_role"])
    active_counts: dict[tuple[str, str], int] = {}
    for item in (state.get("items") or {}).values():
        if not isinstance(item, Mapping) or item.get("phase") not in ACTIVE_PHASES:
            continue
        uid = str(item.get("worker_id") or "")
        role = str(item.get("worker_role") or "")
        if uid and role:
            active_counts[(uid, role)] = active_counts.get((uid, role), 0) + 1

    limit = len(candidates) if max_assignments is None else max(0, int(max_assignments))
    assignments: dict[str, dict[str, str]] = {}
    for item in candidates:
        if len(assignments) >= limit:
            break
        item_id = str(item.get("id") or "")
        required = str(item.get("required_role") or default_role)
        slots = eligible_slots(validated, health, required_role=required)
        choices = []
        for uid, capacity in slots.items():
            used = active_counts.get((uid, required), 0)
            if used < capacity:
                choices.append((used, uid))
        if not item_id or not choices:
            continue
        _, uid = min(choices)
        assignments[item_id] = {"worker_id": uid, "worker_role": required}
        active_counts[(uid, required)] = active_counts.get((uid, required), 0) + 1
    return assignments
