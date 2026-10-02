from __future__ import annotations

from datetime import datetime, timedelta, timezone

from jason_runtime.autonomy_worker_supervisor import TicketWorkerSupervisor


class FakeProcess:
    def __init__(self):
        self.alive = False
        self.started = 0
        self.terminated = 0
        self.joined = 0

    def start(self):
        self.alive = True
        self.started += 1

    def is_alive(self):
        return self.alive

    def terminate(self):
        self.alive = False
        self.terminated += 1

    def join(self, timeout=None):
        self.joined += 1


def test_supervisor_restarts_dead_worker():
    clock = [0.0]
    made = []

    def factory():
        process = FakeProcess()
        made.append(process)
        return process

    supervisor = TicketWorkerSupervisor(
        process_factory=factory,
        heartbeat_reader=lambda: None,
        interval_seconds=60,
        startup_grace_seconds=0,
        monotonic=lambda: clock[0],
    )
    supervisor.start()
    made[0].alive = False
    clock[0] = 10.0

    assert supervisor.poll() is True
    assert len(made) == 2
    assert made[1].alive is True
    assert supervisor.last_restart_reason == "process_exit"


def test_supervisor_restarts_stale_worker_after_grace():
    clock = [0.0]
    now = [datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)]
    made = []

    def factory():
        process = FakeProcess()
        made.append(process)
        return process

    supervisor = TicketWorkerSupervisor(
        process_factory=factory,
        heartbeat_reader=lambda: {
            "last_started_at": (now[0] - timedelta(minutes=10)).isoformat(),
            "last_completed_at": (now[0] - timedelta(minutes=10)).isoformat(),
        },
        interval_seconds=60,
        stale_after_seconds=120,
        startup_grace_seconds=30,
        monotonic=lambda: clock[0],
        now=lambda: now[0],
    )
    supervisor.start()
    clock[0] = 31.0

    assert supervisor.poll() is True
    assert len(made) == 2
    assert made[0].terminated == 1
    assert supervisor.last_restart_reason == "heartbeat_stale"


def test_supervisor_does_not_restart_recent_heartbeat():
    clock = [0.0]
    now = [datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)]
    made = []

    def factory():
        process = FakeProcess()
        made.append(process)
        return process

    supervisor = TicketWorkerSupervisor(
        process_factory=factory,
        heartbeat_reader=lambda: {
            "last_started_at": (now[0] - timedelta(seconds=30)).isoformat(),
            "last_completed_at": (now[0] - timedelta(seconds=60)).isoformat(),
        },
        interval_seconds=60,
        stale_after_seconds=120,
        startup_grace_seconds=0,
        monotonic=lambda: clock[0],
        now=lambda: now[0],
    )
    supervisor.start()

    assert supervisor.poll() is True
    assert len(made) == 1


def test_supervisor_bounds_restart_storm():
    clock = [0.0]
    made = []

    def factory():
        process = FakeProcess()
        made.append(process)
        return process

    supervisor = TicketWorkerSupervisor(
        process_factory=factory,
        heartbeat_reader=lambda: None,
        interval_seconds=60,
        startup_grace_seconds=0,
        max_restarts_per_window=2,
        restart_window_seconds=600,
        monotonic=lambda: clock[0],
    )
    supervisor.start()
    made[0].alive = False
    clock[0] = 1
    assert supervisor.poll() is True
    made[1].alive = False
    clock[0] = 2
    assert supervisor.poll() is True
    made[2].alive = False
    clock[0] = 3
    assert supervisor.poll() is False
    assert supervisor.restart_budget_exhausted is True
    assert supervisor.last_restart_reason == "restart_budget_exhausted:process_exit"
    assert len(made) == 3


def test_supervisor_health_reports_stale_heartbeat():
    clock = [0.0]
    now = [datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)]
    process = FakeProcess()

    supervisor = TicketWorkerSupervisor(
        process_factory=lambda: process,
        heartbeat_reader=lambda: {
            "last_started_at": (now[0] - timedelta(minutes=5)).isoformat(),
            "last_completed_at": (now[0] - timedelta(minutes=5)).isoformat(),
            "consecutive_failures": 0,
        },
        interval_seconds=60,
        stale_after_seconds=120,
        startup_grace_seconds=0,
        monotonic=lambda: clock[0],
        now=lambda: now[0],
    )
    supervisor.start()

    health = supervisor.health_status()

    assert health["status"] == "degraded"
    assert health["ticket_worker"] == "heartbeat_stale"


def test_supervisor_health_reports_recent_heartbeat():
    clock = [0.0]
    now = [datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)]
    process = FakeProcess()

    supervisor = TicketWorkerSupervisor(
        process_factory=lambda: process,
        heartbeat_reader=lambda: {
            "last_started_at": (now[0] - timedelta(seconds=20)).isoformat(),
            "last_completed_at": (now[0] - timedelta(seconds=25)).isoformat(),
            "consecutive_failures": 0,
        },
        interval_seconds=60,
        stale_after_seconds=120,
        startup_grace_seconds=0,
        monotonic=lambda: clock[0],
        now=lambda: now[0],
    )
    supervisor.start()

    health = supervisor.health_status()

    assert health["status"] == "ok"
    assert health["ticket_worker"] == "healthy"
    assert health["heartbeat_age_seconds"] == 25


def test_recent_failed_starts_do_not_mask_stale_successful_scan():
    clock = [0.0]
    now = [datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)]
    made = []

    def factory():
        process = FakeProcess()
        made.append(process)
        return process

    supervisor = TicketWorkerSupervisor(
        process_factory=factory,
        heartbeat_reader=lambda: {
            "last_started_at": (now[0] - timedelta(seconds=10)).isoformat(),
            "last_completed_at": (now[0] - timedelta(minutes=5)).isoformat(),
            "last_failed_at": (now[0] - timedelta(seconds=5)).isoformat(),
            "consecutive_failures": 4,
        },
        interval_seconds=60,
        stale_after_seconds=120,
        startup_grace_seconds=0,
        monotonic=lambda: clock[0],
        now=lambda: now[0],
    )
    supervisor.start()

    assert supervisor.poll() is True
    assert len(made) == 2
    assert made[0].terminated == 1
    assert supervisor.last_restart_reason == "heartbeat_stale"


def test_health_uses_last_successful_scan_not_recent_failed_start():
    clock = [0.0]
    now = [datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)]
    process = FakeProcess()

    supervisor = TicketWorkerSupervisor(
        process_factory=lambda: process,
        heartbeat_reader=lambda: {
            "last_started_at": (now[0] - timedelta(seconds=10)).isoformat(),
            "last_completed_at": (now[0] - timedelta(minutes=5)).isoformat(),
            "last_failed_at": (now[0] - timedelta(seconds=5)).isoformat(),
            "consecutive_failures": 4,
        },
        interval_seconds=60,
        stale_after_seconds=120,
        startup_grace_seconds=0,
        monotonic=lambda: clock[0],
        now=lambda: now[0],
    )
    supervisor.start()

    health = supervisor.health_status()

    assert health["status"] == "degraded"
    assert health["ticket_worker"] == "heartbeat_stale"
    assert health["heartbeat_age_seconds"] == 300
    assert health["consecutive_failures"] == 4
