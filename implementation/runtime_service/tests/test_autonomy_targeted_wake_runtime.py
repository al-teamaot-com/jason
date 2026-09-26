from datetime import datetime, timedelta, timezone

import pytest

from autonomous_remediation.targeted_recheck import (
    SQLiteTargetedWakeStore,
    TargetedWake,
    WakeKind,
    WakeState,
)
from jason_runtime.autonomy_targeted_wake_runtime import (
    CompositeAutonomyMaintenance,
    TargetedWakeMaintenance,
)


class Reads:
    def __init__(self, *, status="succeeded"):
        self.status = status
        self.calls = []

    def execute(self, capability, arguments):
        self.calls.append((capability, dict(arguments)))
        return {
            "status": self.status,
            "error_code": None if self.status == "succeeded" else "READ_FAILED",
        }


class QueueAttention:
    def __init__(self):
        self.reasons = []

    def request_reconcile(self, reason):
        self.reasons.append(reason)


class Service:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    def tick(self):
        self.calls += 1
        return self.result


def fixed_now():
    return datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc)


def test_targeted_read_executes_exact_read_without_queue_scan(tmp_path):
    store = SQLiteTargetedWakeStore(tmp_path / "wake.sqlite3")
    store.schedule(TargetedWake(
        wake_id="job-1",
        resource_id="T1",
        reason="poll exact job",
        kind=WakeKind.TARGETED_READ,
        due_at=fixed_now() - timedelta(seconds=1),
        capability_name="automation.job.read",
        arguments={"resource_id": "J1"},
    ))
    reads = Reads()
    queue = QueueAttention()
    maintenance = TargetedWakeMaintenance(
        store=store,
        reads=reads,
        queue_attention=queue,
        now=fixed_now,
    )

    assert maintenance.tick() is True
    assert reads.calls == [("automation.job.read", {"resource_id": "J1"})]
    assert queue.reasons == []
    assert store.state("job-1") is WakeState.COMPLETE


def test_targeted_read_may_request_queue_reconcile_only_when_declared(tmp_path):
    store = SQLiteTargetedWakeStore(tmp_path / "wake.sqlite3")
    store.schedule(TargetedWake(
        wake_id="ticket-1",
        resource_id="T1",
        reason="ticket state changed",
        kind=WakeKind.TARGETED_READ,
        due_at=fixed_now() - timedelta(seconds=1),
        capability_name="service.ticket.read",
        arguments={"ticket_id": 1},
        queue_reconciliation_required=True,
    ))
    queue = QueueAttention()
    maintenance = TargetedWakeMaintenance(
        store=store,
        reads=Reads(),
        queue_attention=queue,
        now=fixed_now,
    )

    maintenance.tick()
    assert queue.reasons == ["targeted_read_complete:T1"]


def test_queue_reconcile_wake_never_invokes_provider_read(tmp_path):
    store = SQLiteTargetedWakeStore(tmp_path / "wake.sqlite3")
    store.schedule(TargetedWake(
        wake_id="queue-1",
        resource_id="queue",
        reason="capacity available",
        kind=WakeKind.QUEUE_RECONCILE,
        due_at=fixed_now() - timedelta(seconds=1),
    ))
    reads = Reads()
    queue = QueueAttention()
    maintenance = TargetedWakeMaintenance(
        store=store,
        reads=reads,
        queue_attention=queue,
        now=fixed_now,
    )

    maintenance.tick()
    assert reads.calls == []
    assert queue.reasons == ["targeted_wake:capacity available"]
    assert store.state("queue-1") is WakeState.COMPLETE


def test_mutation_capability_in_wake_fails_closed_before_invocation(tmp_path):
    store = SQLiteTargetedWakeStore(tmp_path / "wake.sqlite3")
    store.schedule(TargetedWake(
        wake_id="bad-1",
        resource_id="T1",
        reason="poisoned wake",
        kind=WakeKind.TARGETED_READ,
        due_at=fixed_now() - timedelta(seconds=1),
        capability_name="service.ticket.update",
        arguments={"payload": {"id": 1, "status": 8}},
        max_attempts=1,
    ))
    reads = Reads()
    maintenance = TargetedWakeMaintenance(
        store=store,
        reads=reads,
        queue_attention=QueueAttention(),
        now=fixed_now,
    )

    maintenance.tick()
    assert reads.calls == []
    assert store.state("bad-1") is WakeState.FAILED


def test_failed_read_is_retried_without_queue_reconcile(tmp_path):
    store = SQLiteTargetedWakeStore(tmp_path / "wake.sqlite3")
    store.schedule(TargetedWake(
        wake_id="read-1",
        resource_id="T1",
        reason="device availability",
        kind=WakeKind.TARGETED_READ,
        due_at=fixed_now() - timedelta(seconds=1),
        capability_name="endpoint.device.read",
        arguments={"resource_id": "D1"},
        max_attempts=2,
    ))
    queue = QueueAttention()
    maintenance = TargetedWakeMaintenance(
        store=store,
        reads=Reads(status="failed"),
        queue_attention=queue,
        retry_seconds=60,
        now=fixed_now,
    )

    maintenance.tick()
    assert store.state("read-1") is WakeState.PENDING
    assert queue.reasons == []


def test_composite_maintenance_runs_services_on_same_tick():
    first = Service(False)
    second = Service(True)
    composite = CompositeAutonomyMaintenance(first, second)
    assert composite.tick() is True
    assert first.calls == 1
    assert second.calls == 1


def test_attention_event_ingress_wakes_only_exact_known_work(tmp_path):
    from autonomous_remediation.targeted_recheck import TargetedWake, WakeKind, WakeState
    from jason_runtime.autonomy_targeted_wake_runtime import AutonomyAttentionEventIngress

    store = SQLiteTargetedWakeStore(tmp_path / "wakes.sqlite3")
    store.schedule(TargetedWake(
        wake_id="wake-1",
        resource_id="T1",
        reason="wait for approval",
        kind=WakeKind.TARGETED_READ,
        wake_on="approval_received",
        capability_name="service.ticket.read",
        arguments={"ticket_id": 1},
    ))
    store.schedule(TargetedWake(
        wake_id="wake-2",
        resource_id="T2",
        reason="wait for approval",
        kind=WakeKind.TARGETED_READ,
        wake_on="approval_received",
        capability_name="service.ticket.read",
        arguments={"ticket_id": 2},
    ))
    queue = QueueAttention()
    ingress = AutonomyAttentionEventIngress(store=store, queue_attention=queue)
    ids = ingress.signal(event="approval_received", resource_id="T1")
    assert ids == ("wake-1",)
    assert store.state("wake-1") is WakeState.PENDING
    assert store.state("wake-2") is WakeState.ARMED
    assert queue.reasons == []
    store.close()


def test_attention_event_ingress_queue_reconcile_is_explicit(tmp_path):
    from jason_runtime.autonomy_targeted_wake_runtime import AutonomyAttentionEventIngress

    store = SQLiteTargetedWakeStore(tmp_path / "wakes.sqlite3")
    queue = QueueAttention()
    ingress = AutonomyAttentionEventIngress(store=store, queue_attention=queue)

    assert ingress.signal(
        event="ticket_entered",
        resource_id="T100",
        queue_reconciliation_required=True,
    ) == ()
    assert queue.reasons == ["event:ticket_entered:T100"]
    store.close()


def test_attention_event_ingress_rejects_nonexact_resource(tmp_path):
    from jason_runtime.autonomy_targeted_wake_runtime import AutonomyAttentionEventIngress

    store = SQLiteTargetedWakeStore(tmp_path / "wakes.sqlite3")
    ingress = AutonomyAttentionEventIngress(store=store, queue_attention=QueueAttention())
    with pytest.raises(ValueError):
        ingress.signal(event="approval_received", resource_id="T*")
    store.close()


def test_terminal_datto_job_read_wakes_only_matching_event_subject(tmp_path):
    from jason_runtime.autonomy_targeted_wake_runtime import AutonomyAttentionEventIngress

    now = datetime.now(timezone.utc)
    store = SQLiteTargetedWakeStore(tmp_path / "wakes.sqlite3")
    poll = TargetedWake(
        wake_id="poll-j1",
        resource_id="T1",
        reason="check Datto job",
        kind=WakeKind.TARGETED_READ,
        due_at=now,
        capability_name="automation.job.read",
        arguments={"resource_id": "J1"},
    )
    wait_j1 = TargetedWake(
        wake_id="wait-j1",
        resource_id="T1",
        reason="resume when Datto job completes",
        kind=WakeKind.TARGETED_READ,
        wake_on="job_completed",
        event_subject_id="J1",
        capability_name="service.ticket.read",
        arguments={"ticket_id": 1},
    )
    wait_j2 = TargetedWake(
        wake_id="wait-j2",
        resource_id="T2",
        reason="resume when other Datto job completes",
        kind=WakeKind.TARGETED_READ,
        wake_on="job_completed",
        event_subject_id="J2",
        capability_name="service.ticket.read",
        arguments={"ticket_id": 2},
    )
    for wake in (poll, wait_j1, wait_j2):
        store.schedule(wake)

    class CompletedJobReads:
        def execute(self, capability, arguments):
            assert capability == "automation.job.read"
            assert arguments == {"resource_id": "J1"}
            return {
                "status": "succeeded",
                "evidence": {
                    "job": {"resource_id": "J1", "status": "completed"}
                },
            }

    queue = QueueAttention()
    ingress = AutonomyAttentionEventIngress(store=store, queue_attention=queue)
    maintenance = TargetedWakeMaintenance(
        store=store,
        reads=CompletedJobReads(),
        queue_attention=queue,
        event_ingress=ingress,
        now=lambda: now,
    )

    assert maintenance.tick() is True
    assert store.state("poll-j1") is WakeState.COMPLETE
    assert store.state("wait-j1") is WakeState.PENDING
    assert store.state("wait-j2") is WakeState.ARMED
    assert queue.reasons == []
    store.close()


def test_nonterminal_datto_job_read_does_not_emit_completion_event(tmp_path):
    from jason_runtime.autonomy_targeted_wake_runtime import AutonomyAttentionEventIngress

    store = SQLiteTargetedWakeStore(tmp_path / "wakes.sqlite3")
    store.schedule(TargetedWake(
        wake_id="wait-j1",
        resource_id="T1",
        reason="wait",
        kind=WakeKind.TARGETED_READ,
        wake_on="job_completed",
        event_subject_id="J1",
        capability_name="service.ticket.read",
        arguments={"ticket_id": 1},
    ))
    ingress = AutonomyAttentionEventIngress(store=store, queue_attention=QueueAttention())
    assert ingress.observe_datto_job_read({
        "status": "succeeded",
        "evidence": {"job": {"resource_id": "J1", "status": "running"}},
    }) == ()
    assert store.state("wait-j1") is WakeState.ARMED
    store.close()
