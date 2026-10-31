from __future__ import annotations

import argparse
import json
import signal
import time
from pathlib import Path

from .backlog import reconcile_roadmap
from .components import ComponentRunner
from .config import load_config
from .control import consume_control_requests, publish_status_snapshot
from .health import self_test
from .improvements import reconcile_improvement_proposals
from .recovery import create_snapshot, replicate_snapshot, verify_snapshot
from .release_sync import reconcile_release_bridge
from .scheduler import Scheduler
from .store import PMV2Store


def _existing_todo_issue_numbers(spool: Path) -> dict[str, int]:
    path = spool / "todo-intake-state.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {}
    raw = value.get("existing_todo_issues") if isinstance(value, dict) else None
    if not isinstance(raw, dict):
        return {}
    return {
        str(todo_id): int(number)
        for todo_id, number in raw.items()
        if str(number).isdigit() and int(number) > 0
    }


def run_service(*, repo: Path, config_path: Path, once: bool = False) -> int:
    config = load_config(config_path, repo=repo)
    store = PMV2Store(config.database_path)
    store.initialize()
    health = self_test(config=config, store=store, repo=repo)
    if health["status"] != "healthy":
        print(json.dumps({"event": "pm_v2_start_refused", "health": health}, sort_keys=True))
        return 2

    scheduler = Scheduler(config=config, store=store, repo=repo)
    components = ComponentRunner(config=config, store=store, repo=repo)
    stopping = False
    next_snapshot_at = 0.0

    def stop(*_args):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    try:
        while not stopping:
            controls = consume_control_requests(
                store=store,
                inbox=config.control_request_inbox,
                results=config.control_result_directory,
            )
            intake = reconcile_roadmap(
                store,
                config.roadmap_path,
                owned_todo_ids=config.owned_todo_ids,
                existing_issue_numbers=_existing_todo_issue_numbers(
                    config.legacy_spool
                ),
            )
            downstream = reconcile_release_bridge(
                store=store,
                spool=config.legacy_spool,
                state_root=config.release_state,
            )
            improvements = reconcile_improvement_proposals(
                store=store,
                minimum_recurrences=config.self_improvement_minimum_recurrences,
            )
            reaped = scheduler.reap()
            component_reaped = components.reap()
            dispatched = scheduler.dispatch_available()
            component_dispatched = components.dispatch_due()

            store.heartbeat_node(
                node_id=config.instance_id,
                status="healthy",
                capabilities={
                    "scheduler": True,
                    "durable_state": True,
                    "release_reconciliation": True,
                    "snapshot_recovery": True,
                    "parallel_components": True,
                    "teams_approval_required": config.approval_channel == "microsoft_teams",
                },
                capacity={
                    "max_concurrent_jobs": config.max_concurrent_jobs,
                    "configured_workers": {
                        worker.name: worker.max_concurrency
                        for worker in config.workers if worker.enabled
                    },
                    "max_concurrent_components": config.max_concurrent_components,
                    "component_owners": {
                        component.name: component.owner
                        for component in config.components
                    },
                },
            )

            status_snapshot = publish_status_snapshot(
                store=store,
                path=config.status_snapshot_path,
            )
            snapshot_status = "not_due"
            monotonic = time.monotonic()
            if monotonic >= next_snapshot_at:
                manifest = create_snapshot(
                    store=store,
                    destination=config.snapshot_directory,
                    config_path=config_path,
                )
                verify_snapshot(config.snapshot_directory)
                replicas = replicate_snapshot(
                    snapshot_dir=config.snapshot_directory,
                    replica_directories=config.snapshot_replica_directories,
                )
                store.record_health(
                    component="snapshot_replication",
                    instance_id=config.instance_id,
                    status=(
                        "healthy"
                        if replicas["replica_count"] > 0 else "degraded"
                    ),
                    details={
                        **replicas,
                        "requirement_status": (
                            "configured_and_verified"
                            if replicas["replica_count"] > 0
                            else "host_loss_recovery_not_yet_proven"
                        ),
                    },
                )
                next_snapshot_at = monotonic + config.snapshot_interval_seconds
                snapshot_status = manifest["database"]["sha256"]

            print(json.dumps({
                "event": "pm_v2_cycle",
                "controls": controls,
                "intake": intake,
                "downstream": downstream,
                "self_improvement": improvements,
                "reaped": [
                    {"assignment_id": r.assignment_id, "worker": r.worker,
                     "return_code": r.return_code, "outcome": r.outcome}
                    for r in reaped
                ],
                "dispatched": dispatched,
                "component_reaped": [
                    {"component": r.component, "return_code": r.return_code,
                     "state": r.state}
                    for r in component_reaped
                ],
                "component_dispatched": component_dispatched,
                "snapshot": snapshot_status,
                "status_snapshot_generated_at": status_snapshot["generated_at"],
            }, sort_keys=True), flush=True)
            if once:
                break
            time.sleep(config.poll_interval_seconds)
    finally:
        scheduler.shutdown()
        components.shutdown()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Project Jason Production Manager V2")
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    return run_service(repo=args.repo.resolve(), config_path=args.config.resolve(), once=args.once)


if __name__ == "__main__":
    raise SystemExit(main())
