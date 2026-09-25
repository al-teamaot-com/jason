from datetime import datetime, timedelta, timezone

from .attention_scheduler import (
    AttentionScheduler,
    AutonomyConfig,
    QueueAttentionState,
    WorkItem,
    WorkLedger,
    WorkState,
)


def test_default_active_work_limit_is_two():
    assert AutonomyConfig().max_active_work_items == 2


def test_only_active_and_verifying_consume_slots():
    ledger = WorkLedger([
        WorkItem("A", WorkState.ACTIVE),
        WorkItem("B", WorkState.WAITING),
        WorkItem("C", WorkState.APPROVAL_PENDING),
        WorkItem("D", WorkState.VERIFYING),
    ])
    assert ledger.active_count() == 2
    assert ledger.available_slots(AutonomyConfig()) == 0


def test_waiting_work_releases_capacity_for_next_ticket():
    ledger = WorkLedger([
        WorkItem("A", WorkState.WAITING),
        WorkItem("B", WorkState.AVAILABLE, priority=10),
        WorkItem("C", WorkState.AVAILABLE, priority=5),
        WorkItem("D", WorkState.AVAILABLE, priority=1),
    ])
    activated = ledger.activate_next(AutonomyConfig())
    assert [item.resource_id for item in activated] == ["B", "C"]
    assert ledger.get("D").state == WorkState.AVAILABLE


def test_queue_dirty_reasons_are_coalesced():
    attention = QueueAttentionState()
    attention.mark_dirty("ticket_entered")
    attention.mark_dirty("ticket_entered")
    attention.mark_dirty("customer_note")
    assert attention.dirty
    assert attention.reasons == {"ticket_entered", "customer_note"}


def test_dirty_queue_waits_when_capacity_is_full():
    attention = QueueAttentionState(
        dirty=True,
        reasons={"ticket_entered"},
        last_reconciled_at=datetime.now(timezone.utc),
    )
    decision = AttentionScheduler().should_reconcile(attention, capacity_available=False)
    assert not decision.should_reconcile


def test_dirty_queue_reconciles_when_capacity_opens():
    attention = QueueAttentionState(dirty=True, reasons={"ticket_entered"})
    decision = AttentionScheduler().should_reconcile(attention, capacity_available=True)
    assert decision.should_reconcile
    assert decision.reason == "queue_dirty_capacity_available"


def test_urgent_event_can_reconcile_even_when_capacity_full():
    attention = QueueAttentionState(dirty=True, reasons={"urgent_ticket"})
    decision = AttentionScheduler().should_reconcile(
        attention,
        capacity_available=False,
        urgent_event=True,
    )
    assert decision.should_reconcile
    assert decision.reason == "urgent_event"


def test_staleness_watchdog_recovers_from_missed_events():
    now = datetime.now(timezone.utc)
    attention = QueueAttentionState(
        dirty=False,
        last_reconciled_at=now - timedelta(hours=1),
    )
    decision = AttentionScheduler(staleness_budget=timedelta(minutes=30)).should_reconcile(
        attention,
        capacity_available=False,
        now=now,
    )
    assert decision.should_reconcile
    assert decision.reason == "staleness_budget_exceeded"


def test_sqlite_work_ledger_survives_restart(tmp_path):
    from .attention_scheduler import SQLiteWorkLedger

    path = tmp_path / "autonomous-work.sqlite3"
    first = SQLiteWorkLedger(path)
    first.upsert(
        WorkItem(
            "T100",
            WorkState.WAITING,
            priority=7,
            playbook_id="unexpected-shutdown",
            next_action="Check device availability",
            wake_on="device_online",
            reason="Endpoint offline",
        )
    )
    first.close()

    reopened = SQLiteWorkLedger(path)
    restored = reopened.get("T100")
    assert restored is not None
    assert restored.state == WorkState.WAITING
    assert restored.playbook_id == "unexpected-shutdown"
    assert restored.wake_on == "device_online"
    reopened.close()
