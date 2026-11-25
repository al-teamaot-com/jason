#!/usr/bin/env python3
"""Bounded read-only adapters for Jason's existing service evidence.

The adapters do not call providers, execute actions, or consume protected root
release-control files. They summarize source records without copying secrets.
"""
from __future__ import annotations

import hashlib
import json
import os
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from provider_health_monitor_service import evaluate as evaluate_provider_health
    from work_reconciliation_service import reconcile as reconcile_work
except ModuleNotFoundError:
    from tools.provider_health_monitor_service import evaluate as evaluate_provider_health
    from tools.work_reconciliation_service import reconcile as reconcile_work

MAX_SOURCE_BYTES = 1024 * 1024
FUTURE_SKEW_SECONDS = 60


def timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError("missing observed timestamp")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("timestamp requires timezone")
    return result.astimezone(timezone.utc)


def source_age(value: Any, now: datetime, ttl: int) -> tuple[int | None, bool]:
    try:
        delta = (now - timestamp(value)).total_seconds()
    except (ValueError, TypeError, OverflowError):
        return None, False
    if delta < -FUTURE_SKEW_SECONDS:
        return None, False
    seconds = max(0, int(delta))
    return seconds, seconds <= ttl


def bounded_json_with_mtime(path: Path) -> tuple[dict[str, Any], str, datetime]:
    """Read one regular-file inode and its publisher mtime without following links."""
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_SOURCE_BYTES:
            raise ValueError("source is not a bounded regular file")
        with os.fdopen(os.dup(fd), "rb") as stream:
            data = stream.read(MAX_SOURCE_BYTES + 1)
        if len(data) > MAX_SOURCE_BYTES:
            raise ValueError("source exceeds bounded size")
        value = json.loads(data)
        if not isinstance(value, dict):
            raise ValueError("source JSON must be an object")
        return value, hashlib.sha256(data).hexdigest(), datetime.fromtimestamp(info.st_mtime, timezone.utc)
    finally:
        os.close(fd)


def bounded_json(path: Path) -> tuple[dict[str, Any], str]:
    value, digest, _ = bounded_json_with_mtime(path)
    return value, digest


def provider_canaries(source: dict[str, Any], *, now: datetime, max_age_seconds: int = 900) -> dict[str, Any]:
    generated = source.get("generated_at")
    age, fresh = source_age(generated, now, max_age_seconds)
    results = source.get("results")
    if not isinstance(results, list) or not results:
        return {"status": "unknown", "reason": "missing_provider_results", "age_seconds": age, "providers": []}
    receipts = []
    invalid = 0
    for item in results:
        if not isinstance(item, dict):
            invalid += 1
            continue
        name, healthy = item.get("provider"), item.get("healthy")
        if not isinstance(name, str) or not name.strip() or type(healthy) is not bool:
            invalid += 1
            continue
        receipts.append({"provider": name, "status": "ok" if healthy else "failed", "observed_at": generated, "source": "provider-health-canaries"})
    if not receipts:
        status, reason = "unknown", "no_valid_provider_receipts"
    elif not fresh:
        status, reason = "stale", "source_evidence_not_fresh"
    else:
        result = evaluate_provider_health(receipts, max_age_seconds=max_age_seconds, now=now)
        status, reason = result["status"], "canary_aggregation"
    if invalid:
        status, reason = "unknown", "invalid_provider_receipts"
    if len({r["provider"] for r in receipts}) != len(receipts):
        status, reason = "unknown", "duplicate_provider_receipts"
    return {"status": status, "reason": reason, "age_seconds": age, "providers": [{"provider": r["provider"], "health": "healthy" if r["status"] == "ok" and fresh else ("unhealthy" if r["status"] == "failed" and fresh else "stale")} for r in receipts], "receipt_count": len(receipts), "invalid_count": invalid}


def todo_commitments(source: dict[str, Any], *, now: datetime, max_age_seconds: int = 900) -> dict[str, Any]:
    age, fresh = source_age(source.get("updated_at"), now, max_age_seconds)
    items = source.get("items")
    if not isinstance(items, dict):
        return {"status": "unknown", "reason": "missing_commitment_items", "age_seconds": age, "counts": {}, "buckets": {}}
    clean = []
    for todo_id, value in sorted(items.items()):
        if not isinstance(todo_id, str) or not isinstance(value, dict):
            return {"status": "unknown", "reason": "invalid_commitment_entry", "age_seconds": age, "counts": {}, "buckets": {}}
        clean.append({"todo_id": todo_id, "issue_number": value.get("issue_number"), "phase": value.get("phase"), "reason": value.get("reason"), "next_action": value.get("next_action"), "retry_eligible": value.get("retry_eligible"), "blocker_category": value.get("blocker_category")})
    result = reconcile_work({"items": clean})
    result["age_seconds"] = age
    if not fresh:
        result["status"] = "stale"
        result["reason"] = "commitment_source_not_fresh"
    else:
        result["reason"] = "existing_commitment_ledger"
    return result


def rollback_protected_readback(control: dict[str, Any], drift: dict[str, Any], *,
                                now: datetime, max_age_seconds: int = 90,
                                control_published_at: datetime | None = None,
                                drift_published_at: datetime | None = None) -> dict[str, Any]:
    """Assess existing root-published readbacks without opening protected files.

    This is advisory only. The native Release Manager remains the sole authority
    for breaker state, rollback execution, and production acceptance.
    """
    import re
    if control.get("schema_version") != "1.0" or drift.get("schema_version") != "1.0":
        return {"status": "unknown", "reason": "invalid_release_readback_schema"}
    # The root publisher refreshes file mtime on every readback cycle; the
    # control's updated_at is the last breaker change, not publication time.
    control_clock = control_published_at.isoformat() if control_published_at else control.get("updated_at")
    drift_clock = drift_published_at.isoformat() if drift_published_at else drift.get("observed_at")
    control_age, control_fresh = source_age(control_clock, now, max_age_seconds)
    drift_age, drift_fresh = source_age(drift_clock, now, max_age_seconds)
    if not (control_fresh and drift_fresh):
        return {"status": "stale", "reason": "protected_readback_not_fresh",
                "control_age_seconds": control_age, "drift_age_seconds": drift_age}
    lkg = control.get("last_known_good")
    manifest = lkg.get("manifest") if isinstance(lkg, dict) else None
    if not isinstance(manifest, dict):
        return {"status": "unknown", "reason": "last_known_good_manifest_missing"}
    revision = manifest.get("revision")
    if not isinstance(revision, str) or re.fullmatch(r"[0-9a-f]{40}", revision) is None:
        return {"status": "unknown", "reason": "invalid_last_known_good_sha"}
    aligned = all(manifest.get(name) == revision for name in
                  ("runtime_revision", "mcp_revision", "host_revision", "release_manager_source_revision"))
    complete = (manifest.get("complete") is True and aligned and
                all(isinstance(manifest.get(key), str) and manifest[key].startswith("sha256:")
                    for key in ("runtime_image_id", "mcp_image_id")) and
                isinstance(manifest.get("scheduled_control_units"), dict))
    breaker = control.get("circuit_breaker")
    breaker_state = str(breaker.get("state") or "unknown") if isinstance(breaker, dict) else "unknown"
    drift_status = str(drift.get("status") or "unknown")
    problems = drift.get("problems") if isinstance(drift.get("problems"), list) else []
    if not complete:
        status, reason = "unknown", "last_known_good_manifest_incomplete_or_unaligned"
    elif breaker_state != "closed" or drift_status != "pass":
        status, reason = "blocked", "native_release_safety_hold"
    else:
        status, reason = "evidence_present", "fresh_protected_readback_and_complete_lkg"
    return {"status": status, "reason": reason, "rollback_sha": revision,
            "last_known_good_complete": complete, "circuit_breaker_state": breaker_state,
            "production_drift_status": drift_status, "drift_problem_count": len(problems),
            "control_age_seconds": control_age, "drift_age_seconds": drift_age,
            "advisory_only": True}
