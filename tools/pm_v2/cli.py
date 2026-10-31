from __future__ import annotations

import argparse
import json
from pathlib import Path

from .backlog import reconcile_roadmap
from .config import load_config
from .health import self_test
from .recovery import create_snapshot, restore_snapshot, verify_snapshot
from .release_sync import reconcile_release_bridge
from .store import PMV2Store


def main() -> int:
    parser = argparse.ArgumentParser(description="PM V2 operator read surface")
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("health")
    sub.add_parser("sync")
    sub.add_parser("snapshot")
    sub.add_parser("verify-snapshot")
    restore = sub.add_parser("restore-snapshot")
    restore.add_argument("--destination-config", type=Path, required=True)
    status = sub.add_parser("status")
    status.add_argument("--state", action="append", default=[])
    args = parser.parse_args()

    repo = args.repo.resolve()
    config = load_config(args.config.resolve(), repo=repo)
    store = PMV2Store(config.database_path)
    store.initialize()

    if args.command == "health":
        print(json.dumps(self_test(config=config, store=store, repo=repo), indent=2, sort_keys=True))
        return 0
    if args.command == "sync":
        result = {
            "roadmap": reconcile_roadmap(
                store,
                config.roadmap_path,
                owned_todo_ids=config.owned_todo_ids,
            ),
            "downstream": reconcile_release_bridge(
                store=store,
                spool=config.legacy_spool,
                state_root=config.release_state,
            ),
        }
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.command == "snapshot":
        result = create_snapshot(
            store=store,
            destination=config.snapshot_directory,
            config_path=args.config.resolve(),
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.command == "verify-snapshot":
        print(json.dumps(
            verify_snapshot(config.snapshot_directory),
            indent=2,
            sort_keys=True,
        ))
        return 0
    if args.command == "restore-snapshot":
        result = restore_snapshot(
            snapshot_dir=config.snapshot_directory,
            database_path=config.database_path,
            config_destination=args.destination_config.resolve(),
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    rows = store.list_assignments(states=tuple(args.state) if args.state else None)
    print(json.dumps([
        {
            "assignment_id": row.assignment_id,
            "source": row.source,
            "source_ref": row.source_ref,
            "title": row.title,
            "state": row.state,
            "runnable": row.runnable,
            "attempt_count": row.attempt_count,
            "completion_percent": row.completion_percent,
            "blocked_reason": row.blocked_reason,
        }
        for row in rows
    ], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
