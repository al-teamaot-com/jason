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
    # Independent read-only supervisor records actionable/internal versus
    # genuine external gates even if a prior worker stage fails.
    Stage("engineering_supervisor", "engineering_supervisor.py"),
    # Revalidation is an *intent* to the independently privileged root worker.
    # It never grants release approval and never closes the breaker locally.
    Stage("release_breaker_recovery", "release_breaker_recovery_manager.py"),
)


# Work-item discovery and execution errors are operational incidents, not
# evidence that the installed production runtime or release authority drifted.
# A failed controller, supervisor, or recovery stage is still a hard failure.
ISOLATABLE_WORK_STAGES = frozenset({"support_repair", "todo_intake", "development"})


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



def canonical_support_rows(repo: Path) -> str:
    """Prefer the fetched authoritative main, never a dirty local topic branch."""
    if (repo / ".git").exists():
        result = subprocess.run(
            ["git", "show", "origin/main:SUPPORT.md"], cwd=str(repo),
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, timeout=10, check=False,
        )
        if result.returncode or len(result.stdout) > 1_000_000:
            raise ValueError("authoritative support source unavailable")
        return result.stdout
    # Isolated unit-test directories contain no Git metadata.
    return (repo / "SUPPORT.md").read_text(encoding="utf-8")


def blocked_critical_support(spool: Path, repo: Path) -> dict[str, Any] | None:
    """Surface already-blocked canonical P0 repairs without creating new authority.

    Unadmitted P0 defects and exhausted P0 repairs must remain visible even if
    scheduled worker commands exit successfully. This is a health projection,
    not an instruction to bypass dependency, reasoning or release gates.
    """
    state_path = spool / "state.json"
    if not state_path.exists():
        return None
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if not isinstance(state, dict):
            raise ValueError("invalid support state")
        items = state.get("items", {})
        if not isinstance(items, dict):
            raise ValueError("invalid support items")
        critical = set()
        for line in canonical_support_rows(repo).splitlines():
            cells = [cell.strip() for cell in line.split("|")]
            if (len(cells) >= 4 and cells[2] == "P0"
                    and cells[1].startswith("SUPPORT-")
                    and not any(status in cells[3].casefold()
                                for status in ("closed", "resolved", "reclassified"))):
                critical.add(cells[1])
        mismatches = state.get("support_state_mismatches", {})
        not_open = set(mismatches.get("support_open_issue_not_open", [])) if isinstance(mismatches, dict) else set()
        # A stale SUPPORT.md row never reopens a GitHub issue that is closed.
        blocked = sorted(item for item in critical
                         if item not in not_open
                         and isinstance(items.get(item), dict)
                         and items[item].get("phase") in {"blocked", "escalated"})
        audit = state.get("admission_audit", {})
        missing = sorted(str(item) for item in audit.get("unadmitted_p0", [])) if isinstance(audit, dict) else []
        if blocked or missing:
            return {"reason": "critical_support_stalled", "blocked_count": len(blocked),
                    "blocked_items": blocked[:12], "unadmitted_count": len(missing),
                    "unadmitted_items": missing[:12]}
    except (OSError, TypeError, ValueError, json.JSONDecodeError, subprocess.TimeoutExpired):
        return {"reason": "support_health_unknown"}
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
            if stage.name in {"release_bridge", "release_breaker_recovery"}:
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
    critical = blocked_critical_support(spool, repo) if not failed else None
    state["status"] = "degraded" if failed or stalled or critical else "healthy"
    state["failed_or_skipped_stages"] = failed
    # Keep stage failures visible and actionable even when the systemd runner
    # completes successfully. Only the work-item execution lane is isolated.
    state["failed_work_stages"] = sorted(set(failed) & ISOLATABLE_WORK_STAGES)
    state["failed_control_stages"] = sorted(set(failed) - ISOLATABLE_WORK_STAGES)
    state["failure_domain"] = (
        "control" if state["failed_control_stages"] else
        "engineering_operations" if state["failed_work_stages"] else "none"
    )
    if stalled:
        state["operational_blocker"] = stalled
    if critical:
        state["critical_support_blocker"] = critical
    atomic_json(output, state)
    print("ENGINEERING_PIPELINE_RESULT " + json.dumps({
        "status": state["status"],
        "failed_or_skipped_stages": failed,
        "operational_blocker": stalled,
        "critical_support_blocker": critical,
        "state_path": str(output),
    }, sort_keys=True), flush=True)
    return state


def service_exit_code(state: dict[str, Any]) -> int:
    """Keep work-item failures out of the production-integrity breaker domain.

    The coordinator must have durably completed *every* scheduled stage and
    recorded an honest degraded result. A GitHub listing failure, exhausted
    reasoning budget or rejected work-item operation is reported by its stage,
    supervisor, and durable pipeline state, not as a failed systemd service.
    Real release-control, supervision, recovery, or unknown failures remain
    nonzero and retain the full production drift guard.
    """
    stages = state.get("stages")
    if (not isinstance(stages, dict)
            or set(stages) != {stage.name for stage in STAGES}
            or not isinstance(state.get("finished_at"), str)
            or state.get("status") not in {"healthy", "degraded"}):
        return 1
    for item in stages.values():
        if (not isinstance(item, dict)
                or item.get("status") not in {"succeeded", "failed", "skipped_dependency"}):
            return 1
        # Process-launch errors, hung workers, and signal terminations are
        # infrastructure failures, not validated work-item rejections.
        if (item.get("reason") in {"stage_timeout", "stage_process_launch_failed"}
                or (item.get("status") == "failed"
                    and isinstance(item.get("return_code"), int)
                    and item["return_code"] < 0)):
            return 1
    actual_failed = {name for name, item in stages.items()
                     if item["status"] != "succeeded"}
    recorded_failed = state.get("failed_or_skipped_stages")
    if (not isinstance(recorded_failed, list)
            or len(recorded_failed) != len(set(recorded_failed))
            or set(recorded_failed) != actual_failed
            or (actual_failed and state["status"] != "degraded")):
        return 1
    if actual_failed - ISOLATABLE_WORK_STAGES:
        return 1
    # A legitimately blocked ticket or work-stage failure remains degraded,
    # but does not make the production watchdog open the release breaker.
    return 0

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
