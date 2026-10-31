from __future__ import annotations

import argparse
import json
import signal
import time
from pathlib import Path

from .backlog import reconcile_roadmap
from .config import load_config
from .health import self_test
from .scheduler import Scheduler
from .store import PMV2Store


def run_service(*, repo: Path, config_path: Path, once: bool = False) -> int:
    config = load_config(config_path, repo=repo)
    store = PMV2Store(config.database_path)
    store.initialize()
    health = self_test(config=config, store=store, repo=repo)
    if health["status"] != "healthy":
        print(json.dumps({"event": "pm_v2_start_refused", "health": health}, sort_keys=True))
        return 2

    scheduler = Scheduler(config=config, store=store, repo=repo)
    stopping = False

    def stop(*_args):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    try:
        while not stopping:
            intake = reconcile_roadmap(store, config.roadmap_path)
            reaped = scheduler.reap()
            dispatched = scheduler.dispatch_available()
            print(json.dumps({
                "event": "pm_v2_cycle",
                "intake": intake,
                "reaped": [
                    {"assignment_id": r.assignment_id, "worker": r.worker,
                     "return_code": r.return_code, "outcome": r.outcome}
                    for r in reaped
                ],
                "dispatched": dispatched,
            }, sort_keys=True), flush=True)
            if once:
                break
            time.sleep(config.poll_interval_seconds)
    finally:
        scheduler.shutdown()
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
