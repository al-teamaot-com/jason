#!/usr/bin/env python3
"""Run governed engineering stages with explicit fail-closed dependencies.

A failed stage must never silently turn the entire 24x7 process into a no-op.
The independent release bridge still reconciles in-flight approved releases.
This coordinator grants no new approval, provider access, or release authority.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


@dataclass(frozen=True)
class Stage:
    name: str
    script: str
    args: tuple[str, ...] = ()
    requires: tuple[str, ...] = ()


STAGES = (
    Stage("support_repair", "support_repair_host_worker.py", ("--max-active", "2")),
    Stage("todo_intake", "todo_engineering_intake.py", ("--max-support-repairs", "2"), ("support_repair",)),
    # Already-approved development has its own support-capacity and approval checks;
    # it may continue if intake fails, but must stop if support priority is unknown.
    Stage("development", "owner_approved_development_worker.py", ("--max-active", "2"), ("support_repair",)),
    # Read/reconciliation of durable work state must not be suppressed by earlier
    # GitHub or reasoning failures. This stage retains its own governed gates.
    Stage("release_bridge", "todo_release_bridge.py"),
)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def atomic_json(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(prefix=".engineering-stage-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            os.fchmod(handle.fileno(), 0o600)
            json.dump(state, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def stalled_approved_work(spool: Path) -> dict[str, Any] | None:
    """Fail health projection when approved work is stranded upstream.

    Stage exit code success only proves controller execution, not work progress.
    This read-only assessment does not claim, retry, or mutate work items.
    """
    path = spool / "todo-intake-state.json"
    if not path.exists():
        return None
    try:
        intake = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(intake, dict):
            raise ValueError("invalid intake state")
        commitments = intake.get("downstream_commitments") or {}
        outstanding = int(commitments.get("outstanding_count") or 0)
        active = int(intake.get("active_development_items") or 0) + int(intake.get("active_support_repairs") or 0)
        capacity = int(intake.get("engineering_capacity") or 0)
        if outstanding > 0 and active == 0 and capacity > 0 and intake.get("status") == "stalled_upstream_or_downstream":
            return {"reason": "approved_work_stalled", "outstanding": outstanding, "active": active, "capacity": capacity}
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return {"reason": "intake_health_unknown"}
    return None


def run_pipeline(
    *,
    scripts: Path,
    repo: Path,
    spool: Path,
    release_state: Path,
    stage_timeout: int = 900,
    runner: Callable[..., Any] = subprocess.run,
) -> dict[str, Any]:
    state: dict[str, Any] = {
        "schema_version": "1.0",
        "started_at": now(),
        "finished_at": None,
        "status": "running",
        "stages": {},
    }
    output = spool / "engineering-pipeline-state.json"
    atomic_json(output, state)
    for stage in STAGES:
        blocked = [dep for dep in stage.requires if state["stages"].get(dep, {}).get("status") != "succeeded"]
        if blocked:
            item = {
                "status": "skipped_dependency",
                "reason": "required stage did not succeed: " + ", ".join(blocked),
                "checked_at": now(),
            }
        else:
            command = [
                sys.executable, str(scripts / stage.script),
                "--repo", str(repo), "--spool", str(spool), *stage.args,
            ]
            if stage.name == "release_bridge":
                command += ["--release-state", str(release_state)]
            print(f"ENGINEERING_STAGE_START name={stage.name}", flush=True)
            try:
                # Child output flows to journald; never persist raw provider output,
                # secrets, or an unbounded traceback in the durable summary.
                result = runner(command, cwd=str(repo), timeout=stage_timeout, check=False)
                code = int(result.returncode)
                item = {
                    "status": "succeeded" if code == 0 else "failed",
                    "return_code": code,
                    "checked_at": now(),
                }
            except subprocess.TimeoutExpired:
                item = {"status": "failed", "reason": "stage_timeout", "checked_at": now()}
            except OSError:
                item = {"status": "failed", "reason": "stage_process_launch_failed", "checked_at": now()}
        state["stages"][stage.name] = item
        atomic_json(output, state)
        print(f"ENGINEERING_STAGE_END name={stage.name} status={item['status']}", flush=True)
    failed = [name for name, item in state["stages"].items() if item["status"] != "succeeded"]
    state["finished_at"] = now()
    stalled = stalled_approved_work(spool) if not failed else None
    state["status"] = "degraded" if failed or stalled else "healthy"
    state["failed_or_skipped_stages"] = failed
    if stalled:
        state["operational_blocker"] = stalled
    atomic_json(output, state)
    print("ENGINEERING_PIPELINE_RESULT " + json.dumps({
        "status": state["status"],
        "failed_or_skipped_stages": failed,
        "state_path": str(output),
    }, sort_keys=True), flush=True)
    return state


def service_exit_code(state: dict[str, Any]) -> int:
    """Fail systemd only when a stage failed; degraded backlog remains observable."""
    return 1 if state["failed_or_skipped_stages"] else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--spool", type=Path, required=True)
    parser.add_argument("--release-state", type=Path, required=True)
    parser.add_argument("--stage-timeout", type=int, default=900)
    args = parser.parse_args()
    if args.stage_timeout < 1:
        parser.error("--stage-timeout must be positive")
    state = run_pipeline(
        scripts=Path(__file__).resolve().parent,
        repo=args.repo.resolve(),
        spool=args.spool.resolve(),
        release_state=args.release_state.resolve(),
        stage_timeout=args.stage_timeout,
    )
    # Preserve degraded health without marking successful stage execution as a failed service.
    return service_exit_code(state)


if __name__ == "__main__":
    raise SystemExit(main())
