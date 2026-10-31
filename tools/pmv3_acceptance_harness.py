#!/usr/bin/env python3
"""PMV3 isolated end-to-end acceptance harness.

No production provider calls, no production approvals, and no deployment.
The harness proves the autonomous work-engine semantics with deterministic
preproduction inputs and durable restart boundaries.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from datetime import timedelta
import json

import pmv3_scheduler as scheduler
import pmv3_work_engine as engine


def write(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run_acceptance(root: Path) -> dict[str, object]:
    root.mkdir(parents=True, exist_ok=True)
    paths = {name: root / f"{name}.json" for name in (
        "state", "work", "facts", "approvals", "outcomes", "status"
    )}

    write(paths["work"], {"items": [
        {"id": "NORMAL", "action": "normal-success", "priority": 1},
        {"id": "TRANSIENT", "action": "transport-recovery", "priority": 2},
        {"id": "DEPENDENCY", "action": "dependency-wake", "priority": 3,
         "dependency": "dependency_ready"},
        {"id": "APPROVAL", "action": "teams-approval", "priority": 4,
         "approval_required": True, "approval_request_id": "PMV3-UAT-APPROVAL"},
        {"id": "RESTART", "action": "restart-recovery", "priority": 5},
    ]})
    write(paths["facts"], {"dependency_ready": False})
    write(paths["approvals"], {"approvals": []})
    write(paths["outcomes"], {
        "NORMAL": [{"status": "complete", "receipt": "normal-ok"}],
        "TRANSIENT": [
            {"status": "retry", "reason": "HTTP transport failed"},
            {"status": "complete", "receipt": "transport-ok"},
        ],
        "DEPENDENCY": [{"status": "complete", "receipt": "dependency-ok"}],
        "APPROVAL": [{"status": "complete", "receipt": "approval-ok"}],
        "RESTART": [{"status": "complete", "receipt": "restart-ok"}],
    })

    # Cycle 1: normal completes, transient enters bounded retry. The other
    # states remain independently eligible/waiting without blocking the lane.
    scheduler.run_once(
        state_path=paths["state"], work_path=paths["work"], facts_path=paths["facts"],
        approvals_path=paths["approvals"], outcomes_path=paths["outcomes"],
        status_path=paths["status"], capacity=2,
    )
    state = engine.load_state(paths["state"])
    assert state["items"]["NORMAL"]["phase"] == "complete"
    assert state["items"]["TRANSIENT"]["phase"] == "retry_wait"

    # Simulate a process interruption after claim, before durable action receipt.
    state["items"]["RESTART"]["phase"] = "running"
    state["items"]["RESTART"]["claimed_at"] = state["updated_at"]
    engine.atomic_write(paths["state"], state)

    # Satisfy dependency and provide the later Teams approval.
    write(paths["facts"], {"dependency_ready": True})
    write(paths["approvals"], {"approvals": [{
        "item_id": "APPROVAL",
        "request_id": "PMV3-UAT-APPROVAL",
        "decision": "approve",
        "actor_id": "person-al",
        "tenant_id": "tenant-aot",
        "receipt_id": "teams-uat-receipt",
        "verified": True,
        "channel": "teams",
    }]})

    # Make transport retry due without altering its attempt history.
    state = engine.load_state(paths["state"])
    transient = state["items"]["TRANSIENT"]
    due = engine.parse_time(transient["next_attempt_at"])
    transient["next_attempt_at"] = engine.iso(due - timedelta(seconds=121))
    engine.atomic_write(paths["state"], state)

    # Subsequent cycles must progress everything without a human "continue".
    for _ in range(5):
        scheduler.run_once(
            state_path=paths["state"], work_path=paths["work"], facts_path=paths["facts"],
            approvals_path=paths["approvals"], outcomes_path=paths["outcomes"],
            status_path=paths["status"], capacity=3,
        )
        state = engine.load_state(paths["state"])
        if engine.progress_percent(state) == 100:
            break

    state = engine.load_state(paths["state"])
    phases = {item_id: item["phase"] for item_id, item in state["items"].items()}
    assert all(value == "complete" for value in phases.values())
    assert state["items"]["TRANSIENT"]["attempts"] == 2
    assert state["items"]["APPROVAL"]["approval"]["channel"] == "teams"
    assert state["items"]["RESTART"]["attempts"] == 1
    assert len(state["receipts"]) == 5

    return {
        "status": "pass",
        "progress_percent": engine.progress_percent(state),
        "cycles": state["cycle"],
        "phases": phases,
        "receipts": len(state["receipts"]),
        "transient_attempts": state["items"]["TRANSIENT"]["attempts"],
        "approval_channel": state["items"]["APPROVAL"]["approval"]["channel"],
    }


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="pmv3-acceptance-") as td:
        result = run_acceptance(Path(td))
        print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
