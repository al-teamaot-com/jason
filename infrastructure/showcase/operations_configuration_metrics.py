#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RELEASE_STATES = (
    "requested",
    "development",
    "dev_verified",
    "release_candidate",
    "preproduction",
    "preprod_verified",
    "production_eligible",
    "production",
    "production_verified",
    "closed",
    "blocked",
    "failed",
    "rolled_back",
)

KNOWN_TIMER_DESCRIPTIONS = {
    "jason-release-manager.timer": "Promote production-eligible releases through guarded production closeout.",
    "jason-support-repair-worker.timer": "Reconcile approved Support List repairs and continue bounded repair work.",
    "jason-self-heal-watchdog.timer": "Detect degraded Jason invariants and run bounded self-heal checks.",
    "jason-provider-health-canary.timer": "Run governed synthetic provider-read health canaries.",
    "jason-documentation-reconciliation.timer": "Reconcile generated documentation/control-board state.",
    "jason-openclaw-authority-health.timer": "Verify OpenClaw/JKD-001 authority health.",
    "jason-delegation-maintenance.timer": "Maintain bounded delegation lifecycle state.",
    "jason-grafana-assurance.timer": "Verify Grafana/Prometheus source and provisioning integrity.",
    "jason-pr-integration-reconciler.timer": "Integrate eligible owner-approved development pull requests.",
    "jason-owner-approved-development-worker.timer": "Advance owner-approved TODO/support engineering work.",
    "jason-todo-engineering-intake.timer": "Admit eligible TODO work into governed engineering.",
    "jason-kfs-collector.timer": "Collect scheduled KFS copier telemetry.",
    "jason-dnsfilter-boundary-reconcile.timer": "Reconcile the governed DNSFilter boundary.",
    "jason-boot-recovery.timer": "Check boot recovery and post-restart health.",
    "jason-ccc.timer": "Run recurring constitutional/compliance certification checks.",
    "jason-openbao-backup.timer": "Create the scheduled OpenBao recovery backup/checkpoint.",
}


def metric_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _run(args: list[str], *, user_scope: bool = False, timeout: float = 3.0) -> subprocess.CompletedProcess[str] | None:
    env = os.environ.copy()
    if user_scope:
        uid = os.getuid()
        env["XDG_RUNTIME_DIR"] = f"/run/user/{uid}"
        env["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path=/run/user/{uid}/bus"
    try:
        return subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=env,
        )
    except (OSError, subprocess.SubprocessError):
        return None


def _safe_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _iso_to_epoch(value: object) -> float:
    text = str(value or "").strip()
    if not text:
        return 0.0
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def _timer_rows(user_scope: bool) -> list[dict[str, Any]]:
    command = ["systemctl"]
    if user_scope:
        command.append("--user")
    command += ["list-timers", "--all", "--output=json"]
    completed = _run(command, user_scope=user_scope, timeout=4.0)
    if completed is None or completed.returncode != 0:
        return []
    try:
        payload = json.loads(completed.stdout)
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    if not isinstance(payload, list):
        return []

    rows: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        unit = str(item.get("unit") or "")
        if not unit.startswith("jason-") or not unit.endswith(".timer"):
            continue
        service = str(item.get("activates") or "")
        rows.append(
            {
                "unit": unit,
                "service": service,
                "scope": "user" if user_scope else "system",
                "description": KNOWN_TIMER_DESCRIPTIONS.get(unit, unit.removesuffix(".timer").replace("jason-", "").replace("-", " ").title()),
                "next": float(item.get("next") or 0) / 1_000_000.0,
                "last": float(item.get("last") or 0) / 1_000_000.0,
            }
        )
    return rows


def _service_results(rows: list[dict[str, Any]], *, user_scope: bool) -> dict[str, str]:
    services = sorted({str(row.get("service") or "") for row in rows if row.get("service")})
    if not services:
        return {}
    command = ["systemctl"]
    if user_scope:
        command.append("--user")
    command += ["show", *services, "-p", "Id", "-p", "Result", "--no-pager"]
    completed = _run(command, user_scope=user_scope, timeout=4.0)
    if completed is None or completed.returncode != 0:
        return {}
    results: dict[str, str] = {}
    for block in completed.stdout.split("\n\n"):
        values: dict[str, str] = {}
        for line in block.splitlines():
            key, sep, value = line.partition("=")
            if sep:
                values[key.strip()] = value.strip()
        service_id = values.get("Id", "")
        if service_id:
            results[service_id] = values.get("Result", "") or "unknown"
    return results


def scheduled_tasks() -> list[dict[str, Any]]:
    system_rows = _timer_rows(False)
    user_rows = _timer_rows(True)
    system_results = _service_results(system_rows, user_scope=False)
    user_results = _service_results(user_rows, user_scope=True)
    for row in system_rows:
        row["last_result"] = system_results.get(str(row.get("service") or ""), "unknown")
    for row in user_rows:
        row["last_result"] = user_results.get(str(row.get("service") or ""), "unknown")
    return sorted(system_rows + user_rows, key=lambda row: str(row.get("unit") or ""))


def configuration_rows(repo_root: Path, runtime_env: dict[str, str]) -> list[dict[str, str]]:
    release = _safe_json(repo_root / "config" / "release-manager-policy.json")
    coordinator = _safe_json(repo_root / "config" / "development-release-coordinator.json")
    schedule = release.get("schedule") if isinstance(release.get("schedule"), dict) else {}
    production = release.get("production") if isinstance(release.get("production"), dict) else {}
    support = coordinator.get("support_autonomy") if isinstance(coordinator.get("support_autonomy"), dict) else {}
    todo = coordinator.get("todo_autonomy") if isinstance(coordinator.get("todo_autonomy"), dict) else {}
    integration = coordinator.get("integration_automation") if isinstance(coordinator.get("integration_automation"), dict) else {}

    def row(setting: str, value: object, source: str, change_mode: str = "governed_release") -> dict[str, str]:
        if isinstance(value, bool):
            rendered = "true" if value else "false"
        else:
            rendered = str(value if value is not None else "unknown")
        return {"setting": setting, "value": rendered, "source": source, "change_mode": change_mode}

    return [
        row(
            "autonomy.max_active_work_items",
            runtime_env.get("JASON_AUTONOMY_MAX_ACTIVE_WORK_ITEMS", "2"),
            "jason-runtime environment",
            "governed_runtime_change",
        ),
        row("release.automatic_promotion_enabled", schedule.get("automatic_promotion_enabled"), "config/release-manager-policy.json"),
        row("release.reconcile_interval_minutes", schedule.get("reconcile_interval_minutes"), "config/release-manager-policy.json"),
        row("release.max_concurrent_releases", schedule.get("max_concurrent_releases"), "config/release-manager-policy.json"),
        row("release.protected_core_owner_approval", production.get("protected_core_requires_owner_approval"), "config/release-manager-policy.json"),
        row("support.max_active_items", support.get("max_active_items"), "config/development-release-coordinator.json"),
        row("todo.max_active_items", todo.get("max_active_items"), "config/development-release-coordinator.json"),
        row("integration.max_prs_per_run", integration.get("max_prs_per_run"), "config/development-release-coordinator.json"),
    ]


def _failure_class(record: dict[str, Any]) -> str:
    failure = record.get("failure") if isinstance(record.get("failure"), dict) else {}
    message = str(failure.get("message") or "").casefold()
    if not message:
        return "none"
    if "host reconciliation" in message or "host-reconcile" in message:
        return "host_reconciliation"
    if "protected origin/main" in message or "protected main" in message:
        return "protected_main"
    if "documentation reconciliation" in message:
        return "documentation_reconciliation"
    if "preproduction" in message or "pre-production" in message:
        return "preproduction"
    if "required check" in message or "check run" in message or "github" in message:
        return "ci_validation"
    if "provider" in message and "canary" in message:
        return "provider_canary"
    return "other"


def _source_revision(record: dict[str, Any]) -> str:
    candidates = (
        (record.get("production") or {}).get("live_sha") if isinstance(record.get("production"), dict) else None,
        (record.get("release_candidate") or {}).get("candidate_sha") if isinstance(record.get("release_candidate"), dict) else None,
        (record.get("owner_approval") or {}).get("candidate_sha") if isinstance(record.get("owner_approval"), dict) else None,
        (record.get("development") or {}).get("source_sha") if isinstance(record.get("development"), dict) else None,
    )
    for value in candidates:
        text = str(value or "").strip().casefold()
        if len(text) == 40:
            return text
    return "unknown"


def release_migrations(records_dir: Path, *, limit: int = 12) -> list[dict[str, Any]]:
    try:
        paths = sorted(
            (path for path in records_dir.glob("release-*.json") if path.is_file()),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )[: max(1, int(limit))]
    except OSError:
        return []

    rows: list[dict[str, Any]] = []
    for path in paths:
        record = _safe_json(path)
        if not record:
            continue
        state = str(record.get("state") or "unknown")
        production = record.get("production") if isinstance(record.get("production"), dict) else {}
        failure = record.get("failure") if isinstance(record.get("failure"), dict) else {}
        rows.append(
            {
                "release_id": str(record.get("release_id") or path.stem),
                "source_revision": _source_revision(record),
                "rollback_revision": str(record.get("rollback_sha") or "unknown"),
                "state": state if state in RELEASE_STATES else "unknown",
                "blocker_class": _failure_class(record),
                "updated_at": _iso_to_epoch(record.get("updated_at")),
                "verified": 1 if bool(production.get("alignment_verified")) or state == "closed" else 0,
                "rollback_verified": (
                    1
                    if failure.get("rollback_verified") is True
                    else 0
                    if failure.get("rollback_verified") is False
                    else -1
                ),
            }
        )
    return rows


def render_metrics(repo_root: Path, records_dir: Path, runtime_env: dict[str, str]) -> list[str]:
    lines = [
        "# HELP jason_scheduled_task_info Jason-owned systemd timer inventory and last bounded result.",
        "# TYPE jason_scheduled_task_info gauge",
        "# HELP jason_scheduled_task_next_run_timestamp_seconds Unix timestamp of the next scheduled trigger.",
        "# TYPE jason_scheduled_task_next_run_timestamp_seconds gauge",
        "# HELP jason_scheduled_task_last_run_timestamp_seconds Unix timestamp of the last scheduled trigger.",
        "# TYPE jason_scheduled_task_last_run_timestamp_seconds gauge",
        "# HELP jason_scheduled_task_last_success Whether the last triggered service result was success.",
        "# TYPE jason_scheduled_task_last_success gauge",
    ]
    for row in scheduled_tasks():
        unit = metric_escape(str(row["unit"]))
        service = metric_escape(str(row["service"]))
        scope = metric_escape(str(row["scope"]))
        description = metric_escape(str(row["description"]))
        last_result = metric_escape(str(row.get("last_result") or "unknown"))
        labels = f'unit="{unit}",service="{service}",scope="{scope}"'
        lines.append(f'jason_scheduled_task_info{{{labels},description="{description}",last_result="{last_result}"}} 1')
        lines.append(f"jason_scheduled_task_next_run_timestamp_seconds{{{labels}}} {float(row.get('next') or 0):.6f}")
        lines.append(f"jason_scheduled_task_last_run_timestamp_seconds{{{labels}}} {float(row.get('last') or 0):.6f}")
        lines.append(f"jason_scheduled_task_last_success{{{labels}}} {1 if row.get('last_result') == 'success' else 0}")

    lines.extend(
        [
            "# HELP jason_system_configuration_info Curated secret-safe Jason operational configuration.",
            "# TYPE jason_system_configuration_info gauge",
        ]
    )
    for row in configuration_rows(repo_root, runtime_env):
        labels = ",".join(
            f'{key}="{metric_escape(str(row[key]))}"'
            for key in ("setting", "value", "source", "change_mode")
        )
        lines.append(f"jason_system_configuration_info{{{labels}}} 1")

    lines.extend(
        [
            "# HELP jason_release_migration_info Recent Release Manager migration/upgrade records with bounded blocker classification.",
            "# TYPE jason_release_migration_info gauge",
            "# HELP jason_release_migration_updated_timestamp_seconds Last update time for a Release Manager migration/upgrade record.",
            "# TYPE jason_release_migration_updated_timestamp_seconds gauge",
            "# HELP jason_release_migration_verified Whether production alignment/verification completed for the release migration.",
            "# TYPE jason_release_migration_verified gauge",
            "# HELP jason_release_migration_rollback_verified Rollback verification state: 1 verified, 0 failed, -1 not applicable/unknown.",
            "# TYPE jason_release_migration_rollback_verified gauge",
        ]
    )
    for row in release_migrations(records_dir):
        labels = (
            f'release_id="{metric_escape(str(row["release_id"]))}",'
            f'source_revision="{metric_escape(str(row["source_revision"]))}",'
            f'rollback_revision="{metric_escape(str(row["rollback_revision"]))}",'
            f'state="{metric_escape(str(row["state"]))}",'
            f'blocker_class="{metric_escape(str(row["blocker_class"]))}"'
        )
        lines.append(f"jason_release_migration_info{{{labels}}} 1")
        lines.append(f'jason_release_migration_updated_timestamp_seconds{{release_id="{metric_escape(str(row["release_id"]))}"}} {float(row["updated_at"]):.6f}')
        lines.append(f'jason_release_migration_verified{{release_id="{metric_escape(str(row["release_id"]))}"}} {int(row["verified"])}')
        lines.append(f'jason_release_migration_rollback_verified{{release_id="{metric_escape(str(row["release_id"]))}"}} {int(row["rollback_verified"])}')
    return lines
