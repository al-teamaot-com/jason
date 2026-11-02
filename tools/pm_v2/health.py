from __future__ import annotations

import json
import sqlite3
import shutil
import time
from pathlib import Path
from typing import Any

from .config import PMV2Config
from .store import PMV2Store


def self_test(*, config: PMV2Config, store: PMV2Store, repo: Path) -> dict[str, Any]:
    checks: dict[str, Any] = {}
    checks["repo"] = {"ok": (repo / ".git").exists() or (repo / ".git").is_file(), "path": str(repo)}
    checks["roadmap"] = {"ok": config.roadmap_path.is_file(), "path": str(config.roadmap_path)}
    checks["support"] = {"ok": config.support_path.is_file(), "path": str(config.support_path)}
    try:
        store.initialize()
        with store.connect() as conn:
            conn.execute("SELECT 1").fetchone()
        db_ok = True
        db_error = None
    except (OSError, sqlite3.Error) as exc:
        db_ok = False
        db_error = type(exc).__name__
    checks["database"] = {"ok": db_ok, "path": str(store.path), "error": db_error}
    limits_enabled = any((
        config.subprocess_memory_mb,
        config.subprocess_cpu_seconds,
        config.subprocess_open_files,
    ))
    checks["resource_control"] = {
        "ok": (not limits_enabled) or shutil.which("prlimit") is not None,
        "prlimit": shutil.which("prlimit"),
        "memory_mb": config.subprocess_memory_mb,
        "cpu_seconds": config.subprocess_cpu_seconds,
        "open_files": config.subprocess_open_files,
        "cloud_spend_policy": config.cloud_spend_policy,
        "provider_authority_policy": config.provider_authority_policy,
    }
    if config.production_drift_readback_path is not None:
        drift_path = config.production_drift_readback_path
        try:
            metadata = drift_path.stat()
            age = max(0.0, time.time() - metadata.st_mtime)
            payload = json.loads(drift_path.read_text(encoding="utf-8"))
            problems = payload.get("problems") if isinstance(payload, dict) else None
            valid_problems = problems if isinstance(problems, list) else []
            problem_kinds = sorted({
                str(item.get("kind") or "unknown")
                for item in valid_problems if isinstance(item, dict)
            })
            drift_ok = (
                isinstance(payload, dict)
                and payload.get("schema_version") == "1.0"
                and payload.get("status") == "pass"
                and not valid_problems
                and age <= config.production_drift_maximum_age_seconds
            )
            checks["production_drift"] = {
                "ok": drift_ok,
                "status": payload.get("status") if isinstance(payload, dict) else "invalid",
                "problem_kinds": problem_kinds,
                "age_seconds": round(age, 3),
                "maximum_age_seconds": config.production_drift_maximum_age_seconds,
            }
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            checks["production_drift"] = {
                "ok": False,
                "status": "unavailable",
                "error_type": type(exc).__name__,
            }

    checks["configuration"] = {
        "ok": config.approval_channel == "microsoft_teams" and len(config.required_status_fields) == 5,
        "approval_channel": config.approval_channel,
        "required_status_fields": list(config.required_status_fields),
    }
    status = "healthy" if all(bool(item.get("ok")) for item in checks.values()) else "degraded"
    result = {"status": status, "checks": checks}
    try:
        store.record_health(component="pm_v2_core", instance_id=config.instance_id, status=status, details=result)
    except (OSError, sqlite3.Error):
        pass
    return result
