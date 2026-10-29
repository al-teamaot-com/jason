"""Actual state-machine regression for Teams-independent ticket completion."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from jason_runtime.autonomy_teams_notification_maintenance import (
    TicketOwnerNotificationMaintenance,
)
from jason_runtime.autonomy_worker_runtime import (
    OperationalAutonomyMaintenance,
    OperationalWork,
    SQLiteOperationalWorkStore,
)


class NoWrite:
    def __init__(self):
        self.calls = []

    def execute(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        raise AssertionError("PSA/endpoint mutation never allowed for Teams reconciliation")


class ReadPSA:
    def __init__(self, *, ticket_id=143299, company_id=458,
                 ticket_number="T20261028.0042", status=5,
                 completed_date="2026-10-28T17:42:05.703Z"):
        self.ticket = {
            "id": ticket_id,
            "companyID": company_id,
            "ticketNumber": ticket_number,
            "status": status,
            "completedDate": completed_date,
        }
        self.calls = []

    def execute(self, capability, arguments):
        self.calls.append((capability, dict(arguments)))
        assert capability == "service.ticket.read"
        assert arguments == {"resource_id": 143299}
        return {
            "status": "succeeded",
            "evidence": {"data": {"items": [dict(self.ticket)]}},
        }


class Notifier:
    def __init__(self, *, fail=False, synthetic=False):
        self.fail = fail
        self.synthetic = synthetic
        self.calls = []

    def send(self, event, **arguments):
        self.calls.append((event, dict(arguments)))
        if self.fail:
            raise RuntimeError("simulated provider rejection")
        return {
            "message_id": (
                "accepted:synthetic-reference"
                if self.synthetic else "provider-message-id-1"
            ),
            "message_id_synthetic": self.synthetic,
        }


class NoDiscovery:
    def reconcile_candidates(self):
        return ()


class UnavailableDiscovery:
    def reconcile_candidates(self):
        raise OSError("Autotask temporarily unavailable")


class NoPromotion:
    def find_scope_approved(self, **kwargs):
        return None


def build(tmp_path: Path, *, notifier=None, reads=None, path=None, queue_source=None):
    store = SQLiteOperationalWorkStore(path or tmp_path / "worker.sqlite3")
    actions = NoWrite()
    worker = OperationalAutonomyMaintenance(
        queue_source=queue_source or NoDiscovery(),
        reads=reads or ReadPSA(),
        actions=actions,
        store=store,
        promotion_store=NoPromotion(),
        completion_notifier=notifier or Notifier(),
        interval_seconds=30,
        monotonic=iter([0.,31.,62.,93.,124.,155.]).__next__,
    )
    return worker, store, actions


def vulscan_work(*, phase="complete"):
    return OperationalWork(
        ticket_id=143299, ticket_number="T20261028.0042",
        title="VulScan - Missing patch",
        source_queue="Jason", company_id=458,
        configuration_item_id=1801, device_uid="rmm-exact-uid",
        hostname="LT-FCFG06", playbook_id="vulscan_missing_patch",
        phase=phase,
        last_reason=(
            "Execution failed closed: RuntimeError: autonomous completion "
            "Teams notification failed: CAPABILITY_INVOCATION_FAILED"
            if phase == "blocked" else "Verified Autotask completion"
        ),
    )


def outbox(store):
    return [dict(row) for row in store._connection.execute(
        "SELECT * FROM autonomy_teams_notification_outbox ORDER BY recorded_at,event_key"
    ).fetchall()]


def test_verified_patch_completion_survives_teams_failure_and_retries_once(tmp_path):
    notifier = Notifier(fail=True)
    worker, store, actions = build(tmp_path, notifier=notifier)
    work = vulscan_work()
    store.put(work)
    worker._notify_patch_completion(work, patch_summary="KB installed and verified")
    assert notifier.calls == []  # ticket worker never sends
    worker._drain_teams_notifications()  # independent auxiliary simulation
    assert store.get(work.ticket_id).phase == "complete"
    queued = outbox(store)
    assert len(queued) == 1
    assert queued[0]["event_type"] == "patch_completed"
    assert queued[0]["state"] == "pending"
    assert queued[0]["attempts"] == 1
    assert queued[0]["last_error"] == "RuntimeError"
    assert len(notifier.calls) == 1
    assert actions.calls == []

    # Restart with same durable DB and do not require a repeat patch action.
    store.close()
    new_notifier = Notifier()
    worker, store, actions = build(tmp_path, notifier=new_notifier)
    worker._drain_teams_notifications()
    assert new_notifier.calls == []  # not due until backoff
    store._connection.execute(
        "UPDATE autonomy_teams_notification_outbox SET next_due_at=?",
        ((datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat(),),
    )
    worker._drain_teams_notifications()
    assert len(new_notifier.calls) == 1
    assert outbox(store)[0]["state"] == "delivered"
    assert outbox(store)[0]["message_id"] == "provider-message-id-1"
    assert store.get(work.ticket_id).phase == "complete"
    worker._drain_teams_notifications()
    worker._notify_patch_completion(work, patch_summary="KB installed and verified")
    assert len(new_notifier.calls) == 1  # no duplicate
    assert actions.calls == []
    store.close()


def test_accepted_synthetic_reference_never_claims_delivery_or_auto_resends(tmp_path):
    notifier = Notifier(synthetic=True)
    worker, store, actions = build(tmp_path, notifier=notifier)
    worker._notify_ticket_event(vulscan_work(), "pickup", "In Progress")
    assert notifier.calls == []  # no network I/O on ticket worker
    worker._drain_teams_notifications()
    record = outbox(store)
    assert len(record) == 1
    assert record[0]["state"] == "unverified"
    assert store.last_note_fingerprint(
        143299,"vulscan_missing_patch","Teams - Ticket Activity - pickup",
    ) is None
    worker._drain_teams_notifications()
    assert len(notifier.calls) == 1
    assert actions.calls == []
    store.close()


@pytest.mark.parametrize("field,value", [
    ("id", 1),
    ("companyID", 827),
    ("ticketNumber", "T20261028.9999"),
    ("status", 7),
    ("completedDate", None),
])
def test_historical_completion_reconciliation_fails_closed_on_psa_mismatch(
        tmp_path,field,value):
    reads = ReadPSA()
    reads.ticket[field] = value
    worker,store,actions = build(tmp_path,reads=reads)
    work = vulscan_work(phase="blocked")
    store.put(work)
    worker._reconcile_completed_notification_blocks()
    assert store.get(work.ticket_id).phase=="blocked"
    assert actions.calls == []
    assert outbox(store)==[]
    store.close()


def test_historical_teams_failure_reconciles_true_completion_without_reremediation(tmp_path):
    notifier=Notifier(fail=True)
    reads=ReadPSA()
    worker,store,actions=build(tmp_path,notifier=notifier,reads=reads)
    work=vulscan_work(phase="blocked")
    store.put(work)
    worker._reconcile_completed_notification_blocks()
    row=store.get(work.ticket_id)
    assert row.phase=="complete"
    assert row.job_uid is None
    assert "readback verified" in row.last_reason
    assert len(reads.calls)==1
    assert reads.calls[0][0]=="service.ticket.read"
    assert actions.calls==[]
    assert outbox(store)[0]["event_type"]=="work_completed"
    assert outbox(store)[0]["state"]=="pending"
    worker._reconcile_completed_notification_blocks()
    assert len(reads.calls)==1  # no longer blocked
    store.close()


def test_ticket_pickup_notification_uses_durable_outbox_without_duplicate_or_psa_mutation(tmp_path):
    notifier=Notifier(fail=True)
    worker,store,actions=build(tmp_path,notifier=notifier)
    work=vulscan_work(phase="claim")
    store.put(work)
    worker._notify_ticket_event(work,"pickup","In Progress")
    worker._notify_ticket_event(work,"pickup","In Progress")
    assert store.get(work.ticket_id).phase=="claim"
    assert len(outbox(store))==1
    assert notifier.calls == []
    worker._drain_teams_notifications()
    assert len(notifier.calls)==1  # backoff
    assert actions.calls==[]
    store.close()


def test_readonly_reconciliation_and_notification_outbox_survive_psa_queue_outage(tmp_path):
    notifier = Notifier()
    worker,store,actions=build(tmp_path,notifier=notifier,queue_source=UnavailableDiscovery())
    work=vulscan_work()
    store.put(work)
    now=datetime.now(timezone.utc)
    store.queue_teams_notification(
        ticket_id=work.ticket_id,playbook_id=work.playbook_id,
        note_title="Teams - Ticket Activity - completion",
        fingerprint="f"*64,event_type="work_completed",
        arguments={"work_id":work.ticket_number,"work_title":work.title,
                   "summary":"Verified complete"},
        now=now,
    )
    worker.tick()
    assert notifier.calls == []  # PSA outage must not trigger or stall Teams I/O
    independent = TicketOwnerNotificationMaintenance(
        store=store, notifier=notifier, interval_seconds=15,
        monotonic=iter([0.0, 16.0]).__next__,
    )
    independent.tick()
    assert len(notifier.calls)==1
    assert outbox(store)[0]["state"]=="delivered"
    assert store.get(work.ticket_id).phase=="complete"
    assert actions.calls==[]
    store.close()


def test_outbox_expires_old_events_without_delayed_notifications(tmp_path):
    notifier=Notifier()
    worker,store,actions=build(tmp_path,notifier=notifier)
    work=vulscan_work()
    store.queue_teams_notification(
        ticket_id=work.ticket_id,playbook_id=work.playbook_id,
        note_title="Teams - Ticket Activity - pickup",
        fingerprint="f"*64,event_type="work_started",
        arguments={"work_id":work.ticket_number,"work_title":work.title,
                   "summary":"Historical pickup"},
        now=datetime.now(timezone.utc)-timedelta(days=2),
    )
    worker._drain_teams_notifications()
    assert outbox(store)[0]["state"]=="expired"
    assert notifier.calls==[]
    assert actions.calls==[]
    store.close()
