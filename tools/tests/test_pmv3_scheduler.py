import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

engine_spec = importlib.util.spec_from_file_location("pmv3_work_engine", ROOT / "tools/pmv3_work_engine.py")
engine = importlib.util.module_from_spec(engine_spec)
sys.modules[engine_spec.name] = engine
engine_spec.loader.exec_module(engine)

runner_spec = importlib.util.spec_from_file_location("pmv3_scheduler", ROOT / "tools/pmv3_scheduler.py")
runner = importlib.util.module_from_spec(runner_spec)
sys.modules[runner_spec.name] = runner
runner_spec.loader.exec_module(runner)


def write(path: Path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def test_persists_state_across_cycles_and_does_not_duplicate(tmp_path):
    state = tmp_path / "state.json"
    work = tmp_path / "work.json"
    facts = tmp_path / "facts.json"
    approvals = tmp_path / "approvals.json"
    outcomes = tmp_path / "outcomes.json"
    status = tmp_path / "status.json"

    write(work, {"items": [{"id": "A", "action": "build"}]})
    write(facts, {})
    write(approvals, {"approvals": []})
    write(outcomes, {"A": [{"status": "complete", "receipt": "r-a"}]})

    first = runner.run_once(
        state_path=state, work_path=work, facts_path=facts,
        approvals_path=approvals, outcomes_path=outcomes,
        status_path=status, capacity=1,
    )
    assert first["progress_percent"] == 100
    persisted = engine.load_state(state)
    assert persisted["items"]["A"]["phase"] == "complete"
    assert len(persisted["receipts"]) == 1

    second = runner.run_once(
        state_path=state, work_path=work, facts_path=facts,
        approvals_path=approvals, outcomes_path=outcomes,
        status_path=status, capacity=1,
    )
    persisted = engine.load_state(state)
    assert second["admitted_this_cycle"] == 0
    assert persisted["items"]["A"]["attempts"] == 1
    assert len(persisted["receipts"]) == 1


def test_waiting_dependency_wakes_on_later_cycle(tmp_path):
    paths = {name: tmp_path / f"{name}.json" for name in ("state","work","facts","approvals","outcomes","status")}
    write(paths["work"], {"items": [{"id": "B", "action": "merge", "dependency": "checks_passed"}]})
    write(paths["facts"], {"checks_passed": False})
    write(paths["approvals"], {"approvals": []})
    write(paths["outcomes"], {"B": [{"status": "complete", "receipt": "r-b"}]})

    runner.run_once(
        state_path=paths["state"], work_path=paths["work"], facts_path=paths["facts"],
        approvals_path=paths["approvals"], outcomes_path=paths["outcomes"],
        status_path=paths["status"], capacity=1,
    )
    assert engine.load_state(paths["state"])["items"]["B"]["phase"] == "waiting"

    write(paths["facts"], {"checks_passed": True})
    result = runner.run_once(
        state_path=paths["state"], work_path=paths["work"], facts_path=paths["facts"],
        approvals_path=paths["approvals"], outcomes_path=paths["outcomes"],
        status_path=paths["status"], capacity=1,
    )
    assert result["progress_percent"] == 100


def test_teams_approval_required_and_persisted(tmp_path):
    paths = {name: tmp_path / f"{name}.json" for name in ("state","work","facts","approvals","outcomes","status")}
    write(paths["work"], {"items": [{
        "id": "C", "action": "release",
        "approval_required": True, "approval_request_id": "REQ-C"
    }]})
    write(paths["facts"], {})
    write(paths["approvals"], {"approvals": []})
    write(paths["outcomes"], {"C": [{"status": "complete", "receipt": "r-c"}]})

    result = runner.run_once(
        state_path=paths["state"], work_path=paths["work"], facts_path=paths["facts"],
        approvals_path=paths["approvals"], outcomes_path=paths["outcomes"],
        status_path=paths["status"], capacity=1,
    )
    assert result["progress_percent"] == 0
    assert engine.load_state(paths["state"])["items"]["C"]["attempts"] == 0

    write(paths["approvals"], {"approvals": [{
        "item_id": "C", "request_id": "REQ-C", "decision": "approve",
        "actor_id": "person-al", "tenant_id": "tenant-aot",
        "receipt_id": "teams-receipt-c", "verified": True, "channel": "teams"
    }]})
    result = runner.run_once(
        state_path=paths["state"], work_path=paths["work"], facts_path=paths["facts"],
        approvals_path=paths["approvals"], outcomes_path=paths["outcomes"],
        status_path=paths["status"], capacity=1,
    )
    assert result["progress_percent"] == 100
    persisted = engine.load_state(paths["state"])
    assert persisted["items"]["C"]["approval"]["channel"] == "teams"


def test_non_teams_approval_input_fails_closed(tmp_path):
    paths = {name: tmp_path / f"{name}.json" for name in ("state","work","facts","approvals","outcomes","status")}
    write(paths["work"], {"items": [{
        "id": "D", "action": "release",
        "approval_required": True, "approval_request_id": "REQ-D"
    }]})
    write(paths["facts"], {})
    write(paths["approvals"], {"approvals": [{
        "item_id": "D", "request_id": "REQ-D", "decision": "approve",
        "actor_id": "person-al", "tenant_id": "tenant-aot",
        "receipt_id": "shell-d", "verified": True, "channel": "ssh"
    }]})
    write(paths["outcomes"], {"D": [{"status": "complete", "receipt": "r-d"}]})

    try:
        runner.run_once(
            state_path=paths["state"], work_path=paths["work"], facts_path=paths["facts"],
            approvals_path=paths["approvals"], outcomes_path=paths["outcomes"],
            status_path=paths["status"], capacity=1,
        )
    except ValueError as exc:
        assert "Teams" in str(exc)
    else:
        raise AssertionError("non-Teams approval must fail closed")
