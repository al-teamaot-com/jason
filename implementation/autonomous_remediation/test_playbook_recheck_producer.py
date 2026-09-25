from datetime import datetime, timedelta, timezone

import pytest

from .attention_scheduler import (
    AttentionScheduler,
    AutonomyConfig,
    QueueAttentionState,
    WorkLedger,
    WorkState,
)
from .autonomous_queue_worker import (
    AutonomousQueueWorker,
    QueueCandidate,
    RecheckRequest,
    WorkStepResult,
)
from .playbook_matching import EligibilityGate, GateState, PlaybookMatcher
from .targeted_recheck import SQLiteTargetedWakeStore, WakeState


class QueueSource:
    def reconcile_candidates(self):
        return (
            QueueCandidate(
                "T1",
                10,
                "Jason",
                owned_by_jason=True,
                source_version="v1",
                context={"title": "Known issue", "configurationItemID": 1},
            ),
        )


class Classifier:
    def classify(self, candidate):
        return PlaybookMatcher.evaluate(
            playbook_id="pb",
            gates=[
                EligibilityGate("trigger", GateState.PASS),
                EligibilityGate("evidence", GateState.UNKNOWN),
                EligibilityGate("autonomy_approved", GateState.PASS, True),
            ],
        )


class Ownership:
    def ensure_jason_ownership(self, candidate, playbook_id):
        raise AssertionError("candidate investigation must not claim ownership")


class Execution:
    def execute(self, candidate, match):
        raise AssertionError("candidate investigation must not execute")


class Audit:
    def __init__(self):
        self.events = []

    def record(self, event_type, payload):
        self.events.append((event_type, dict(payload)))


class Investigation:
    def __init__(self, result):
        self.result = result

    def investigate(self, candidate, match):
        return self.result


def worker(result, *, wake_scheduler):
    audit = Audit()
    instance = AutonomousQueueWorker(
        config=AutonomyConfig(2),
        ledger=WorkLedger(),
        attention=QueueAttentionState(dirty=True, reasons={"test"}),
        scheduler=AttentionScheduler(),
        queue_source=QueueSource(),
        classifier=Classifier(),
        ownership=Ownership(),
        investigation=Investigation(result),
        execution=Execution(),
        audit=audit,
        wake_scheduler=wake_scheduler,
    )
    return instance, audit


def test_recheck_requires_exactly_one_trigger():
    with pytest.raises(ValueError):
        RecheckRequest(
            capability_name="service.ticket.read",
            arguments={"ticket_id": 1},
        )
    with pytest.raises(ValueError):
        RecheckRequest(
            capability_name="service.ticket.read",
            arguments={"ticket_id": 1},
            due_at=datetime.now(timezone.utc),
            wake_on="ticket_changed",
        )


def test_recheck_rejects_naive_time_and_nonserializable_arguments():
    with pytest.raises(ValueError):
        RecheckRequest(
            capability_name="service.ticket.read",
            arguments={"ticket_id": 1},
            due_at=datetime.now(),
        )
    with pytest.raises(ValueError):
        RecheckRequest(
            capability_name="service.ticket.read",
            arguments={"bad": object()},
            wake_on="ticket_changed",
        )


def test_structured_recheck_only_valid_for_waiting_states():
    recheck = RecheckRequest(
        capability_name="service.ticket.read",
        arguments={"ticket_id": 1},
        wake_on="ticket_changed",
    )
    with pytest.raises(ValueError):
        WorkStepResult(
            WorkState.COMPLETE,
            "done",
            recheck=recheck,
        )


def test_structured_recheck_cannot_mix_legacy_trigger_fields():
    recheck = RecheckRequest(
        capability_name="service.ticket.read",
        arguments={"ticket_id": 1},
        wake_on="ticket_changed",
    )
    with pytest.raises(ValueError):
        WorkStepResult(
            WorkState.WAITING,
            "wait",
            wake_on="legacy",
            recheck=recheck,
        )


def test_timed_playbook_recheck_persists_exact_wake_and_work_state(tmp_path):
    due = datetime.now(timezone.utc) + timedelta(minutes=10)
    store = SQLiteTargetedWakeStore(tmp_path / "wakes.sqlite3")
    result = WorkStepResult(
        WorkState.WAITING,
        "poll exact job",
        next_action="Read the existing Datto job",
        recheck=RecheckRequest(
            capability_name="automation.job.read",
            arguments={"resource_id": "J1"},
            due_at=due,
            max_attempts=2,
        ),
    )
    instance, audit = worker(result, wake_scheduler=store)

    cycle = instance.cycle(now=datetime.now(timezone.utc))

    assert cycle.investigated == ("T1",)
    item = instance.ledger.get("T1")
    assert item.state is WorkState.WAITING
    assert item.next_check_at == due
    assert item.wake_on is None

    due_items = store.due(now=due + timedelta(seconds=1))
    assert len(due_items) == 1
    wake = due_items[0].wake
    assert wake.resource_id == "T1"
    assert wake.capability_name == "automation.job.read"
    assert wake.arguments == {"resource_id": "J1"}
    assert wake.max_attempts == 2
    assert wake.resume_work_item is True
    assert store.state(wake.wake_id) is WakeState.PENDING

    events = [name for name, _ in audit.events]
    assert "autonomy.work.recheck_scheduled" in events
    store.close()


def test_event_playbook_recheck_is_armed_until_exact_signal(tmp_path):
    store = SQLiteTargetedWakeStore(tmp_path / "wakes.sqlite3")
    result = WorkStepResult(
        WorkState.WAITING,
        "wait for device",
        recheck=RecheckRequest(
            capability_name="endpoint.device.read",
            arguments={"resource_id": "D1"},
            wake_on="device_online",
        ),
    )
    instance, _ = worker(result, wake_scheduler=store)
    instance.cycle(now=datetime.now(timezone.utc))

    assert store.due() == ()
    assert store.signal("device_online", resource_id="OTHER") == ()
    ids = store.signal("device_online", resource_id="T1")
    assert len(ids) == 1
    assert store.state(ids[0]) is WakeState.PENDING
    store.close()


def test_same_recheck_spec_generates_stable_idempotent_wake(tmp_path):
    when = datetime(2026, 9, 25, 15, 0, tzinfo=timezone.utc)
    request = RecheckRequest(
        capability_name="service.ticket.read",
        arguments={"ticket_id": 140629},
        due_at=when,
    )
    first = request.to_wake(
        resource_id="140629",
        playbook_id="pb",
        reason="wait",
    )
    assert first.resume_work_item is True
    second = request.to_wake(
        resource_id="140629",
        playbook_id="pb",
        reason="wait",
    )
    assert first.wake_id == second.wake_id

    store = SQLiteTargetedWakeStore(tmp_path / "wakes.sqlite3")
    store.schedule(first)
    store.schedule(second)
    assert len(store.due(now=when + timedelta(seconds=1))) == 1
    store.close()


def test_structured_recheck_without_scheduler_fails_closed():
    result = WorkStepResult(
        WorkState.WAITING,
        "wait for exact ticket state",
        recheck=RecheckRequest(
            capability_name="service.ticket.read",
            arguments={"ticket_id": 1},
            wake_on="ticket_changed",
        ),
    )
    instance, _ = worker(result, wake_scheduler=None)
    with pytest.raises(RuntimeError):
        instance.cycle(now=datetime.now(timezone.utc))
