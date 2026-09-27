from datetime import datetime, timedelta, timezone

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


class WorkResume:
    def __init__(self, *, result=True):
        self.result = result
        self.calls = []

    def resume(self, resource_id, *, reason):
        self.calls.append((resource_id, reason))
        return self.result


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



def test_successful_targeted_read_resumes_exact_work_item(tmp_path):
    store = SQLiteTargetedWakeStore(tmp_path / "wake.sqlite3")
    store.schedule(TargetedWake(
        wake_id="resume-1",
        resource_id="T1",
        reason="device availability",
        kind=WakeKind.TARGETED_READ,
        due_at=fixed_now() - timedelta(seconds=1),
        capability_name="service.ticket.read",
        arguments={"ticket_id": 1},
        resume_work_item=True,
    ))
    resume = WorkResume()
    queue = QueueAttention()
    maintenance = TargetedWakeMaintenance(
        store=store,
        reads=Reads(),
        queue_attention=queue,
        work_resume=resume,
        now=fixed_now,
    )

    maintenance.tick()

    assert resume.calls == [
        ("T1", "targeted_read_complete:service.ticket.read")
    ]
    assert store.state("resume-1") is WakeState.COMPLETE
    assert queue.reasons == []


def test_resume_requested_without_resume_port_fails_closed(tmp_path):
    store = SQLiteTargetedWakeStore(tmp_path / "wake.sqlite3")
    store.schedule(TargetedWake(
        wake_id="resume-missing",
        resource_id="T1",
        reason="device availability",
        kind=WakeKind.TARGETED_READ,
        due_at=fixed_now() - timedelta(seconds=1),
        capability_name="service.ticket.read",
        arguments={"ticket_id": 1},
        resume_work_item=True,
        max_attempts=1,
    ))
    maintenance = TargetedWakeMaintenance(
        store=store,
        reads=Reads(),
        queue_attention=QueueAttention(),
        work_resume=None,
        now=fixed_now,
    )

    maintenance.tick()

    assert store.state("resume-missing") is WakeState.FAILED


def test_stale_work_resume_noop_still_completes_safe_read(tmp_path):
    store = SQLiteTargetedWakeStore(tmp_path / "wake.sqlite3")
    store.schedule(TargetedWake(
        wake_id="resume-stale",
        resource_id="T1",
        reason="device availability",
        kind=WakeKind.TARGETED_READ,
        due_at=fixed_now() - timedelta(seconds=1),
        capability_name="service.ticket.read",
        arguments={"ticket_id": 1},
        resume_work_item=True,
    ))
    resume = WorkResume(result=False)
    maintenance = TargetedWakeMaintenance(
        store=store,
        reads=Reads(),
        queue_attention=QueueAttention(),
        work_resume=resume,
        now=fixed_now,
    )

    maintenance.tick()

    assert resume.calls
    assert store.state("resume-stale") is WakeState.COMPLETE
