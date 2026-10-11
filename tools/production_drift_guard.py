#!/usr/bin/env python3
"""Fail-closed production desired-state drift guard for Project Jason."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "production-desired-state.json"
FORBIDDEN_FIELD_NAMES = ("ExecStart", "WorkingDirectory")


def run(args: list[str], *, env: dict[str, str] | None = None) -> str:
    completed = subprocess.run(
        args,
        env=env,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return completed.stdout.strip()


def user_env() -> dict[str, str]:
    env = os.environ.copy()
    env["HOME"] = "/home/al"
    env["XDG_RUNTIME_DIR"] = "/run/user/1000"
    env["DBUS_SESSION_BUS_ADDRESS"] = "unix:path=/run/user/1000/bus"
    return env


def systemctl_command(arguments: list[str], *, user: bool) -> tuple[list[str], dict[str, str] | None]:
    if not user:
        return ["systemctl", *arguments], None
    if os.geteuid() == 0:
        return (
            [
                "runuser",
                "-u",
                "al",
                "--",
                "env",
                "HOME=/home/al",
                "XDG_RUNTIME_DIR=/run/user/1000",
                "DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus",
                "PATH=/usr/local/bin:/usr/bin:/bin",
                "systemctl",
                "--user",
                *arguments,
            ],
            None,
        )
    return ["systemctl", "--user", *arguments], user_env()


def unit_names(*, user: bool) -> set[str]:
    names: set[str] = set()
    queries = (
        ["list-units", "--all", "--type=service", "--type=timer", "--type=path", "--no-legend", "--plain"],
        ["list-unit-files", "--type=service", "--type=timer", "--type=path", "--no-legend", "--plain"],
    )
    for query in queries:
        args, env = systemctl_command(query, user=user)
        for line in run(args, env=env).splitlines():
            if not line.strip():
                continue
            name = line.split()[0]
            if name.startswith("jason-"):
                names.add(name)
    return names


def active_state(unit: str, *, user: bool) -> str:
    args, env = systemctl_command(["is-active", unit], user=user)
    return run(args, env=env).strip()


def unit_properties(unit: str, *, user: bool) -> dict[str, str]:
    args, env = systemctl_command(
        ["show", unit, "-p", "ExecStart", "-p", "WorkingDirectory", "-p", "FragmentPath", "--no-pager"],
        user=user,
    )
    props: dict[str, str] = {}
    for line in run(args, env=env).splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            props[key] = value
    return props


def running_containers() -> set[str]:
    text = run(["docker", "ps", "--format", "{{.Names}}"])
    return {line.strip() for line in text.splitlines() if line.strip().startswith("jason-")}


def stopped_rollback_containers(prefixes: list[str]) -> list[str]:
    text = run(["docker", "ps", "-a", "--filter", "status=exited", "--format", "{{.Names}}"])
    return sorted(
        name.strip()
        for name in text.splitlines()
        if name.strip() and any(name.strip().startswith(prefix) for prefix in prefixes)
    )


def evaluate(config: dict[str, Any]) -> dict[str, Any]:
    problems: list[dict[str, Any]] = []
    forbidden = tuple(str(value) for value in config.get("forbidden_execution_prefixes") or [])

    system_seen = unit_names(user=False)
    user_seen = unit_names(user=True)
    required_system = set(config.get("required_system_units") or [])
    required_user = set(config.get("required_user_units") or [])
    allowed_system = required_system | set(config.get("allowed_system_units") or [])
    allowed_user = required_user | set(config.get("allowed_user_units") or [])

    system_states = {unit: active_state(unit, user=False) for unit in sorted(system_seen)}
    user_states = {unit: active_state(unit, user=True) for unit in sorted(user_seen)}

    for unit in sorted(required_system):
        state = system_states.get(unit, active_state(unit, user=False))
        if state not in {"active", "activating"}:
            problems.append({"kind": "required_system_unit_not_active", "unit": unit, "state": state})
    for unit in sorted(required_user):
        state = user_states.get(unit, active_state(unit, user=True))
        if state not in {"active", "activating"}:
            problems.append({"kind": "required_user_unit_not_active", "unit": unit, "state": state})

    for unit, state in sorted(system_states.items()):
        if state == "failed":
            problems.append({"kind": "failed_system_unit", "unit": unit, "state": state})
    for unit, state in sorted(user_states.items()):
        if state == "failed":
            problems.append({"kind": "failed_user_unit", "unit": unit, "state": state})

    for unit in sorted(system_seen - allowed_system):
        state = system_states.get(unit, active_state(unit, user=False))
        problems.append({"kind": "undeclared_installed_system_unit", "unit": unit, "state": state})
    for unit in sorted(user_seen - allowed_user):
        state = user_states.get(unit, active_state(unit, user=True))
        problems.append({"kind": "undeclared_installed_user_unit", "unit": unit, "state": state})

    for user, units in ((False, system_seen), (True, user_seen)):
        for unit in sorted(units):
            props = unit_properties(unit, user=user)
            combined = " ".join(props.get(field, "") for field in FORBIDDEN_FIELD_NAMES)
            hit = next((prefix for prefix in forbidden if prefix and prefix in combined), None)
            if hit:
                problems.append(
                    {
                        "kind": "forbidden_execution_path",
                        "scope": "user" if user else "system",
                        "unit": unit,
                        "forbidden_prefix": hit,
                        "working_directory": props.get("WorkingDirectory", ""),
                        "exec_start": props.get("ExecStart", "")[:700],
                    }
                )

    running = running_containers()
    required_containers = set(config.get("required_containers") or [])
    allowed_containers = set(config.get("allowed_running_containers") or [])
    for name in sorted(required_containers - running):
        problems.append({"kind": "required_container_not_running", "container": name})
    for name in sorted(running - allowed_containers):
        problems.append({"kind": "undeclared_running_container", "container": name})

    rollback = stopped_rollback_containers(list(config.get("rollback_container_prefixes") or []))
    maximum = int(config.get("max_stopped_rollback_containers", 20) or 20)
    if len(rollback) > maximum:
        problems.append(
            {
                "kind": "rollback_container_retention_exceeded",
                "count": len(rollback),
                "maximum": maximum,
                "sample": rollback[:20],
            }
        )

    return {
        "schema_version": "1.0",
        "status": "pass" if not problems else "drift_detected",
        "observed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "problems": problems,
        "evidence": {
            "system_units_seen": sorted(system_seen),
            "user_units_seen": sorted(user_seen),
            "running_containers": sorted(running),
            "stopped_rollback_container_count": len(rollback),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    result = evaluate(config)
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    return 0 if result["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
