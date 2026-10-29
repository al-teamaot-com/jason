"""Issue #770: every actionable gap gets an owner alert, not a silent skip."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from jason_runtime.autonomy_worker_runtime import (
    OperationalAutonomyMaintenance, SQLiteOperationalWorkStore,
)
from jason_runtime.autonomy_teams_notification_maintenance import (
    TicketOwnerNotificationMaintenance,
)


class TeamsStub:
    def __init__(self, *, fail=False, synthetic=False):
        self.calls = []
        self.fail = fail
        self.synthetic = synthetic

    def send(self, event, **arguments):
        self.calls.append((event, arguments))
        if self.fail:
            raise RuntimeError("simulated transport failure")
        if self.synthetic:
            return {"message_id": "accepted:test", "message_id_synthetic": True}
        return {
            "message_id": f"provider-message-{len(self.calls)}",
            "message_id_synthetic": False,
        }


def setup(tmp_path):
    store = SQLiteOperationalWorkStore(tmp_path / "operational.sqlite3")
    notifier = TeamsStub()
    worker = object.__new__(OperationalAutonomyMaintenance)
    worker.store = store
    worker.completion_notifier = notifier
    worker.audit = None
    return worker, store, notifier


def candidate(ticket_id, *, company_id=333, ci_id=1259, version="version-1"):
    return SimpleNamespace(
        resource_id=str(ticket_id), source_version=version,
        context={
            "ticketNumber": f"T20261029.{ticket_id % 10000:04}",
            "companyID": company_id,
            "configurationItemID": ci_id,
            "title": "Remote endpoint diagnostics needed",
        },
    )


def classify(store, dispositions, now=None):
    when = now or datetime.now(timezone.utc)
    rows = [
        (ticket_id, state, reason, "version-1", False)
        for ticket_id, (state, reason) in dispositions.items()
    ]
    store.record_classifications(rows, observed_at=when.isoformat())
    return {n: (s, r, "version-1", False) for n, (s, r) in dispositions.items()}


def outbox(store):
    return [
        dict(row) for row in store._connection.execute(
            "SELECT * FROM autonomy_teams_notification_outbox "
            "ORDER BY recorded_at,event_key"
        ).fetchall()
    ]


@pytest.mark.parametrize("state,reason,action_fragment", [
    ("unsupported_capability", "no_applicable_promoted_playbook", "playbook"),
    ("unsupported_capability", "windows_licensing_diagnostics_candidate", "Windows"),
    ("governance_blocked", "admission_identity_or_governance_failure", "identity"),
    ("governance_blocked", "worker_blocked", "persisted block"),
    ("governance_blocked", "playbook_not_promoted", "promote"),
    ("waiting_human_review", "technician_review_required", "handoff"),
    ("waiting_device_access", "endpoint_offline_corroborated_deb", "reconnection"),
    ("waiting_dependency", "patch_approval_pending", "exact outstanding"),
    ("waiting_dependency", "active_capacity_full", "slot opens"),
])
def test_each_unactionable_ticket_emits_one_actionable_owner_message(
        tmp_path, state, reason, action_fragment):
    worker,store,notifier=setup(tmp_path)
    item=candidate(143338)
    data=classify(store,{143338:(state,reason)})
    worker._enqueue_owner_attention([item],data)
    rows=outbox(store)
    assert len(rows)==1
    assert rows[0]["event_type"]=="work_blocked"
    assert rows[0]["state"]=="pending"
    args=json.loads(rows[0]["arguments_json"])
    assert "T20261029." in args["summary"]
    assert "Autotask company #333" in args["summary"]
    assert "CI #1259" in args["summary"]
    assert state in args["summary"] and reason in args["summary"]
    assert "Checked" in args["summary"]
    assert action_fragment.casefold() in args["owner_action"].casefold()
    assert notifier.calls==[]  # scan only persists, no Teams call
    worker._enqueue_owner_attention([item],data)
    assert len(outbox(store))==1  # no per-scan duplicate

    maintenance=TicketOwnerNotificationMaintenance(
        store=store,notifier=notifier,monotonic=iter([0.0]).__next__
    )
    maintenance.tick()
    assert len(notifier.calls)==1
    assert notifier.calls[0][0]=="work_blocked"
    assert outbox(store)[0]["state"]=="delivered"
    maintenance._next_due=0
    assert len(notifier.calls)==1
    store.close()


def test_every_backlog_ticket_queued_without_first_page_starvation(tmp_path):
    worker,store,notifier=setup(tmp_path)
    ticket_ids=list(range(143400,143465))
    disposition={i:("unsupported_capability","no_applicable_promoted_playbook") for i in ticket_ids}
    data=classify(store,disposition)
    items=[candidate(i) for i in ticket_ids]
    worker._enqueue_owner_attention(items,data)
    assert len(outbox(store))==len(ticket_ids)
    assert notifier.calls==[]
    worker._enqueue_owner_attention(items,data)
    assert len(outbox(store))==len(ticket_ids)
    maintenance=TicketOwnerNotificationMaintenance(
        store=store,notifier=notifier,monotonic=iter([0.0,16.0]).__next__,
    )
    maintenance.tick()
    assert len(notifier.calls)==4
    maintenance.tick()
    assert len(notifier.calls)==8
    assert sum(row["state"]=="delivered" for row in outbox(store))==8
    store.close()


def test_resolved_ticket_attention_is_expired_before_send(tmp_path):
    worker,store,notifier=setup(tmp_path)
    item=candidate(143338)
    data=classify(store,{143338:("governance_blocked","worker_blocked")})
    worker._enqueue_owner_attention([item],data)
    assert len(outbox(store))==1
    classify(store,{143338:("eligible_now","active_work")})
    maintenance=TicketOwnerNotificationMaintenance(
        store=store,notifier=notifier,monotonic=iter([0.0]).__next__,
    )
    maintenance.tick()
    assert notifier.calls==[]
    assert outbox(store)[0]["state"]=="expired"
    assert outbox(store)[0]["last_error"]=="ticket_disposition_changed_or_missing"
    store.close()


def test_failed_teams_send_has_durable_retry_and_no_false_delivered(tmp_path):
    worker,store,notifier=setup(tmp_path)
    notifier.fail=True
    item=candidate(143338)
    data=classify(store,{143338:("governance_blocked","worker_blocked")})
    worker._enqueue_owner_attention([item],data)
    maintenance=TicketOwnerNotificationMaintenance(
        store=store,notifier=notifier,monotonic=iter([0.0]).__next__,
    )
    maintenance.tick()
    assert outbox(store)[0]["state"]=="pending"
    assert outbox(store)[0]["attempts"]==1
    assert outbox(store)[0]["last_error"]=="RuntimeError"
    assert len(notifier.calls)==1
    store.close()

    restored=SQLiteOperationalWorkStore(tmp_path / "operational.sqlite3")
    successful=TeamsStub()
    maintenance=TicketOwnerNotificationMaintenance(
        store=restored,notifier=successful,monotonic=iter([0.0,16.0]).__next__,
    )
    maintenance.tick()
    assert successful.calls==[]  # backoff remains durable over restart
    restored._connection.execute(
        "UPDATE autonomy_teams_notification_outbox SET next_due_at=?",
        ((datetime.now(timezone.utc)-timedelta(seconds=10)).isoformat(),),
    )
    maintenance._next_due=0
    maintenance.tick()
    assert len(successful.calls)==1
    assert outbox(restored)[0]["state"]=="delivered"
    restored.close()


def test_unknown_client_and_device_do_not_silently_skip_ticket(tmp_path):
    worker,store,notifier=setup(tmp_path)
    item=candidate(143338,company_id="bad",ci_id="not-an-id")
    data=classify(store,{143338:("unsupported_capability","no_applicable_promoted_playbook")})
    worker._enqueue_owner_attention([item],data)
    args=json.loads(outbox(store)[0]["arguments_json"])
    assert "Client Not verified" in args["summary"]
    assert "Device Unlinked" in args["summary"]
    assert "playbook" in args["owner_action"]
    assert notifier.calls==[]
    store.close()


def test_nonactionable_or_successfully_handled_tickets_do_not_alert(tmp_path):
    worker,store,notifier=setup(tmp_path)
    dispositions={
        143338:("not_actionable","existing_technician_activity"),
        143339:("eligible_now","active_work"),
        143340:("waiting_dependency","patch_window_pending"),
    }
    data=classify(store,dispositions)
    worker._enqueue_owner_attention([candidate(i) for i in dispositions],data)
    assert outbox(store)==[]
    assert notifier.calls==[]
    store.close()


def test_accepted_gateway_reference_is_not_falsely_delivered(tmp_path):
    worker,store,notifier=setup(tmp_path)
    notifier.synthetic=True
    item=candidate(143338)
    data=classify(store,{143338:("unsupported_capability","no_applicable_promoted_playbook")})
    worker._enqueue_owner_attention([item],data)
    maintenance=TicketOwnerNotificationMaintenance(
        store=store,notifier=notifier,monotonic=iter([0.0,16.0]).__next__,
    )
    maintenance.tick()
    assert len(notifier.calls)==1
    assert outbox(store)[0]["state"]=="unverified"
    maintenance._next_due=0
    maintenance.tick()
    assert len(notifier.calls)==1
    store.close()
