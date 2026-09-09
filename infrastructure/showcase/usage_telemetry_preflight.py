#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

MODEL_USAGE_DB = Path(
    os.environ.get(
        "JASON_MODEL_USAGE_DB",
        "/var/lib/jason/openclaw/model-usage.sqlite3",
    )
)
ORCHESTRATION_EVENTS_DB = Path(
    os.environ.get(
        "JASON_ORCHESTRATION_EVENTS_DB",
        "/var/lib/jason/openclaw/orchestration-events.sqlite3",
    )
)
IDENTITY_BINDINGS_DB = Path(
    os.environ.get(
        "JASON_TEAMS_IDENTITY_BINDINGS_DB",
        "/var/lib/jason/openclaw/teams-identity-bindings.sqlite3",
    )
)
RUNTIME_CONTAINER = os.environ.get("JASON_RUNTIME_CONTAINER", "jason-runtime").strip()

SAFE_ENV_KEYS = (
    "JASON_HOSTED_SEMANTICS_ENABLED",
    "JASON_HOSTED_CONVERSATION_ENABLED",
    "JASON_OPENAI_SEMANTIC_MODEL",
    "JASON_OPENAI_CONVERSATION_MODEL",
    "JASON_OPENAI_PRICING_MODEL",
    "JASON_OPENAI_INPUT_COST_PER_MILLION",
    "JASON_OPENAI_CACHED_INPUT_COST_PER_MILLION",
    "JASON_OPENAI_OUTPUT_COST_PER_MILLION",
    "JASON_MODEL_USAGE_DB",
    "JASON_ORCHESTRATION_EVENTS_DB",
    "JASON_TEAMS_IDENTITY_BINDINGS_DB",
)


def connect_readonly(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise FileNotFoundError(path)
    uri = f"file:{quote(str(path.resolve()), safe='/')}?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=1.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    return connection


def runtime_safe_env() -> dict[str, str]:
    completed = subprocess.run(
        [
            "docker",
            "inspect",
            "-f",
            "{{range .Config.Env}}{{println .}}{{end}}",
            RUNTIME_CONTAINER,
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=5,
    )
    if completed.returncode != 0:
        return {}

    allowed = set(SAFE_ENV_KEYS)
    result: dict[str, str] = {}
    for line in completed.stdout.splitlines():
        key, separator, value = line.partition("=")
        if separator and key in allowed:
            result[key] = value
    return result


def inspect_model_usage(path: Path) -> dict[str, object]:
    connection = connect_readonly(path)
    try:
        count = int(
            connection.execute(
                "SELECT COUNT(*) FROM model_usage_entries"
            ).fetchone()[0]
        )
        rows = connection.execute(
            "SELECT payload_json FROM model_usage_entries ORDER BY rowid DESC LIMIT 1000"
        ).fetchall()
    finally:
        connection.close()

    models: set[str] = set()
    providers: set[str] = set()
    newest = ""
    cost_rows = 0
    no_cost_rows = 0
    for row in rows:
        try:
            payload = json.loads(str(row[0]))
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        model = str(payload.get("model") or "").strip()
        provider = str(payload.get("provider") or "").strip()
        completed_at = str(payload.get("completed_at") or "").strip()
        if model:
            models.add(model)
        if provider:
            providers.add(provider)
        if completed_at and completed_at > newest:
            newest = completed_at
        cost = payload.get("cost")
        has_cost = False
        if isinstance(cost, dict):
            has_cost = any(
                cost.get(name) not in (None, "")
                for name in (
                    "provider_reported_cost",
                    "calculated_cost",
                )
            )
        if has_cost:
            cost_rows += 1
        else:
            no_cost_rows += 1

    return {
        "rows": count,
        "recent_models": sorted(models),
        "recent_providers": sorted(providers),
        "newest_completed_at": newest or None,
        "recent_rows_with_cost": cost_rows,
        "recent_rows_without_cost": no_cost_rows,
    }


def inspect_events(path: Path) -> dict[str, object]:
    connection = connect_readonly(path)
    try:
        total = int(
            connection.execute(
                "SELECT COUNT(*) FROM orchestration_events"
            ).fetchone()[0]
        )
        received = int(
            connection.execute(
                "SELECT COUNT(*) FROM orchestration_events WHERE event_type = ?",
                ("orchestration.request.received",),
            ).fetchone()[0]
        )
        newest = connection.execute(
            "SELECT MAX(occurred_at) FROM orchestration_events"
        ).fetchone()[0]
        principals = int(
            connection.execute(
                """
                SELECT COUNT(DISTINCT principal_id)
                FROM orchestration_events
                WHERE event_type = ?
                """,
                ("orchestration.request.received",),
            ).fetchone()[0]
        )
    finally:
        connection.close()
    return {
        "rows": total,
        "request_received_rows": received,
        "distinct_request_principals": principals,
        "newest_occurred_at": newest,
    }


def inspect_bindings(path: Path) -> dict[str, object]:
    connection = connect_readonly(path)
    try:
        total = int(
            connection.execute(
                "SELECT COUNT(*) FROM microsoft_identity_bindings"
            ).fetchone()[0]
        )
        active = int(
            connection.execute(
                "SELECT COUNT(*) FROM microsoft_identity_bindings WHERE status = 'active'"
            ).fetchone()[0]
        )
        with_email = int(
            connection.execute(
                """
                SELECT COUNT(*)
                FROM microsoft_identity_bindings
                WHERE status = 'active'
                  AND email_address IS NOT NULL
                  AND TRIM(email_address) <> ''
                """
            ).fetchone()[0]
        )
    finally:
        connection.close()
    return {
        "rows": total,
        "active_rows": active,
        "active_rows_with_email": with_email,
    }


def main() -> int:
    print("=== JASON USAGE TELEMETRY READ-ONLY PREFLIGHT ===")
    print(f"runtime_container={RUNTIME_CONTAINER}")

    safe_env = runtime_safe_env()
    print("\n=== SAFE RUNTIME MODEL / PRICING SETTINGS ===")
    if safe_env:
        for key in SAFE_ENV_KEYS:
            if key in safe_env:
                print(f"{key}={safe_env[key]}")
    else:
        print("RUNTIME_SAFE_ENV=UNAVAILABLE")

    checks = (
        ("MODEL_USAGE", MODEL_USAGE_DB, inspect_model_usage),
        ("ORCHESTRATION_EVENTS", ORCHESTRATION_EVENTS_DB, inspect_events),
        ("IDENTITY_BINDINGS", IDENTITY_BINDINGS_DB, inspect_bindings),
    )

    failures = 0
    for label, path, inspector in checks:
        print(f"\n=== {label} ===")
        print(f"path={path}")
        try:
            stat = path.stat()
            print(f"size_bytes={stat.st_size}")
            print(f"mode={oct(stat.st_mode & 0o777)}")
            result = inspector(path)
        except Exception as error:
            failures += 1
            print(f"status=FAIL error={type(error).__name__}: {error}")
            continue
        print("status=PASS")
        for key, value in result.items():
            print(f"{key}={json.dumps(value, sort_keys=True)}")

    print()
    if failures:
        print(f"USAGE_TELEMETRY_PREFLIGHT=FAIL failed_sources={failures}")
        return 1
    print("USAGE_TELEMETRY_PREFLIGHT=PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
