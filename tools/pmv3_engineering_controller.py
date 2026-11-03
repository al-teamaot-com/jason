#!/usr/bin/env python3
"""PMV3 persistent engineering controller.

Runs the existing governed engineering pipeline repeatedly while durable evidence
shows recoverable work can still progress. It never grants approval, changes
provider authority, or deploys production. Production release approval remains
in the existing Teams-only Release Manager path.

The controller stops only when:
- pipeline is healthy;
- a genuine external/governed gate remains;
- a control-plane failure occurs;
- bounded retry budget is exhausted without forward progress.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temp = tempfile.mkstemp(prefix=".pmv3-controller-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump(value, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("invalid PMV3 controller evidence")
    return value


def progress_fingerprint(pipeline: Mapping[str, Any], supervisor: Mapping[str, Any]) -> str:
    bounded = {
        "pipeline_status": pipeline.get("status"),
        "failed_work_stages": pipeline.get("failed_work_stages"),
        "failed_control_stages": pipeline.get("failed_control_stages"),
        "operational_blocker": pipeline.get("operational_blocker"),
        "critical_support_blocker": pipeline.get("critical_support_blocker"),
        "supervisor_status": supervisor.get("status"),
        "supervisor_reason": supervisor.get("reason"),
        "supervisor_counts": supervisor.get("category_counts"),
        "supervisor_disposition": supervisor.get("disposition_sha256"),
        "approved_outstanding": supervisor.get("approved_outstanding"),
        "active": supervisor.get("active"),
    }
    return hashlib.sha256(json.dumps(bounded, sort_keys=True).encode()).hexdigest()


def classify(
    pipeline: Mapping[str, Any],
    supervisor: Mapping[str, Any],
) -> tuple[str, str]:
    failed_control = pipeline.get("failed_control_stages") or []
    if failed_control:
        return "control_failure", "control_plane_failure"
    if pipeline.get("status") == "healthy":
        return "complete", "pipeline_healthy"

    reason = str(supervisor.get("reason") or "")
    if reason == "internal_recovery_needed":
        return "recoverable", "internal_recovery_needed"
    if reason == "external_or_governed_gate":
        return "waiting_external", "external_or_governed_gate"

    blocker = pipeline.get("operational_blocker")
    if isinstance(blocker, Mapping) and blocker.get("reason") == "approved_work_stalled":
        counts = supervisor.get("category_counts") if isinstance(supervisor.get("category_counts"), Mapping) else {}
        recoverable = sum(int(counts.get(name) or 0) for name in (
            "recoverable_source", "recoverable_transport",
            "recoverable_validation", "needs_triage",
        ))
        if recoverable:
            return "recoverable", "approved_work_stalled_recoverable"
        return "waiting_external", "approved_work_stalled_external"

    if pipeline.get("failed_work_stages"):
        return "recoverable", "work_stage_failed"

    if pipeline.get("critical_support_blocker"):
        counts = supervisor.get("category_counts") if isinstance(supervisor.get("category_counts"), Mapping) else {}
        recoverable = sum(int(counts.get(name) or 0) for name in (
            "recoverable_source", "recoverable_transport",
            "recoverable_validation", "needs_triage",
        ))
        return (
            ("recoverable", "critical_support_recoverable")
            if recoverable else
            ("waiting_external", "critical_support_external")
        )

    return "waiting_external", "unclassified_governed_gate"


def run_pipeline(
    *,
    scripts: Path,
    repo: Path,
    spool: Path,
    release_state: Path,
    timeout: int,
    runner: Callable[..., Any],
) -> int:
    command = [
        sys.executable,
        str(scripts / "engineering_pipeline.py"),
        "--repo", str(repo),
        "--spool", str(spool),
        "--release-state", str(release_state),
    ]
    result = runner(command, cwd=str(repo), timeout=timeout, check=False)
    return int(result.returncode)


def controller_run(
    *,
    scripts: Path,
    repo: Path,
    spool: Path,
    release_state: Path,
    max_passes: int = 4,
    unchanged_limit: int = 2,
    retry_delay: float = 0.0,
    pipeline_timeout: int = 3900,
    runner: Callable[..., Any] = subprocess.run,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    state_path = spool / "pmv3-engineering-controller-state.json"
    state = {
        "schema_version": "3.0",
        "started_at": now(),
        "finished_at": None,
        "status": "running",
        "passes": [],
        "teams_only_approval": True,
    }
    atomic_json(state_path, state)

    previous_fp = None
    unchanged = 0

    for pass_number in range(1, max(1, int(max_passes)) + 1):
        try:
            return_code = run_pipeline(
                scripts=scripts, repo=repo, spool=spool,
                release_state=release_state, timeout=pipeline_timeout,
                runner=runner,
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            state["passes"].append({
                "pass": pass_number,
                "status": "control_failure",
                "reason": "pipeline_process_failure",
                "error_type": type(exc).__name__,
                "checked_at": now(),
            })
            state["status"] = "control_failure"
            state["reason"] = "pipeline_process_failure"
            break

        pipeline = load_json(spool / "engineering-pipeline-state.json")
        supervisor = load_json(spool / "engineering-supervisor-state.json")
        disposition, reason = classify(pipeline, supervisor)
        fp = progress_fingerprint(pipeline, supervisor)
        if fp == previous_fp:
            unchanged += 1
        else:
            unchanged = 0
        previous_fp = fp

        entry = {
            "pass": pass_number,
            "pipeline_return_code": return_code,
            "disposition": disposition,
            "reason": reason,
            "progress_sha256": fp,
            "unchanged_passes": unchanged,
            "checked_at": now(),
        }
        state["passes"].append(entry)
        atomic_json(state_path, state)

        if disposition == "complete":
            state["status"] = "complete"
            state["reason"] = reason
            break
        if disposition in {"control_failure", "waiting_external"}:
            state["status"] = disposition
            state["reason"] = reason
            break
        if unchanged >= max(1, int(unchanged_limit)):
            state["status"] = "bounded_stall"
            state["reason"] = "recoverable_state_not_advancing"
            break
        if pass_number < max_passes and retry_delay > 0:
            sleeper(retry_delay)
    else:
        state["status"] = "bounded_stall"
        state["reason"] = "max_passes_exhausted"

    state["finished_at"] = now()
    state["pass_count"] = len(state["passes"])
    atomic_json(state_path, state)
    return state


def service_exit_code(state: Mapping[str, Any]) -> int:
    # A bounded work stall is operational evidence, not a production-integrity
    # failure. Only controller/control-plane failure should fail the systemd unit.
    return 1 if state.get("status") == "control_failure" else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--spool", type=Path, required=True)
    parser.add_argument("--release-state", type=Path, required=True)
    parser.add_argument("--max-passes", type=int, default=4)
    parser.add_argument("--unchanged-limit", type=int, default=2)
    parser.add_argument("--retry-delay", type=float, default=5.0)
    parser.add_argument("--pipeline-timeout", type=int, default=3900)
    args = parser.parse_args()
    state = controller_run(
        scripts=Path(__file__).resolve().parent,
        repo=args.repo.resolve(),
        spool=args.spool.resolve(),
        release_state=args.release_state.resolve(),
        max_passes=max(1, args.max_passes),
        unchanged_limit=max(1, args.unchanged_limit),
        retry_delay=max(0.0, args.retry_delay),
        pipeline_timeout=max(1, args.pipeline_timeout),
    )
    print("PMV3_ENGINEERING_CONTROLLER " + json.dumps({
        "status": state["status"],
        "reason": state.get("reason"),
        "pass_count": state.get("pass_count"),
        "teams_only_approval": True,
    }, sort_keys=True))
    return service_exit_code(state)


if __name__ == "__main__":
    raise SystemExit(main())
