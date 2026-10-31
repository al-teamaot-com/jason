import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("pmv3_work_engine", ROOT / "tools/pmv3_work_engine.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


NOW = datetime(2026, 10, 31, 17, 0, tzinfo=timezone.utc)


def test_success_runs_without_repeat_prompt():
    state = module.empty_state()
    module.admit(state, module.make_item("PMV3-1", "build"))
    calls = []

    def handler(item, key):
        calls.append((item["id"], key))
        return module.Outcome("complete", receipt="ok-1")

    module.execute_cycle(state, facts={}, handler=handler, now=NOW)
    assert state["items"]["PMV3-1"]["phase"] == "complete"
    assert state["metrics"]["completed"] == 1
    assert len(calls) == 1


def test_transient_failure_retries_with_bounded_backoff():
    state = module.empty_state()
    module.admit(state, module.make_item("PMV3-2", "transport"))
    calls = []

    def handler(item, key):
        calls.append(item["attempts"])
        if len(calls) == 1:
            return module.Outcome("retry", reason="HTTP transport failed")
        return module.Outcome("complete", receipt="ok-2")

    module.execute_cycle(state, facts={}, handler=handler, now=NOW)
    item = state["items"]["PMV3-2"]
    assert item["phase"] == "retry_wait"
    due = module.parse_time(item["next_attempt_at"])
    assert due == NOW + timedelta(seconds=30)

    module.execute_cycle(state, facts={}, handler=handler, now=due)
    assert state["items"]["PMV3-2"]["phase"] == "complete"
    assert len(calls) == 2


def test_waiting_dependency_wakes_automatically():
    state = module.empty_state()
    module.admit(state, module.make_item("PMV3-3", "merge", dependency="checks_passed"))

    def handler(item, key):
        return module.Outcome("complete", receipt="ok-3")

    module.execute_cycle(state, facts={"checks_passed": False}, handler=handler, now=NOW)
    assert state["items"]["PMV3-3"]["phase"] == "waiting"

    module.execute_cycle(
        state,
        facts={"checks_passed": True},
        handler=handler,
        now=NOW + timedelta(minutes=1),
    )
    assert state["items"]["PMV3-3"]["phase"] == "complete"


def test_blocked_item_does_not_consume_other_capacity():
    state = module.empty_state()
    first = module.make_item("PMV3-4", "external", priority=1)
    first["phase"] = "failed_external"
    first["reason"] = "credentials required"
    module.admit(state, first)
    module.admit(state, module.make_item("PMV3-5", "independent", priority=2))

    def handler(item, key):
        return module.Outcome("complete", receipt="ok-5")

    module.execute_cycle(state, facts={}, handler=handler, capacity=1, now=NOW)
    assert state["items"]["PMV3-4"]["phase"] == "failed_external"
    assert state["items"]["PMV3-5"]["phase"] == "complete"


def test_crash_recovery_does_not_duplicate_completed_action():
    state = module.empty_state()
    item = module.make_item("PMV3-6", "deploy-candidate")
    module.admit(state, item)
    key = module.action_key("PMV3-6", "deploy-candidate", 1)
    state["items"]["PMV3-6"]["phase"] = "running"
    state["receipts"][key] = {
        "item_id": "PMV3-6",
        "receipt": "already-done",
        "recorded_at": module.iso(NOW),
    }
    called = False

    def handler(item, action_key):
        nonlocal called
        called = True
        return module.Outcome("complete", receipt="duplicate")

    module.execute_cycle(state, facts={}, handler=handler, now=NOW + timedelta(minutes=2))
    assert state["items"]["PMV3-6"]["phase"] == "complete"
    assert called is False


def test_interrupted_action_without_receipt_is_readmitted():
    state = module.empty_state()
    module.admit(state, module.make_item("PMV3-7", "recover"))
    state["items"]["PMV3-7"]["phase"] = "running"

    def handler(item, key):
        return module.Outcome("complete", receipt="ok-7")

    module.execute_cycle(state, facts={}, handler=handler, now=NOW)
    assert state["items"]["PMV3-7"]["phase"] == "complete"
    assert state["items"]["PMV3-7"]["attempts"] == 1


def test_external_authority_is_not_retried():
    state = module.empty_state()
    module.admit(state, module.make_item("PMV3-8", "approval"))

    def handler(item, key):
        return module.Outcome(
            "external",
            reason="owner approval required",
            retry_class="owner_approval_required",
        )

    module.execute_cycle(state, facts={}, handler=handler, now=NOW)
    assert state["items"]["PMV3-8"]["phase"] == "failed_external"
    assert state["items"]["PMV3-8"]["attempts"] == 1


def test_progress_percentage_measures_whole_inventory():
    state = module.empty_state()
    module.admit(state, module.make_item("PMV3-9", "a"))
    module.admit(state, module.make_item("PMV3-10", "b"))
    state["items"]["PMV3-9"]["phase"] = "complete"
    assert module.progress_percent(state) == 50
