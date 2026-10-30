"""Regression coverage for permission-preserving unsupported ticket triage."""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from autonomous_remediation.autonomous_queue_worker import QueueCandidate
from jason_runtime.autonomy_worker_runtime import (
    OperationalAutonomyMaintenance, SQLiteOperationalWorkStore,
)
from jason_runtime.unsupported_ticket_triage import (
    WINDOWS_DISK_READ, WINDOWS_LICENSING_READ, WINDOWS_SERVICE_READ,
    category_for, gather,
)


class ReadStub:
    def __init__(self):
        self.calls = []
        self.fail_next_ticket = False
        self.online = True
        self.endpoint_uid = "device-7"
        self.company_id = 777
        self.os = "Windows 11 Pro"

    def execute(self, capability, arguments):
        self.calls.append((capability, dict(arguments)))
        if capability == "service.ticket.read":
            raise AssertionError("worker has no service.ticket.read authority")
        if capability == "service.ticket.notes.search":
            if self.fail_next_ticket:
                self.fail_next_ticket = False
                return {"status": "denied", "error_code": "PROVIDER_TRANSPORT_FAILURE"}
            content = {"items": [{"id": 8, "title": "Ticket arrived"}]}
        elif capability == "service.configuration.read":
            content = {"item": {
                "id": 1100, "companyID": 777, "referenceNumber": "device-7",
                "isActive": True, "rmmDeviceAuditHostname": "PC-7",
            }}
        elif capability == "endpoint.device.read":
            content = {"record": {
                "resource_id": self.endpoint_uid, "hostname": "PC-7",
                "operatingSystem": self.os, "online": self.online,
            }}
        elif capability == "endpoint.audit.read":
            content = {"audit": {"logicalDisks": [
                {"description": "Local Fixed Disk", "diskIdentifier": "C:",
                 "freespace": 63 * 1024 ** 3, "size": 254 * 1024 ** 3},
                {"description": "Network Drive", "diskIdentifier": "Z:",
                 "freespace": 1, "size": 1},
            ]}}
        elif capability == "endpoint.powershell.read":
            raise AssertionError("Generic read-only triage cannot launch endpoint jobs")
        else:
            raise AssertionError(capability)
        return {"status": "succeeded", "evidence": {"data": content}}


class NoMutation:
    def __init__(self):
        self.calls = []

    def execute(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        raise AssertionError("generic triage must never use a write capability")


class NoPromotion:
    def find_scope_approved(self, **kwargs):
        return None


class Queue:
    def __init__(self, *items):
        self.items = items

    def reconcile_candidates(self):
        return self.items


def ticket(*, ticket_id=200001, title="Windows License Status failed",
           company_id=777, status="New", assigned=False, version="v1",
           queue="Help Desk I"):
    return QueueCandidate(
        resource_id=str(ticket_id), priority=80, source_queue=queue,
        owned_by_jason=queue == "Jason", urgent=False,
        source_version=version, context={
            "id": ticket_id, "ticketNumber": f"T20261029.{ticket_id}",
            "title": title, "companyID": company_id,
            "configurationItemID": 1100,
            "_jason_source_status_label": status,
            "_jason_assigned_elsewhere": assigned,
        },
    )


def make_worker(tmp_path, items, reads, *, max_triage=2):
    actions = NoMutation()
    store = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    worker = OperationalAutonomyMaintenance(
        queue_source=Queue(*items), reads=reads, actions=actions, store=store,
        promotion_store=NoPromotion(), max_unsupported_triage_per_scan=max_triage,
        triage_note_pilot_ticket_ids=(200001, 200002),
        interval_seconds=30, monotonic=iter((0.0, 31.0, 62.0, 93.0, 124.0)).__next__,
    )
    return worker, store, actions


def test_fixed_command_category_mapping():
    assert category_for("OS Licence Status", "") == "windows_licensing"
    assert category_for("Service RocketAgent is stopped", "") == "rocketagent_service"
    assert category_for("Space Issue", "") == "disk_capacity"
    assert category_for("Linux logs cleared", "") == "security_review"
    assert category_for("General printer question", "") == "general"
    for script in (WINDOWS_LICENSING_READ, WINDOWS_SERVICE_READ, WINDOWS_DISK_READ):
        assert "ConvertTo-Json" in script
        assert "Remove-" not in script and "Restart-" not in script
        assert "Set-Service" not in script and "Invoke-" not in script


def test_gather_exact_same_company_identity_and_license_whitelist():
    reads = ReadStub()

    def read(capability, args):
        result = reads.execute(capability, args)
        return dict(result["evidence"]["data"])

    result = gather(ticket_snapshot={"id":200001,"companyID":777,"configurationItemID":1100},
        ticket_id=200001, company_id=777, configuration_item_id=1100,
        title="License Status", unsupported_reason="windows_licensing_diagnostics_candidate",
        read=read,
    )
    assert result.state == "needs_execution_authority"
    assert result.evidence["company_verified"] is True
    assert all(cap != "service.ticket.read" for cap, _ in reads.calls)
    assert result.evidence["rmm_identity_verified"] is True
    assert result.evidence["notes_observed"] == 1
    assert "diagnostic" not in result.evidence
    assert all(cap != "endpoint.powershell.read" for cap, _ in reads.calls)
    assert "separately governed" in result.next_step


def test_unverified_endpoint_blocks_powershell_and_fails_closed():
    reads = ReadStub()
    reads.endpoint_uid = "other-customer-endpoint"

    def read(capability, args):
        return reads.execute(capability, args)["evidence"]["data"]

    with pytest.raises(ValueError, match="endpoint_identity_mismatch"):
        gather(ticket_snapshot={"id":200001,"companyID":777,"configurationItemID":1100}, ticket_id=200001, company_id=777, configuration_item_id=1100,
               title="License Status", unsupported_reason="", read=read)
    assert not any(cap == "endpoint.powershell.read" for cap, _ in reads.calls)


def test_wrong_company_fails_before_configuration_or_endpoint_reads():
    reads = ReadStub()
    def read(capability, args):
        return reads.execute(capability, args)["evidence"]["data"]

    with pytest.raises(ValueError, match="ticket_company_mismatch"):
        gather(ticket_snapshot={"id":200001,"companyID":777,"configurationItemID":1100}, ticket_id=200001, company_id=888, configuration_item_id=1100,
               title="License Status", unsupported_reason="", read=read)
    assert reads.calls == []


def test_offline_ticket_never_executes_powershell():
    reads = ReadStub()
    reads.online = False
    def read(capability, args):
        return reads.execute(capability, args)["evidence"]["data"]

    result = gather(ticket_snapshot={"id":200001,"companyID":777,"configurationItemID":1100}, ticket_id=200001, company_id=777, configuration_item_id=1100,
                    title="License Status", unsupported_reason="", read=read)
    assert result.state == "waiting_device_access"
    assert not any(cap == "endpoint.powershell.read" for cap, _ in reads.calls)


def test_non_windows_device_does_not_receive_windows_command():
    reads = ReadStub()
    reads.os = "Ubuntu Linux"
    def read(capability, args):
        return reads.execute(capability, args)["evidence"]["data"]

    result = gather(ticket_snapshot={"id":200001,"companyID":777,"configurationItemID":1100}, ticket_id=200001, company_id=777, configuration_item_id=1100,
                    title="License Status", unsupported_reason="", read=read)
    assert result.state == "diagnostic_not_applicable"
    assert not any(cap == "endpoint.powershell.read" for cap, _ in reads.calls)


def test_unsupported_triage_persists_without_ticket_mutations(tmp_path):
    reads = ReadStub()
    worker, store, actions = make_worker(tmp_path, [ticket(title="Space Issue")], reads)
    worker.tick()
    record = store.unsupported_triage(200001)
    assert record["state"] == "read_only_assessed"
    assert record["category"] == "disk_capacity"
    assert record["evidence"]["rmm_identity_verified"] is True
    assert record["evidence"]["disk_audit"][0]["drive"] == "C:"
    assert record["evidence"]["disk_audit"][0]["free_percent"] == 24.8
    assert record["next_step"]
    assert store.get(200001) is None
    assert store.latest_scan().eligible == 0
    assert store.latest_scan().selected == 0
    assert actions.calls == []
    assert not any(name == "endpoint.powershell.read" for name, _ in reads.calls)
    assert sum(x[0] == "endpoint.audit.read" for x in reads.calls) == 1

    # Existing evidence is not recollected every minute.
    worker.tick()
    assert sum(x[0] == "endpoint.audit.read" for x in reads.calls) == 1
    store.close()

    # Durable record survives worker restart.
    reopened = SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3")
    assert reopened.unsupported_triage(200001)["state"] == "read_only_assessed"
    reopened.close()


def test_source_change_triggers_retriage(tmp_path):
    reads = ReadStub()
    item = ticket(title="Space Issue")
    worker, store, _ = make_worker(tmp_path, [item], reads)
    worker.tick()
    worker.queue_source = Queue(replace(item, source_version="v2"))
    worker.tick()
    assert store.unsupported_triage(200001)["source_version"] == "v2"
    assert sum(x[0] == "endpoint.audit.read" for x in reads.calls) == 2
    store.close()


def test_one_read_failure_does_not_starve_second_ticket_and_retries_when_due(tmp_path):
    reads = ReadStub()
    reads.fail_next_ticket = True
    worker, store, actions = make_worker(
        tmp_path, [ticket(ticket_id=200001, title="Space Issue"), ticket(ticket_id=200002, title="Space Issue")], reads,
    )
    worker.tick()
    first = store.unsupported_triage(200001)
    second = store.unsupported_triage(200002)
    assert first["state"] == "read_failed_retry"
    assert first["attempts"] == 1
    assert second["state"] == "read_only_assessed"
    assert actions.calls == []
    worker.tick()
    assert store.unsupported_triage(200001)["attempts"] == 1

    # Explicit simulated passage of the next_due time exercises bounded recovery.
    with store._connection:
        store._connection.execute(
            "UPDATE autonomy_unsupported_triage SET next_due_at=? WHERE ticket_id=?",
            ("2020-01-01T00:00:00+00:00", 200001),
        )
    worker.tick()
    assert store.unsupported_triage(200001)["state"] == "read_only_assessed"
    assert store.unsupported_triage(200001)["attempts"] == 0
    store.close()


def test_assigned_new_ticket_gets_readonly_assessment_without_claim_or_note(tmp_path):
    reads = ReadStub()
    worker, store, actions = make_worker(
        tmp_path, [ticket(assigned=True), ticket(ticket_id=200002, status="In Progress")], reads,
    )
    worker.tick()
    assessed = store.unsupported_triage(200001)
    assert assessed is not None
    assert assessed["state"] == "needs_execution_authority"
    assert assessed["evidence"]["read_only_investigation"] is True
    assert store.unsupported_triage(200002) is None
    assert store.get(200001) is None
    assert store.get(200002) is None
    assert reads.calls
    assert actions.calls == []
    store.close()


def test_missing_ci_is_durable_human_identity_outcome(tmp_path):
    item = ticket()
    item = replace(item, context={**item.context, "configurationItemID": None})
    reads = ReadStub()
    reads.execute = lambda cap, args: {
        "status": "succeeded", "evidence": {"data": (
            {"items": [{"id": 200001, "companyID": 777, "configurationItemID": None}]}
            if cap == "service.ticket.read" else
            {"items": []} if cap == "service.ticket.notes.search" else
            (_ for _ in ()).throw(AssertionError("no endpoint read"))
        )}
    }
    worker, store, actions = make_worker(tmp_path, [item], reads)
    worker.tick()
    state = store.unsupported_triage(200001)
    assert state["state"] == "needs_device_identity"
    assert "CI" in state["next_step"]
    assert actions.calls == []
    store.close()


def test_maximum_two_unsupported_diagnostics_per_cycle(tmp_path):
    reads = ReadStub()
    items = [ticket(ticket_id=200001+i) for i in range(5)]
    worker, store, _ = make_worker(tmp_path, items, reads, max_triage=2)
    worker.tick()
    assert sum(store.unsupported_triage(int(x.resource_id)) is not None for x in items) == 2
    worker.tick()
    assert sum(store.unsupported_triage(int(x.resource_id)) is not None for x in items) == 4
    store.close()


def test_missing_company_id_is_a_human_identity_outcome(tmp_path):
    item = ticket(company_id=0, title="RocketAgent service stopped")
    reads = ReadStub()
    reads.company_id = 0
    worker, store, actions = make_worker(tmp_path, [item], reads)
    worker.tick()
    result = store.unsupported_triage(200001)
    assert result["state"] == "needs_company_identity"
    assert result["next_step"].startswith("Verify the customer/company")
    assert reads.calls == []
    assert actions.calls == []
    store.close()


@pytest.mark.parametrize("title,expected", (
    ("Linux logs cleared", "needs_security_review"),
    ("General software question", "needs_playbook_review"),
))
def test_security_and_generic_cases_never_assert_resolution(tmp_path, title, expected):
    item = ticket(title=title)
    reads = ReadStub()
    worker, store, actions = make_worker(tmp_path, [item], reads)
    worker.tick()
    result = store.unsupported_triage(200001)
    assert result["state"] == expected
    assert "does not authorize" in result["next_step"].casefold() or "security technician" in result["next_step"].casefold()
    assert all(cap != "endpoint.powershell.read" for cap, _ in reads.calls)
    assert actions.calls == []
    store.close()


def test_authorization_denial_is_persisted_not_retried_each_scan(tmp_path):
    class DenyingRead(ReadStub):
        def execute(self, capability, arguments):
            if capability == "service.ticket.notes.search":
                self.calls.append((capability, arguments))
                return {"status": "denied", "error_code": "INFORMATION_RELEASE_DENIED"}
            return super().execute(capability, arguments)

    reads = DenyingRead()
    worker, store, actions = make_worker(tmp_path, [ticket()], reads)
    worker.tick()
    result = store.unsupported_triage(200001)
    assert result["state"] == "governance_blocked"
    assert result["last_error"] == "OperationalAutonomyError"
    worker.tick()
    assert sum(cap == "service.ticket.notes.search" for cap, _ in reads.calls) == 1
    assert actions.calls == []
    store.close()


def test_unknown_endpoint_os_is_not_authority_for_windows_powershell(tmp_path):
    reads = ReadStub()
    reads.os = ""
    worker, store, actions = make_worker(tmp_path, [ticket()], reads)
    worker.tick()
    assert store.unsupported_triage(200001)["state"] == "diagnostic_not_applicable"
    assert not any(cap == "endpoint.powershell.read" for cap, _ in reads.calls)
    assert actions.calls == []
    store.close()


def test_repeated_provider_errors_signal_human_review_without_remediation(tmp_path):
    class BrokenRead(ReadStub):
        def execute(self, capability, arguments):
            self.calls.append((capability, dict(arguments)))
            return {"status": "denied", "error_code": "PROVIDER_TRANSPORT_FAILURE"}

    reads = BrokenRead()
    worker, store, actions = make_worker(tmp_path, [ticket()], reads)
    for i in range(3):
        if i:
            with store._connection:
                store._connection.execute(
                    "UPDATE autonomy_unsupported_triage SET next_due_at=? WHERE ticket_id=?",
                    ("2020-01-01T00:00:00+00:00", 200001),
                )
        worker.tick()
    result = store.unsupported_triage(200001)
    assert result["state"] == "needs_human_review"
    assert result["attempts"] == 3
    assert "technician" in result["next_step"].casefold()
    assert result["last_error"] == "OperationalAutonomyError"
    assert len(reads.calls) == 3
    assert actions.calls == []
    store.close()


def test_ticket_id_conflict_in_governed_search_snapshot_is_identity_review(tmp_path):
    reads = ReadStub()
    item = ticket()
    # QueueCandidate must agree with the signed service.ticket.search record.
    item = replace(item, context={**item.context, "id": 200002})
    worker, store, actions = make_worker(tmp_path, [item], reads)
    worker.tick()
    result = store.unsupported_triage(200001)
    assert result["state"] == "needs_company_identity"
    assert result["last_error"] == "ValueError"
    assert result["attempts"] == 1
    assert reads.calls == []
    assert actions.calls == []
    store.close()


def test_prior_production_policy_denial_is_reevaluated_once_after_upgrade(tmp_path):
    reads = ReadStub()
    worker, store, actions = make_worker(tmp_path, [ticket()], reads)
    store.record_unsupported_triage(
        ticket_id=200001, ticket_number="T20261029.200001",
        source_version="v1", category="windows_licensing",
        state="governance_blocked", evidence={"ticket_id": 200001},
        next_step="Governed ticket.read denied under previous code",
        attempts=1, checked_at="2026-10-29T10:00:00+00:00",
        next_due_at="2026-10-30T10:00:00+00:00",
        last_error="OperationalAutonomyError",
    )
    worker.tick()
    row = store.unsupported_triage(200001)
    assert row["state"] == "needs_execution_authority"
    assert row["evidence"]["triage_logic_version"] == "read_only_admission_assurance_v5"
    assert all(cap != "service.ticket.read" for cap, _ in reads.calls)
    first_count = len(reads.calls)
    worker.tick()
    assert len(reads.calls) == first_count
    assert actions.calls == []
    store.close()


def test_snapshot_path_preserves_existing_autonomous_information_release_boundary():
    from orchestrator.autotask_information_authorizer import (
        _AUTONOMOUS_WORKER_READS, SERVICE_TICKET_READ,
        SERVICE_TICKET_SEARCH, SERVICE_TICKET_NOTES_SEARCH,
        SERVICE_CONFIGURATION_READ,
    )

    assert SERVICE_TICKET_SEARCH in _AUTONOMOUS_WORKER_READS
    assert SERVICE_TICKET_NOTES_SEARCH in _AUTONOMOUS_WORKER_READS
    assert SERVICE_CONFIGURATION_READ in _AUTONOMOUS_WORKER_READS
    assert SERVICE_TICKET_READ not in _AUTONOMOUS_WORKER_READS


def test_passive_disk_read_has_no_endpoint_execution_and_excludes_other_drives():
    from jason_runtime.unsupported_ticket_triage import _audit_disk_evidence

    raw = {"audit": {"logicalDisks": [
        {"description": "Local Fixed Disk", "diskIdentifier": "C:",
         "freespace": 63 * 1024**3, "size": 254 * 1024**3,
         "serialNumber": "SECRET-DO-NOT-COPY"},
        {"description": "Network Drive", "diskIdentifier": "Z:",
         "freespace": 99, "size": 100},
        {"description": "Local Fixed Disk", "diskIdentifier": "D:",
         "freespace": -1, "size": 100},
    ]}}
    disks = _audit_disk_evidence(raw)
    assert len(disks) == 1
    assert disks[0]["drive"] == "C:"
    assert disks[0]["free_percent"] == 24.8
    assert "SECRET-DO-NOT-COPY" not in json.dumps(disks)


def test_missing_disk_audit_does_not_claim_success():
    reads = ReadStub()
    original_execute = reads.execute

    def no_disks(capability, arguments):
        if capability == "endpoint.audit.read":
            return {"status": "succeeded",
                    "evidence": {"data": {"audit": {"logicalDisks": []}}}}
        return original_execute(capability, arguments)

    reads.execute = no_disks
    result = gather(
        ticket_snapshot={"id": 200001, "companyID": 777, "configurationItemID": 1100},
        ticket_id=200001, company_id=777, configuration_item_id=1100,
        title="Space Issue", unsupported_reason="",
        read=lambda cap, args: dict(reads.execute(cap, args)["evidence"]["data"]),
    )
    assert result.state == "needs_diagnostic_evidence"
    assert "diagnostic" not in result.evidence
    assert all(name != "endpoint.powershell.read" for name, _ in reads.calls)


class PromotionForTriage:
    def __init__(self, handoff=False):
        self.handoff = handoff

    def find_scope_approved(self, **kwargs):
        if kwargs.get("playbook_id") == "unsupported_readonly_triage_note":
            return object()
        if kwargs.get("playbook_id") == "unsupported_triage_human_review" and self.handoff:
            return object()
        return None


class NoteReadStub(ReadStub):
    def __init__(self):
        super().__init__()
        self.notes = [{"id": 8, "title": "Ticket arrived", "description": "Internal history"}]

    def execute(self, capability, arguments):
        if capability == "service.ticket.notes.search":
            self.calls.append((capability, dict(arguments)))
            return {"status": "succeeded", "evidence": {"data": {"items": list(self.notes)}}}
        return super().execute(capability, arguments)


class NoteActionStub:
    def __init__(self, reads, *, verify_handoff=True):
        self.reads = reads
        self.verify_handoff = verify_handoff
        self.calls = []

    def execute(self, scope, capability, arguments):
        payload = dict(arguments.get("payload") or {})
        self.calls.append((scope.playbook_id, capability, payload))
        if capability in ("service.ticket.note.create", "service.ticket.note.update"):
            assert scope.playbook_id == "unsupported_readonly_triage_note"
            assert payload["ticketID"] == 200001
            assert payload["title"] == "Jason - Governed Read-Only Investigation"
            assert payload["noteType"] == 3
            assert payload["publish"] == 2
            existing = next((r for r in self.reads.notes
                             if r["title"] == payload["title"]), None)
            if existing:
                assert capability == "service.ticket.note.update"
                assert payload["id"] == existing["id"]
                existing["description"] = payload["description"]
            else:
                assert capability == "service.ticket.note.create"
                self.reads.notes.append({
                    "id": 9001,
                    "title": payload["title"],
                    "description": payload["description"],
                })
            return {"data": {"status": "succeeded"}}
        if capability == "service.ticket.update":
            assert scope.playbook_id == "unsupported_triage_human_review"
            assert payload == {"id": 200001, "queueID": "Help Desk I",
                               "status": "Human Review"}
            if self.verify_handoff:
                return {"data": {"jasonVerification": {
                    "readbackVerified": True,
                    "verifiedFields": ["queueID", "status"],
                }}}
            return {"data": {"jasonVerification": {"readbackVerified": False}}}
        raise AssertionError(capability)


def test_readonly_evidence_draft_staged_without_any_note_promotion(tmp_path):
    reads = NoteReadStub()
    worker, store, actions = make_worker(
        tmp_path, [ticket(title="Space Issue")], reads,
    )
    worker.tick()
    row = store.unsupported_triage(200001)
    assert row["state"] == "read_only_assessed"
    body = row["evidence"]["note_draft"]
    assert body.startswith("JASON READ-ONLY INVESTIGATION")
    assert "Datto audit volume C:" in body
    assert "63.0 GiB free" in body
    assert "CHANGES MADE" in body
    assert "Not resolved or closed" in body
    assert "service.ticket.note.create" not in [x[0] for x in reads.calls]
    assert actions.calls == []
    assert store.last_note_fingerprint(
        200001, "unsupported_readonly_triage_note",
        "Jason - Governed Read-Only Investigation",
    ) is None
    store.close()


def test_exact_note_promotion_posts_once_and_requires_provider_readback(tmp_path):
    reads = NoteReadStub()
    worker, store, _ = make_worker(
        tmp_path, [ticket(title="Space Issue")], reads,
    )
    worker.promotion_store = PromotionForTriage()
    actions = NoteActionStub(reads)
    worker.actions = actions
    worker.tick()
    assert len(actions.calls) == 1
    assert actions.calls[0][1] == "service.ticket.note.create"
    assert "Datto audit volume C:" in reads.notes[-1]["description"]
    assert store.last_note_fingerprint(
        200001, "unsupported_readonly_triage_note",
        "Jason - Governed Read-Only Investigation",
    )
    worker.tick()
    assert len(actions.calls) == 1
    store.close()


def test_existing_note_reconciles_without_create_or_duplicate(tmp_path):
    reads = NoteReadStub()
    worker, store, _ = make_worker(
        tmp_path, [ticket(title="Space Issue")], reads,
    )
    worker.tick()
    body = store.unsupported_triage(200001)["evidence"]["note_draft"]
    reads.notes.append({
        "id": 9001, "title": "Jason - Governed Read-Only Investigation",
        "description": body,
    })
    worker.promotion_store = PromotionForTriage()
    worker.actions = NoteActionStub(reads)
    worker.tick()
    assert worker.actions.calls == []
    assert store.last_note_fingerprint(
        200001, "unsupported_readonly_triage_note",
        "Jason - Governed Read-Only Investigation",
    )
    store.close()


def test_human_review_handoff_requires_separate_promotion_and_queue_status_readback(tmp_path):
    from datetime import datetime, timezone
    from jason_runtime.unsupported_ticket_triage import render_triage_note
    source = ticket(title="Space Issue", queue="Jason")
    reads = NoteReadStub()
    worker, store, _ = make_worker(tmp_path, [source], reads)
    worker.promotion_store = PromotionForTriage(handoff=True)
    actions = NoteActionStub(reads, verify_handoff=False)
    worker.actions = actions
    now = datetime.now(timezone.utc)
    evidence = {"company_verified": True, "ticket_id": 200001, "notes_observed": 1}
    evidence["note_draft"] = render_triage_note(
        ticket_number="T20261029.0001", state="needs_human_review",
        category="general", evidence=evidence,
        next_step="Technician must inspect the failed provider evidence path.",
    )
    record = {"state": "needs_human_review", "evidence": evidence,
              "source_version": "v1", "ticket_number": source.context["ticketNumber"]}
    worker._maybe_publish_unsupported_triage_note(source, record, now=now)
    assert [cap for _, cap, _ in actions.calls] == [
        "service.ticket.note.create", "service.ticket.update",
    ]
    assert store.last_note_fingerprint(
        200001, "unsupported_readonly_triage_note",
        "Jason - Governed Read-Only Investigation",
    )
    assert store.unsupported_note_delivery(200001)["attempts"] == 0
    assert store.unsupported_handoff_delivery(200001)["state"] == "retry_pending"
    assert store.unsupported_handoff_delivery(200001)["attempts"] == 1

    # Retry sees the already-verified note and must not create a duplicate.
    with store._connection:
        store._connection.execute(
            "UPDATE autonomy_unsupported_handoff_delivery SET next_due_at=? WHERE ticket_id=?",
            ("2020-01-01T00:00:00+00:00", 200001),
        )
    actions.verify_handoff = True
    worker._maybe_publish_unsupported_triage_note(source, record, now=now)
    assert [cap for _, cap, _ in actions.calls] == [
        "service.ticket.note.create", "service.ticket.update",
        "service.ticket.update",
    ]
    assert store.last_note_fingerprint(
        200001, "unsupported_readonly_triage_note",
        "Jason - Governed Read-Only Investigation",
    )
    assert store.unsupported_handoff_delivery(200001)["state"] == "verified"
    worker._maybe_publish_unsupported_triage_note(source, record, now=now)
    assert len(actions.calls) == 3
    store.close()


@pytest.mark.parametrize("state,category", [
    ("read_only_assessed", "disk_capacity"),
    ("needs_diagnostic_evidence", "user_device_settings"),
])
@pytest.mark.parametrize("handoff_promoted", [False, True])
def test_unresolved_triage_outcomes_handoff_only_with_exact_promotion(
    tmp_path, state, category, handoff_promoted,
):
    from datetime import datetime, timezone
    from jason_runtime.unsupported_ticket_triage import render_triage_note

    source = ticket(title="Ticket still requires technician", queue="Jason")
    reads = NoteReadStub()
    worker, store, _ = make_worker(tmp_path, [source], reads)
    worker.promotion_store = PromotionForTriage(handoff=handoff_promoted)
    actions = NoteActionStub(reads)
    worker.actions = actions
    evidence = {"company_verified": True, "ticket_id": 200001}
    evidence["note_draft"] = render_triage_note(
        ticket_number=source.context["ticketNumber"],
        state=state, category=category, evidence=evidence,
        next_step="Technician must verify outstanding issue before closing.",
    )
    record = {
        "state": state, "evidence": evidence,
        "source_version": source.source_version,
        "ticket_number": source.context["ticketNumber"],
    }
    worker._maybe_publish_unsupported_triage_note(
        source, record, now=datetime.now(timezone.utc),
    )
    expected = ["service.ticket.note.create"]
    if handoff_promoted:
        expected.append("service.ticket.update")
    assert [cap for _, cap, _ in actions.calls] == expected
    if handoff_promoted:
        assert store.unsupported_handoff_delivery(200001)["state"] == "verified"
    else:
        assert store.unsupported_handoff_delivery(200001) is None
    worker._maybe_publish_unsupported_triage_note(
        source, record, now=datetime.now(timezone.utc),
    )
    assert [cap for _, cap, _ in actions.calls] == expected
    store.close()


def test_helpdesk_ticket_never_requeued_even_with_handoff_promotion(tmp_path):
    from datetime import datetime, timezone
    from jason_runtime.unsupported_ticket_triage import render_triage_note
    source = ticket(title="Space Issue", queue="Help Desk I")
    reads = NoteReadStub()
    worker, store, _ = make_worker(tmp_path, [source], reads)
    worker.promotion_store = PromotionForTriage(handoff=True)
    actions = NoteActionStub(reads)
    worker.actions = actions
    evidence = {"company_verified": True, "ticket_id": 200001}
    evidence["note_draft"] = render_triage_note(
        ticket_number="T20261029.0001", state="needs_human_review",
        category="general", evidence=evidence,
        next_step="Technician must review provider evidence.",
    )
    worker._maybe_publish_unsupported_triage_note(
        source, {"state": "needs_human_review", "evidence": evidence,
                 "source_version": "v1", "ticket_number": source.context["ticketNumber"]},
        now=datetime.now(timezone.utc),
    )
    assert len(actions.calls) == 1
    assert actions.calls[0][1] == "service.ticket.note.create"
    store.close()


def test_at_most_two_promoted_note_attempts_per_scan_and_no_starvation(tmp_path):
    from datetime import datetime, timedelta, timezone
    items = [ticket(ticket_id=200001 + i, title="Space Issue") for i in range(5)]
    worker, store, actions = make_worker(
        tmp_path, items, NoteReadStub(), max_triage=2,
    )
    now = datetime.now(timezone.utc)
    for item in items:
        store.record_unsupported_triage(
            ticket_id=int(item.resource_id),
            ticket_number=item.context["ticketNumber"],
            source_version="v1", category="disk_capacity",
            state="read_only_assessed",
            evidence={
                "ticket_id": int(item.resource_id), "company_verified": True,
                "triage_logic_version": "passive_rmm_audit_v3",
                "note_draft": "JASON READ-ONLY INVESTIGATION\n",
            },
            next_step="Review passive audit", attempts=0,
            checked_at=now.isoformat(),
            next_due_at=(now + timedelta(days=1)).isoformat(),
        )

    observed = set()
    attempts = []
    def attempted_once(candidate, record, *, now):
        identity = int(candidate.resource_id)
        if identity in observed:
            return False
        observed.add(identity)
        attempts.append(identity)
        return True

    worker._maybe_publish_unsupported_triage_note = attempted_once
    worker.tick()
    assert attempts == [200001, 200002]
    worker.tick()
    assert attempts == [200001, 200002, 200003, 200004]
    assert actions.calls == []
    store.close()


def test_note_pilot_registry_and_runtime_scope_are_exactly_aligned():
    import json
    from jason_runtime.autonomy_worker_composition import TRIAGE_NOTE_PILOT_TICKET_IDS
    from jason_runtime.autonomy_worker_runtime import (
        UNSUPPORTED_TRIAGE_NOTE_SCOPE, UNSUPPORTED_TRIAGE_HANDOFF_SCOPE,
    )
    registry = json.loads((
        Path(__file__).resolve().parents[2] / "autonomous_remediation"
        / "playbook_registry.json"
    ).read_text())
    by_id = {p["id"]: p for p in registry["playbooks"]}
    assert TRIAGE_NOTE_PILOT_TICKET_IDS == (143305, 143272)
    for scope in (UNSUPPORTED_TRIAGE_NOTE_SCOPE, UNSUPPORTED_TRIAGE_HANDOFF_SCOPE):
        entry = by_id[scope.playbook_id]
        assert entry["lifecycle"] == "production" and entry["enabled"] is True
        assert entry["version"] == scope.playbook_version
        assert entry["autonomy"]["policy_id"] == scope.policy_id
        assert tuple(entry["autonomy"]["allowed_capabilities"]) == tuple(
            scope.required_action_capabilities
        )
        assert entry["autonomy"]["pilot_ticket_ids"] == list(TRIAGE_NOTE_PILOT_TICKET_IDS)


def test_promotion_never_writes_to_a_ticket_outside_pilot(tmp_path):
    reads = NoteReadStub()
    worker, store, _ = make_worker(tmp_path, [ticket(ticket_id=200003, title="Space Issue")], reads)
    worker.promotion_store = PromotionForTriage(handoff=True)
    actions = NoteActionStub(reads)
    worker.actions = actions
    worker.tick()
    assert store.unsupported_triage(200003)["state"] == "read_only_assessed"
    assert actions.calls == []
    assert store.unsupported_note_delivery(200003) is None
    store.close()


def test_stale_draft_is_not_published_even_with_promotion(tmp_path):
    from datetime import datetime, timezone
    reads = NoteReadStub()
    worker, store, _ = make_worker(tmp_path, [ticket(title="Space Issue")], reads)
    worker.promotion_store = PromotionForTriage()
    actions = NoteActionStub(reads)
    worker.actions = actions
    worker._maybe_publish_unsupported_triage_note(
        ticket(title="Space Issue", version="v2"),
        {"state": "read_only_assessed", "source_version": "v1",
         "ticket_number": ticket().context["ticketNumber"],
         "evidence": {"company_verified": True,
                      "note_draft": "JASON READ-ONLY INVESTIGATION\nNot resolved"}},
        now=datetime.now(timezone.utc),
    )
    assert actions.calls == []
    store.close()


def test_unowned_same_title_note_is_not_overwritten(tmp_path):
    reads = NoteReadStub()
    reads.notes.append({
        "id": 9999, "title": "Jason - Governed Read-Only Investigation",
        "description": "Manual note not owned by pilot",
    })
    worker, store, _ = make_worker(tmp_path, [ticket(title="Space Issue")], reads)
    worker.promotion_store = PromotionForTriage()
    actions = NoteActionStub(reads)
    worker.actions = actions
    worker.tick()
    row = store.unsupported_note_delivery(200001)
    assert row is not None and row["attempts"] == 1
    assert row["last_error"] == "OperationalAutonomyError"
    assert reads.notes[-1]["description"] == "Manual note not owned by pilot"
    assert actions.calls == []
    store.close()


def test_later_handoff_promotion_resumes_after_note_was_already_verified(tmp_path):
    from datetime import datetime, timezone
    from jason_runtime.unsupported_ticket_triage import render_triage_note
    source = ticket(title="Space Issue", queue="Jason")
    reads = NoteReadStub()
    worker, store, _ = make_worker(tmp_path, [source], reads)
    actions = NoteActionStub(reads)
    worker.actions = actions
    worker.promotion_store = PromotionForTriage(handoff=False)
    now = datetime.now(timezone.utc)
    evidence = {"company_verified": True, "ticket_id": 200001}
    evidence["note_draft"] = render_triage_note(
        ticket_number="T20261029.0001", state="needs_device_identity",
        category="general", evidence=evidence, next_step="Associate a verified CI",
    )
    record = {"state": "needs_device_identity", "evidence": evidence,
              "source_version": "v1", "ticket_number": source.context["ticketNumber"]}
    worker._maybe_publish_unsupported_triage_note(source, record, now=now)
    assert [x[1] for x in actions.calls] == ["service.ticket.note.create"]
    assert store.unsupported_handoff_delivery(200001) is None
    # Owner may approve handoff independently after publishing a note.
    worker.promotion_store = PromotionForTriage(handoff=True)
    worker._maybe_publish_unsupported_triage_note(source, record, now=now)
    assert [x[1] for x in actions.calls] == [
        "service.ticket.note.create", "service.ticket.update",
    ]
    assert store.unsupported_handoff_delivery(200001)["state"] == "verified"
    store.close()


def test_later_handoff_denied_when_managed_note_was_edited(tmp_path):
    from datetime import datetime, timezone
    from jason_runtime.unsupported_ticket_triage import render_triage_note
    source = ticket(title="Space Issue", queue="Jason")
    reads = NoteReadStub()
    worker, store, _ = make_worker(tmp_path, [source], reads)
    actions = NoteActionStub(reads)
    worker.actions = actions
    worker.promotion_store = PromotionForTriage(handoff=False)
    now = datetime.now(timezone.utc)
    evidence = {"company_verified": True, "ticket_id": 200001}
    evidence["note_draft"] = render_triage_note(
        ticket_number="T20261029.0001", state="needs_device_identity",
        category="general", evidence=evidence, next_step="Associate a verified CI",
    )
    record = {"state": "needs_device_identity", "evidence": evidence,
              "source_version": "v1", "ticket_number": source.context["ticketNumber"]}
    worker._maybe_publish_unsupported_triage_note(source, record, now=now)
    assert len(actions.calls) == 1
    reads.notes[-1]["description"] = "A technician changed this note"
    worker.promotion_store = PromotionForTriage(handoff=True)
    worker._maybe_publish_unsupported_triage_note(source, record, now=now)
    assert len(actions.calls) == 1
    assert store.unsupported_handoff_delivery(200001)["state"] == "retry_pending"
    assert store.unsupported_handoff_delivery(200001)["last_error"] == "OperationalAutonomyError"
    store.close()


def test_terminal_failed_handoff_does_not_retry_unbounded(tmp_path):
    from datetime import datetime, timezone
    from hashlib import sha256
    from jason_runtime.unsupported_ticket_triage import render_triage_note
    source = ticket(title="Space Issue", queue="Jason")
    reads = NoteReadStub()
    worker, store, _ = make_worker(tmp_path, [source], reads)
    worker.promotion_store = PromotionForTriage(handoff=True)
    actions = NoteActionStub(reads)
    worker.actions = actions
    body = render_triage_note(
        ticket_number="T20261029.0001", state="needs_device_identity",
        category="general", evidence={"company_verified": True},
        next_step="Validate a same-company configuration item",
    )
    fingerprint = sha256(body.encode("utf-8")).hexdigest()
    store.remember_note_fingerprint(
        200001, "unsupported_readonly_triage_note",
        "Jason - Governed Read-Only Investigation", fingerprint,
    )
    store.record_unsupported_handoff_delivery(
        ticket_id=200001, note_fingerprint=fingerprint,
        state="needs_human_review", attempts=3,
        next_due_at="2020-01-01T00:00:00+00:00",
        last_error="OperationalAutonomyError",
    )
    record = {
        "state": "needs_device_identity", "source_version": "v1",
        "ticket_number": source.context["ticketNumber"],
        "evidence": {"company_verified": True, "note_draft": body},
    }
    worker._maybe_publish_unsupported_triage_note(
        source, record, now=datetime.now(timezone.utc),
    )
    assert actions.calls == []
    assert store.unsupported_handoff_delivery(200001)["attempts"] == 3
    store.close()


@pytest.mark.parametrize("title,contact_id,ci_id,expected", [
    ("General account issue", 42, None, "needs_playbook_review"),
    ("Network disconnections and screen timeout settings reverting", 42, None, "needs_diagnostic_evidence"),
    ("Service outage for remote users", None, None, "needs_playbook_review"),
    ("Linux logs cleared", None, None, "needs_security_review"),
    ("Disk space issue", 42, None, "needs_device_identity"),
    ("Windows activation failed", None, None, "needs_device_identity"),
])
def test_optional_ci_never_blocks_non_endpoint_investigation(
        title, contact_id, ci_id, expected):
    calls = []
    def read(capability, args):
        calls.append(capability)
        if capability == "service.ticket.notes.search":
            return {"items": [{"id": 1}]}
        if capability == "service.contact.read":
            return {"item": {"id": 42, "companyID": 777}}
        raise AssertionError("No endpoint access expected: " + capability)
    result = gather(
        ticket_id=200001, company_id=777, configuration_item_id=ci_id,
        ticket_snapshot={"id": 200001, "companyID": 777,
                         "contactID": contact_id, "configurationItemID": ci_id},
        title=title, unsupported_reason="", read=read)
    assert result.state == expected
    assert "service.configuration.read" not in calls
    assert "endpoint.device.read" not in calls
    if contact_id:
        assert result.evidence["contact_verified"] is True


def test_mismatched_contact_company_rejected_before_endpoint_access():
    calls = []
    def read(capability, args):
        calls.append(capability)
        if capability == "service.ticket.notes.search":
            return {"items": []}
        if capability == "service.contact.read":
            return {"item": {"id": 42, "companyID": 999}}
        raise AssertionError(capability)
    with pytest.raises(ValueError, match="contact_identity_unverified"):
        gather(ticket_id=200001, company_id=777, configuration_item_id=None,
               ticket_snapshot={"id": 200001, "companyID": 777, "contactID": 42},
               title="Network disconnect", unsupported_reason="", read=read)
    assert "endpoint.device.read" not in calls



def test_real_ticket_shape_143272_contact_first_no_ci_and_title_hint():
    calls = []
    def read(capability, args):
        calls.append((capability, dict(args)))
        if capability == "service.ticket.notes.search":
            return {"items": [{"id": 30532713, "title": "Jason - Governed Read-Only Investigation"}]}
        if capability == "service.contact.read":
            return {"item": {"id": 30683105, "companyID": 827}}
        if capability == "service.configuration.search":
            assert args == {"company_id": 827, "name": "202315PC14", "page_size": 25}
            return {"items": []}
        raise AssertionError("No endpoint/device actions allowed: " + capability)
    result = gather(
        ticket_id=143272, company_id=827, configuration_item_id=None,
        ticket_snapshot={
            "id": 143272, "companyID": 827, "contactID": 30683105,
            "configurationItemID": None,
            "description": (
                "IT Service Request - Network Connectivity & Computer Sleep Settings. "
                "Computer frequently disconnects from network; the screen goes black "
                "after three minutes. Windows updates revert screen timeout settings."
            ),
        },
        title="202315PC14 -", unsupported_reason="no_promoted_playbook", read=read)
    assert result.category == "user_device_settings"
    assert result.state == "needs_diagnostic_evidence"
    assert result.evidence["investigation_scope"] == "user_device"
    assert result.evidence["contact_verified"] is True
    assert result.evidence["device_title_hint_unverified"] == "202315PC14"
    assert result.evidence["same_company_ci_search_count"] == 0
    assert [cap for cap, _ in calls] == [
        "service.ticket.notes.search", "service.contact.read",
        "service.configuration.search",
    ]
    assert "no ticket CI" in result.next_step
    assert "endpoint.device.read" not in [cap for cap, _ in calls]


@pytest.mark.parametrize("title,description,category", (
    ("Sign-in problem", "User cannot sign in to Microsoft 365", "account_service"),
    ("Print Server -", "DHCP issue on domain controller", "infrastructure_service"),
    ("General assistance", "Please review our accounting application", "general"),
    ("Linux logs cleared", "Server alert", "security_review"),
))
def test_nonendpoint_context_skips_irrelevant_existing_ci(title, description, category):
    calls = []
    def read(cap, args):
        calls.append(cap)
        assert cap == "service.ticket.notes.search"
        return {"items": []}
    result = gather(
        ticket_id=200001, company_id=777, configuration_item_id=1100,
        ticket_snapshot={"id": 200001, "companyID": 777,
                         "description": description, "configurationItemID": 1100},
        title=title, unsupported_reason="", read=read,
    )
    assert result.category == category
    assert result.state == (
        "needs_security_review" if category == "security_review"
        else "needs_playbook_review"
    )
    assert calls == ["service.ticket.notes.search"]


def test_denied_optional_contact_read_does_not_block_user_service_assessment():
    def read(cap, args):
        if cap == "service.ticket.notes.search":
            return {"items": []}
        if cap == "service.contact.read":
            raise PermissionError("INFORMATION_RELEASE_DENIED")
        raise AssertionError(cap)
    result = gather(
        ticket_id=200001, company_id=777, configuration_item_id=None,
        ticket_snapshot={"id": 200001, "companyID": 777,
                         "contactID": 42, "configurationItemID": None,
                         "description": "Microsoft 365 mailbox problem"},
        title="User mail issue", unsupported_reason="", read=read,
    )
    assert result.category == "account_service"
    assert result.state == "needs_playbook_review"
    assert result.evidence["contact_lookup_unavailable"] is True
    assert result.evidence.get("contact_verified") is None


def test_worker_persists_non_escalating_contact_first_triage_for_143272_shape(tmp_path):
    source = ticket(title="202315PC14 -", queue="Jason", status="In Progress")
    source = replace(source, context={
        **source.context,
        "configurationItemID": None,
        "contactID": 42,
        "description": (
            "Customer reports recurring network disconnections. "
            "Screen automatically goes black after three minutes. "
            "Computer sleep settings revert after Windows updates."
        ),
    })
    class ContactFirstRead(ReadStub):
        def execute(self, capability, arguments):
            if capability == "service.configuration.search":
                self.calls.append((capability, dict(arguments)))
                assert arguments["company_id"] == 777
                return {"status": "succeeded", "evidence": {"data": {"items": []}}}
            return super().execute(capability, arguments)

    reads = ContactFirstRead()
    worker, store, actions = make_worker(tmp_path, [source], reads)
    worker.tick()
    record = store.unsupported_triage(200001)
    assert record is not None
    assert record["category"] == "user_device_settings"
    assert record["state"] == "needs_diagnostic_evidence"
    assert record["evidence"]["device_title_hint_unverified"] == "202315PC14"
    assert record["evidence"]["contact_associated"] is True
    assert record["evidence"]["contact_lookup_unavailable"] is True
    assert record["evidence"].get("contact_verified") is None
    assert record["evidence"]["triage_logic_version"] == "read_only_admission_assurance_v5"
    assert store.get(200001) is None
    assert actions.calls == []
    assert [name for name, _ in reads.calls] == [
        "service.ticket.notes.search", "service.configuration.search",
    ]
    assert "needs device identity" not in record["evidence"]["note_draft"].casefold()
    worker.tick()
    assert store.unsupported_triage(200001)["state"] == "needs_diagnostic_evidence"
    store.close()


def test_worker_separate_contact_read_port_verifies_same_company_context(tmp_path):
    source = ticket(title="Account issue", queue="Jason", status="In Progress")
    source = replace(source, context={**source.context,
                                      "contactID": 42, "configurationItemID": None,
                                      "description": "Microsoft 365 mailbox issue"})
    reads = ReadStub()
    class AuthorizedContactPort:
        calls = []
        def execute(self, capability, arguments):
            self.calls.append((capability, dict(arguments)))
            return {"status": "succeeded", "evidence": {"data": {
                "item": {"id": 42, "companyID": 777},
            }}}
    contact = AuthorizedContactPort()
    worker, store, actions = make_worker(tmp_path, [source], reads)
    worker.contact_reads = contact
    worker.tick()
    record = store.unsupported_triage(200001)
    assert record["category"] == "account_service"
    assert record["state"] == "needs_playbook_review"
    assert record["evidence"]["contact_verified"] is True
    assert record["evidence"].get("contact_lookup_unavailable") is None
    assert contact.calls == [("service.contact.read", {"resource_id": 42})]
    assert "service.contact.read" not in [cap for cap, _ in reads.calls]
    assert actions.calls == []
    store.close()


def test_worker_contact_company_conflict_is_not_mislabeled_device_identity(tmp_path):
    source = ticket(title="Account issue", queue="Jason", status="In Progress")
    source = replace(source, context={
        **source.context, "contactID": 42, "configurationItemID": None,
        "description": "Microsoft 365 account question",
    })
    reads = ReadStub()
    class ConflictingContactPort:
        def execute(self, capability, arguments):
            assert capability == "service.contact.read"
            assert arguments == {"resource_id": 42}
            return {"status": "succeeded", "evidence": {"data": {
                "item": {"id": 42, "companyID": 999},
            }}}
    worker, store, actions = make_worker(tmp_path, [source], reads)
    worker.contact_reads = ConflictingContactPort()
    worker.tick()
    record = store.unsupported_triage(200001)
    assert record["state"] == "needs_company_identity"
    assert record["category"] == "account_service"
    assert record["last_error"] == "ValueError"
    assert "contact" in record["next_step"].casefold()
    assert "needs device identity" not in record["evidence"]["note_draft"].casefold()
    assert all(cap not in {"service.configuration.read", "endpoint.device.read"}
               for cap, _ in reads.calls)
    assert actions.calls == []
    store.close()



def test_unpromoted_playbook_does_not_block_readonly_investigation(tmp_path):
    from jason_runtime.autonomy_worker_runtime import EDR_SCOPE
    reads = ReadStub()
    candidate = ticket(title="Microsoft 365 mailbox problem")
    worker, store, actions = make_worker(tmp_path, [candidate], reads)
    worker._match_scope = lambda context: EDR_SCOPE
    worker.tick()
    assessment = store.unsupported_triage(200001)
    assert assessment is not None
    assert assessment["category"] == "account_service"
    assert assessment["state"] == "needs_playbook_promotion"
    assert assessment["evidence"]["remediation_promotion_required"] is True
    assert assessment["evidence"]["admission_reason"] == "playbook_not_promoted"
    assert "not received exact governed promotion" in assessment["next_step"]
    assert "execution NOT authorized" in assessment["evidence"]["note_draft"]
    assert store.get(200001) is None
    assert store.latest_scan().selected == 0
    assert actions.calls == []
    assert [name for name, _ in reads.calls] == ["service.ticket.notes.search"]
    store.close()


def test_assigned_ticket_cannot_publish_even_with_independent_pilot_promotion(tmp_path):
    source = ticket(assigned=True, title="Microsoft 365 mailbox issue")
    reads = NoteReadStub()
    worker, store, _ = make_worker(tmp_path, [source], reads)
    worker.promotion_store = PromotionForTriage()
    actions = NoteActionStub(reads)
    worker.actions = actions
    worker.tick()
    assert store.unsupported_triage(200001) is not None
    assert store.unsupported_note_delivery(200001) is None
    assert actions.calls == []
    store.close()


def test_readonly_intake_has_bounded_independent_default_budget(tmp_path):
    reads = ReadStub()
    candidates = [ticket(ticket_id=200001 + offset,
                         title="Microsoft 365 mailbox problem")
                  for offset in range(9)]
    worker = OperationalAutonomyMaintenance(
        queue_source=Queue(*candidates),
        reads=reads,
        actions=NoMutation(),
        store=SQLiteOperationalWorkStore(tmp_path / "worker.sqlite3"),
        promotion_store=NoPromotion(),
        interval_seconds=30,
        monotonic=iter((0.0, 31.0, 62.0, 93.0)).__next__,
    )
    try:
        assert worker.max_active_work_items == 2
        assert worker.max_unsupported_triage_per_scan == 4
        worker.tick()
        assert sum(worker.store.unsupported_triage(int(i.resource_id)) is not None
                   for i in candidates) == 4
        worker.tick()
        assert sum(worker.store.unsupported_triage(int(i.resource_id)) is not None
                   for i in candidates) == 8
        assert worker.store.latest_scan().selected == 0
        assert worker.store.list_open() == ()
    finally:
        worker.store.close()



def test_unowned_intake_is_assessed_before_equal_priority_assigned_ticket(tmp_path):
    assigned = ticket(ticket_id=200001, assigned=True,
                      title="Microsoft 365 sign-in issue")
    unowned = ticket(ticket_id=200002, assigned=False,
                     title="Microsoft 365 sign-in issue")
    reads = ReadStub()
    worker, store, actions = make_worker(
        tmp_path, [assigned, unowned], reads, max_triage=1)
    worker.tick()
    assert store.unsupported_triage(200001) is None
    assert store.unsupported_triage(200002)["state"] == "needs_playbook_review"
    worker.tick()
    assert store.unsupported_triage(200001)["state"] == "needs_playbook_review"
    assert actions.calls == []
    store.close()
