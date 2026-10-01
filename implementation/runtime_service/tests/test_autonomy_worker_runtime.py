from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from types import SimpleNamespace

from autonomous_remediation.autonomous_queue_worker import QueueCandidate
from autonomous_remediation.targeted_recheck import SQLiteTargetedWakeStore, WakeKind, WakeState
from jason_runtime.autonomy_worker_runtime import (
    BACKUPIQ_SCOPE,
    OperationalAutonomyError,
    OperationalAutonomyMaintenance,
    OperationalWork,
    SQLiteOperationalWorkStore,
)


class PromotionStore:
    def __init__(self, promoted=("datto_edr_av",)):
        self.promoted = set(promoted)

    def find_scope_approved(self, **kwargs):
        if kwargs.get("playbook_id") not in self.promoted:
            return None
        return SimpleNamespace(
            approval_id="approval-owner",
            allowed_capabilities=(
                "automation.component.execute",
                "service.ticket.note.create",
                "service.ticket.update",
                "service.ticket.client.notification.create",
            ),
        )


class ExactPromotionStore:
    def __init__(self, approved_scopes=()):
        self.approved_scopes = set(approved_scopes)

    def find_scope_approved(self, **kwargs):
        key = (
            kwargs.get("playbook_id"),
            kwargs.get("playbook_version"),
        )
        if key not in self.approved_scopes:
            return None
        return SimpleNamespace(
            approval_id="approval-owner-exact",
            allowed_capabilities=tuple(kwargs.get("required_capabilities") or ()),
        )


class QueueSource:
    def __init__(self, candidate):
        self.candidate = candidate

    def reconcile_candidates(self):
        context = dict(self.candidate.context)
        if (
            str(self.candidate.source_queue).strip().casefold() != "jason"
            and "_jason_source_status_label" not in context
        ):
            # Production Autotask discovery always supplies the source-status
            # marker. Keep generic worker fixtures shaped like live candidates.
            context["_jason_source_status_label"] = "New"
        return (replace(self.candidate, context=context),)


class Reads:
    def __init__(self):
        self.job_status = "completed"
        self.ticket_notes = []
        self.notification_history_reads = 0
        self.resource_license_types = {
            29682899: 1,
            29682888: 7,
            29682911: 7,
            29682922: 7,
        }

    def execute(self, capability, arguments):
        if capability == "service.ticket.notes.search":
            return {
                "status": "succeeded",
                "evidence": {"data": {"items": list(self.ticket_notes)}},
            }
        if capability == "service.notification.history.search":
            self.notification_history_reads += 1
            items = []
            if self.notification_history_reads > 1:
                items = [{
                    "id": self.notification_history_reads,
                    "ticketID": int(arguments["ticket_id"]),
                    "recipientEmailAddress": "chris.benton@e-gai.com",
                    "templateName": "Ticket - Update ticket notification 12082024",
                }]
            return {
                "status": "succeeded",
                "evidence": {"data": {"items": items}},
            }
        if capability == "service.resource.read":
            resource_id = int(arguments["resource_id"])
            return {
                "status": "succeeded",
                "evidence": {
                    "data": {
                        "item": {
                            "id": resource_id,
                            "licenseType": self.resource_license_types.get(resource_id, 1),
                        }
                    }
                },
            }
        if capability == "service.configuration.read":
            return {
                "status": "succeeded",
                "evidence": {
                    "data": {
                        "item": {
                            "id": 1583,
                            "companyID": 507,
                            "isActive": True,
                            "referenceNumber": "device-uid-1",
                            "referenceTitle": "PC-1",
                        }
                    }
                },
            }
        if capability == "endpoint.device.read":
            return {
                "status": "succeeded",
                "evidence": {
                    "record": {
                        "resource_id": "device-uid-1",
                        "hostname": "PC-1",
                        "online": True,
                    }
                },
            }
        if capability == "automation.job.read":
            return {
                "status": "succeeded",
                "evidence": {
                    "job": {
                        "resource_id": arguments["resource_id"],
                        "status": self.job_status,
                    }
                },
            }
        if capability == "automation.job.output.read":
            return {
                "status": "succeeded",
                "evidence": {
                    "resource_id": arguments["resource_id"],
                    "outputs": [
                        {
                            "component_uid": arguments["component_uid"],
                            "stream": "stdout",
                            "text": "Status=Healthy\nEDRVersion=3.17.1",
                        }
                    ],
                },
            }
        raise AssertionError(capability)


class Actions:
    def __init__(self):
        self.calls = []
        self.jobs = 0

    def execute(self, scope, capability, arguments):
        self.calls.append((scope.playbook_id, capability, arguments))
        if capability == "automation.component.execute":
            self.jobs += 1
            return {
                "data": {
                    "job_uid": f"job-{self.jobs}",
                    "job_status": "active",
                }
            }
        if capability == "service.ticket.update":
            payload = arguments.get("payload") or {}
            verified = [key for key in payload if key != "id"]
            return {
                "data": {
                    "jasonVerification": {
                        "readbackVerified": True,
                        "ticketId": payload.get("id"),
                        "verifiedFields": verified,
                    }
                }
            }
        return {}


def candidate(title="[Monitor] Antivirus status issue"):
    return QueueCandidate(
        resource_id="140933",
        priority=100,
        source_queue="Monitoring Alert",
        owned_by_jason=False,
        urgent=False,
        context={
            "id": 140933,
            "ticketNumber": "T20260925.9999",
            "title": title,
            "companyID": 507,
            "configurationItemID": 1583,
            "_jason_source_status_label": "New",
        },
    )


@pytest.mark.parametrize(
    ("queue_name", "status_label"),
    (
        ("Help Desk I", "New"),
        ("Help Desk II", "New"),
        ("Help Desk I", "Emergency"),
    ),
)
def test_help_desk_intake_status_is_continuously_admission_eligible(
    tmp_path: Path,
    queue_name: str,
    status_label: str,
):
    base = candidate()
    item = replace(
        base,
        source_queue=queue_name,
        context={
            **base.context,
            "_jason_source_status_label": status_label,
        },
    )
    actions = Actions()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(item),
        reads=Reads(),
        actions=actions,
        store=store,
        promotion_store=PromotionStore(),
        max_active_work_items=2,
        interval_seconds=30,
        monotonic=iter((0.0,)).__next__,
    )

    worker.tick()

    assert store.get(140933) is not None
    assert any(
        capability == "service.ticket.update"
        and arguments["payload"].get("queueID") == "Jason"
        for _, capability, arguments in actions.calls
    )
    store.close()


def test_help_desk_in_progress_is_assessed_but_not_admitted(tmp_path: Path):
    base = candidate()
    item = replace(
        base,
        source_queue="Help Desk I",
        context={
            **base.context,
            "_jason_source_status_label": "In Progress",
        },
    )
    actions = Actions()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(item),
        reads=Reads(),
        actions=actions,
        store=store,
        promotion_store=PromotionStore(),
        max_active_work_items=2,
        interval_seconds=30,
        monotonic=iter((0.0,)).__next__,
    )

    worker.tick()

    assert store.get(140933) is None
    assert store.classification_state(140933) == "not_actionable"
    assert actions.calls == []
    store.close()




def _owned_device_candidate(*, status_label: str = "In Progress") -> QueueCandidate:
    return QueueCandidate(
        resource_id="140933",
        priority=100,
        source_queue="Jason",
        owned_by_jason=True,
        urgent=False,
        context={
            "id": 140933,
            "ticketNumber": "T20260925.9999",
            "title": "[Monitor] Antivirus status issue",
            "companyID": 507,
            "configurationItemID": 1583,
            "_jason_source_status_label": status_label,
        },
    )


class UnverifiedClaimActions(Actions):
    def execute(self, scope, capability, arguments):
        if capability == "service.ticket.update":
            self.calls.append((scope.playbook_id, capability, arguments))
            payload = arguments.get("payload") or {}
            if payload.get("queueID") == "Jason":
                return {
                    "data": {
                        "jasonVerification": {
                            "readbackVerified": False,
                            "ticketId": payload.get("id"),
                            "verifiedFields": [],
                        }
                    }
                }
        return super().execute(scope, capability, arguments)


def test_claim_must_verify_jason_queue_before_diagnostics(tmp_path: Path):
    actions = UnverifiedClaimActions()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    maintenance = OperationalAutonomyMaintenance(
        queue_source=QueueSource(candidate()),
        reads=Reads(),
        actions=actions,
        store=store,
        promotion_store=PromotionStore(),
        interval_seconds=60,
    )

    maintenance.tick()

    capabilities = [call[1] for call in actions.calls]
    assert capabilities[0] == "service.ticket.update"
    assert "automation.component.execute" not in capabilities
    persisted = store.get(140933)
    assert persisted is not None
    assert persisted.phase == "blocked"
    assert store.list_open() == ()


class OfflineReads(Reads):
    def execute(self, capability, arguments):
        if capability == "endpoint.device.read":
            return {
                "status": "succeeded",
                "evidence": {
                    "record": {
                        "resource_id": "device-uid-1",
                        "hostname": "PC-1",
                        "online": False,
                    }
                },
            }
        return super().execute(capability, arguments)


class DebOnlineWhileDrmmOfflineReads(OfflineReads):
    def execute(self, capability, arguments):
        if capability == "backup.endpoint.asset.search":
            return {
                "status": "succeeded",
                "evidence": {
                    "data": {
                        "items": [
                            {
                                "id": "deb-current",
                                "name": "PC-1",
                                "status": "online",
                                "backupEnabled": True,
                                "lastSuccessfulBackupTimestamp": "2026-09-30T17:20:00Z",
                            }
                        ]
                    }
                },
            }
        return super().execute(capability, arguments)


class DebOfflineWhileDrmmOfflineReads(OfflineReads):
    def execute(self, capability, arguments):
        if capability == "backup.endpoint.asset.search":
            return {
                "status": "succeeded",
                "evidence": {
                    "data": {
                        "items": [
                            {
                                "id": "deb-offline",
                                "name": "PC-1",
                                "status": "offline",
                                "backupEnabled": True,
                                "lastOnlineTimestamp": "2026-09-29T17:20:00Z",
                            }
                        ]
                    }
                },
            }
        return super().execute(capability, arguments)


def test_recoverable_block_is_retried_after_backoff(tmp_path: Path):
    actions = Actions()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    store.put(OperationalWork(
        ticket_id=140933,
        ticket_number="T20260925.9999",
        title="[Monitor] Antivirus status issue",
        playbook_id="datto_edr_av",
        source_queue="Jason",
        company_id=507,
        configuration_item_id=1583,
        device_uid="device-uid-1",
        hostname="PC-1",
        phase="blocked",
        last_reason="governed read failed: CAPABILITY_INVOCATION_FAILED",
        updated_at="2026-09-28T00:00:00+00:00",
    ))
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(candidate()),
        reads=Reads(),
        actions=actions,
        store=store,
        promotion_store=PromotionStore(),
        max_active_work_items=2,
        interval_seconds=30,
        monotonic=iter((0.0,)).__next__,
    )
    worker.tick()
    current = store.get(140933)
    assert current is not None
    assert current.phase == "health_wait"
    assert any(capability == "automation.component.execute" for _, capability, _ in actions.calls)
    store.close()


def test_identity_resolution_block_remains_terminal(tmp_path: Path):
    actions = Actions()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    store.put(OperationalWork(
        ticket_id=140933,
        ticket_number="T20260925.9999",
        title="[Monitor] Antivirus status issue",
        playbook_id="datto_edr_av",
        source_queue="Jason",
        company_id=507,
        configuration_item_id=1583,
        device_uid="device-uid-1",
        hostname="PC-1",
        phase="blocked",
        last_reason="structured hostname did not resolve to one active same-company configuration item",
        updated_at="2026-09-28T00:00:00+00:00",
    ))
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(candidate()),
        reads=Reads(),
        actions=actions,
        store=store,
        promotion_store=PromotionStore(),
        max_active_work_items=2,
        interval_seconds=30,
        monotonic=iter((0.0,)).__next__,
    )
    worker.tick()
    current = store.get(140933)
    assert current is not None
    assert current.phase == "blocked"
    assert actions.calls == []
    store.close()


def test_owned_offline_ticket_moves_to_waiting_device_access_without_active_slot(tmp_path: Path):
    actions = Actions()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(_owned_device_candidate()),
        reads=OfflineReads(),
        actions=actions,
        store=store,
        promotion_store=PromotionStore(),
        max_active_work_items=2,
        interval_seconds=30,
        monotonic=iter((0.0,)).__next__,
    )

    worker.tick()

    work = store.get(140933)
    assert work is not None
    assert work.phase == "waiting_device_access:claim"
    assert work.company_id == 507
    assert work.configuration_item_id == 1583
    assert work.device_uid == "device-uid-1"
    assert work.hostname == "PC-1"
    updates = [
        args["payload"]
        for _, capability, args in actions.calls
        if capability == "service.ticket.update"
    ]
    assert updates == [{"id": 140933, "status": "Waiting Device Access"}]
    store.close()


def test_waiting_device_access_offline_is_idempotent(tmp_path: Path):
    actions = Actions()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(_owned_device_candidate(status_label="Waiting Device Access")),
        reads=OfflineReads(),
        actions=actions,
        store=store,
        promotion_store=PromotionStore(),
        max_active_work_items=2,
        interval_seconds=30,
        monotonic=iter((0.0,)).__next__,
    )

    worker.tick()

    work = store.get(140933)
    assert work is not None
    assert work.phase == "waiting_device_access:claim"
    assert work.device_uid == "device-uid-1"
    assert work.hostname == "PC-1"
    assert actions.calls == []
    store.close()


def test_orphaned_waiting_device_completed_ticket_retires_local_wait(tmp_path: Path):
    class EmptyQueueSource:
        def reconcile_candidates(self):
            return ()

    class TicketReads(Reads):
        def execute(self, capability, arguments):
            if capability == "service.ticket.read":
                return {
                    "status": "succeeded",
                    "evidence": {
                        "data": {
                            "items": [
                                {
                                    "id": 140933,
                                    "completedDate": "2026-09-30T11:32:22.750Z",
                                }
                            ]
                        }
                    },
                }
            return super().execute(capability, arguments)

    actions = Actions()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    store.put(OperationalWork(
        ticket_id=140933,
        ticket_number="T20260925.9999",
        title="[Monitor] Antivirus status issue",
        playbook_id="datto_edr_av",
        source_queue="Jason",
        company_id=507,
        configuration_item_id=1583,
        device_uid="device-uid-1",
        hostname="PC-1",
        phase="waiting_device_access:health_wait",
        last_reason="endpoint offline",
    ))
    worker = OperationalAutonomyMaintenance(
        queue_source=EmptyQueueSource(), reads=TicketReads(), actions=actions,
        store=store, promotion_store=PromotionStore(), max_active_work_items=2,
        interval_seconds=30, monotonic=iter((0.0,)).__next__,
    )

    worker.tick()

    current = store.get(140933)
    assert current is not None
    assert current.phase == "complete"
    assert "stale Waiting Device Access" in current.last_reason
    assert actions.calls == []
    store.close()


def test_orphaned_waiting_device_open_ticket_stops_without_psa_override(tmp_path: Path):
    class EmptyQueueSource:
        def reconcile_candidates(self):
            return ()

    class TicketReads(Reads):
        def execute(self, capability, arguments):
            if capability == "service.ticket.read":
                return {
                    "status": "succeeded",
                    "evidence": {"data": {"items": [{"id": 140933, "completedDate": None}]}},
                }
            return super().execute(capability, arguments)

    actions = Actions()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    store.put(OperationalWork(
        ticket_id=140933,
        ticket_number="T20260925.9999",
        title="[Monitor] Antivirus status issue",
        playbook_id="datto_edr_av",
        source_queue="Jason",
        company_id=507,
        configuration_item_id=1583,
        device_uid="device-uid-1",
        hostname="PC-1",
        phase="waiting_device_access:health_wait",
        last_reason="endpoint offline",
    ))
    worker = OperationalAutonomyMaintenance(
        queue_source=EmptyQueueSource(), reads=TicketReads(), actions=actions,
        store=store, promotion_store=PromotionStore(), max_active_work_items=2,
        interval_seconds=30, monotonic=iter((0.0,)).__next__,
    )

    worker.tick()

    current = store.get(140933)
    assert current is not None
    assert current.phase == "escalated"
    assert "preserve authoritative PSA/human state" in current.last_reason
    assert actions.calls == []
    store.close()


def test_waiting_device_access_online_returns_to_in_progress_and_resumes(tmp_path: Path):
    actions = Actions()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(_owned_device_candidate(status_label="Waiting Device Access")),
        reads=Reads(),
        actions=actions,
        store=store,
        promotion_store=PromotionStore(),
        max_active_work_items=2,
        interval_seconds=30,
        monotonic=iter((0.0,)).__next__,
    )

    worker.tick()

    work = store.get(140933)
    assert work is not None
    assert work.phase == "health_wait"
    updates = [
        args["payload"]
        for _, capability, args in actions.calls
        if capability == "service.ticket.update"
    ]
    assert updates[0] == {
        "id": 140933,
        "queueID": "Jason",
        "status": "In Progress",
        "billingCodeID": "Remote Support",
    }
    store.close()


def test_health_only_edr_ticket_is_admitted_but_threat_ticket_is_not():
    assert OperationalAutonomyMaintenance._is_health_only_edr_ticket(
        candidate().context
    )
    assert not OperationalAutonomyMaintenance._is_health_only_edr_ticket(
        candidate("Security Threat detected - Antivirus status").context
    )


def test_verified_healthy_ticket_is_claimed_documented_and_completed(tmp_path: Path):
    actions = Actions()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(candidate()),
        reads=Reads(),
        actions=actions,
        store=store,
        promotion_store=PromotionStore(),
        max_active_work_items=2,
        interval_seconds=30,
        monotonic=iter((0.0, 31.0)).__next__,
    )

    worker.tick()
    first = store.get(140933)
    assert first is not None
    assert first.phase == "health_wait"
    assert first.job_uid == "job-1"

    worker.tick()
    final = store.get(140933)
    assert final is not None
    assert final.phase == "complete"
    assert final.repair_attempts == 0

    ticket_updates = [
        args["payload"]
        for _, capability, args in actions.calls
        if capability == "service.ticket.update"
    ]
    assert ticket_updates[0] == {
        "id": 140933,
        "queueID": "Jason",
        "status": "In Progress",
        "billingCodeID": "Remote Support",
    }
    assert ticket_updates[-1] == {"id": 140933, "status": "Complete"}

    component_calls = [
        args
        for _, capability, args in actions.calls
        if capability == "automation.component.execute"
    ]
    assert len(component_calls) == 1
    assert component_calls[0]["component_name"].startswith(
        "Check Datto EDR/AV Status"
    )

    note_calls = [
        args["payload"]
        for _, capability, args in actions.calls
        if capability == "service.ticket.note.create"
    ]
    assert len(note_calls) == 1
    assert "Status=Healthy" in note_calls[0]["description"]
    store.close()



def test_duplicate_note_is_suppressed_across_terminal_work_reconsideration(tmp_path: Path):
    from jason_runtime.autonomy_worker_runtime import OperationalWork

    actions = Actions()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(candidate()),
        reads=Reads(),
        actions=actions,
        store=store,
        promotion_store=PromotionStore(),
        max_active_work_items=2,
        interval_seconds=30,
        monotonic=iter((0.0,)).__next__,
    )
    work = OperationalWork(
        ticket_id=140933,
        ticket_number="T20260925.9999",
        title="[Monitor] Antivirus status issue",
        playbook_id="datto_edr_av",
        source_queue="Jason",
        company_id=507,
        configuration_item_id=1583,
        device_uid="device-uid-1",
        hostname="PC-1",
        phase="escalated",
        last_reason="same terminal evidence",
    )

    assert worker._write_note(work, "Same result.", "Jason - Diagnostic") is True
    store.put(work)
    store.delete(work.ticket_id)
    assert worker._write_note(work, "Same   result.", "Jason - Diagnostic") is False

    note_calls = [
        args for _, capability, args in actions.calls
        if capability == "service.ticket.note.create"
    ]
    assert len(note_calls) == 1
    store.close()


def test_legacy_note_fingerprint_seeds_canonical_key_without_duplicate_write(tmp_path: Path):
    actions = Actions()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(candidate()),
        reads=Reads(),
        actions=actions,
        store=store,
        promotion_store=PromotionStore(),
        max_active_work_items=2,
        interval_seconds=30,
        monotonic=iter((0.0,)).__next__,
    )
    work = OperationalWork(
        ticket_id=140933,
        ticket_number="T20260925.9999",
        title="[Monitor] Antivirus status issue",
        playbook_id="datto_edr_av",
        source_queue="Jason",
        company_id=507,
        configuration_item_id=1583,
        device_uid="device-uid-1",
        hostname="PC-1",
        phase="escalated",
        last_reason="technician review required",
    )
    legacy_title = "Jason - Diagnostic"
    legacy_body = "Same result."
    legacy_encoded = json.dumps(
        {"title": legacy_title, "body": legacy_body},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    legacy_fingerprint = hashlib.sha256(legacy_encoded).hexdigest()
    store.remember_note_fingerprint(
        work.ticket_id,
        work.playbook_id,
        legacy_title,
        legacy_fingerprint,
    )

    assert worker._write_note(work, legacy_body, legacy_title) is False
    assert not [
        args for _, capability, args in actions.calls
        if capability == "service.ticket.note.create"
    ]
    canonical_fingerprint = store.last_note_fingerprint(
        work.ticket_id,
        work.playbook_id,
        "Jason - Human Review Required",
    )
    assert canonical_fingerprint
    assert canonical_fingerprint != legacy_fingerprint
    store.close()


def test_completion_fails_closed_without_terminal_readback_verification(tmp_path: Path):
    class NoReadbackActions(Actions):
        def execute(self, scope, capability, arguments):
            if capability == "service.ticket.update" and arguments.get("payload", {}).get("status") == "Complete":
                self.calls.append((scope.playbook_id, capability, arguments))
                return {"data": {"jasonVerification": {"readbackVerified": False, "verifiedFields": []}}}
            return super().execute(scope, capability, arguments)

    actions = NoReadbackActions()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(candidate()),
        reads=Reads(),
        actions=actions,
        store=store,
        promotion_store=PromotionStore(),
        max_active_work_items=2,
        interval_seconds=30,
        monotonic=iter((0.0,)).__next__,
    )
    from jason_runtime.autonomy_worker_runtime import OperationalWork, OperationalAutonomyError
    work = OperationalWork(
        ticket_id=140933,
        ticket_number="T20260925.9999",
        title="[Monitor] Antivirus status issue",
        playbook_id="datto_edr_av",
        source_queue="Jason",
        company_id=507,
        configuration_item_id=1583,
        device_uid="device-uid-1",
        hostname="PC-1",
        phase="health_wait",
    )

    try:
        worker._complete(work, "Status=Healthy\nEDRVersion=3.17.1")
    except OperationalAutonomyError:
        pass
    else:
        raise AssertionError("completion must fail closed when terminal readback is not verified")

    assert store.get(140933) is None
    assert not [
        args for _, capability, args in actions.calls
        if capability == "service.ticket.note.create"
    ]
    store.close()


def test_nonhealthy_health_check_runs_one_repair_then_verifies(tmp_path: Path):
    class RepairReads(Reads):
        def __init__(self):
            super().__init__()
            self.output_reads = 0

        def execute(self, capability, arguments):
            if capability == "automation.job.output.read":
                self.output_reads += 1
                text = (
                    "Status=IssuesFound\nAVHealthy=False"
                    if self.output_reads == 1
                    else "Status=Healthy\nAVHealthy=True"
                )
                return {
                    "status": "succeeded",
                    "evidence": {
                        "outputs": [
                            {
                                "component_uid": arguments["component_uid"],
                                "stream": "stdout",
                                "text": text,
                            }
                        ]
                    },
                }
            return super().execute(capability, arguments)

    actions = Actions()
    reads = RepairReads()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    clock = iter((0.0, 31.0, 62.0, 93.0, 124.0)).__next__
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(candidate()),
        reads=reads,
        actions=actions,
        store=store,
        promotion_store=PromotionStore(),
        interval_seconds=30,
        monotonic=clock,
    )

    worker.tick()  # claim + health dispatch
    worker.tick()  # nonhealthy -> repair_dispatch
    assert store.get(140933).phase == "repair_dispatch"
    worker.tick()  # repair dispatch
    assert store.get(140933).phase == "repair_wait"
    worker.tick()  # repair completed -> verify_dispatch
    assert store.get(140933).phase == "verify_dispatch"
    worker.tick()  # verify dispatch
    assert store.get(140933).phase == "verify_wait"

    component_names = [
        args["component_name"]
        for _, capability, args in actions.calls
        if capability == "automation.component.execute"
    ]
    assert component_names == [
        "Check Datto EDR/AV Status AOT Ver 12122025-1",
        "Datto EDR Force Reinstall and Upgrade [WIN] AOT 09162024",
        "Check Datto EDR/AV Status AOT Ver 12122025-1",
    ]
    assert store.get(140933).repair_attempts == 1
    store.close()


def test_worker_accepts_provider_native_datto_device_identity(tmp_path: Path):
    class RawEndpointReads(Reads):
        def execute(self, capability, arguments):
            if capability == "endpoint.device.read":
                return {
                    "status": "succeeded",
                    "evidence": {
                        "data": {
                            "uid": "device-uid-1",
                            "hostname": "PC-1",
                            "online": True,
                        }
                    },
                }
            return super().execute(capability, arguments)

    actions = Actions()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(candidate()),
        reads=RawEndpointReads(),
        actions=actions,
        store=store,
        promotion_store=PromotionStore(),
        max_active_work_items=2,
        interval_seconds=30,
        monotonic=iter((0.0,)).__next__,
    )

    worker.tick()

    work = store.get(140933)
    assert work is not None
    assert work.phase == "health_wait"
    assert work.device_uid == "device-uid-1"
    assert work.hostname == "PC-1"
    store.close()


def dns_candidate(title="DNS Agent service isStopped for PC-1"):
    return QueueCandidate(
        resource_id="140944",
        priority=90,
        source_queue="Monitoring Alert",
        owned_by_jason=False,
        urgent=False,
        context={
            "id": 140944,
            "ticketNumber": "T20260926.0001",
            "title": title,
            "companyID": 507,
            "configurationItemID": 1583,
        },
    )


def test_dns_ticket_requires_dns_promotion(tmp_path: Path):
    actions = Actions()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(dns_candidate()),
        reads=Reads(),
        actions=actions,
        store=store,
        promotion_store=PromotionStore(promoted=("datto_edr_av",)),
        max_active_work_items=2,
        interval_seconds=30,
        monotonic=iter((0.0,)).__next__,
    )

    worker.tick()

    assert store.get(140944) is None
    assert actions.calls == []
    store.close()


def test_dns_ticket_runs_standing_safe_diagnostic_then_escalates(tmp_path: Path):
    class DnsReads(Reads):
        def execute(self, capability, arguments):
            if capability == "automation.job.output.read":
                return {
                    "status": "succeeded",
                    "evidence": {
                        "outputs": [
                            {
                                "component_uid": arguments["component_uid"],
                                "stream": "stdout",
                                "text": (
                                    "INCIDENT_CLASSIFICATION=agent_corrupt_or_partial\n"
                                    "FILTERING_SERVICE=Stopped\n"
                                    "SERVICE_MANAGER=Running\n"
                                    "DNS_RESOLUTION=Success"
                                ),
                            }
                        ]
                    },
                }
            return super().execute(capability, arguments)

    actions = Actions()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(dns_candidate()),
        reads=DnsReads(),
        actions=actions,
        store=store,
        promotion_store=PromotionStore(promoted=("datto_edr_av", "dns_agent_diagnostic")),
        max_active_work_items=2,
        interval_seconds=30,
        monotonic=iter((0.0, 31.0)).__next__,
    )

    worker.tick()
    first = store.get(140944)
    assert first is not None
    assert first.playbook_id == "dns_agent_diagnostic"
    assert first.phase == "dns_diagnostic_wait"

    worker.tick()
    final = store.get(140944)
    assert final is not None
    assert final.phase == "escalated"
    assert "remediation branch requires separate accepted authority" in final.last_reason

    component_calls = [
        args
        for playbook_id, capability, args in actions.calls
        if capability == "automation.component.execute"
    ]
    assert len(component_calls) == 1
    assert component_calls[0]["component_name"] == (
        "DNSFilter / DNS Agent Diagnostic [WIN] AOT Ver 09242026"
    )
    assert component_calls[0]["component_uid"] == (
        "c3340a58-48d5-457b-bc30-5fd79e5ad8b1"
    )

    update_calls = [
        args["payload"]
        for _, capability, args in actions.calls
        if capability == "service.ticket.update"
    ]
    assert update_calls == [
        {
            "id": 140944,
            "queueID": "Jason",
            "status": "In Progress",
            "billingCodeID": "Remote Support",
        },
        {"id": 140944, "queueID": "Help Desk I", "status": "New"},
    ]

    note_calls = [
        args["payload"]
        for _, capability, args in actions.calls
        if capability == "service.ticket.note.create"
    ]
    assert len(note_calls) == 1
    assert "No service restart" in note_calls[0]["description"]
    store.close()


def security_candidate(title="SET-03 - Windows Security Log unreadable"):
    return QueueCandidate(
        resource_id="140955",
        priority=95,
        source_queue="Monitoring Alert",
        owned_by_jason=False,
        urgent=False,
        context={
            "id": 140955,
            "ticketNumber": "T20260926.0002",
            "title": title,
            "companyID": 507,
            "configurationItemID": 1583,
        },
    )


def test_security_log_ticket_requires_separate_promotion(tmp_path: Path):
    actions = Actions()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(security_candidate()),
        reads=Reads(),
        actions=actions,
        store=store,
        promotion_store=PromotionStore(promoted=("datto_edr_av", "dns_agent_diagnostic")),
        max_active_work_items=2,
        interval_seconds=30,
        monotonic=iter((0.0,)).__next__,
    )

    worker.tick()

    assert store.get(140955) is None
    assert actions.calls == []
    store.close()


def test_security_log_healthy_quick_test_documents_and_stops_before_alert_cleanup(
    tmp_path: Path,
):
    actions = Actions()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(security_candidate()),
        reads=Reads(),
        actions=actions,
        store=store,
        promotion_store=PromotionStore(
            promoted=("datto_edr_av", "dns_agent_diagnostic", "security_log_self_heal")
        ),
        max_active_work_items=2,
        interval_seconds=30,
        monotonic=iter((0.0, 31.0)).__next__,
    )

    worker.tick()
    first = store.get(140955)
    assert first is not None
    assert first.playbook_id == "security_log_self_heal"
    assert first.phase == "security_quick_wait"

    worker.tick()
    final = store.get(140955)
    assert final is not None
    assert final.phase == "escalated"
    assert final.repair_attempts == 0
    assert "cleanup remains separately gated" in final.last_reason

    component_calls = [
        args
        for playbook_id, capability, args in actions.calls
        if capability == "automation.component.execute"
    ]
    assert len(component_calls) == 1
    assert component_calls[0]["component_name"] == (
        "Security Log Quick Test [WIN] AOT Ver 12012025-1"
    )

    update_calls = [
        args["payload"]
        for _, capability, args in actions.calls
        if capability == "service.ticket.update"
    ]
    assert update_calls == [
        {
            "id": 140955,
            "queueID": "Jason",
            "status": "In Progress",
            "billingCodeID": "Remote Support",
        },
        {"id": 140955, "queueID": "Help Desk I", "status": "New"},
    ]

    note_calls = [
        args["payload"]
        for _, capability, args in actions.calls
        if capability == "service.ticket.note.create"
    ]
    assert len(note_calls) == 1
    assert "No repair was required" in note_calls[0]["description"]
    store.close()


def test_security_log_unhealthy_runs_one_self_heal_then_verifies(tmp_path: Path):
    class SecurityReads(Reads):
        def __init__(self):
            super().__init__()
            self.output_reads = 0

        def execute(self, capability, arguments):
            if capability == "automation.job.output.read":
                self.output_reads += 1
                text = (
                    "Status=Unhealthy\nSecurityLogReadable=False"
                    if self.output_reads == 1
                    else "Status=Healthy\nSecurityLogReadable=True"
                )
                return {
                    "status": "succeeded",
                    "evidence": {
                        "outputs": [
                            {
                                "component_uid": arguments["component_uid"],
                                "stream": "stdout",
                                "text": text,
                            }
                        ]
                    },
                }
            return super().execute(capability, arguments)

    actions = Actions()
    reads = SecurityReads()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(security_candidate()),
        reads=reads,
        actions=actions,
        store=store,
        promotion_store=PromotionStore(
            promoted=("datto_edr_av", "dns_agent_diagnostic", "security_log_self_heal")
        ),
        interval_seconds=30,
        monotonic=iter((0.0, 31.0, 62.0, 93.0, 124.0, 155.0)).__next__,
    )

    worker.tick()
    worker.tick()
    assert store.get(140955).phase == "security_repair_dispatch"
    worker.tick()
    assert store.get(140955).phase == "security_repair_wait"
    worker.tick()
    assert store.get(140955).phase == "security_verify_dispatch"
    worker.tick()
    assert store.get(140955).phase == "security_verify_wait"
    worker.tick()

    final = store.get(140955)
    assert final.phase == "escalated"
    assert final.repair_attempts == 1
    assert "cleanup remains separately gated" in final.last_reason

    component_names = [
        args["component_name"]
        for _, capability, args in actions.calls
        if capability == "automation.component.execute"
    ]
    assert component_names == [
        "Security Log Quick Test [WIN] AOT Ver 12012025-1",
        "Security Log Self-Heal [WIN] AOT Ver 11262025-2",
        "Security Log Quick Test [WIN] AOT Ver 12012025-1",
    ]
    store.close()


def post_candidate(title="Power-On-Self-Test (POST) errors occurred during the last system startup."):
    return QueueCandidate(
        resource_id="141004",
        priority=95,
        source_queue="Monitoring Alert",
        owned_by_jason=True,
        urgent=False,
        context={
            "id": 141004,
            "ticketNumber": "T20260923.0075",
            "title": title,
            "companyID": 311,
            "configurationItemID": 1583,
            "_jason_source_status_label": "New",
        },
    )


def test_post_ticket_requires_separate_promotion(tmp_path: Path):
    actions = Actions()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(post_candidate()),
        reads=Reads(),
        actions=actions,
        store=store,
        promotion_store=PromotionStore(
            promoted=("datto_edr_av", "dns_agent_diagnostic", "security_log_self_heal")
        ),
        max_active_work_items=2,
        interval_seconds=30,
        monotonic=iter((0.0,)).__next__,
    )

    worker.tick()

    assert store.get(141004) is None
    assert actions.calls == []
    store.close()


def test_post_protected_recurring_target_documents_and_escalates(tmp_path: Path):
    class PostReads(Reads):
        def execute(self, capability, arguments):
            if capability == "service.configuration.read":
                return {
                    "status": "succeeded",
                    "evidence": {
                        "data": {
                            "item": {
                                "id": 1583,
                                "companyID": 311,
                                "isActive": True,
                                "referenceNumber": "device-uid-1",
                                "referenceTitle": "PC-1",
                            }
                        }
                    },
                }
            if capability == "endpoint.device.read":
                return {
                    "status": "succeeded",
                    "evidence": {
                        "record": {
                            "resource_id": "device-uid-1",
                            "hostname": "PC-1",
                            "online": True,
                            "reboot_required": False,
                            "operating_system": "Microsoft HyperV Server 2012",
                            "device_type": {
                                "category": "Server",
                                "type": "Main System Chassis",
                            },
                        }
                    },
                }
            if capability == "endpoint.alert.history.search":
                return {
                    "status": "succeeded",
                    "evidence": {
                        "data": {
                            "alerts": [
                                {
                                    "alertUid": "post-1",
                                    "ticketNumber": "T20260923.0075",
                                    "alertContext": {
                                        "description": "Power-On-Self-Test (POST) errors occurred"
                                    },
                                },
                                {
                                    "alertUid": "post-2",
                                    "ticketNumber": "T20260726.0006",
                                    "alertContext": {
                                        "description": "Power-On-Self-Test (POST) errors occurred"
                                    },
                                },
                            ]
                        }
                    },
                }
            return super().execute(capability, arguments)

    actions = Actions()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(post_candidate()),
        reads=PostReads(),
        actions=actions,
        store=store,
        promotion_store=PromotionStore(
            promoted=(
                "datto_edr_av",
                "dns_agent_diagnostic",
                "security_log_self_heal",
                "post_error_investigation",
            )
        ),
        max_active_work_items=2,
        interval_seconds=30,
        monotonic=iter((0.0, 31.0)).__next__,
    )

    worker.tick()
    first = store.get(141004)
    assert first is not None
    assert first.playbook_id == "post_error_investigation"

    final = store.get(141004)
    assert final is not None
    assert final.phase == "escalated"
    assert "requires technician review" in final.last_reason

    component_calls = [
        args
        for _, capability, args in actions.calls
        if capability == "automation.component.execute"
    ]
    assert component_calls == []

    note_calls = [
        args["payload"]
        for _, capability, args in actions.calls
        if capability == "service.ticket.note.create"
    ]
    assert len(note_calls) == 1
    body = note_calls[0]["description"]
    assert "ProtectedRole=Yes" in body
    assert "Recurring=Yes" in body
    assert "No reboot" in body
    store.close()


def test_offline_high_priority_candidates_do_not_starve_online_post_ticket(tmp_path: Path):
    class MultiQueueSource:
        def reconcile_candidates(self):
            offline_one = candidate("[Monitor] Antivirus status issue")
            offline_one = QueueCandidate(
                resource_id="140901",
                priority=10000,
                source_queue="Monitoring Alert",
                owned_by_jason=False,
                urgent=True,
                context={
                    **offline_one.context,
                    "id": 140901,
                    "ticketNumber": "T20260926.0901",
                    "configurationItemID": 1901,
                },
            )
            offline_two = QueueCandidate(
                resource_id="140902",
                priority=9999,
                source_queue="Monitoring Alert",
                owned_by_jason=False,
                urgent=False,
                context={
                    **offline_one.context,
                    "id": 140902,
                    "ticketNumber": "T20260926.0902",
                    "configurationItemID": 1902,
                },
            )
            online_post = post_candidate()
            return (offline_one, offline_two, online_post)

    class StarvationReads(Reads):
        def execute(self, capability, arguments):
            if capability == "service.configuration.read":
                rid = int(arguments["resource_id"])
                if rid in {1901, 1902}:
                    return {
                        "status": "succeeded",
                        "evidence": {
                            "data": {
                                "item": {
                                    "id": rid,
                                    "companyID": 507,
                                    "isActive": True,
                                    "referenceNumber": f"offline-{rid}",
                                    "referenceTitle": f"OFFLINE-{rid}",
                                }
                            }
                        },
                    }
                if rid == 1583:
                    return {
                        "status": "succeeded",
                        "evidence": {
                            "data": {
                                "item": {
                                    "id": 1583,
                                    "companyID": 311,
                                    "isActive": True,
                                    "referenceNumber": "device-uid-1",
                                    "referenceTitle": "PC-1",
                                }
                            }
                        },
                    }
            if capability == "endpoint.device.read":
                rid = arguments["resource_id"]
                if str(rid).startswith("offline-"):
                    suffix = str(rid).split("-")[-1]
                    return {
                        "status": "succeeded",
                        "evidence": {
                            "record": {
                                "resource_id": rid,
                                "hostname": f"OFFLINE-{suffix}",
                                "online": False,
                            }
                        },
                    }
                return {
                    "status": "succeeded",
                    "evidence": {
                        "record": {
                            "resource_id": "device-uid-1",
                            "hostname": "PC-1",
                            "online": True,
                            "reboot_required": False,
                            "operating_system": "Microsoft HyperV Server 2012",
                            "device_type": {"category": "Server"},
                        }
                    },
                }
            if capability == "endpoint.alert.history.search":
                return {
                    "status": "succeeded",
                    "evidence": {
                        "data": {
                            "alerts": [
                                {
                                    "alertUid": "post-1",
                                    "ticketNumber": "T20260923.0075",
                                    "alertContext": {
                                        "description": "Power-On-Self-Test (POST) errors occurred"
                                    },
                                },
                                {
                                    "alertUid": "post-2",
                                    "ticketNumber": "T20260726.0006",
                                    "alertContext": {
                                        "description": "Power-On-Self-Test (POST) errors occurred"
                                    },
                                },
                            ]
                        }
                    },
                }
            return super().execute(capability, arguments)

    actions = Actions()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    worker = OperationalAutonomyMaintenance(
        queue_source=MultiQueueSource(),
        reads=StarvationReads(),
        actions=actions,
        store=store,
        promotion_store=PromotionStore(
            promoted=(
                "datto_edr_av",
                "dns_agent_diagnostic",
                "security_log_self_heal",
                "post_error_investigation",
            )
        ),
        max_active_work_items=2,
        interval_seconds=30,
        monotonic=iter((0.0,)).__next__,
    )

    worker.tick()

    offline_one_work = store.get(140901)
    offline_two_work = store.get(140902)
    assert offline_one_work is not None
    assert offline_two_work is not None
    assert offline_one_work.phase == "waiting_device_access:claim"
    assert offline_two_work.phase == "waiting_device_access:claim"
    assert store.list_open() == ()
    post = store.get(141004)
    assert post is not None
    assert post.phase == "escalated"
    note_calls = [
        args["payload"]
        for _, capability, args in actions.calls
        if capability == "service.ticket.note.create"
    ]
    assert len(note_calls) == 1
    assert note_calls[0]["ticketID"] == 141004
    store.close()


def unexpected_shutdown_candidate():
    return QueueCandidate(
        resource_id="141099",
        priority=95,
        source_queue="Monitoring Alert",
        owned_by_jason=False,
        urgent=False,
        context={
            "id": 141099,
            "ticketNumber": "T20260926.0100",
            "title": (
                "The previous system shutdown at 10:00:00 AM on 9/26/2026 "
                "was unexpected. for PC-1"
            ),
            "companyID": 507,
            "configurationItemID": 1583,
        },
    )


def test_unexpected_shutdown_requires_separate_promotion(tmp_path: Path):
    actions = Actions()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(unexpected_shutdown_candidate()),
        reads=Reads(),
        actions=actions,
        store=store,
        promotion_store=PromotionStore(
            promoted=(
                "datto_edr_av",
                "dns_agent_diagnostic",
                "security_log_self_heal",
                "post_error_investigation",
            )
        ),
        max_active_work_items=2,
        interval_seconds=30,
        monotonic=iter((0.0,)).__next__,
    )

    worker.tick()

    assert store.get(141099) is None
    assert actions.calls == []
    store.close()


def test_unexpected_shutdown_correlates_small_site_and_closes_after_clean_health_checks(
    tmp_path: Path,
):
    incident_ms = 1790416800000

    class ShutdownReads(Reads):
        def execute(self, capability, arguments):
            if capability == "endpoint.device.read":
                rid = str(arguments["resource_id"])
                if rid == "device-uid-1":
                    return {
                        "status": "succeeded",
                        "evidence": {
                            "record": {
                                "resource_id": "device-uid-1",
                                "hostname": "PC-1",
                                "site": "Site A",
                                "online": True,
                                "reboot_required": False,
                                "device_type": {
                                    "category": "Desktop",
                                    "type": "Desktop",
                                },
                            }
                        },
                    }
                if rid == "device-uid-2":
                    return {
                        "status": "succeeded",
                        "evidence": {
                            "record": {
                                "resource_id": "device-uid-2",
                                "hostname": "PC-2",
                                "site": "Site A",
                                "online": True,
                                "device_type": {
                                    "category": "Desktop",
                                    "type": "Desktop",
                                },
                            }
                        },
                    }
                if rid == "device-uid-vm":
                    return {
                        "status": "succeeded",
                        "evidence": {
                            "record": {
                                "resource_id": "device-uid-vm",
                                "hostname": "VM-1",
                                "site": "Site A",
                                "online": True,
                                "device_type": {
                                    "category": "Server",
                                    "type": "Virtual Machine",
                                },
                            }
                        },
                    }
            if capability == "endpoint.device.search":
                return {
                    "status": "succeeded",
                    "evidence": {
                        "resource_matches": [
                            {"resource_id": "device-uid-1", "hostname": "PC-1"},
                            {"resource_id": "device-uid-2", "hostname": "PC-2"},
                            {"resource_id": "device-uid-vm", "hostname": "VM-1"},
                        ]
                    },
                }
            if capability == "endpoint.powershell.read":
                return {
                    "status": "succeeded",
                    "evidence": {"data": {"stdout": "[]"}},
                }
            if capability == "endpoint.alert.history.search":
                rid = str(arguments["resource_id"])
                if rid == "device-uid-1":
                    alerts = [
                        {
                            "alertUid": "shutdown-current",
                            "ticketNumber": "T20260926.0100",
                            "timestamp": incident_ms,
                            "alertContext": {
                                "code": "6008",
                                "description": "The previous system shutdown was unexpected.",
                            },
                        },
                        {
                            "alertUid": "shutdown-prior",
                            "ticketNumber": "T20260920.0001",
                            "timestamp": incident_ms - 5 * 24 * 60 * 60 * 1000,
                            "alertContext": {
                                "code": "6008",
                                "description": "The previous system shutdown was unexpected.",
                            },
                        },
                    ]
                elif rid == "device-uid-2":
                    alerts = [
                        {
                            "alertUid": "shutdown-peer",
                            "ticketNumber": "T20260926.0101",
                            "timestamp": incident_ms + 4 * 60 * 1000,
                            "alertContext": {
                                "code": "6008",
                                "description": "The previous system shutdown was unexpected.",
                            },
                        }
                    ]
                else:
                    alerts = [
                        {
                            "alertUid": "shutdown-vm",
                            "ticketNumber": "T20260926.0102",
                            "timestamp": incident_ms + 2 * 60 * 1000,
                            "alertContext": {
                                "code": "6008",
                                "description": "The previous system shutdown was unexpected.",
                            },
                        }
                    ]
                return {
                    "status": "succeeded",
                    "evidence": {"data": {"alerts": alerts}},
                }
            return super().execute(capability, arguments)

    actions = Actions()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(unexpected_shutdown_candidate()),
        reads=ShutdownReads(),
        actions=actions,
        store=store,
        promotion_store=PromotionStore(
            promoted=(
                "datto_edr_av",
                "dns_agent_diagnostic",
                "security_log_self_heal",
                "post_error_investigation",
                "unexpected_shutdown",
            )
        ),
        max_active_work_items=2,
        interval_seconds=30,
        monotonic=iter((0.0,)).__next__,
    )

    worker.tick()

    final = store.get(141099)
    assert final is not None
    assert final.playbook_id == "unexpected_shutdown"
    assert final.phase == "complete"
    assert "SITE_CORRELATED_SMALL_SITE" in final.last_reason

    component_calls = [
        args
        for _, capability, args in actions.calls
        if capability == "automation.component.execute"
    ]
    assert component_calls == []

    note_calls = [
        args["payload"]
        for _, capability, args in actions.calls
        if capability == "service.ticket.note.create"
    ]
    assert len(note_calls) == 1
    body = note_calls[0]["description"]
    assert "ShutdownEvents30d=2" in body
    assert "SITE_CORRELATED_SMALL_SITE" in body
    assert "AffectedPhysicalDevicesPlusMinus15Min=2" in body
    assert "StorageHealthRisk=No" in body
    assert "No CHKDSK repair" in body
    store.close()


def backupiq_candidate():
    return QueueCandidate(
        resource_id="141185",
        priority=90,
        source_queue="Jason",
        owned_by_jason=True,
        urgent=False,
        context={
            "id": 141185,
            "ticketNumber": "T20260925.0003",
            "title": "BackupIQ: Backup for asset is not available for Atomic Plumbing & Drain Cleaning",
            "companyID": 333,
            "configurationItemID": 1259,
            "createDate": "2026-09-25T09:00:00Z",
        },
    )


def test_backupiq_unassigned_company_recovers_from_exact_endpoint_and_ci(tmp_path: Path):
    class RecoveryReads(Reads):
        def execute(self, capability, arguments):
            if capability == "endpoint.device.search":
                if str(arguments.get("hostname") or "").casefold() == "sos-50767":
                    return {
                        "status": "succeeded",
                        "evidence": {
                            "resource_matches": [
                                {
                                    "resource_id": "a241a6c6-c477-e7d3-4d1f-c878aaf92ce2",
                                    "hostname": "SOS-50767",
                                }
                            ]
                        },
                    }
                return {"status": "succeeded", "evidence": {"resource_matches": []}}
            if capability == "service.configuration.search":
                assert "company_id" not in arguments
                return {
                    "status": "succeeded",
                    "evidence": {
                        "data": {
                            "items": [
                                {
                                    "id": 433,
                                    "companyID": 878,
                                    "isActive": True,
                                    "referenceNumber": "a241a6c6-c477-e7d3-4d1f-c878aaf92ce2",
                                    "referenceTitle": "SOS-50767",
                                }
                            ]
                        }
                    },
                }
            if capability == "service.configuration.read":
                return {
                    "status": "succeeded",
                    "evidence": {
                        "data": {
                            "item": {
                                "id": 433,
                                "companyID": 878,
                                "isActive": True,
                                "referenceNumber": "a241a6c6-c477-e7d3-4d1f-c878aaf92ce2",
                                "referenceTitle": "SOS-50767",
                            }
                        }
                    },
                }
            if capability == "endpoint.device.read":
                return {
                    "status": "succeeded",
                    "evidence": {
                        "record": {
                            "resource_id": "a241a6c6-c477-e7d3-4d1f-c878aaf92ce2",
                            "hostname": "SOS-50767",
                            "online": False,
                        }
                    },
                }
            return super().execute(capability, arguments)

    candidate = QueueCandidate(
        resource_id="141679",
        priority=90,
        source_queue="Jason",
        owned_by_jason=True,
        urgent=False,
        context={
            "id": 141679,
            "ticketNumber": "T20260929.0041",
            "title": "BackupIQ: Backup for asset is not available for Star of the Sea Catholic Church",
            "description": "Asset: SOS-50767; backup is not available.",
            "companyID": 0,
            "configurationItemID": None,
            "createDate": "2026-09-30T00:52:00Z",
        },
    )
    actions = Actions()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(candidate),
        reads=RecoveryReads(),
        actions=actions,
        store=store,
        promotion_store=PromotionStore(promoted=("backupiq_endpoint_backup",)),
        max_active_work_items=2,
        interval_seconds=30,
        monotonic=iter((0.0,)).__next__,
    )

    work = worker._admit(candidate, BACKUPIQ_SCOPE)

    assert work.company_id == 878
    assert work.configuration_item_id == 433
    assert work.device_uid == "a241a6c6-c477-e7d3-4d1f-c878aaf92ce2"
    assert work.hostname == "SOS-50767"
    update_payloads = [
        args["payload"]
        for _, capability, args in actions.calls
        if capability == "service.ticket.update"
    ]
    assert {"id": 141679, "configurationItemID": 433} not in update_payloads
    store.close()


def test_backupiq_provider_asset_without_rmm_endpoint_hands_off_human_review(tmp_path: Path):
    class MissingEndpointReads(Reads):
        def execute(self, capability, arguments):
            if capability == "endpoint.device.search":
                return {"status": "succeeded", "evidence": {"resource_matches": []}}
            if capability == "service.configuration.search":
                if str(arguments.get("name") or "").casefold() == "sos-50767":
                    return {
                        "status": "succeeded",
                        "evidence": {
                            "data": {
                                "items": [
                                    {
                                        "id": 433,
                                        "companyID": 878,
                                        "isActive": True,
                                        "referenceNumber": "stale-rmm-uid",
                                        "referenceTitle": "SOS-50767",
                                    }
                                ]
                            }
                        },
                    }
                return {"status": "succeeded", "evidence": {"data": {"items": []}}}
            if capability == "backup.endpoint.asset.search":
                assert arguments["company_id"] == 878
                assert arguments["name"] == "SOS-50767"
                return {
                    "status": "succeeded",
                    "evidence": {
                        "data": {
                            "items": [
                                {
                                    "id": "0XX3NXQH2",
                                    "name": "SOS-50767",
                                    "status": "offline",
                                }
                            ]
                        }
                    },
                }
            return super().execute(capability, arguments)

    candidate = QueueCandidate(
        resource_id="141679",
        priority=90,
        source_queue="Jason",
        owned_by_jason=True,
        urgent=False,
        context={
            "id": 141679,
            "ticketNumber": "T20260929.0041",
            "title": "BackupIQ: Backup for asset is not available for Star of the Sea Catholic Church",
            "description": "Asset: SOS-50767; backup is not available.",
            "companyID": 0,
            "configurationItemID": None,
        },
    )
    actions = Actions()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(candidate), reads=MissingEndpointReads(), actions=actions, store=store,
        promotion_store=PromotionStore(promoted=("backupiq_endpoint_backup",)),
        max_active_work_items=2, interval_seconds=30, monotonic=iter((0.0,)).__next__,
    )

    try:
        worker._admit(candidate, BACKUPIQ_SCOPE)
    except OperationalAutonomyError as exc:
        worker._record_admission_failure(candidate, BACKUPIQ_SCOPE, exc)
    else:
        raise AssertionError("missing managed endpoint must not be admitted")

    work = store.get(141679)
    assert work is not None
    assert work.phase == "escalated"
    assert work.company_id == 878
    assert work.configuration_item_id == 433
    assert work.hostname == "SOS-50767"
    update_payloads = [
        args["payload"]
        for _, capability, args in actions.calls
        if capability == "service.ticket.update"
    ]
    assert {"id": 141679, "queueID": "Help Desk I", "status": "Human Review"} in update_payloads
    note_payloads = [
        args["payload"]
        for _, capability, args in actions.calls
        if capability == "service.ticket.note.create"
    ]
    assert any(payload["title"] == "Jason - Human Review Required" for payload in note_payloads)
    assert any(
        "managed Datto RMM endpoint is no longer present" in payload["description"]
        for payload in note_payloads
    )
    store.close()


def test_backupiq_unassigned_company_does_not_guess_ambiguous_endpoint(tmp_path: Path):
    class AmbiguousReads(Reads):
        def execute(self, capability, arguments):
            if capability == "endpoint.device.search":
                if str(arguments.get("hostname") or "").casefold() == "sos-50767":
                    return {
                        "status": "succeeded",
                        "evidence": {
                            "resource_matches": [
                                {"resource_id": "uid-1", "hostname": "SOS-50767"},
                                {"resource_id": "uid-2", "hostname": "SOS-50767"},
                            ]
                        },
                    }
                return {"status": "succeeded", "evidence": {"resource_matches": []}}
            if capability == "service.configuration.search":
                return {"status": "succeeded", "evidence": {"data": {"items": []}}}
            return super().execute(capability, arguments)

    candidate = QueueCandidate(
        resource_id="141679",
        priority=90,
        source_queue="Jason",
        owned_by_jason=True,
        urgent=False,
        context={
            "id": 141679,
            "ticketNumber": "T20260929.0041",
            "title": "BackupIQ: Backup for asset is not available for Star of the Sea Catholic Church",
            "description": "Asset: SOS-50767; backup is not available.",
            "companyID": 0,
            "configurationItemID": None,
        },
    )
    actions = Actions()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(candidate), reads=AmbiguousReads(), actions=actions, store=store,
        promotion_store=PromotionStore(promoted=("backupiq_endpoint_backup",)),
        max_active_work_items=2, interval_seconds=30, monotonic=iter((0.0,)).__next__,
    )

    try:
        worker._admit(candidate, BACKUPIQ_SCOPE)
    except OperationalAutonomyError:
        pass
    else:
        raise AssertionError("ambiguous endpoint correlation must fail closed")
    store.close()


def test_backupiq_scope_is_owner_approved_version_1_2_0():
    from jason_runtime.autonomy_worker_runtime import BACKUPIQ_SCOPE

    assert BACKUPIQ_SCOPE.playbook_id == "backupiq_endpoint_backup"
    assert BACKUPIQ_SCOPE.playbook_version == "1.2.0"
    assert BACKUPIQ_SCOPE.policy_id == "playbook-autonomy:backupiq_endpoint_backup"
    assert BACKUPIQ_SCOPE.required_action_capabilities == (
        "automation.component.execute",
        "service.ticket.note.create",
        "service.ticket.update",
    )


def test_backupiq_requires_separate_promotion(tmp_path: Path):
    actions = Actions()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(backupiq_candidate()),
        reads=Reads(),
        actions=actions,
        store=store,
        promotion_store=PromotionStore(
            promoted=(
                "datto_edr_av",
                "dns_agent_diagnostic",
                "security_log_self_heal",
                "post_error_investigation",
                "unexpected_shutdown",
            )
        ),
        max_active_work_items=2,
        interval_seconds=30,
        monotonic=iter((0.0, 31.0)).__next__,
    )

    worker.tick()
    worker.tick()

    assert store.get(141185) is None
    assert actions.calls == []
    store.close()


def test_backupiq_queue_normalization_precedes_active_capacity(tmp_path: Path):
    class MultiQueueSource:
        def reconcile_candidates(self):
            return (
                candidate(),
                replace(
                    backupiq_candidate(),
                    source_queue="Monitoring Alert",
                    owned_by_jason=False,
                ),
            )

    actions = Actions()
    reads = Reads()
    reads.job_status = "active"
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    store.put(
        OperationalWork(
            ticket_id=140933,
            ticket_number="T20260925.9999",
            title="[Monitor] Antivirus status issue",
            playbook_id="datto_edr_av",
            source_queue="Jason",
            company_id=507,
            configuration_item_id=1583,
            device_uid="device-uid-1",
            hostname="PC-1",
            phase="health_wait",
            job_uid="job-active",
            component_uid="component-active",
        )
    )
    worker = OperationalAutonomyMaintenance(
        queue_source=MultiQueueSource(),
        reads=reads,
        actions=actions,
        store=store,
        promotion_store=PromotionStore(
            promoted=("datto_edr_av", "backupiq_endpoint_backup")
        ),
        max_active_work_items=1,
        interval_seconds=30,
        monotonic=iter((0.0,)).__next__,
    )

    worker.tick()

    update_calls = [
        args["payload"]
        for _, capability, args in actions.calls
        if capability == "service.ticket.update"
    ]
    assert {"id": 141185, "queueID": "Jason"} in update_calls
    assert store.get(141185) is None
    store.close()


def test_backupiq_offline_endpoint_waits_for_device_without_consuming_slot(tmp_path: Path):
    class BackupReads(Reads):
        def execute(self, capability, arguments):
            if capability == "service.configuration.read":
                return {
                    "status": "succeeded",
                    "evidence": {
                        "data": {
                            "item": {
                                "id": 1259,
                                "companyID": 333,
                                "isActive": True,
                                "referenceNumber": "backup-device-1",
                                "referenceTitle": "APD-50399",
                            }
                        }
                    },
                }
            if capability == "endpoint.device.read":
                return {
                    "status": "succeeded",
                    "evidence": {
                        "record": {
                            "resource_id": "backup-device-1",
                            "hostname": "APD-50399",
                            "online": False,
                            "reboot_required": False,
                        }
                    },
                }
            if capability == "backup.endpoint.asset.search":
                return {
                    "status": "succeeded",
                    "evidence": {
                        "data": {
                            "items": [
                                {
                                    "id": "backup-asset-1",
                                    "name": "APD-50399",
                                    "status": "offline",
                                    "backupEnabled": True,
                                    "lastSuccessfulBackupTimestamp": "2026-09-24T08:00:00Z",
                                    "lastOnlineTimestamp": "2026-09-24T09:00:00Z",
                                }
                            ]
                        }
                    },
                }
            if capability == "backup.backupiq.alert.search":
                return {
                    "status": "succeeded",
                    "evidence": {"data": {"items": [{"id": "alert-1"}]}},
                }
            return super().execute(capability, arguments)

    actions = Actions()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(backupiq_candidate()),
        reads=BackupReads(),
        actions=actions,
        store=store,
        promotion_store=PromotionStore(
            promoted=(
                "datto_edr_av",
                "dns_agent_diagnostic",
                "security_log_self_heal",
                "post_error_investigation",
                "unexpected_shutdown",
                "backupiq_endpoint_backup",
            )
        ),
        max_active_work_items=2,
        interval_seconds=30,
        monotonic=iter((0.0, 31.0)).__next__,
    )

    worker.tick()
    worker.tick()

    work = store.get(141185)
    assert work is not None
    assert work.phase == "waiting_device_access:backupiq_investigate"
    assert "waiting for exact endpoint access" in work.last_reason
    assert store.list_open() == ()
    component_calls = [
        args
        for _, capability, args in actions.calls
        if capability == "automation.component.execute"
    ]
    assert component_calls == []
    note_calls = [
        args["payload"]
        for _, capability, args in actions.calls
        if capability == "service.ticket.note.create"
    ]
    assert len(note_calls) == 1
    assert note_calls[0]["title"] == "Jason - Technical Review"
    description = note_calls[0]["description"]
    assert "STATUS:" in description
    assert "FINDINGS:" in description
    assert "NEXT ACTION:" in description
    assert "JASON STATE:" in description
    assert "Classification=true_offline_both_sources" in description
    update_calls = [
        args["payload"]
        for _, capability, args in actions.calls
        if capability == "service.ticket.update"
    ]
    assert update_calls == [
        {
            "id": 141185,
            "queueID": "Jason",
            "status": "In Progress",
            "billingCodeID": "Remote Support",
        },
        {
            "id": 141185,
            "status": "Waiting Device Access",
        },
    ]
    assert all(payload.get("queueID") != "Help Desk I" for payload in update_calls)
    store.close()


def test_backupiq_legacy_offline_escalation_migrates_to_waiting(tmp_path: Path):
    class LegacyOfflineReads(Reads):
        def execute(self, capability, arguments):
            if capability == "endpoint.device.read":
                return {
                    "status": "succeeded",
                    "evidence": {
                        "record": {
                            "resource_id": "backup-device-1",
                            "hostname": "APD-50399",
                            "online": False,
                            "reboot_required": False,
                        }
                    },
                }
            return super().execute(capability, arguments)

    actions = Actions()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    store.put(
        OperationalWork(
            ticket_id=141185,
            ticket_number="T20260925.0003",
            title="BackupIQ: Backup for asset is not available for Atomic Plumbing & Drain Cleaning",
            playbook_id="backupiq_endpoint_backup",
            source_queue="Jason",
            company_id=333,
            configuration_item_id=1259,
            device_uid="backup-device-1",
            hostname="APD-50399",
            phase="escalated",
            last_reason=(
                "BackupIQ diagnostic classified an inactive/offline endpoint; "
                "waiting/recheck automation remains separately gated."
            ),
        )
    )
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(backupiq_candidate()),
        reads=LegacyOfflineReads(),
        actions=actions,
        store=store,
        promotion_store=PromotionStore(promoted=("backupiq_endpoint_backup",)),
        max_active_work_items=2,
        interval_seconds=30,
        monotonic=iter((0.0,)).__next__,
    )

    worker.tick()

    work = store.get(141185)
    assert work is not None
    assert work.phase == "waiting_device_access:backupiq_investigate"
    assert "Migrated legacy BackupIQ offline escalation" in work.last_reason
    assert store.list_open() == ()
    update_calls = [
        args["payload"]
        for _, capability, args in actions.calls
        if capability == "service.ticket.update"
    ]
    assert update_calls == [
        {
            "id": 141185,
            "status": "Waiting Device Access",
        }
    ]
    note_calls = [
        args["payload"]
        for _, capability, args in actions.calls
        if capability == "service.ticket.note.create"
    ]
    assert note_calls == []
    store.close()



class BackupIQScenarioReads(Reads):
    def __init__(
        self,
        *,
        drmm_online: bool,
        provider_status: str,
        last_success: str | None,
        current_alerts: bool = True,
        recovered_after_reinstall: bool = False,
    ):
        super().__init__()
        self.drmm_online = drmm_online
        self.provider_status = provider_status
        self.last_success = last_success
        self.current_alerts = current_alerts
        self.recovered_after_reinstall = recovered_after_reinstall
        self.asset_reads = 0

    def execute(self, capability, arguments):
        if capability == "service.configuration.read":
            return {
                "status": "succeeded",
                "evidence": {"data": {"item": {
                    "id": 1259,
                    "companyID": 333,
                    "isActive": True,
                    "referenceNumber": "backup-device-1",
                    "referenceTitle": "APD-50399",
                }}},
            }
        if capability == "endpoint.device.read":
            return {
                "status": "succeeded",
                "evidence": {"record": {
                    "resource_id": "backup-device-1",
                    "hostname": "APD-50399",
                    "online": self.drmm_online,
                    "reboot_required": False,
                }},
            }
        if capability == "backup.endpoint.asset.search":
            self.asset_reads += 1
            status = self.provider_status
            last_success = self.last_success
            if self.recovered_after_reinstall and self.asset_reads > 1:
                status = "online"
                last_success = "2099-01-01T00:00:00Z"
            return {
                "status": "succeeded",
                "evidence": {"data": {"items": [{
                    "id": "backup-asset-1",
                    "name": "APD-50399",
                    "status": status,
                    "backupEnabled": True,
                    "lastSuccessfulBackupTimestamp": last_success,
                    "lastOnlineTimestamp": "2026-09-29T14:00:00Z",
                }]}},
            }
        if capability == "backup.backupiq.alert.search":
            return {
                "status": "succeeded",
                "evidence": {"data": {
                    "items": ([{"id": "alert-1"}] if self.current_alerts else [])
                }},
            }
        return super().execute(capability, arguments)


def _backupiq_worker(tmp_path: Path, reads, actions=None, candidate_value=None, times=None):
    actions = actions or Actions()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(candidate_value or backupiq_candidate()),
        reads=reads,
        actions=actions,
        store=store,
        promotion_store=PromotionStore(promoted=("backupiq_endpoint_backup",)),
        max_active_work_items=2,
        interval_seconds=30,
        monotonic=iter(times or (0.0, 31.0, 62.0, 93.0, 124.0)).__next__,
    )
    return worker, store, actions


def test_backupiq_drmm_only_offline_hands_off_to_hd1_human_review(tmp_path: Path):
    worker, store, actions = _backupiq_worker(
        tmp_path,
        BackupIQScenarioReads(
            drmm_online=False,
            provider_status="online",
            last_success="2026-09-29T13:00:00Z",
        ),
    )

    worker.tick()

    final = store.get(141185)
    assert final is not None
    assert final.phase == "escalated"
    updates = [
        args["payload"]
        for _, capability, args in actions.calls
        if capability == "service.ticket.update"
    ]
    assert updates[-1] == {
        "id": 141185,
        "queueID": "Help Desk I",
        "status": "Human Review",
    }
    assert not [
        args for _, capability, args in actions.calls
        if capability == "automation.component.execute"
    ]
    notes = [
        args["payload"]
        for _, capability, args in actions.calls
        if capability == "service.ticket.note.create"
    ]
    assert any("DRMMOnline=No" in note["description"] for note in notes)
    assert any("ProviderStatus=online" in note["description"] for note in notes)
    store.close()


def test_backupiq_backup_only_offline_runs_one_standing_safe_reinstall_and_verifies(
    tmp_path: Path,
):
    worker, store, actions = _backupiq_worker(
        tmp_path,
        BackupIQScenarioReads(
            drmm_online=True,
            provider_status="offline",
            last_success="2026-09-24T08:00:00Z",
            recovered_after_reinstall=True,
        ),
    )

    worker.tick()
    assert store.get(141185).phase == "backupiq_reinstall_dispatch"

    worker.tick()
    assert store.get(141185).phase == "backupiq_reinstall_wait"

    worker.tick()
    assert store.get(141185).phase == "waiting_recheck:backupiq_verify_reinstall"

    worker.tick()
    final = store.get(141185)
    assert final is not None
    assert final.phase == "complete"
    assert final.repair_attempts == 1

    component_calls = [
        args
        for _, capability, args in actions.calls
        if capability == "automation.component.execute"
    ]
    assert len(component_calls) == 1
    assert component_calls[0]["component_name"] == "Datto Endpoint Backup Agent v2 [WIN]"
    assert component_calls[0]["component_uid"] == "f39412b2-bfdc-4ac6-b4be-f2fa8bc5f967"
    assert component_calls[0]["variables"] == {}

    updates = [
        args["payload"]
        for _, capability, args in actions.calls
        if capability == "service.ticket.update"
    ]
    assert updates[-1] == {"id": 141185, "status": "Complete"}
    store.close()


def test_backupiq_online_online_recent_success_can_reinstall_when_condition_persists(
    tmp_path: Path,
):
    worker, store, actions = _backupiq_worker(
        tmp_path,
        BackupIQScenarioReads(
            drmm_online=True,
            provider_status="online",
            last_success="2026-09-25T10:00:00Z",
            current_alerts=True,
        ),
        times=(0.0, 31.0),
    )

    worker.tick()
    assert store.get(141185).phase == "backupiq_reinstall_dispatch"
    worker.tick()

    component_calls = [
        args
        for _, capability, args in actions.calls
        if capability == "automation.component.execute"
    ]
    assert len(component_calls) == 1
    assert component_calls[0]["component_name"] == "Datto Endpoint Backup Agent v2 [WIN]"
    store.close()


def test_backupiq_online_online_recovered_without_current_condition_completes(
    tmp_path: Path,
):
    worker, store, actions = _backupiq_worker(
        tmp_path,
        BackupIQScenarioReads(
            drmm_online=True,
            provider_status="online",
            last_success="2026-09-25T10:00:00Z",
            current_alerts=False,
        ),
        times=(0.0,),
    )

    worker.tick()

    final = store.get(141185)
    assert final is not None
    assert final.phase == "complete"
    assert not [
        args for _, capability, args in actions.calls
        if capability == "automation.component.execute"
    ]
    updates = [
        args["payload"]
        for _, capability, args in actions.calls
        if capability == "service.ticket.update"
    ]
    assert updates[-1] == {"id": 141185, "status": "Complete"}
    store.close()


def test_backupiq_online_online_stale_backup_uses_reinstall_fallback(tmp_path: Path):
    worker, store, actions = _backupiq_worker(
        tmp_path,
        BackupIQScenarioReads(
            drmm_online=True,
            provider_status="online",
            last_success="2026-09-24T08:00:00Z",
            current_alerts=True,
        ),
        times=(0.0, 31.0),
    )

    worker.tick()
    assert store.get(141185).phase == "backupiq_reinstall_dispatch"
    worker.tick()

    component_calls = [
        args
        for _, capability, args in actions.calls
        if capability == "automation.component.execute"
    ]
    assert len(component_calls) == 1
    assert component_calls[0]["component_uid"] == "f39412b2-bfdc-4ac6-b4be-f2fa8bc5f967"
    store.close()


def test_backupiq_human_review_handoff_is_not_normalized_back_to_jason(tmp_path: Path):
    human_candidate = replace(
        backupiq_candidate(),
        source_queue="Help Desk I",
        owned_by_jason=False,
        context={
            **backupiq_candidate().context,
            "_jason_source_status_label": "Human Review",
        },
    )
    actions = Actions()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    store.put(
        OperationalWork(
            ticket_id=141185,
            ticket_number="T20260925.0003",
            title=human_candidate.context["title"],
            playbook_id="backupiq_endpoint_backup",
            source_queue="Jason",
            company_id=333,
            configuration_item_id=1259,
            device_uid="backup-device-1",
            hostname="APD-50399",
            phase="escalated",
            last_reason="Technician review required.",
        )
    )
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(human_candidate),
        reads=Reads(),
        actions=actions,
        store=store,
        promotion_store=PromotionStore(promoted=("backupiq_endpoint_backup",)),
        max_active_work_items=2,
        interval_seconds=30,
        monotonic=iter((0.0,)).__next__,
    )

    worker.tick()

    assert actions.calls == []
    assert store.get(141185).phase == "escalated"
    store.close()



def test_backupiq_second_reinstall_is_blocked_before_component_dispatch(tmp_path: Path):
    from jason_runtime.autonomy_worker_runtime import (
        BACKUPIQ_INSTALLER_NAME,
        BACKUPIQ_SCOPE,
        OperationalAutonomyError,
    )

    actions = Actions()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(backupiq_candidate()),
        reads=Reads(),
        actions=actions,
        store=store,
        promotion_store=PromotionStore(promoted=("backupiq_endpoint_backup",)),
        max_active_work_items=2,
        interval_seconds=30,
        monotonic=iter((0.0,)).__next__,
    )
    work = OperationalWork(
        ticket_id=141185,
        ticket_number="T20260925.0003",
        title=backupiq_candidate().context["title"],
        playbook_id=BACKUPIQ_SCOPE.playbook_id,
        source_queue="Jason",
        company_id=333,
        configuration_item_id=1259,
        device_uid="backup-device-1",
        hostname="APD-50399",
        phase="backupiq_reinstall_dispatch",
        repair_attempts=1,
    )

    try:
        worker._dispatch_component(
            work,
            BACKUPIQ_INSTALLER_NAME,
            "backupiq_reinstall_wait",
        )
    except OperationalAutonomyError as exc:
        assert "one per incident cycle" in str(exc)
    else:
        raise AssertionError("second BackupIQ reinstall did not fail closed")

    assert not [
        args for _, capability, args in actions.calls
        if capability == "automation.component.execute"
    ]
    store.close()


def low_disk_candidate():
    return QueueCandidate(
        resource_id="141101",
        priority=90,
        source_queue="Jason",
        owned_by_jason=True,
        urgent=False,
        context={
            "id": 141101,
            "ticketNumber": "T20260924.0078",
            "title": "Low Disk Space - GAI-LT2830",
            "companyID": 597,
            "configurationItemID": 280,
        },
    )


def test_low_disk_requires_separate_promotion(tmp_path: Path):
    actions = Actions()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(low_disk_candidate()),
        reads=Reads(),
        actions=actions,
        store=store,
        promotion_store=PromotionStore(
            promoted=(
                "datto_edr_av",
                "dns_agent_diagnostic",
                "security_log_self_heal",
                "post_error_investigation",
                "unexpected_shutdown",
                "backupiq_endpoint_backup",
            )
        ),
        max_active_work_items=2,
        interval_seconds=30,
        monotonic=iter((0.0,)).__next__,
    )

    worker.tick()

    assert store.get(141101) is None
    assert actions.calls == []
    store.close()


class LowDiskReads(Reads):
    def __init__(
        self,
        *,
        alert_open=True,
        storage_warning=False,
        sysmon_bytes=0,
        software_bytes=0,
        protected=False,
    ):
        super().__init__()
        self.alert_open = alert_open
        self.storage_warning = storage_warning
        self.sysmon_bytes = sysmon_bytes
        self.software_bytes = software_bytes
        self.protected = protected

    def execute(self, capability, arguments):
        if capability == "service.configuration.read":
            return {
                "status": "succeeded",
                "evidence": {
                    "data": {
                        "item": {
                            "id": 280,
                            "companyID": 597,
                            "isActive": True,
                            "referenceNumber": "disk-device-1",
                            "referenceTitle": "GAI-LT2830",
                        }
                    }
                },
            }
        if capability == "endpoint.device.read":
            category = "Server" if self.protected else "Laptop"
            return {
                "status": "succeeded",
                "evidence": {
                    "record": {
                        "resource_id": "disk-device-1",
                        "hostname": "GAI-LT2830",
                        "online": True,
                        "reboot_required": False,
                        "device_type": {"category": category, "type": "Notebook"},
                        "operating_system": (
                            "Microsoft Windows Server 2022"
                            if self.protected
                            else "Microsoft Windows 11 Pro"
                        ),
                    }
                },
            }
        if capability == "endpoint.audit.read":
            return {
                "status": "succeeded",
                "evidence": {
                    "audit": {
                        "logicalDisks": [
                            {
                                "description": "Local Fixed Disk",
                                "diskIdentifier": "C:",
                                "freespace": 10 * 1024**3,
                                "size": 250 * 1024**3,
                            }
                        ]
                    },
                },
            }
        if capability == "endpoint.alert.search":
            items = []
            if self.alert_open:
                items = [{"description": "Low Disk Space - C:", "status": "open"}]
            return {
                "status": "succeeded",
                "evidence": {"data": {"items": items}},
            }
        if capability == "endpoint.alert.history.search":
            alerts = []
            if self.storage_warning:
                alerts = [{"code": "7", "description": "disk bad block"}]
            return {
                "status": "succeeded",
                "evidence": {"data": {"alerts": alerts}},
            }
        if capability == "service.ticket.search":
            return {
                "status": "succeeded",
                "evidence": {
                    "data": {
                        "items": [
                            {
                                "id": 141000,
                                "title": "Low Disk Space - GAI-LT2830",
                            }
                        ]
                    }
                },
            }
        if capability == "endpoint.powershell.read":
            command = arguments["command"]
            payload = []
            if "Get-ChildItem C:\\" in command and "-Directory -Force" in command:
                payload = [
                    {"FullName": r"C:\Users", "Bytes": 180 * 1024**3},
                    {"FullName": r"C:\Windows", "Bytes": 42 * 1024**3},
                ]
            elif "Sort-Object Length -Descending" in command:
                payload = [
                    {
                        "FullName": r"C:\ProgramData\App\data.bin",
                        "Length": 28 * 1024**3,
                        "Extension": ".bin",
                    }
                ]
            elif "Win32_ShadowStorage" in command:
                payload = [{"UsedSpace": 2 * 1024**3}]
            elif "hiberfil.sys" in command:
                payload = [{"FullName": r"C:\hiberfil.sys", "Length": 6 * 1024**3}]
            elif "Get-PhysicalDisk" in command and "Get-StorageReliabilityCounter" not in command:
                payload = [
                    {
                        "FriendlyName": "NVMe Test",
                        "MediaType": "SSD",
                        "BusType": "NVMe",
                        "HealthStatus": "Warning" if self.storage_warning else "Healthy",
                        "OperationalStatus": "OK",
                        "Size": 250 * 1024**3,
                    }
                ]
            elif "Get-StorageReliabilityCounter" in command:
                payload = [{"ReadErrorsTotal": 0, "WriteErrorsTotal": 0}]
            elif "Get-Item C:\\Sysmon" in command:
                payload = (
                    [{"FullName": r"C:\Sysmon", "Bytes": self.sysmon_bytes}]
                    if self.sysmon_bytes
                    else []
                )
            elif "Win32_Service" in command:
                payload = []
            elif "SoftwareDistribution.bak_*" in command:
                payload = (
                    [
                        {
                            "FullName": r"C:\Windows\SoftwareDistribution.bak_20260901",
                            "Bytes": self.software_bytes,
                        }
                    ]
                    if self.software_bytes
                    else []
                )
            return {
                "status": "succeeded",
                "evidence": {"data": {"stdout": json.dumps(payload)}},
            }
        return super().execute(capability, arguments)


def _promoted_low_disk_worker(tmp_path: Path, reads, actions=None):
    actions = actions or Actions()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(low_disk_candidate()),
        reads=reads,
        actions=actions,
        store=store,
        promotion_store=PromotionStore(
            promoted=(
                "datto_edr_av",
                "dns_agent_diagnostic",
                "security_log_self_heal",
                "post_error_investigation",
                "unexpected_shutdown",
                "backupiq_endpoint_backup",
                "low_disk_space",
            )
        ),
        max_active_work_items=2,
        interval_seconds=30,
        monotonic=iter(float(value * 31) for value in range(100)).__next__,
    )
    return worker, store, actions


def _expire_low_disk_grace(store):
    current = store.get(141101)
    assert current is not None
    started = datetime.now(timezone.utc) - timedelta(minutes=20)
    store.put(
        replace(
            current,
            phase="waiting_recheck:low_disk_investigate",
            last_reason=f"low_disk_grace_started_at={started.isoformat()}; expired",
        )
    )


def test_low_disk_waits_for_existing_autotask_cleanup(tmp_path: Path):
    worker, store, actions = _promoted_low_disk_worker(
        tmp_path,
        LowDiskReads(),
    )

    worker.tick()

    current = store.get(141101)
    assert current is not None
    assert current.phase == "waiting_recheck:low_disk_investigate"
    assert "Autotask-triggered Disk Cleanup" in current.last_reason
    assert not [
        call for call in actions.calls
        if call[1] == "automation.component.execute"
    ]
    assert not [
        call for call in actions.calls
        if call[1] == "service.ticket.note.create"
    ]
    store.close()


def test_low_disk_recovered_after_autotask_cleanup_completes(tmp_path: Path):
    reads = LowDiskReads(alert_open=False)
    worker, store, actions = _promoted_low_disk_worker(tmp_path, reads)

    worker.tick()

    final = store.get(141101)
    assert final is not None
    assert final.phase == "complete"
    note_calls = [
        args["payload"]
        for _, capability, args in actions.calls
        if capability == "service.ticket.note.create"
    ]
    assert len(note_calls) == 1
    assert "existing Autotask-triggered cleanup" in note_calls[0]["description"]
    store.close()


def test_low_disk_root_cause_note_is_relevant_and_capacity_oriented(tmp_path: Path):
    worker, store, actions = _promoted_low_disk_worker(
        tmp_path,
        LowDiskReads(),
    )
    worker.tick()
    _expire_low_disk_grace(store)
    worker.tick()

    final = store.get(141101)
    assert final is not None
    assert final.phase == "escalated"
    assert "no further approved autonomous cleanup target" in final.last_reason

    note_calls = [
        args["payload"]
        for _, capability, args in actions.calls
        if capability == "service.ticket.note.create"
    ]
    body = note_calls[-1]["description"]
    assert r"C:\Users - 180.0 GB" in body
    assert "larger capacity" in body
    assert "Recurrence: 1 prior low-disk ticket" in body
    assert "VSS/shadow copies - 2.0 GB" in body
    assert "ReadErrorsTotal" not in body
    assert "ACTION REQUIRED" not in body
    update_calls = [
        args["payload"]
        for _, capability, args in actions.calls
        if capability == "service.ticket.update"
    ]
    assert {"id": 141101, "queueID": "Help Desk I", "status": "Human Review"} in update_calls
    store.close()


def test_low_disk_storage_health_warning_prevents_cleanup(tmp_path: Path):
    worker, store, actions = _promoted_low_disk_worker(
        tmp_path,
        LowDiskReads(
            storage_warning=True,
            sysmon_bytes=20 * 1024**3,
        ),
    )
    worker.tick()
    _expire_low_disk_grace(store)
    worker.tick()

    final = store.get(141101)
    assert final is not None
    assert final.phase == "escalated"
    assert "Storage-health evidence" in final.last_reason
    assert not [
        call for call in actions.calls
        if call[1] == "automation.component.execute"
    ]
    note_calls = [
        args["payload"]
        for _, capability, args in actions.calls
        if capability == "service.ticket.note.create"
    ]
    assert "Drive replacement should be reviewed" in note_calls[-1]["description"]
    store.close()


def test_low_disk_failed_sysmon_dependency_read_never_authorizes_cleanup(tmp_path: Path):
    class MissingDependencyEvidenceReads(LowDiskReads):
        def execute(self, capability, arguments):
            if (
                capability == "endpoint.powershell.read"
                and "Win32_Service" in arguments.get("command", "")
            ):
                return {
                    "status": "failed",
                    "error_code": "DEPENDENCY_EVIDENCE_UNAVAILABLE",
                }
            return super().execute(capability, arguments)

    worker, store, actions = _promoted_low_disk_worker(
        tmp_path,
        MissingDependencyEvidenceReads(sysmon_bytes=20 * 1024**3),
    )
    worker.tick()
    _expire_low_disk_grace(store)
    worker.tick()

    final = store.get(141101)
    assert final is not None
    assert final.phase == "escalated"
    assert not [
        call for call in actions.calls
        if call[1] == "automation.component.execute"
    ]
    store.close()


def test_low_disk_softwaredistribution_cleanup_is_review_bound(tmp_path: Path):
    worker, store, actions = _promoted_low_disk_worker(
        tmp_path,
        LowDiskReads(software_bytes=14 * 1024**3),
    )
    worker.tick()
    _expire_low_disk_grace(store)
    worker.tick()

    final = store.get(141101)
    assert final is not None
    assert final.phase == "escalated"
    assert not [
        call for call in actions.calls
        if call[1] == "automation.component.execute"
    ]
    note_calls = [
        args["payload"]
        for _, capability, args in actions.calls
        if capability == "service.ticket.note.create"
    ]
    body = note_calls[-1]["description"]
    assert "SoftwareDistribution backup folders - 14.0 GB" in body
    assert "destructive/review-bound" in body
    store.close()


def test_low_disk_runs_one_narrow_cleanup_then_verifies_monitor(tmp_path: Path):
    reads = LowDiskReads(sysmon_bytes=12 * 1024**3)
    worker, store, actions = _promoted_low_disk_worker(
        tmp_path,
        reads,
    )
    worker.tick()
    _expire_low_disk_grace(store)
    worker.tick()
    assert store.get(141101).phase == "low_disk_sysmon_cleanup_dispatch"

    worker.tick()
    current = store.get(141101)
    assert current.phase == "low_disk_cleanup_wait"
    assert current.repair_attempts == 1

    worker.tick()
    assert store.get(141101).phase == "waiting_recheck:low_disk_verify"

    reads.alert_open = False
    worker.tick()

    final = store.get(141101)
    assert final.phase == "complete"
    component_calls = [
        args
        for _, capability, args in actions.calls
        if capability == "automation.component.execute"
    ]
    assert len(component_calls) == 1
    assert component_calls[0]["component_uid"] == (
        "97ddcdd5-2b74-4a4b-9516-cc872af6a7b6"
    )
    store.close()


def vulscan_candidate():
    return QueueCandidate(
        resource_id="141183",
        priority=100,
        source_queue="Jason",
        owned_by_jason=True,
        urgent=True,
        context={
            "id": 141183,
            "ticketNumber": "T20260925.0001",
            "title": "Vulnerability Detected by VulScan - GAI-DT2850",
            "description": (
                "Issue: Missing Critical Security Patch - "
                "2026-09 Security Update (KB5124008) (26100.9445)\n"
                "Issue: Missing Critical Security Patch - "
                "2026-09 .NET Framework Security Update (KB5126052)"
            ),
            "companyID": 597,
            "configurationItemID": 68,
        },
    )


class VulscanBranchReads(Reads):
    def __init__(self, patch_status: str):
        super().__init__()
        self.patch_status = patch_status

    def execute(self, capability, arguments):
        if capability == "service.configuration.read":
            return {
                "status": "succeeded",
                "evidence": {
                    "data": {
                        "item": {
                            "id": 68,
                            "companyID": 597,
                            "isActive": True,
                            "referenceNumber": "vul-device-1",
                            "referenceTitle": "GAI-DT2850",
                        }
                    }
                },
            }
        if capability == "endpoint.device.read":
            return {
                "status": "succeeded",
                "evidence": {
                    "record": {
                        "resource_id": "vul-device-1",
                        "hostname": "GAI-DT2850",
                        "online": True,
                        "reboot_required": False,
                    }
                },
            }
        if capability == "endpoint.patch.search":
            kb = str(arguments["kb"])
            return {
                "status": "succeeded",
                "evidence": {
                    "data": {
                        "patches": [
                            {
                                "kbArticleId": kb.replace("KB", ""),
                                "installStatus": self.patch_status,
                                "rebootRequired": False,
                            }
                        ],
                        "match_count": 1,
                        "exact_selector_match": True,
                        "ambiguous": False,
                    }
                },
            }
        return super().execute(capability, arguments)


def test_vulscan_core_scope_remains_eligible_without_client_disposition_promotion(
    tmp_path: Path,
):
    actions = Actions()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(vulscan_candidate()),
        reads=VulscanBranchReads("NOT_APPROVED"),
        actions=actions,
        store=store,
        promotion_store=ExactPromotionStore(
            approved_scopes=(("vulscan_missing_patch", "1.0.0"),)
        ),
        max_active_work_items=2,
        interval_seconds=30,
        monotonic=iter((0.0,)).__next__,
    )

    worker.tick()

    current = store.get(141183)
    assert current is not None
    assert current.phase == "waiting_patch_approval"
    assert not any(
        capability == "service.ticket.client.notification.create"
        for _, capability, _ in actions.calls
    )
    store.close()


def test_vulscan_client_disposition_waits_then_resumes_on_exact_v11_promotion(
    tmp_path: Path,
):
    reads = VulscanBranchReads("INSTALLED")
    actions = Actions()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    promotions = ExactPromotionStore(
        approved_scopes=(("vulscan_missing_patch", "1.0.0"),)
    )
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(vulscan_candidate()),
        reads=reads,
        actions=actions,
        store=store,
        promotion_store=promotions,
        max_active_work_items=2,
        interval_seconds=30,
        monotonic=iter((0.0, 31.0)).__next__,
    )

    worker.tick()

    waiting = store.get(141183)
    assert waiting is not None
    assert waiting.phase == "waiting_client_notification_authority"
    assert store.list_open() == ()
    assert not any(
        capability == "service.ticket.client.notification.create"
        for _, capability, _ in actions.calls
    )
    assert not any(
        capability == "service.ticket.update"
        and (args.get("payload") or {}).get("status") == "Close Pending"
        for _, capability, args in actions.calls
    )

    promotions.approved_scopes.add(("vulscan_missing_patch", "1.1.0"))
    worker.tick()

    final = store.get(141183)
    assert final is not None
    assert final.phase == "complete"

    client_calls = [
        args
        for _, capability, args in actions.calls
        if capability == "service.ticket.client.notification.create"
    ]
    assert len(client_calls) == 1
    assert client_calls[0]["workflow_id"] == "vulscan_missing_patch"
    assert client_calls[0]["template_id"] == "vulscan-approved-or-installed-v1"
    assert client_calls[0]["payload"] == {"ticketID": 141183}
    assert "recipient" not in client_calls[0]

    updates = [
        args["payload"]
        for _, capability, args in actions.calls
        if capability == "service.ticket.update"
    ]
    assert any(
        update.get("contactID") == 30684489
        and update.get("status") == "Close Pending"
        for update in updates
    )
    store.close()


def test_vulscan_requires_separate_promotion(tmp_path: Path):
    actions = Actions()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(vulscan_candidate()),
        reads=Reads(),
        actions=actions,
        store=store,
        promotion_store=PromotionStore(
            promoted=(
                "datto_edr_av",
                "dns_agent_diagnostic",
                "security_log_self_heal",
                "post_error_investigation",
                "unexpected_shutdown",
                "backupiq_endpoint_backup",
                "low_disk_space",
            )
        ),
        max_active_work_items=2,
        interval_seconds=30,
        monotonic=iter((0.0,)).__next__,
    )
    worker.tick()
    assert store.get(141183) is None
    assert actions.calls == []
    store.close()


def test_vulscan_not_approved_kbs_wait_in_jason_without_helpdesk_handoff(tmp_path: Path):
    class VulscanReads(Reads):
        def __init__(self):
            super().__init__()
            self.patch_status = "NOT_APPROVED"

        def execute(self, capability, arguments):
            if capability == "service.configuration.read":
                return {
                    "status": "succeeded",
                    "evidence": {
                        "data": {
                            "item": {
                                "id": 68,
                                "companyID": 597,
                                "isActive": True,
                                "referenceNumber": "vul-device-1",
                                "referenceTitle": "GAI-DT2850",
                            }
                        }
                    },
                }
            if capability == "endpoint.device.read":
                return {
                    "status": "succeeded",
                    "evidence": {
                        "record": {
                            "resource_id": "vul-device-1",
                            "hostname": "GAI-DT2850",
                            "online": True,
                            "reboot_required": False,
                        }
                    },
                }
            if capability == "endpoint.patch.search":
                kb = str(arguments["kb"])
                return {
                    "status": "succeeded",
                    "evidence": {
                        "data": {
                            "patches": [
                                {
                                    "kbArticleId": kb.replace("KB", ""),
                                    "installStatus": self.patch_status,
                                    "rebootRequired": True,
                                }
                            ],
                            "match_count": 1,
                            "exact_selector_match": True,
                            "ambiguous": False,
                        }
                    },
                }
            return super().execute(capability, arguments)

    reads = VulscanReads()
    actions = Actions()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(vulscan_candidate()),
        reads=reads,
        actions=actions,
        store=store,
        promotion_store=PromotionStore(
            promoted=(
                "datto_edr_av",
                "dns_agent_diagnostic",
                "security_log_self_heal",
                "post_error_investigation",
                "unexpected_shutdown",
                "backupiq_endpoint_backup",
                "low_disk_space",
                "vulscan_missing_patch",
            )
        ),
        max_active_work_items=2,
        interval_seconds=30,
        monotonic=iter((0.0, 31.0, 62.0)).__next__,
    )

    worker.tick()

    final = store.get(141183)
    assert final is not None
    assert final.playbook_id == "vulscan_missing_patch"
    assert final.phase == "waiting_patch_approval"
    assert "first_not_approved_at=" in final.last_reason

    component_calls = [
        args
        for _, capability, args in actions.calls
        if capability == "automation.component.execute"
    ]
    assert component_calls == []

    note_calls = [
        args["payload"]
        for _, capability, args in actions.calls
        if capability == "service.ticket.note.create"
    ]
    assert len(note_calls) == 1
    body = note_calls[0]["description"]
    assert "KB5124008=NOT_APPROVED" in body
    assert "KB5126052=NOT_APPROVED" in body
    assert "STATUS: WAITING - PATCH NOT APPROVED" in body

    ticket_updates = [
        args["payload"]
        for _, capability, args in actions.calls
        if capability == "service.ticket.update"
    ]
    assert ticket_updates == [
        {
            "id": 141183,
            "queueID": "Jason",
            "status": "In Progress",
            "billingCodeID": "Remote Support",
        },
        {"id": 141183, "status": "Waiting"},
    ]

    # A normal worker tick before the daily recheck is due must not emit
    # another note or hand the ticket off.
    worker.tick()
    assert store.get(141183).phase == "waiting_patch_approval"
    note_calls = [
        args["payload"]
        for _, capability, args in actions.calls
        if capability == "service.ticket.note.create"
    ]
    assert len(note_calls) == 1
    store.close()


def test_vulscan_approval_change_resumes_without_helpdesk_handoff(tmp_path: Path):
    class VulscanReads(Reads):
        def __init__(self):
            super().__init__()
            self.patch_status = "NOT_APPROVED"

        def execute(self, capability, arguments):
            if capability == "service.configuration.read":
                return {
                    "status": "succeeded",
                    "evidence": {"data": {"item": {
                        "id": 68,
                        "companyID": 261,
                        "isActive": True,
                        "referenceNumber": "vul-device-1",
                        "referenceTitle": "TEST-DT2850",
                    }}},
                }
            if capability == "endpoint.device.read":
                return {
                    "status": "succeeded",
                    "evidence": {"record": {
                        "resource_id": "vul-device-1",
                        "hostname": "TEST-DT2850",
                        "online": True,
                        "reboot_required": False,
                    }},
                }
            if capability == "endpoint.patch.search":
                kb = str(arguments["kb"])
                return {
                    "status": "succeeded",
                    "evidence": {"data": {"patches": [{
                        "kbArticleId": kb.replace("KB", ""),
                        "installStatus": self.patch_status,
                        "rebootRequired": True,
                    }]}},
                }
            return super().execute(capability, arguments)

    reads = VulscanReads()
    actions = Actions()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    base_candidate = vulscan_candidate()
    generic_candidate = replace(
        base_candidate,
        context={
            **base_candidate.context,
            "title": "Vulnerability Detected by VulScan - TEST-DT2850",
            "companyID": 261,
        },
    )
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(generic_candidate),
        reads=reads,
        actions=actions,
        store=store,
        promotion_store=PromotionStore(promoted=("vulscan_missing_patch",)),
        max_active_work_items=2,
        interval_seconds=30,
        monotonic=iter((0.0, 31.0)).__next__,
    )

    worker.tick()
    waiting = store.get(141183)
    assert waiting is not None
    reads.patch_status = "APPROVED_PENDING"
    store.put(
        replace(
            waiting,
            updated_at=(datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
        )
    )

    worker.tick()
    resumed = store.get(141183)
    assert resumed is not None
    assert resumed.phase == "waiting_patch_window"
    updates = [
        args["payload"]
        for _, capability, args in actions.calls
        if capability == "service.ticket.update"
    ]
    assert {"id": 141183, "queueID": "Help Desk I", "status": "New"} not in updates
    assert {"id": 141183, "queueID": "Help Desk I", "status": "Human Review"} not in updates
    assert {"id": 141183, "status": "Waiting"} in updates
    assert {"id": 141183, "status": "In Progress"} in updates
    assert updates[-1] == {"id": 141183, "status": "Waiting"}
    store.close()


def test_vulscan_not_approved_for_ten_days_hands_off_as_human_review(tmp_path: Path):
    class VulscanReads(Reads):
        def execute(self, capability, arguments):
            if capability == "service.configuration.read":
                return {
                    "status": "succeeded",
                    "evidence": {"data": {"item": {
                        "id": 68,
                        "companyID": 597,
                        "isActive": True,
                        "referenceNumber": "vul-device-1",
                        "referenceTitle": "GAI-DT2850",
                    }}},
                }
            if capability == "endpoint.device.read":
                return {
                    "status": "succeeded",
                    "evidence": {"record": {
                        "resource_id": "vul-device-1",
                        "hostname": "GAI-DT2850",
                        "online": True,
                        "reboot_required": False,
                    }},
                }
            if capability == "endpoint.patch.search":
                kb = str(arguments["kb"])
                return {
                    "status": "succeeded",
                    "evidence": {"data": {"patches": [{
                        "kbArticleId": kb.replace("KB", ""),
                        "installStatus": "NOT_APPROVED",
                        "rebootRequired": True,
                    }]}},
                }
            return super().execute(capability, arguments)

    actions = Actions()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(vulscan_candidate()),
        reads=VulscanReads(),
        actions=actions,
        store=store,
        promotion_store=PromotionStore(promoted=("vulscan_missing_patch",)),
        max_active_work_items=2,
        interval_seconds=30,
        monotonic=iter((0.0, 31.0)).__next__,
    )

    worker.tick()
    waiting = store.get(141183)
    assert waiting is not None
    old = datetime.now(timezone.utc) - timedelta(days=11)
    store.put(
        replace(
            waiting,
            last_reason=(
                "VulScan waiting for patch approval; "
                f"first_not_approved_at={old.isoformat()}; "
                "one or more exact KBs remain NOT_APPROVED."
            ),
            updated_at=(datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
        )
    )

    worker.tick()
    final = store.get(141183)
    assert final is not None
    assert final.phase == "escalated"
    updates = [
        args["payload"]
        for _, capability, args in actions.calls
        if capability == "service.ticket.update"
    ]
    assert updates[-1] == {
        "id": 141183,
        "queueID": "Help Desk I",
        "status": "Human Review",
    }
    notes = [
        args["payload"]
        for _, capability, args in actions.calls
        if capability == "service.ticket.note.create"
    ]
    assert any(
        "ACTION REQUIRED: Approve or intentionally defer" in note["description"]
        for note in notes
    )
    store.close()



def test_vulscan_all_exact_kbs_installed_without_reboot_completes(tmp_path: Path):
    class InstalledReads(Reads):
        def execute(self, capability, arguments):
            if capability == "service.configuration.read":
                return {
                    "status": "succeeded",
                    "evidence": {"data": {"item": {
                        "id": 68, "companyID": 597, "isActive": True,
                        "referenceNumber": "vul-device-1", "referenceTitle": "GAI-DT2850",
                    }}},
                }
            if capability == "endpoint.device.read":
                return {
                    "status": "succeeded",
                    "evidence": {"record": {
                        "resource_id": "vul-device-1", "hostname": "GAI-DT2850",
                        "online": True, "reboot_required": False,
                    }},
                }
            if capability == "endpoint.patch.search":
                kb = str(arguments["kb"])
                return {
                    "status": "succeeded",
                    "evidence": {"data": {"patches": [{
                        "kbArticleId": kb.replace("KB", ""),
                        "installStatus": "INSTALLED",
                        "rebootRequired": True,
                    }], "match_count": 1, "exact_selector_match": True, "ambiguous": False}},
                }
            return super().execute(capability, arguments)

    actions = Actions()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(vulscan_candidate()), reads=InstalledReads(), actions=actions,
        store=store, promotion_store=PromotionStore(promoted=("vulscan_missing_patch",)),
        max_active_work_items=2, interval_seconds=30, monotonic=iter((0.0,)).__next__,
    )
    worker.tick()
    final = store.get(141183)
    assert final is not None
    assert final.phase == "complete"
    updates = [args["payload"] for _, capability, args in actions.calls if capability == "service.ticket.update"]
    assert updates[-1] == {
        "id": 141183,
        "contactID": 30684489,
        "status": "Close Pending",
    }
    assert {"id": 141183, "status": "Complete"} not in updates
    assert {"id": 141183, "queueID": "Help Desk I", "status": "New"} not in updates
    notifications = [
        args for _, capability, args in actions.calls
        if capability == "service.ticket.client.notification.create"
    ]
    assert len(notifications) == 1
    assert notifications[0]["workflow_id"] == "vulscan_missing_patch"
    assert notifications[0]["template_id"] == "vulscan-approved-or-installed-v1"
    assert notifications[0]["payload"] == {"ticketID": 141183}
    assert "recipient" not in notifications[0]
    notes = [args["payload"] for _, capability, args in actions.calls if capability == "service.ticket.note.create"]
    assert len(notes) == 1
    assert "verified stale/recovered VulScan finding" in notes[0]["description"]
    store.close()


def test_vulscan_installed_but_reboot_required_still_escalates(tmp_path: Path):
    class InstalledRebootReads(Reads):
        def execute(self, capability, arguments):
            if capability == "service.configuration.read":
                return {
                    "status": "succeeded",
                    "evidence": {"data": {"item": {
                        "id": 68, "companyID": 597, "isActive": True,
                        "referenceNumber": "vul-device-1", "referenceTitle": "GAI-DT2850",
                    }}},
                }
            if capability == "endpoint.device.read":
                return {
                    "status": "succeeded",
                    "evidence": {"record": {
                        "resource_id": "vul-device-1", "hostname": "GAI-DT2850",
                        "online": True, "reboot_required": True,
                    }},
                }
            if capability == "endpoint.patch.search":
                kb = str(arguments["kb"])
                return {
                    "status": "succeeded",
                    "evidence": {"data": {"patches": [{
                        "kbArticleId": kb.replace("KB", ""),
                        "installStatus": "INSTALLED",
                        "rebootRequired": True,
                    }]}},
                }
            return super().execute(capability, arguments)

    actions = Actions()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(vulscan_candidate()), reads=InstalledRebootReads(), actions=actions,
        store=store, promotion_store=PromotionStore(promoted=("vulscan_missing_patch",)),
        max_active_work_items=2, interval_seconds=30, monotonic=iter((0.0,)).__next__,
    )
    worker.tick()
    final = store.get(141183)
    assert final is not None
    assert final.phase == "escalated"
    assert "reboot remains required" in final.last_reason
    updates = [args["payload"] for _, capability, args in actions.calls if capability == "service.ticket.update"]
    assert updates[-1] == {"id": 141183, "queueID": "Help Desk I", "status": "New"}
    store.close()

def test_vulscan_offline_endpoint_waits_for_device_access(tmp_path: Path):
    class OfflineVulscanReads(Reads):
        def execute(self, capability, arguments):
            if capability == "service.configuration.read":
                return {
                    "status": "succeeded",
                    "evidence": {
                        "data": {
                            "item": {
                                "id": 68,
                                "companyID": 597,
                                "isActive": True,
                                "referenceNumber": "vul-device-1",
                                "referenceTitle": "GAI-DT2850",
                            }
                        }
                    },
                }
            if capability == "endpoint.device.read":
                return {
                    "status": "succeeded",
                    "evidence": {
                        "record": {
                            "resource_id": "vul-device-1",
                            "hostname": "GAI-DT2850",
                            "online": False,
                            "reboot_required": True,
                        }
                    },
                }
            if capability == "endpoint.patch.search":
                raise AssertionError("offline admission must not query patch state")
            return super().execute(capability, arguments)

    actions = Actions()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(vulscan_candidate()),
        reads=OfflineVulscanReads(),
        actions=actions,
        store=store,
        promotion_store=PromotionStore(
            promoted=(
                "datto_edr_av",
                "dns_agent_diagnostic",
                "security_log_self_heal",
                "post_error_investigation",
                "unexpected_shutdown",
                "backupiq_endpoint_backup",
                "low_disk_space",
                "vulscan_missing_patch",
            )
        ),
        max_active_work_items=2,
        interval_seconds=30,
        monotonic=iter((0.0,)).__next__,
    )

    worker.tick()

    work = store.get(141183)
    assert work is not None
    assert work.phase == "waiting_device_access:claim"
    assert work.device_uid == "vul-device-1"
    assert work.hostname == "GAI-DT2850"
    update_calls = [
        args["payload"]
        for _, capability, args in actions.calls
        if capability == "service.ticket.update"
    ]
    assert update_calls == [{"id": 141183, "status": "Waiting Device Access"}]
    assert not [
        args
        for _, capability, args in actions.calls
        if capability == "service.ticket.note.create"
    ]
    store.close()


def disk_bad_block_candidate():
    return QueueCandidate(
        resource_id="141300",
        priority=90,
        source_queue="Monitoring Alert",
        owned_by_jason=False,
        urgent=False,
        context={
            "id": 141300,
            "ticketNumber": "T20260926.0300",
            "title": "Disk Event ID 7 - The device, \\Device\\Harddisk1\\DR1, has a bad block.",
            "description": "The device, \\Device\\Harddisk1\\DR1, has a bad block.",
            "companyID": 507,
            "configurationItemID": 1583,
        },
    )


def test_disk_bad_block_diagnostic_does_not_guess_physical_mapping(tmp_path: Path):
    class DiskReads(Reads):
        def execute(self, capability, arguments):
            if capability == "service.configuration.read":
                return {"status":"succeeded","evidence":{"data":{"item":{
                    "id":1583,"companyID":507,"isActive":True,
                    "referenceNumber":"disk-device-1","referenceTitle":"PC-1"}}}}
            if capability == "endpoint.device.read":
                return {"status":"succeeded","evidence":{"record":{
                    "resource_id":"disk-device-1","hostname":"PC-1","online":True}}}
            if capability == "endpoint.alert.history.search":
                return {"status":"succeeded","evidence":{"data":{"alerts":[{
                    "alertUid":"alert-7","ticketNumber":"T20260926.0300","timestamp":1790416800000,
                    "alertContext":{"code":"7","description":"The device, \\Device\\Harddisk1\\DR1, has a bad block."}
                }]}}}
            if capability == "endpoint.audit.read":
                return {"status":"succeeded","evidence":{"audit":{
                    "logicalDisks":[{"description":"Local Fixed Disk","diskIdentifier":"C:","freespace":1,"size":2}],
                    "attachedDevices":[{"deviceName":"USB Mass-Storage","deviceType":"Disk"}]
                }}}
            return super().execute(capability, arguments)

    actions=Actions()
    store=SQLiteOperationalWorkStore(tmp_path/"worker.sqlite3")
    worker=OperationalAutonomyMaintenance(
        queue_source=QueueSource(disk_bad_block_candidate()),
        reads=DiskReads(),actions=actions,store=store,
        promotion_store=PromotionStore(promoted=(
            "datto_edr_av","dns_agent_diagnostic","security_log_self_heal",
            "post_error_investigation","unexpected_shutdown","backupiq_endpoint_backup",
            "low_disk_space","vulscan_missing_patch","disk_bad_block_event_7")),
        max_active_work_items=2,interval_seconds=30,monotonic=iter((0.0,)).__next__,
    )
    worker.tick()
    final=store.get(141300)
    assert final is not None
    assert final.phase=="escalated"
    assert "physical-disk mapping" in final.last_reason
    assert not [x for x in actions.calls if x[1]=="automation.component.execute"]
    notes=[x[2]["payload"] for x in actions.calls if x[1]=="service.ticket.note.create"]
    assert len(notes)==1
    assert "HarddiskX=1" in notes[0]["description"]
    assert "RemovableDeviceHints=1" in notes[0]["description"]
    assert "did not guess" in notes[0]["description"]
    store.close()


def idle_logoff_candidate():
    return QueueCandidate(
        resource_id="141066",
        priority=90,
        source_queue="Jason",
        owned_by_jason=True,
        urgent=False,
        context={
            "id":141066,"ticketNumber":"T20260924.0043",
            "title":"[Get Idle Log Off Status AOT Ver 08202024] - Compliant: False () for AVMAC-1096",
            "companyID":1179,"configurationItemID":1583,
        },
    )


def test_idle_logoff_monitor_failure_is_diagnostic_only(tmp_path: Path):
    class IdleReads(Reads):
        def execute(self, capability, arguments):
            if capability=="service.configuration.read":
                return {"status":"succeeded","evidence":{"data":{"item":{
                    "id":1583,"companyID":1179,"isActive":True,
                    "referenceNumber":"idle-device-1","referenceTitle":"AVMAC-1096"}}}}
            if capability=="endpoint.device.read":
                return {"status":"succeeded","evidence":{"record":{
                    "resource_id":"idle-device-1","hostname":"AVMAC-1096","online":True,
                    "device_type":{"category":"Desktop","type":"Desktop"},
                    "operating_system":"Microsoft Windows 11 Pro"}}}
            if capability=="endpoint.alert.search":
                return {"status":"succeeded","evidence":{"items":[{
                    "alertUid":"idle-alert","ticketNumber":"T20260924.0043",
                    "diagnostics":"Invalid MyFileDestination",
                    "alertContext":{"description":"Get Idle Log Off Status - Compliant: False"}
                }]}}
            if capability=="endpoint.alert.history.search":
                return {"status":"succeeded","evidence":{"data":{"alerts":[{
                    "alertUid":"idle-alert","ticketNumber":"T20260924.0043","timestamp":1790416800000,
                    "diagnostics":"Invalid MyFileDestination",
                    "alertContext":{"description":"Get Idle Log Off Status - Compliant: False"}
                }]}}}
            return super().execute(capability, arguments)

    actions=Actions()
    store=SQLiteOperationalWorkStore(tmp_path/"worker.sqlite3")
    worker=OperationalAutonomyMaintenance(
        queue_source=QueueSource(idle_logoff_candidate()),reads=IdleReads(),
        actions=actions,store=store,
        promotion_store=PromotionStore(promoted=(
            "datto_edr_av","dns_agent_diagnostic","security_log_self_heal",
            "post_error_investigation","unexpected_shutdown","backupiq_endpoint_backup",
            "low_disk_space","vulscan_missing_patch","disk_bad_block_event_7","idle_log_off")),
        max_active_work_items=2,interval_seconds=30,monotonic=iter((0.0,)).__next__,
    )
    worker.tick()
    final=store.get(141066)
    assert final is not None and final.phase=="escalated"
    assert "monitor/plumbing failure" in final.last_reason
    assert not [x for x in actions.calls if x[1]=="automation.component.execute"]
    notes=[x[2]["payload"] for x in actions.calls if x[1]=="service.ticket.note.create"]
    assert len(notes)==1
    assert "Classification=monitor_execution_failure" in notes[0]["description"]
    assert notes[0]["title"] == "Jason - Technical Review"
    assert "setter" in notes[0]["description"].casefold()
    store.close()


def test_idle_logoff_true_noncompliance_runs_exact_setter_and_waits_for_monitor_clear(tmp_path: Path):
    class IdleReads(Reads):
        def __init__(self):
            super().__init__()
            self.current_alert_reads = 0

        def execute(self, capability, arguments):
            if capability=="service.configuration.read":
                return {"status":"succeeded","evidence":{"data":{"item":{
                    "id":1583,"companyID":1179,"isActive":True,
                    "referenceNumber":"idle-device-1","referenceTitle":"AVMAC-1096"}}}}
            if capability=="endpoint.device.read":
                return {"status":"succeeded","evidence":{"record":{
                    "resource_id":"idle-device-1","hostname":"AVMAC-1096","online":True,
                    "device_type":{"category":"Desktop","type":"Desktop"},
                    "operating_system":"Microsoft Windows 11 Pro"}}}
            if capability=="endpoint.alert.search":
                self.current_alert_reads += 1
                alerts = ([{
                    "alertUid":"idle-alert","ticketNumber":"T20260924.0043",
                    "diagnostics":"Compliant: False",
                    "alertContext":{"description":"Get Idle Log Off Status - Compliant: False"}
                }] if self.current_alert_reads == 1 else [])
                return {"status":"succeeded","evidence":{"items":alerts}}
            if capability=="endpoint.alert.history.search":
                return {"status":"succeeded","evidence":{"data":{"alerts":[{
                    "alertUid":"idle-alert","ticketNumber":"T20260924.0043","timestamp":1790416800000,
                    "diagnostics":"Compliant: False",
                    "alertContext":{"description":"Get Idle Log Off Status - Compliant: False"}
                }]}}}
            if capability=="automation.job.read":
                return {"status":"succeeded","evidence":{"job":{
                    "resource_id":arguments["resource_id"],"status":"completed"}}}
            if capability=="automation.job.output.read":
                text = (
                    ""
                    if arguments.get("stream")=="stderr"
                    else "Idle Log Off installation completed successfully."
                )
                return {"status":"succeeded","evidence":{
                    "resource_id":arguments["resource_id"],
                    "outputs":[{
                        "component_uid":arguments["component_uid"],
                        "stream":arguments.get("stream"),
                        "text":text,
                    }]
                }}
            return super().execute(capability, arguments)

    actions=Actions()
    store=SQLiteOperationalWorkStore(tmp_path/"worker.sqlite3")
    worker=OperationalAutonomyMaintenance(
        queue_source=QueueSource(idle_logoff_candidate()),reads=IdleReads(),
        actions=actions,store=store,
        promotion_store=PromotionStore(promoted=(
            "datto_edr_av","dns_agent_diagnostic","security_log_self_heal",
            "post_error_investigation","unexpected_shutdown","backupiq_endpoint_backup",
            "low_disk_space","vulscan_missing_patch","disk_bad_block_event_7","idle_log_off")),
        max_active_work_items=2,interval_seconds=30,
        monotonic=iter((0.0,31.0,62.0,93.0)).__next__,
    )

    worker.tick()
    assert store.get(141066).phase=="idle_log_off_repair_dispatch"
    worker.tick()
    assert store.get(141066).phase=="idle_log_off_repair_wait"
    worker.tick()
    assert store.get(141066).phase=="waiting_recheck:idle_log_off_verify_monitor"
    assert store.list_open()==()
    worker.tick()

    final=store.get(141066)
    assert final is not None and final.phase=="complete"
    component_calls=[
        x[2] for x in actions.calls if x[1]=="automation.component.execute"
    ]
    assert len(component_calls)==1
    assert component_calls[0]["component_uid"]=="acc6a240-881d-4655-9470-87f60c8e35e8"
    assert component_calls[0]["component_name"]=="Set Idle Log Off AOT Ver 02042026-1"
    assert component_calls[0]["variables"]=={}
    notes=[x[2]["payload"] for x in actions.calls if x[1]=="service.ticket.note.create"]
    assert [n["title"] for n in notes]==[
        "Jason - Technical Review",
        "Jason - Remediation Result",
        "Jason - Remediation Result",
    ]
    assert all("NEXT ACTION:" in n["description"] for n in notes)
    assert not any(
        "powershell" in str(call).casefold()
        for call in component_calls
    )
    store.close()


def test_idle_logoff_offline_uses_resumable_waiting_state(tmp_path: Path):
    class IdleReads(Reads):
        def execute(self, capability, arguments):
            if capability=="service.configuration.read":
                return {"status":"succeeded","evidence":{"data":{"item":{
                    "id":1583,"companyID":1179,"isActive":True,
                    "referenceNumber":"idle-device-1","referenceTitle":"AVMAC-1096"}}}}
            if capability=="endpoint.device.read":
                return {"status":"succeeded","evidence":{"record":{
                    "resource_id":"idle-device-1","hostname":"AVMAC-1096","online":False,
                    "device_type":{"category":"Desktop","type":"Desktop"},
                    "operating_system":"Microsoft Windows 11 Pro"}}}
            return super().execute(capability, arguments)

    actions=Actions()
    store=SQLiteOperationalWorkStore(tmp_path/"worker.sqlite3")
    worker=OperationalAutonomyMaintenance(
        queue_source=QueueSource(idle_logoff_candidate()),reads=IdleReads(),
        actions=actions,store=store,
        promotion_store=PromotionStore(promoted=(
            "datto_edr_av","dns_agent_diagnostic","security_log_self_heal",
            "post_error_investigation","unexpected_shutdown","backupiq_endpoint_backup",
            "low_disk_space","vulscan_missing_patch","disk_bad_block_event_7","idle_log_off")),
        max_active_work_items=2,interval_seconds=30,monotonic=iter((0.0,)).__next__,
    )
    worker.tick()
    final=store.get(141066)
    assert final is not None
    assert final.phase=="waiting_device_access:idle_log_off_investigate"
    assert store.list_open()==()
    assert not [x for x in actions.calls if x[1]=="automation.component.execute"]
    update_calls=[x[2]["payload"] for x in actions.calls if x[1]=="service.ticket.update"]
    assert any(x.get("status")=="Waiting Device Access" for x in update_calls)
    store.close()


def test_unowned_candidate_missing_identity_is_retriable_not_terminal(tmp_path: Path):
    broken = candidate()
    broken = QueueCandidate(
        resource_id=broken.resource_id,
        priority=broken.priority,
        source_queue=broken.source_queue,
        owned_by_jason=broken.owned_by_jason,
        urgent=broken.urgent,
        source_version="v1",
        context={**broken.context, "companyID": 0},
    )
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(broken),
        reads=Reads(),
        actions=Actions(),
        store=store,
        promotion_store=PromotionStore(),
        max_active_work_items=2,
        interval_seconds=30,
        monotonic=iter((0.0,)).__next__,
    )

    worker.tick()

    assert store.get(140933) is None
    store.close()


def test_terminal_work_is_reconsidered_when_ticket_source_version_changes(tmp_path: Path):
    from jason_runtime.autonomy_worker_runtime import OperationalWork

    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    store.put(
        OperationalWork(
            ticket_id=140933,
            ticket_number="T20260925.9999",
            title="[Monitor] Antivirus status issue",
            playbook_id="datto_edr_av",
            source_queue="Monitoring Alert",
            company_id=507,
            configuration_item_id=1583,
            device_uid="device-uid-1",
            hostname="PC-1",
            phase="blocked",
            last_reason="old evidence",
            source_version="v1",
        )
    )
    refreshed = candidate()
    refreshed = QueueCandidate(
        resource_id=refreshed.resource_id,
        priority=refreshed.priority,
        source_queue=refreshed.source_queue,
        owned_by_jason=refreshed.owned_by_jason,
        urgent=refreshed.urgent,
        source_version="v2",
        context=refreshed.context,
    )
    actions = Actions()
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(refreshed),
        reads=Reads(),
        actions=actions,
        store=store,
        promotion_store=PromotionStore(),
        max_active_work_items=2,
        interval_seconds=30,
        monotonic=iter((0.0,)).__next__,
    )

    worker.tick()

    work = store.get(140933)
    assert work is not None
    assert work.source_version == "v2"
    assert work.phase == "health_wait"
    assert any(capability == "service.ticket.update" for _, capability, _ in actions.calls)
    store.close()

def test_missing_ci_is_exactly_correlated_and_verified_before_claim(tmp_path: Path):
    class CorrelationReads(Reads):
        def execute(self, capability, arguments):
            if capability == "endpoint.device.search":
                return {
                    "status": "succeeded",
                    "evidence": {"data": {"resource_matches": [{
                        "resource_id": "device-uid-1",
                        "hostname": "PC-1",
                        "online": True,
                    }]}}
                }
            if capability == "service.configuration.search":
                return {
                    "status": "succeeded",
                    "evidence": {"data": {"items": [{
                        "id": 1583,
                        "companyID": 507,
                        "isActive": True,
                        "referenceNumber": "device-uid-1",
                        "referenceTitle": "PC-1",
                    }]}}
                }
            return super().execute(capability, arguments)

    item = candidate(title="[Monitor] Antivirus status issue PC-1")

    item.context.pop("configurationItemID", None)
    actions = Actions()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(item),
        reads=CorrelationReads(),
        actions=actions,
        store=store,
        promotion_store=PromotionStore(),
        max_active_work_items=2,
        interval_seconds=30,
        monotonic=iter((0.0,)).__next__,
    )
    worker.tick()
    ticket_updates = [
        args["payload"]
        for _, capability, args in actions.calls
        if capability == "service.ticket.update"
    ]
    assert ticket_updates[0] == {"id": 140933, "configurationItemID": 1583}
    assert ticket_updates[1]["queueID"] == "Jason"
    store.close()


def test_structured_letters_only_hostname_correlates_within_company_before_datto(tmp_path: Path):
    class CompanyFirstReads(Reads):
        def __init__(self):
            super().__init__()
            self.endpoint_search_called = False

        def execute(self, capability, arguments):
            if capability == "service.configuration.search":
                assert arguments == {"company_id": 827, "name": "VMHOST", "page_size": 25}
                return {
                    "status": "succeeded",
                    "evidence": {"data": {"items": [{
                        "id": 35,
                        "companyID": 827,
                        "isActive": True,
                        "referenceNumber": "vmhost-device-uid",
                        "referenceTitle": "VMHOST",
                    }]}},
                }
            if capability == "endpoint.device.read":
                assert arguments == {"resource_id": "vmhost-device-uid"}
                return {
                    "status": "succeeded",
                    "evidence": {"record": {
                        "resource_id": "vmhost-device-uid",
                        "hostname": "VMHOST",
                        "online": True,
                    }},
                }
            if capability == "endpoint.device.search":
                self.endpoint_search_called = True
                raise AssertionError("structured company-first correlation must not use global endpoint search")
            return super().execute(capability, arguments)

    item = candidate(title="Vulnerability Detected by VulScan - VMHOST (192.168.1.177 / D4:F5:EF:8F:E7:21)")
    item.context["companyID"] = 827
    item.context.pop("configurationItemID", None)
    reads = CompanyFirstReads()
    actions = Actions()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(item),
        reads=reads,
        actions=actions,
        store=store,
        promotion_store=PromotionStore(),
        max_active_work_items=2,
        interval_seconds=30,
        monotonic=iter((0.0,)).__next__,
    )
    scope = worker._match_scope(item.context)
    assert scope is not None

    ci_id = worker._associate_exact_ticket_device(
        candidate=item, scope=scope, company_id=827
    )

    assert ci_id == 35
    assert reads.endpoint_search_called is False
    updates = [
        args["payload"]
        for _, capability, args in actions.calls
        if capability == "service.ticket.update"
    ]
    assert updates == [{"id": 140933, "configurationItemID": 35}]
    store.close()



def test_missing_ci_ambiguous_hostname_uses_two_signal_identity_score(tmp_path: Path):
    class ScoredCorrelationReads(Reads):
        def execute(self, capability, arguments):
            if capability == "endpoint.device.search":
                return {
                    "status": "succeeded",
                    "evidence": {"data": {"resource_matches": [
                        {
                            "resource_id": "device-a",
                            "hostname": "PC-1",
                            "lan_ip": "192.168.1.10",
                            "mac_address": "AA:BB:CC:DD:EE:01",
                            "serial_number": "SERIAL-A",
                        },
                        {
                            "resource_id": "device-b",
                            "hostname": "PC-1",
                            "lan_ip": "192.168.1.20",
                            "mac_address": "AA:BB:CC:DD:EE:02",
                            "serial_number": "SERIAL-B",
                        },
                    ]}},
                }
            if capability == "service.configuration.search":
                assert arguments == {"company_id": 507, "name": "PC-1", "page_size": 25}
                return {
                    "status": "succeeded",
                    "evidence": {"data": {"items": [{
                        "id": 1583,
                        "companyID": 507,
                        "isActive": True,
                        "referenceNumber": "device-b",
                        "referenceTitle": "PC-1",
                    }]}},
                }
            return super().execute(capability, arguments)

    item = candidate(
        title="[Monitor] Antivirus status issue PC-1 192.168.1.20 AA:BB:CC:DD:EE:02"
    )
    item.context.pop("configurationItemID", None)
    actions = Actions()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(item),
        reads=ScoredCorrelationReads(),
        actions=actions,
        store=store,
        promotion_store=PromotionStore(),
        max_active_work_items=2,
        interval_seconds=30,
        monotonic=iter((0.0,)).__next__,
    )
    scope = worker._match_scope(item.context)
    assert scope is not None

    ci_id = worker._associate_exact_ticket_device(
        candidate=item, scope=scope, company_id=507
    )

    assert ci_id == 1583
    updates = [
        args["payload"]
        for _, capability, args in actions.calls
        if capability == "service.ticket.update"
    ]
    assert updates == [{"id": 140933, "configurationItemID": 1583}]
    store.close()


def test_missing_ci_multi_signal_tie_fails_closed(tmp_path: Path):
    class TiedCorrelationReads(Reads):
        def execute(self, capability, arguments):
            if capability == "endpoint.device.search":
                return {
                    "status": "succeeded",
                    "evidence": {"data": {"resource_matches": [
                        {
                            "resource_id": "device-a",
                            "hostname": "PC-1",
                            "lan_ip": "192.168.1.20",
                        },
                        {
                            "resource_id": "device-b",
                            "hostname": "PC-1",
                            "lan_ip": "192.168.1.20",
                        },
                    ]}},
                }
            return super().execute(capability, arguments)

    item = candidate(title="[Monitor] Antivirus status issue PC-1 192.168.1.20")
    item.context.pop("configurationItemID", None)
    actions = Actions()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(item),
        reads=TiedCorrelationReads(),
        actions=actions,
        store=store,
        promotion_store=PromotionStore(),
        max_active_work_items=2,
        interval_seconds=30,
        monotonic=iter((0.0,)).__next__,
    )
    scope = worker._match_scope(item.context)
    assert scope is not None

    with pytest.raises(
        OperationalAutonomyError,
        match="remains ambiguous after multi-signal scoring",
    ):
        worker._associate_exact_ticket_device(
            candidate=item, scope=scope, company_id=507
        )
    store.close()



def test_structured_vulscan_duplicate_hostname_uses_multi_signal_score(tmp_path: Path):
    class StructuredScoredReads(Reads):
        def execute(self, capability, arguments):
            if capability == "service.configuration.search":
                if arguments == {"company_id": 827, "name": "PC-1", "page_size": 25}:
                    return {
                        "status": "succeeded",
                        "evidence": {"data": {"items": [
                            {
                                "id": 35,
                                "companyID": 827,
                                "isActive": True,
                                "referenceNumber": "device-a",
                                "referenceTitle": "PC-1",
                            },
                            {
                                "id": 36,
                                "companyID": 827,
                                "isActive": True,
                                "referenceNumber": "device-b",
                                "referenceTitle": "PC-1",
                            },
                        ]}},
                    }
            if capability == "endpoint.device.search":
                return {
                    "status": "succeeded",
                    "evidence": {"data": {"resource_matches": [
                        {
                            "resource_id": "device-a",
                            "hostname": "PC-1",
                            "lan_ip": "192.168.1.10",
                            "mac_address": "AA:BB:CC:DD:EE:01",
                        },
                        {
                            "resource_id": "device-b",
                            "hostname": "PC-1",
                            "lan_ip": "192.168.1.20",
                            "mac_address": "AA:BB:CC:DD:EE:02",
                        },
                    ]}},
                }
            return super().execute(capability, arguments)

    item = candidate(
        title=(
            "Vulnerability Detected by VulScan - PC-1 "
            "(192.168.1.20 / AA:BB:CC:DD:EE:02)"
        )
    )
    item.context["companyID"] = 827
    item.context.pop("configurationItemID", None)
    actions = Actions()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(item),
        reads=StructuredScoredReads(),
        actions=actions,
        store=store,
        promotion_store=PromotionStore(),
        max_active_work_items=2,
        interval_seconds=30,
        monotonic=iter((0.0,)).__next__,
    )
    scope = worker._match_scope(item.context)
    assert scope is not None

    ci_id = worker._associate_exact_ticket_device(
        candidate=item, scope=scope, company_id=827
    )

    assert ci_id == 36
    store.close()


def test_internal_autotask_company_zero_preserves_exact_ticket_ci_boundary(tmp_path: Path):
    class InternalCompanyReads(Reads):
        def execute(self, capability, arguments):
            if capability == "service.configuration.read":
                return {
                    "status": "succeeded",
                    "evidence": {
                        "data": {
                            "item": {
                                "id": 1583,
                                "companyID": 0,
                                "isActive": True,
                                "referenceNumber": "device-uid-1",
                                "referenceTitle": "PC-1",
                            }
                        }
                    },
                }
            return super().execute(capability, arguments)

    item = candidate()
    item.context["companyID"] = 0
    actions = Actions()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(item),
        reads=InternalCompanyReads(),
        actions=actions,
        store=store,
        promotion_store=PromotionStore(),
        max_active_work_items=2,
        interval_seconds=30,
        monotonic=iter((0.0,)).__next__,
    )

    worker.tick()

    work = store.get(140933)
    assert work is not None
    assert work.company_id == 0
    assert work.configuration_item_id == 1583
    assert work.phase == "health_wait"
    updates = [
        args["payload"]
        for _, capability, args in actions.calls
        if capability == "service.ticket.update"
    ]
    assert updates[0]["queueID"] == "Jason"
    store.close()

def test_existing_escalated_jason_ticket_is_backfilled_to_helpdesk(tmp_path: Path):
    from jason_runtime.autonomy_worker_runtime import OperationalWork

    item = QueueCandidate(
        resource_id="140933",
        priority=100,
        source_queue="Jason",
        owned_by_jason=True,
        urgent=False,
        source_version="v1",
        context={
            "id": 140933,
            "ticketNumber": "T20260925.9999",
            "title": "[Monitor] Antivirus status issue",
            "companyID": 507,
            "configurationItemID": 1583,
        },
    )
    actions = Actions()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    store.put(
        OperationalWork(
            ticket_id=140933,
            ticket_number="T20260925.9999",
            title=item.context["title"],
            playbook_id="datto_edr_av",
            source_queue="Jason",
            company_id=507,
            configuration_item_id=1583,
            device_uid="device-uid-1",
            hostname="PC-1",
            phase="escalated",
            last_reason="technician review required",
            source_version="v1",
        )
    )
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(item),
        reads=Reads(),
        actions=actions,
        store=store,
        promotion_store=PromotionStore(),
        max_active_work_items=2,
        interval_seconds=30,
        monotonic=iter((0.0,)).__next__,
    )

    worker.tick()

    updates = [
        args["payload"]
        for _, capability, args in actions.calls
        if capability == "service.ticket.update"
    ]
    assert updates == [{"id": 140933, "queueID": "Help Desk I", "status": "New"}]
    current = store.get(140933)
    assert current is not None and current.phase == "escalated"
    store.close()

def test_scan_reflection_event_uses_canonical_audit_shape(tmp_path: Path):
    class StrictAudit:
        def __init__(self):
            self.events = []

        def append(self, event_type, payload):
            for key in (
                "execution_id",
                "correlation_id",
                "organization_id",
                "principal_id",
                "capability_name",
                "stage",
            ):
                assert payload[key]
            self.events.append((event_type, dict(payload)))

    item = candidate()
    item.context["_jason_assigned_elsewhere"] = True
    audit = StrictAudit()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(item),
        reads=Reads(),
        actions=Actions(),
        store=store,
        promotion_store=PromotionStore(),
        max_active_work_items=2,
        interval_seconds=30,
        monotonic=iter((0.0,)).__next__,
        audit=audit,
    )

    worker.tick()

    assert len(audit.events) == 1
    event_type, payload = audit.events[0]
    assert event_type == "orchestration.capability.completed"
    assert payload["principal_id"] == "jason-autonomy-worker"
    assert payload["stage"] == "completed"
    assert payload["capability_name"] == "autonomy.ticket.worker.scan"
    store.close()


def test_assigned_new_ticket_without_technician_notes_can_be_claimed(tmp_path: Path):
    item = candidate()
    item.context["_jason_assigned_elsewhere"] = True
    item.context["_jason_source_status_label"] = "New"
    reads = Reads()
    actions = Actions()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(item),
        reads=reads,
        actions=actions,
        store=store,
        promotion_store=PromotionStore(),
        max_active_work_items=2,
        interval_seconds=30,
        monotonic=iter((0.0,)).__next__,
    )

    worker.tick()

    assert store.get(140933) is not None
    assert any(capability == "service.ticket.update" for _, capability, _ in actions.calls)
    store.close()


def test_assigned_new_ticket_with_technician_note_is_not_claimed(tmp_path: Path):
    item = candidate()
    item.context["_jason_assigned_elsewhere"] = True
    item.context["_jason_source_status_label"] = "New"
    reads = Reads()
    reads.ticket_notes = [
        {
            "creatorResourceID": 29682899,
            "createdByContactID": None,
            "noteType": 1,
            "title": "Technician update",
            "description": "Investigating with the user.",
        }
    ]
    actions = Actions()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(item),
        reads=reads,
        actions=actions,
        store=store,
        promotion_store=PromotionStore(),
        max_active_work_items=2,
        interval_seconds=30,
        monotonic=iter((0.0,)).__next__,
    )

    worker.tick()

    assert store.get(140933) is None
    assert not any(capability == "service.ticket.update" for _, capability, _ in actions.calls)
    store.close()


def test_assigned_new_ticket_with_only_system_and_gpt_insights_notes_can_be_claimed(tmp_path: Path):
    item = candidate()
    item.context["_jason_assigned_elsewhere"] = True
    item.context["_jason_source_status_label"] = "New"
    reads = Reads()
    reads.ticket_notes = [
        {"creatorResourceID": 4, "noteType": 13, "title": "Workflow Rule fired", "description": "system"},
        {"creatorResourceID": 29682899, "noteType": 1, "title": "GPT Insights", "description": "automated insight"},
    ]
    actions = Actions()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(item),
        reads=reads,
        actions=actions,
        store=store,
        promotion_store=PromotionStore(),
        max_active_work_items=2,
        interval_seconds=30,
        monotonic=iter((0.0,)).__next__,
    )

    worker.tick()

    assert store.get(140933) is not None
    store.close()


def _active_dispatched_work() -> OperationalWork:
    return OperationalWork(
        ticket_id=140933,
        ticket_number="T20260925.9999",
        title="[Monitor] Antivirus status issue",
        playbook_id="datto_edr_av",
        source_queue="Jason",
        company_id=507,
        configuration_item_id=1583,
        device_uid="device-uid-1",
        hostname="PC-1",
        phase="health_wait",
        job_uid="job-existing",
        component_uid="component-existing",
        last_reason="Dispatched health diagnostic.",
    )


def test_dispatched_job_offline_moves_to_waiting_device_access_and_releases_slot(tmp_path: Path):
    item = _owned_device_candidate(status_label="In Progress")
    actions = Actions()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    store.put(_active_dispatched_work())
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(item),
        reads=OfflineReads(),
        actions=actions,
        store=store,
        promotion_store=PromotionStore(),
        max_active_work_items=2,
        interval_seconds=30,
        monotonic=iter((0.0,)).__next__,
    )

    worker.tick()

    current = store.get(140933)
    assert current is not None
    assert current.phase == "waiting_device_access:health_wait"
    assert current.job_uid == "job-existing"
    assert current.component_uid == "component-existing"
    assert store.list_open() == ()
    updates = [
        args["payload"]
        for _, capability, args in actions.calls
        if capability == "service.ticket.update"
    ]
    assert updates == [{"id": 140933, "status": "Waiting Device Access"}]
    assert not any(capability == "automation.component.execute" for _, capability, _ in actions.calls)
    store.close()


def test_dispatched_job_offline_wait_is_idempotent(tmp_path: Path):
    item = _owned_device_candidate(status_label="Waiting Device Access")
    actions = Actions()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    work = _active_dispatched_work()
    store.put(replace(work, phase="waiting_device_access:health_wait"))
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(item),
        reads=OfflineReads(),
        actions=actions,
        store=store,
        promotion_store=PromotionStore(),
        max_active_work_items=2,
        interval_seconds=30,
        monotonic=iter((0.0,)).__next__,
    )

    worker.tick()

    current = store.get(140933)
    assert current is not None and current.phase == "waiting_device_access:health_wait"
    assert current.job_uid == "job-existing"
    assert store.list_open() == ()
    assert actions.calls == []
    store.close()


def test_dispatched_job_resumes_same_job_when_endpoint_returns_online(tmp_path: Path):
    item = _owned_device_candidate(status_label="Waiting Device Access")
    reads = Reads()
    reads.job_status = "active"
    actions = Actions()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    work = _active_dispatched_work()
    store.put(replace(work, phase="waiting_device_access:health_wait"))
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(item),
        reads=reads,
        actions=actions,
        store=store,
        promotion_store=PromotionStore(),
        max_active_work_items=2,
        interval_seconds=30,
        monotonic=iter((0.0,)).__next__,
    )

    worker.tick()

    current = store.get(140933)
    assert current is not None
    assert current.phase == "health_wait"
    assert current.job_uid == "job-existing"
    assert len(store.list_open()) == 1
    updates = [
        args["payload"]
        for _, capability, args in actions.calls
        if capability == "service.ticket.update"
    ]
    assert updates == [{"id": 140933, "status": "In Progress"}]
    assert not any(capability == "automation.component.execute" for _, capability, _ in actions.calls)
    store.close()


def test_waiting_job_uses_deb_online_to_poll_existing_job_without_redispatch(
    tmp_path: Path,
):
    item = _owned_device_candidate(status_label="Waiting Device Access")
    reads = DebOnlineWhileDrmmOfflineReads()
    reads.job_status = "active"
    actions = Actions()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    work = _active_dispatched_work()
    store.put(replace(work, phase="waiting_device_access:health_wait"))
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(item),
        reads=reads,
        actions=actions,
        store=store,
        promotion_store=PromotionStore(),
        max_active_work_items=2,
        interval_seconds=30,
        monotonic=iter((0.0,)).__next__,
    )

    worker.tick()

    current = store.get(140933)
    assert current is not None
    assert current.phase == "health_wait"
    assert current.job_uid == "job-existing"
    assert "DEB independently reports the endpoint online" in current.last_reason
    updates = [
        args["payload"]
        for _, capability, args in actions.calls
        if capability == "service.ticket.update"
    ]
    assert updates == [{"id": 140933, "status": "In Progress"}]
    notes = [
        args["payload"]
        for _, capability, args in actions.calls
        if capability == "service.ticket.note.create"
    ]
    assert len(notes) == 1
    assert notes[0]["title"] == "Jason - Waiting State"
    assert "DEB online state=Yes" in notes[0]["description"]
    assert not any(
        capability == "automation.component.execute"
        for _, capability, _ in actions.calls
    )
    store.close()


def test_waiting_device_access_is_corroborated_when_drmm_and_deb_are_offline(
    tmp_path: Path,
):
    item = _owned_device_candidate(status_label="Waiting Device Access")
    actions = Actions()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    work = _active_dispatched_work()
    store.put(replace(work, phase="waiting_device_access:health_wait"))
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(item),
        reads=DebOfflineWhileDrmmOfflineReads(),
        actions=actions,
        store=store,
        promotion_store=PromotionStore(),
        max_active_work_items=2,
        interval_seconds=30,
        monotonic=iter((0.0,)).__next__,
    )

    worker.tick()

    current = store.get(140933)
    assert current is not None
    assert current.phase == "waiting_device_access:health_wait"
    assert "availability=offline_corroborated" in current.last_reason
    assert store.list_open() == ()
    assert actions.calls == []
    store.close()


def test_waiting_device_access_records_unconfirmed_when_deb_is_unavailable(
    tmp_path: Path,
):
    item = _owned_device_candidate(status_label="Waiting Device Access")
    actions = Actions()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    work = _active_dispatched_work()
    store.put(replace(work, phase="waiting_device_access:health_wait"))
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(item),
        reads=OfflineReads(),
        actions=actions,
        store=store,
        promotion_store=PromotionStore(),
        max_active_work_items=2,
        interval_seconds=30,
        monotonic=iter((0.0,)).__next__,
    )

    worker.tick()

    current = store.get(140933)
    assert current is not None
    assert current.phase == "waiting_device_access:health_wait"
    assert "availability=drmm_offline_unconfirmed" in current.last_reason
    assert actions.calls == []
    store.close()


def test_assigned_new_ticket_with_api_resource_note_can_be_claimed(tmp_path: Path):
    item = candidate()
    item.context["_jason_assigned_elsewhere"] = True
    item.context["_jason_source_status_label"] = "New"
    reads = Reads()
    reads.ticket_notes = [
        {
            "creatorResourceID": 29682888,
            "createdByContactID": None,
            "noteType": 99,
            "title": "DEVICE SNAPSHOT",
            "description": "Automated Datto RMM device snapshot.",
        }
    ]
    actions = Actions()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(item), reads=reads, actions=actions, store=store,
        promotion_store=PromotionStore(), max_active_work_items=2,
        interval_seconds=30, monotonic=iter((0.0,)).__next__,
    )
    worker.tick()
    assert store.get(140933) is not None
    store.close()


def test_assigned_new_ticket_with_singular_gpt_insight_can_be_claimed(tmp_path: Path):
    item = candidate()
    item.context["_jason_assigned_elsewhere"] = True
    item.context["_jason_source_status_label"] = "New"
    reads = Reads()
    reads.ticket_notes = [
        {
            "creatorResourceID": 29682922,
            "createdByContactID": None,
            "noteType": 3,
            "title": "GPT Insight",
            "description": "Automated insight.",
        }
    ]
    actions = Actions()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(item), reads=reads, actions=actions, store=store,
        promotion_store=PromotionStore(), max_active_work_items=2,
        interval_seconds=30, monotonic=iter((0.0,)).__next__,
    )
    worker.tick()
    assert store.get(140933) is not None
    store.close()


def test_assigned_unsupported_ticket_skips_note_history_read(tmp_path: Path):
    class TrackingReads(Reads):
        def __init__(self):
            super().__init__()
            self.notes_called = False

        def execute(self, capability, arguments):
            if capability == "service.ticket.notes.search":
                self.notes_called = True
            return super().execute(capability, arguments)

    item = candidate(title="General software question with no promoted playbook")
    item.context["_jason_assigned_elsewhere"] = True
    item.context["_jason_source_status_label"] = "New"
    reads = TrackingReads()
    actions = Actions()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(item),
        reads=reads,
        actions=actions,
        store=store,
        promotion_store=PromotionStore(),
        max_active_work_items=2,
        interval_seconds=30,
        monotonic=iter((0.0,)).__next__,
    )

    worker.tick()

    assert reads.notes_called is False
    assert store.get(140933) is None
    store.close()


def test_new_admission_attempts_are_throttled_per_scan(tmp_path: Path):
    class MultiQueue:
        def reconcile_candidates(self):
            items = []
            for i in range(6):
                base = candidate()
                item = replace(
                    base,
                    resource_id=str(150000 + i),
                    context={
                        **base.context,
                        "id": 150000 + i,
                        "ticketNumber": f"T{i}",
                    },
                )
                items.append(item)
            return tuple(items)

    class CountingWorker(OperationalAutonomyMaintenance):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.admission_attempts_seen = 0

        def _scope_is_promoted(self, scope):
            return True

        def _admit(self, candidate, scope):
            self.admission_attempts_seen += 1
            raise RuntimeError("synthetic admission failure")

    actions = Actions()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    worker = CountingWorker(
        queue_source=MultiQueue(),
        reads=Reads(),
        actions=actions,
        store=store,
        promotion_store=PromotionStore(),
        max_active_work_items=2,
        max_admission_attempts_per_scan=4,
        interval_seconds=30,
        monotonic=iter((0.0,)).__next__,
    )

    worker.tick()

    assert worker.admission_attempts_seen == 4
    assert store.get(150004) is None
    assert store.get(150005) is None
    store.close()


def test_offline_candidates_do_not_consume_actionable_admission_budget(tmp_path: Path):
    class MultiQueue:
        def reconcile_candidates(self):
            items = []
            for i in range(8):
                base = candidate()
                items.append(replace(base, resource_id=str(160000 + i), context={**base.context, "id": 160000 + i, "ticketNumber": f"O{i}"}))
            return tuple(items)

    class CountingWorker(OperationalAutonomyMaintenance):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.calls = 0

        def _scope_is_promoted(self, scope):
            return True

        def _admit(self, candidate, scope):
            self.calls += 1
            if self.calls <= 4:
                raise RuntimeError("endpoint is not currently online")
            raise RuntimeError("synthetic actionable admission failure")

    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    worker = CountingWorker(
        queue_source=MultiQueue(), reads=Reads(), actions=Actions(), store=store,
        promotion_store=PromotionStore(), max_active_work_items=2,
        max_admission_attempts_per_scan=4, interval_seconds=30,
        monotonic=iter((0.0,)).__next__,
    )

    worker.tick()

    assert worker.calls == 8
    store.close()


def test_candidate_evaluation_budget_bounds_all_offline_probes(tmp_path: Path):
    class MultiQueue:
        def reconcile_candidates(self):
            items = []
            for i in range(12):
                base = candidate()
                items.append(replace(base, resource_id=str(170000 + i), context={**base.context, "id": 170000 + i, "ticketNumber": f"P{i}"}))
            return tuple(items)

    class OfflineWorker(OperationalAutonomyMaintenance):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.calls = 0

        def _scope_is_promoted(self, scope):
            return True

        def _admit(self, candidate, scope):
            self.calls += 1
            raise RuntimeError("endpoint is not currently online")

    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    worker = OfflineWorker(
        queue_source=MultiQueue(), reads=Reads(), actions=Actions(), store=store,
        promotion_store=PromotionStore(), max_active_work_items=2,
        max_admission_attempts_per_scan=4, max_candidate_evaluations_per_scan=8,
        interval_seconds=30, monotonic=iter((0.0,)).__next__,
    )

    worker.tick()

    assert worker.calls == 8
    store.close()


def test_eight_offline_candidates_do_not_starve_online_candidate(tmp_path: Path):
    class MultiQueue:
        def reconcile_candidates(self):
            items = []
            for i in range(9):
                base = candidate()
                items.append(
                    replace(
                        base,
                        resource_id=str(180000 + i),
                        context={
                            **base.context,
                            "id": 180000 + i,
                            "ticketNumber": f"F{i}",
                        },
                    )
                )
            return tuple(items)

    class FairWorker(OperationalAutonomyMaintenance):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.calls = []

        def _scope_is_promoted(self, scope):
            return True

        def _admit(self, candidate, scope):
            ticket_id = int(candidate.resource_id)
            self.calls.append(ticket_id)
            if ticket_id < 180008:
                raise RuntimeError("endpoint is not currently online")
            return OperationalWork(
                ticket_id=ticket_id,
                ticket_number="F8",
                title="Synthetic online candidate",
                playbook_id=scope.playbook_id,
                source_queue=str(candidate.source_queue),
                company_id=1,
                configuration_item_id=1,
                device_uid="online-device",
                hostname="ONLINE-PC",
                phase="claim",
            )

        def _advance(self, work, ticket):
            self.store.put(self._replace(work, phase="active_test"))

    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    worker = FairWorker(
        queue_source=MultiQueue(), reads=Reads(), actions=Actions(), store=store,
        promotion_store=PromotionStore(), max_active_work_items=2,
        max_admission_attempts_per_scan=4, max_candidate_evaluations_per_scan=12,
        interval_seconds=30, monotonic=iter((0.0,)).__next__,
    )

    worker.tick()

    assert worker.calls == [180000, 180001, 180002, 180003, 180004, 180005, 180006, 180007, 180008]
    assert store.get(180008) is not None
    assert store.latest_scan().selected == 1
    store.close()


def test_operational_work_store_appends_ticket_activity_and_seeds_existing_state(tmp_path: Path):
    path = tmp_path / "worker.sqlite3"
    store = SQLiteOperationalWorkStore(path)
    first = OperationalWork(
        ticket_id=140933,
        ticket_number="T20260925.9999",
        title="[Monitor] Antivirus status issue",
        playbook_id="datto_edr_av",
        source_queue="Jason",
        company_id=507,
        configuration_item_id=1583,
        device_uid="device-uid-1",
        hostname="PC-1",
        phase="claim",
        last_reason="claimed",
        updated_at="2026-09-29T01:00:00+00:00",
    )
    store.put(first)
    store.put(replace(
        first,
        phase="complete",
        last_reason="verified complete",
        updated_at="2026-09-29T01:05:00+00:00",
    ))
    rows = store._connection.execute(
        "SELECT phase,reason,occurred_at FROM autonomy_ticket_activity "
        "WHERE ticket_id=? ORDER BY activity_id",
        (140933,),
    ).fetchall()
    assert [(row["phase"], row["reason"], row["occurred_at"]) for row in rows] == [
        ("claim", "claimed", "2026-09-29T01:00:00+00:00"),
        ("complete", "verified complete", "2026-09-29T01:05:00+00:00"),
    ]

    store._connection.execute("DELETE FROM autonomy_ticket_activity")
    store._connection.close()
    reopened = SQLiteOperationalWorkStore(path)
    seeded = reopened._connection.execute(
        "SELECT phase,reason,occurred_at FROM autonomy_ticket_activity "
        "WHERE ticket_id=?",
        (140933,),
    ).fetchall()
    assert [(row["phase"], row["reason"], row["occurred_at"]) for row in seeded] == [
        ("complete", "verified complete", "2026-09-29T01:05:00+00:00")
    ]


def _owned_vulscan_candidate(*, status_label: str = "New") -> QueueCandidate:
    return QueueCandidate(
        resource_id="149001",
        priority=100,
        source_queue="Jason",
        owned_by_jason=True,
        urgent=False,
        context={
            "id": 149001,
            "ticketNumber": "T20260930.9001",
            "title": "Vulnerability Detected by VulScan - PC-1",
            "companyID": 507,
            "configurationItemID": 1583,
            "_jason_source_status_label": status_label,
        },
    )


class InactiveConfigurationReads(Reads):
    def execute(self, capability, arguments):
        if capability == "service.configuration.read":
            result = super().execute(capability, arguments)
            result["evidence"]["data"]["item"]["isActive"] = False
            return result
        return super().execute(capability, arguments)


def test_owned_nonretryable_admission_block_hands_off_instead_of_staying_new(tmp_path: Path):
    actions = Actions()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(_owned_vulscan_candidate()),
        reads=InactiveConfigurationReads(),
        actions=actions,
        store=store,
        promotion_store=PromotionStore(promoted=("vulscan_missing_patch",)),
        interval_seconds=60,
    )

    worker.tick()

    persisted = store.get(149001)
    assert persisted is not None
    assert persisted.phase == "escalated"
    updates = [call[2]["payload"] for call in actions.calls if call[1] == "service.ticket.update"]
    assert {"id": 149001, "queueID": "Help Desk I", "status": "Human Review"} in updates
    assert any(call[1] == "service.ticket.note.create" for call in actions.calls)


class Provider500ConfigurationReads(Reads):
    def execute(self, capability, arguments):
        if capability == "service.configuration.read":
            return {"status": "failed", "error_code": "PROVIDER_HTTP_STATUS_500"}
        return super().execute(capability, arguments)


def test_owned_retryable_provider_block_leaves_new_status_and_retries_under_jason(tmp_path: Path):
    actions = Actions()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(_owned_vulscan_candidate()),
        reads=Provider500ConfigurationReads(),
        actions=actions,
        store=store,
        promotion_store=PromotionStore(promoted=("vulscan_missing_patch",)),
        interval_seconds=60,
    )

    worker.tick()

    persisted = store.get(149001)
    assert persisted is not None
    assert persisted.phase == "blocked"
    updates = [call[2]["payload"] for call in actions.calls if call[1] == "service.ticket.update"]
    assert {"id": 149001, "status": "In Progress"} in updates
    assert not any(payload.get("queueID") == "Help Desk I" for payload in updates)


def test_worker_heartbeat_records_successful_scan(tmp_path: Path):
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(candidate()),
        reads=Reads(),
        actions=Actions(),
        store=store,
        promotion_store=PromotionStore(),
        max_active_work_items=2,
        interval_seconds=30,
        monotonic=iter((0.0,)).__next__,
    )

    worker.tick()

    heartbeat = store.worker_heartbeat()
    assert heartbeat is not None
    assert heartbeat["last_started_at"]
    assert heartbeat["last_completed_at"]
    assert heartbeat["last_failed_at"] is None
    assert heartbeat["last_error"] is None
    assert heartbeat["consecutive_failures"] == 0
    assert heartbeat["last_cycle_id"] == store.latest_scan().cycle_id
    assert heartbeat["last_duration_ms"] >= 0
    store.close()


def test_worker_heartbeat_records_failed_scan(tmp_path: Path):
    class BrokenQueue:
        def reconcile_candidates(self):
            raise RuntimeError("synthetic queue read failure")

    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    worker = OperationalAutonomyMaintenance(
        queue_source=BrokenQueue(),
        reads=Reads(),
        actions=Actions(),
        store=store,
        promotion_store=PromotionStore(),
        max_active_work_items=2,
        interval_seconds=30,
        monotonic=iter((0.0,)).__next__,
    )

    with pytest.raises(RuntimeError, match="synthetic queue read failure"):
        worker.tick()

    heartbeat = store.worker_heartbeat()
    assert heartbeat is not None
    assert heartbeat["last_started_at"]
    assert heartbeat["last_completed_at"] is None
    assert heartbeat["last_failed_at"]
    assert "synthetic queue read failure" in heartbeat["last_error"]
    assert heartbeat["consecutive_failures"] == 1
    store.close()


def test_vulscan_wait_schedules_durable_reconcile_wake(tmp_path: Path):
    actions = Actions()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    wake_store = SQLiteTargetedWakeStore(tmp_path / "wakes.sqlite3")
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(vulscan_candidate()),
        reads=VulscanBranchReads("NOT_APPROVED"),
        actions=actions,
        store=store,
        promotion_store=PromotionStore(promoted=("vulscan_missing_patch",)),
        targeted_wake_store=wake_store,
        max_active_work_items=2,
        interval_seconds=30,
        monotonic=iter((0.0,)).__next__,
    )

    worker.tick()

    rows = wake_store._connection.execute(
        "SELECT kind,state,resource_id,payload FROM autonomy_targeted_wakes "
        "WHERE resource_id=?",
        ("141183",),
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["kind"] == WakeKind.QUEUE_RECONCILE.value
    assert rows[0]["state"] == WakeState.PENDING.value
    assert rows[0]["resource_id"] == "141183"
    assert "VulScan patch approval recheck due" in rows[0]["payload"]
    wake_store.close()
    store.close()


def test_waiting_device_access_schedules_exact_endpoint_wake(tmp_path: Path):
    base = candidate()
    owned = replace(
        base,
        source_queue="Jason",
        owned_by_jason=True,
        context={
            **base.context,
            "_jason_source_status_label": "New",
        },
    )

    class OfflineReads(Reads):
        def execute(self, capability, arguments):
            if capability == "endpoint.device.read":
                return {
                    "status": "succeeded",
                    "evidence": {"record": {
                        "resource_id": "device-uid-1",
                        "hostname": "PC-1",
                        "online": False,
                    }},
                }
            if capability == "backup.endpoint.asset.search":
                return {
                    "status": "succeeded",
                    "evidence": {"data": {"items": []}},
                }
            return super().execute(capability, arguments)

    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    wake_store = SQLiteTargetedWakeStore(tmp_path / "wakes.sqlite3")
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(owned),
        reads=OfflineReads(),
        actions=Actions(),
        store=store,
        promotion_store=PromotionStore(),
        targeted_wake_store=wake_store,
        max_active_work_items=2,
        interval_seconds=30,
        monotonic=iter((0.0,)).__next__,
    )

    worker.tick()

    waiting = store.get(140933)
    assert waiting is not None
    assert waiting.phase == "waiting_device_access:claim"
    rows = wake_store._connection.execute(
        "SELECT kind,state,resource_id,payload FROM autonomy_targeted_wakes "
        "WHERE resource_id=?",
        ("140933",),
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["kind"] == WakeKind.TARGETED_READ.value
    assert rows[0]["state"] == WakeState.PENDING.value
    assert '"capability_name":"endpoint.device.read"' in rows[0]["payload"]
    assert '"resource_id":"device-uid-1"' in rows[0]["payload"]
    wake_store.close()
    store.close()


def test_unsupported_helpdesk_ticket_gets_one_gpt_insights_note_when_promoted(tmp_path: Path):
    class InsightReads(Reads):
        def execute(self, capability, arguments):
            if capability == "service.ticket.search":
                return {"status": "succeeded", "evidence": {"data": {"items": []}}}
            if capability == "endpoint.powershell.read":
                return {
                    "status": "succeeded",
                    "evidence": {"data": {"stdout": json.dumps({
                        "Name": "Ethernet",
                        "PhysicalMediaType": "802.3",
                        "Profile": "Rigginsco.local",
                    })}},
                }
            return super().execute(capability, arguments)

    item = QueueCandidate(
        resource_id="140999",
        priority=50,
        source_queue="Help Desk I",
        owned_by_jason=False,
        urgent=False,
        context={
            "id": 140999,
            "ticketNumber": "T20261001.0099",
            "title": "My PC keeps disconnecting from the network",
            "description": "Connection drops randomly.",
            "companyID": 507,
            "configurationItemID": 1583,
        },
    )
    actions = Actions()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(item),
        reads=InsightReads(),
        actions=actions,
        store=store,
        promotion_store=PromotionStore(promoted=("gpt_insights_tech_assist",)),
        max_active_work_items=2,
        interval_seconds=30,
        monotonic=iter((0.0,)).__next__,
    )
    worker.tick()

    notes = [args["payload"] for _, capability, args in actions.calls if capability == "service.ticket.note.create"]
    assert len(notes) == 1
    assert notes[0]["title"] == "GPT Insights"
    assert "Wired: Ethernet (Rigginsco.local)" in notes[0]["description"]
    assert "do not ask the technician or user to rediscover it" in notes[0]["description"]
    assert not any(capability == "service.ticket.update" for _, capability, _ in actions.calls)
    store.close()


def test_unsupported_helpdesk_ticket_does_not_write_without_exact_promotion(tmp_path: Path):
    item = QueueCandidate(
        resource_id="140998",
        priority=50,
        source_queue="Help Desk I",
        owned_by_jason=False,
        urgent=False,
        context={
            "id": 140998,
            "ticketNumber": "T20261001.0098",
            "title": "General question Jason cannot classify",
            "description": "Please call me.",
            "companyID": 507,
            "configurationItemID": 1583,
        },
    )
    actions = Actions()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    worker = OperationalAutonomyMaintenance(
        queue_source=QueueSource(item), reads=Reads(), actions=actions, store=store,
        promotion_store=PromotionStore(promoted=()), max_active_work_items=2,
        interval_seconds=30, monotonic=iter((0.0,)).__next__,
    )
    worker.tick()
    assert actions.calls == []
    store.close()
