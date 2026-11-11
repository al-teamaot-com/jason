#!/usr/bin/env python3
"""Source-only, fail-closed native OpenClaw task observer for PMv4 preproduction.

Reads ONLY the existing OpenClaw task ledger via the native CLI. A trusted
caller must separately obtain a fresh Workboard card and PMV3 state, enforce
exact authority and re-read all state before invoking the existing governed
engine. This observer never runs a task, edits a card, or grants authority.
"""
from __future__ import annotations

import json
import re
import subprocess
from typing import Any, Callable, Mapping

from pmv4_workboard_reconciliation import (
    native_task_terminal_evidence, assess_governed_stale_recovery,
)
from pmv4_subscription_capacity import assess_live_subscription_capacity

# Native task run IDs are UUIDs. Reject options, whitespace, shell syntax,
# paths and ambiguous strings before invoking a fixed argv.
RUN_ID = re.compile(
    r"\A[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\Z"
)
MAX_JSON_BYTES = 128 * 1024


def _read_native_task(
    card: Mapping[str, Any],
    *,
    cli: str = "/usr/local/bin/openclaw",
    runner: Callable[..., Any] = subprocess.run,
    timeout_seconds: float = 10,
) -> tuple[dict[str, Any] | None, str]:
    """Fetch exact runId; return task only when read was trusted and well formed.

    The absolute CLI path must be pinned by trusted integration configuration,
    not by an end-user/card value. Test runner injection is test-only.
    """
    if not isinstance(card, Mapping):
        return None, "invalid_workboard_card"
    run_id = card.get("runId")
    if not isinstance(run_id, str) or not RUN_ID.fullmatch(run_id):
        return None, "invalid_native_run_identifier"
    if not isinstance(cli, str) or not cli.startswith("/") or any(
        part in ("", ".", "..") for part in cli.split("/")[1:]
    ) or not cli.endswith("/openclaw"):
        return None, "native_cli_path_not_trusted"
    if not isinstance(timeout_seconds, (int, float)) or isinstance(timeout_seconds, bool) or not 0 < timeout_seconds <= 30:
        return None, "invalid_observer_timeout"
    try:
        process = runner(
            [cli, "tasks", "show", run_id, "--json"],
            shell=False, capture_output=True, text=True,
            timeout=timeout_seconds, check=False,
        )
    except (OSError, subprocess.TimeoutExpired, ValueError, TypeError):
        return None, "native_task_query_failed"
    if process.returncode != 0:
        return None, "native_task_query_failed"
    stdout = process.stdout
    if not isinstance(stdout, str) or len(stdout.encode("utf-8")) > MAX_JSON_BYTES:
        return None, "native_task_response_invalid"
    try:
        task = json.loads(stdout)
    except (ValueError, TypeError):
        return None, "native_task_response_invalid"
    if not isinstance(task, dict):
        return None, "native_task_response_invalid"
    return task, ""


def observe_native_task(
    card: Mapping[str, Any],
    *,
    cli: str = "/usr/local/bin/openclaw",
    runner: Callable[..., Any] = subprocess.run,
    timeout_seconds: float = 10,
) -> dict[str, Any]:
    """Read only native task status; no authorization or recovery is granted."""
    task, problem = _read_native_task(
        card, cli=cli, runner=runner, timeout_seconds=timeout_seconds,
    )
    if task is None:
        return {
            "disposition": "HOLD",
            "reason": problem,
            "native_termination_confirmed": False,
            "independent_operational_completion_verified": False,
            "provider_action_authorized": False,
        }
    return {
        **native_task_terminal_evidence(card, task),
        "provider_action_authorized": False,
    }


def assess_native_stale_recovery(
    card: Mapping[str, Any],
    state: Mapping[str, Any],
    *,
    authorized_readonly_actions: frozenset[str] = frozenset(),
    cli: str = "/usr/local/bin/openclaw",
    runner: Callable[..., Any] = subprocess.run,
    timeout_seconds: float = 10,
) -> dict[str, Any]:
    """Read native ledger, then call EXISTING PMV3 advisor without execution.

    This is neither authorization nor a state-replay interface. The trusted
    integration must independently re-read Workboard/PMV3 authority and receipts
    before handing a candidate to the existing governed worker.
    """
    task, problem = _read_native_task(
        card, cli=cli, runner=runner, timeout_seconds=timeout_seconds,
    )
    if task is None:
        return {
            "disposition": "HOLD",
            "reason": problem,
            "governed_engine_recovery_candidate": False,
            "provider_action_authorized": False,
            "workboard_auto_reset_allowed": False,
            "operational_completion_verified": False,
        }
    return assess_governed_stale_recovery(
        card, state,
        authorized_readonly_actions=authorized_readonly_actions,
        native_task=task,
    )


def probe_native_subscription_capacity(
    *,
    agent_id: str,
    cli: str = "/usr/local/bin/openclaw",
    runner: Callable[..., Any] = subprocess.run,
    timeout_seconds: float = 15,
) -> dict[str, Any]:
    """Read native subscription capacity with a bounded OAuth-only probe.

    Intended for an already-governed trusted adapter. The native CLI controls
    credentials and model selection. This function never starts a Workboard
    task, edits auth settings, or permits a separately billed API fallback.
    """
    denied = {
        "status": "HOLD_UNVERIFIED",
        "reason": "trusted_subscription_probe_unavailable",
        "metered_fallback_permitted": False,
        "automatic_replay_authorized": False,
        "subscription_capacity_verified": False,
    }
    if agent_id not in ("j-man", "j-dev"):
        return denied
    if (not isinstance(cli, str) or not cli.startswith("/")
            or not cli.endswith("/openclaw")
            or any(piece in ("", ".", "..") for piece in cli.split("/")[1:])):
        return denied
    if (not isinstance(timeout_seconds, (int, float))
            or isinstance(timeout_seconds, bool)
            or not 0 < timeout_seconds <= 30):
        return denied
    argv = [
        cli, "models", "status", "--agent", agent_id,
        "--probe", "--probe-concurrency", "1",
        "--probe-max-tokens", "8", "--probe-timeout", "9000",
        "--json",
    ]
    try:
        process = runner(
            argv, shell=False, capture_output=True, text=True,
            timeout=timeout_seconds, check=False,
        )
        if process.returncode != 0:
            return denied
        stdout = process.stdout
        if not isinstance(stdout, str) or len(stdout.encode("utf-8")) > MAX_JSON_BYTES:
            return denied
        status = json.loads(stdout)
        if not isinstance(status, dict):
            return denied
    except (OSError, subprocess.TimeoutExpired, ValueError, TypeError):
        return denied
    return assess_live_subscription_capacity(status)


if __name__ == "__main__":
    raise SystemExit("Library only: trusted integration must supply a fresh native card.")
