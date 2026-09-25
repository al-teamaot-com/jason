from datetime import datetime, timedelta, timezone

import pytest

from .targeted_recheck import (
    SQLiteTargetedWakeStore,
    TargetedWake,
    WakeKind,
    WakeState,
)


def now():
    return datetime.now(timezone.utc)


def test_timed_wake_becomes_due_without_queue_scan(tmp_path):
    store = SQLiteTargetedWakeStore(tmp_path / "wake.sqlite3")
    wake = TargetedWake(
        wake_id="job-1",
        resource_id="T1",
        reason="check exact Datto job",
        kind=WakeKind.TARGETED_READ,
        due_at=now() - timedelta(seconds=1),
        capability_name="automation.job.read",
        arguments={"resource_id": "job-1"},
    )
    store.schedule(wake)
    due = store.due(now=now())
    assert len(due) == 1
    assert due[0].wake.resource_id == "T1"
    assert due[0].wake.capability_name == "automation.job.read"
    store.close()


def test_event_wake_stays_armed_until_signaled(tmp_path):
    store = SQLiteTargetedWakeStore(tmp_path / "wake.sqlite3")
    store.schedule(TargetedWake(
        wake_id="approval-1",
        resource_id="T1",
        reason="approval received",
        kind=WakeKind.TARGETED_READ,
        wake_on="approval_received",
        capability_name="service.ticket.read",
        arguments={"ticket_id": 1},
    ))
    assert store.due(now=now()) == ()
    assert store.state("approval-1") is WakeState.ARMED
    signaled = store.signal("approval_received", resource_id="T1", now=now())
    assert signaled == ("approval-1",)
    assert len(store.due(now=now() + timedelta(seconds=1))) == 1
    store.close()


def test_event_signal_can_target_one_resource(tmp_path):
    store = SQLiteTargetedWakeStore(tmp_path / "wake.sqlite3")
    for resource_id in ("T1", "T2"):
        store.schedule(TargetedWake(
            wake_id=f"w-{resource_id}",
            resource_id=resource_id,
            reason="device online",
            kind=WakeKind.TARGETED_READ,
            wake_on="device_online",
            capability_name="endpoint.device.read",
            arguments={"resource_id": resource_id},
        ))
    assert store.signal("device_online", resource_id="T2", now=now()) == ("w-T2",)
    assert store.state("w-T1") is WakeState.ARMED
    assert store.state("w-T2") is WakeState.PENDING
    store.close()


def test_same_wake_id_is_idempotent_only_for_exact_scope(tmp_path):
    store = SQLiteTargetedWakeStore(tmp_path / "wake.sqlite3")
    due = now() + timedelta(minutes=5)
    original = TargetedWake(
        wake_id="w1",
        resource_id="T1",
        reason="job status",
        kind=WakeKind.TARGETED_READ,
        due_at=due,
        capability_name="automation.job.read",
        arguments={"resource_id": "J1"},
    )
    store.schedule(original)
    store.schedule(original)
    with pytest.raises(ValueError):
        store.schedule(TargetedWake(
            wake_id="w1",
            resource_id="T1",
            reason="job status",
            kind=WakeKind.TARGETED_READ,
            due_at=due,
            capability_name="automation.job.read",
            arguments={"resource_id": "J2"},
        ))
    store.close()


def test_failed_read_retries_then_fails_closed(tmp_path):
    store = SQLiteTargetedWakeStore(tmp_path / "wake.sqlite3")
    store.schedule(TargetedWake(
        wake_id="w1",
        resource_id="T1",
        reason="job status",
        kind=WakeKind.TARGETED_READ,
        due_at=now() - timedelta(seconds=1),
        capability_name="automation.job.read",
        arguments={"resource_id": "J1"},
        max_attempts=2,
    ))
    state = store.retry_or_fail(
        "w1",
        error="provider unavailable",
        next_due_at=now() + timedelta(minutes=1),
    )
    assert state is WakeState.PENDING
    state = store.retry_or_fail(
        "w1",
        error="provider unavailable",
        next_due_at=now() + timedelta(minutes=2),
    )
    assert state is WakeState.FAILED
    store.close()


def test_queue_reconcile_wake_cannot_smuggle_read_capability(tmp_path):
    with pytest.raises(ValueError):
        TargetedWake(
            wake_id="w1",
            resource_id="queue",
            reason="capacity available",
            kind=WakeKind.QUEUE_RECONCILE,
            due_at=now(),
            capability_name="service.ticket.update",
        )
