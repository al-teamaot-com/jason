from __future__ import annotations

import sqlite3
import shutil
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
