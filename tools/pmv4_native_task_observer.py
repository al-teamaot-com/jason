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

from pmv4_workboard_reconciliation import native_task_terminal_evidence

# Native task run IDs are UUIDs. Reject options, whitespace, shell syntax,
# paths and ambiguous strings before invoking a fixed argv.
RUN_ID = re.compile(
    r"\A[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\Z"
)
MAX_JSON_BYTES = 128 * 1024


def observe_native_task(
    card: Mapping[str, Any],
    *,
    cli: str = "/usr/local/bin/openclaw",
    runner: Callable[..., Any] = subprocess.run,
    timeout_seconds: float = 10,
) -> dict[str, Any]:
    """Fetch a native task by exact Workboard runId and advise; never replay.

    The absolute CLI path must be pinned by trusted integration configuration,
    not by an end-user/card value. Test runner injection is test-only.
    """
    held = {
        "disposition": "HOLD",
        "reason": "native_task_observation_unavailable",
        "native_termination_confirmed": False,
        "independent_operational_completion_verified": False,
        "provider_action_authorized": False,
    }
    if not isinstance(card, Mapping):
        return dict(held, reason="invalid_workboard_card")
    run_id = card.get("runId")
    if not isinstance(run_id, str) or not RUN_ID.fullmatch(run_id):
        return dict(held, reason="invalid_native_run_identifier")
    if not isinstance(cli, str) or not cli.startswith("/") or any(
        part in ("", ".", "..") for part in cli.split("/")[1:]
    ) or not cli.endswith("/openclaw"):
        return dict(held, reason="native_cli_path_not_trusted")
    if not isinstance(timeout_seconds, (int, float)) or isinstance(timeout_seconds, bool) or not 0 < timeout_seconds <= 30:
        return dict(held, reason="invalid_observer_timeout")
    try:
        process = runner(
            [cli, "tasks", "show", run_id, "--json"],
            shell=False, capture_output=True, text=True,
            timeout=timeout_seconds, check=False,
        )
    except (OSError, subprocess.TimeoutExpired, ValueError, TypeError):
        return dict(held, reason="native_task_query_failed")
    if process.returncode != 0:
        return dict(held, reason="native_task_query_failed")
    stdout = process.stdout
    if not isinstance(stdout, str) or len(stdout.encode("utf-8")) > MAX_JSON_BYTES:
        return dict(held, reason="native_task_response_invalid")
    try:
        task = json.loads(stdout)
    except (ValueError, TypeError):
        return dict(held, reason="native_task_response_invalid")
    if not isinstance(task, dict):
        return dict(held, reason="native_task_response_invalid")
    decision = native_task_terminal_evidence(card, task)
    # Keep this observer deliberately narrower than the recovery assessor:
    # terminal evidence is not independent completion or authority to execute.
    return {**decision, "provider_action_authorized": False}


if __name__ == "__main__":
    raise SystemExit("Library only: trusted integration must supply a fresh native card.")
