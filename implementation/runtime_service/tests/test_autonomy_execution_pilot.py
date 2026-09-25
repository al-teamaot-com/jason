from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from autonomous_remediation.playbook_autonomy_approval import (
    SQLitePlaybookAutonomyApprovalStore,
)
from jason_runtime.autonomy_execution_pilot import (
    AutonomyExecutionPilotError,
    AutonomyInternalNotePilotSpec,
    ControlledAutonomyInternalNotePilot,
)


@dataclass
class _Request:
    approval_id: str = "approval-exact"
    idempotency_key: str = "idem-exact"


class _RequestFactory:
    def __init__(self):
        self.calls = []

    def build(self, **kwargs):
        self.calls.append(kwargs)
        return _Request()


class _Status:
    value = "succeeded"


class _Result:
    status = _Status()
    output = {
        "jasonVerification": {
            "readbackVerified": True,
            "ticketNoteId": 77,
        }
    }
    provider_id = "autotask_internal_note"
    correlation_id = "corr-pilot"


class _Orchestrator:
    def __init__(self):
        self.calls = []

    def execute(self, request):
        self.calls.append(request)
        return _Result()


class _Reads:
    def __init__(self, *, existing_notes=None, company_name="XYZ Test Company", ticket_number="T20191013.0001"):
        self.existing_notes = list(existing_notes or [])
        self.company_name = company_name
        self.ticket_number = ticket_number
        self.calls = []
        self.post_write_note = None

    def execute(self, capability, arguments):
        self.calls.append((capability, dict(arguments)))
        if capability == "service.ticket.read":
            return self._result({
                "items": [{
                    "id": 8870,
                    "ticketNumber": self.ticket_number,
                    "companyID": 1158,
                }]
            })
        if capability == "service.company.read":
            return self._result({
                "item": {
                    "id": 1158,
                    "companyName": self.company_name,
                }
            })
        if capability == "service.ticket.notes.search":
            items = list(self.existing_notes)
            if self.post_write_note is not None:
                items.append(dict(self.post_write_note))
            return self._result({"items": items})
        raise AssertionError(capability)

    @staticmethod
    def _result(data):
        return {
            "status": "succeeded",
            "evidence": {"data": data},
        }


def _spec():
    return AutonomyInternalNotePilotSpec(
        ticket_id=8870,
        expected_ticket_number="T20191013.0001",
        company_id=1158,
        expected_company_name="XYZ Test Company",
        playbook_id="autonomy_execution_acceptance",
        playbook_version="1.0.0",
        policy_id="playbook-autonomy:autonomy_execution_acceptance",
        note_title="Jason - Autonomous Execution Acceptance",
        note_body=(
            "Controlled autonomous service-principal acceptance test. "
            "No ticket fields or endpoint state changed."
        ),
    )


def _promote(store):
    record = store.new(
        playbook_id="autonomy_execution_acceptance",
        playbook_version="1.0.0",
        policy_id="playbook-autonomy:autonomy_execution_acceptance",
        allowed_capabilities=["service.ticket.note.create"],
        approved_by="person-al",
    )
    store.put(record)
    return record


def test_missing_promotion_fails_before_mutation(tmp_path):
    store = SQLitePlaybookAutonomyApprovalStore(tmp_path / "promotions.sqlite3")
    reads = _Reads()
    factory = _RequestFactory()
    orchestrator = _Orchestrator()
    pilot = ControlledAutonomyInternalNotePilot(
        spec=_spec(),
        reads=reads,
        request_factory=factory,
        orchestrator=orchestrator,
        promotion_store=store,
    )

    with pytest.raises(AutonomyExecutionPilotError, match="promotion"):
        pilot.run_once()

    assert factory.calls == []
    assert orchestrator.calls == []
    store.close()


def test_ticket_or_company_identity_drift_fails_closed(tmp_path):
    store = SQLitePlaybookAutonomyApprovalStore(tmp_path / "promotions.sqlite3")
    _promote(store)

    for reads in (
        _Reads(ticket_number="T20990101.9999"),
        _Reads(company_name="Not XYZ"),
    ):
        factory = _RequestFactory()
        orchestrator = _Orchestrator()
        pilot = ControlledAutonomyInternalNotePilot(
            spec=_spec(),
            reads=reads,
            request_factory=factory,
            orchestrator=orchestrator,
            promotion_store=store,
        )
        with pytest.raises(AutonomyExecutionPilotError):
            pilot.run_once()
        assert factory.calls == []
        assert orchestrator.calls == []

    store.close()


def test_existing_exact_marker_avoids_duplicate_write(tmp_path):
    spec = _spec()
    existing = {
        "id": 55,
        "title": spec.note_title,
        "description": spec.note_body,
        "noteType": 3,
        "publish": 1,
    }
    store = SQLitePlaybookAutonomyApprovalStore(tmp_path / "promotions.sqlite3")
    _promote(store)
    reads = _Reads(existing_notes=[existing])
    factory = _RequestFactory()
    orchestrator = _Orchestrator()

    result = ControlledAutonomyInternalNotePilot(
        spec=spec,
        reads=reads,
        request_factory=factory,
        orchestrator=orchestrator,
        promotion_store=store,
    ).run_once()

    assert result.status == "already_verified"
    assert result.ticket_note_id == 55
    assert result.duplicate_write_avoided is True
    assert factory.calls == []
    assert orchestrator.calls == []
    store.close()


def test_success_requires_exact_promotion_and_independent_post_read(tmp_path):
    spec = _spec()
    store = SQLitePlaybookAutonomyApprovalStore(tmp_path / "promotions.sqlite3")
    promotion = _promote(store)
    reads = _Reads()
    factory = _RequestFactory()
    orchestrator = _Orchestrator()

    original_execute = orchestrator.execute

    def execute_and_expose_note(request):
        result = original_execute(request)
        reads.post_write_note = {
            "id": 77,
            "title": spec.note_title,
            "description": spec.note_body,
            "noteType": 3,
            "publish": 1,
        }
        return result

    orchestrator.execute = execute_and_expose_note

    result = ControlledAutonomyInternalNotePilot(
        spec=spec,
        reads=reads,
        request_factory=factory,
        orchestrator=orchestrator,
        promotion_store=store,
    ).run_once()

    assert result.status == "succeeded"
    assert result.ticket_id == 8870
    assert result.ticket_note_id == 77
    assert result.readback_verified is True
    assert result.duplicate_write_avoided is False
    assert len(orchestrator.calls) == 1
    assert len(factory.calls) == 1

    call = factory.calls[0]
    assert call["capability_name"] == "service.ticket.note.create"
    assert call["arguments"] == {
        "payload": {
            "ticketID": 8870,
            "description": spec.note_body,
            "noteType": 3,
            "publish": 1,
            "title": spec.note_title,
        }
    }
    assert call["standing_policy"].promotion_approval_id == promotion.approval_id

    note_reads = [
        c for c in reads.calls if c[0] == "service.ticket.notes.search"
    ]
    assert len(note_reads) == 2
    store.close()


def test_duplicate_marker_records_fail_closed(tmp_path):
    spec = _spec()
    duplicate = {
        "id": 55,
        "title": spec.note_title,
        "description": spec.note_body,
        "noteType": 3,
        "publish": 1,
    }
    store = SQLitePlaybookAutonomyApprovalStore(tmp_path / "promotions.sqlite3")
    _promote(store)
    pilot = ControlledAutonomyInternalNotePilot(
        spec=spec,
        reads=_Reads(existing_notes=[duplicate, {**duplicate, "id": 56}]),
        request_factory=_RequestFactory(),
        orchestrator=_Orchestrator(),
        promotion_store=store,
    )

    with pytest.raises(AutonomyExecutionPilotError, match="duplicated"):
        pilot.run_once()
    store.close()
