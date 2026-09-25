from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from autonomous_remediation.playbook_autonomy_approval import (
    SQLitePlaybookAutonomyApprovalStore,
)
from jason_mcp import server


class Audit:
    def __init__(self):
        self.events = []

    def append_authority_audit(self, **kwargs):
        self.events.append(kwargs)


class Grants:
    def __init__(self, records=()):
        self.records = tuple(records)

    def list_for_subject(self, subject_id):
        return self.records


@pytest.fixture
def owner(monkeypatch, tmp_path):
    store = SQLitePlaybookAutonomyApprovalStore(tmp_path / "promotions.sqlite3")
    authority = SimpleNamespace(
        audit=Audit(),
        grants=Grants(),
        approvals=SimpleNamespace(),
    )
    runtime = SimpleNamespace(
        identity_authority=authority,
        capabilities=SimpleNamespace(),
        governed_orchestrator=SimpleNamespace(),
    )
    monkeypatch.setattr(server, "_runtime", lambda: runtime)
    monkeypatch.setattr(server, "_playbook_autonomy_store", lambda: store)
    monkeypatch.setattr(
        server,
        "_authenticated_write_identity",
        lambda: ("person-al", "aot", "entra", None),
    )
    monkeypatch.setattr(
        server,
        "approval_owner_identities",
        lambda: frozenset({"person-al"}),
    )
    yield runtime, store
    store.close()


def test_owner_approval_is_exact_short_lived_and_idempotent(owner):
    runtime, store = owner

    first = server.approve_autonomy_execution_acceptance()
    assert first["status"] == "succeeded"
    assert first["idempotent"] is False
    assert first["playbook_id"] == "autonomy_execution_acceptance"
    assert first["playbook_version"] == "1.0.0"
    assert first["policy_id"] == "playbook-autonomy:autonomy_execution_acceptance"
    assert first["allowed_capabilities"] == ["service.ticket.note.create"]

    record = store.get(first["approval_id"])
    assert record is not None
    assert record.approved_by == "person-al"
    assert record.allowed_capabilities == ("service.ticket.note.create",)
    assert record.expires_at is not None
    remaining = record.expires_at - datetime.now(timezone.utc)
    assert timedelta(minutes=29) < remaining <= timedelta(minutes=30)

    second = server.approve_autonomy_execution_acceptance()
    assert second["status"] == "succeeded"
    assert second["idempotent"] is True
    assert second["approval_id"] == first["approval_id"]

    event_types = [event["event_type"] for event in runtime.identity_authority.audit.events]
    assert event_types == [
        "autonomy.acceptance.promotion.requested",
        "autonomy.acceptance.promotion.created",
    ]


def test_revoke_removes_active_promotion_and_is_idempotent(owner):
    runtime, store = owner

    created = server.approve_autonomy_execution_acceptance()
    revoked = server.revoke_autonomy_execution_acceptance("pilot complete")

    assert revoked["status"] == "succeeded"
    assert revoked["revoked"] is True
    assert revoked["approval_id"] == created["approval_id"]
    assert revoked["reason"] == "pilot complete"
    assert store.find_approved(
        playbook_id="autonomy_execution_acceptance",
        playbook_version="1.0.0",
        policy_id="playbook-autonomy:autonomy_execution_acceptance",
        capability="service.ticket.note.create",
    ) is None

    again = server.revoke_autonomy_execution_acceptance()
    assert again == {
        "status": "succeeded",
        "idempotent": True,
        "revoked": False,
    }


def test_non_owner_cannot_approve_revoke_status_or_run(monkeypatch, tmp_path):
    store = SQLitePlaybookAutonomyApprovalStore(tmp_path / "promotions.sqlite3")
    runtime = SimpleNamespace(
        identity_authority=SimpleNamespace(audit=Audit(), grants=Grants(), approvals=SimpleNamespace()),
        capabilities=SimpleNamespace(),
        governed_orchestrator=SimpleNamespace(),
    )
    monkeypatch.setattr(server, "_runtime", lambda: runtime)
    monkeypatch.setattr(server, "_playbook_autonomy_store", lambda: store)
    monkeypatch.setattr(
        server,
        "_authenticated_write_identity",
        lambda: ("person-tech", "aot", "entra", None),
    )
    monkeypatch.setattr(
        server,
        "approval_owner_identities",
        lambda: frozenset({"person-al"}),
    )

    for result in (
        server.approve_autonomy_execution_acceptance(),
        server.revoke_autonomy_execution_acceptance(),
        server.autonomy_execution_acceptance_status(),
        server.run_autonomy_execution_acceptance(),
    ):
        assert result["status"] == "rejected"
        assert "OWNER_REQUIRED" in result["error_code"]

    store.close()


def test_status_reports_only_exact_acceptance_grants_and_target(owner):
    runtime, store = owner

    permission_observe = SimpleNamespace(value="observe")
    permission_execute = SimpleNamespace(value="execute")
    runtime.identity_authority.grants = Grants(
        (
            SimpleNamespace(
                capability="service.ticket.read",
                grant_id="g-read",
                permission=permission_observe,
                approval_required=False,
                status="active",
                client_id=None,
            ),
            SimpleNamespace(
                capability="service.ticket.note.create",
                grant_id="g-write",
                permission=permission_execute,
                approval_required=True,
                status="active",
                client_id=None,
            ),
            SimpleNamespace(
                capability="automation.component.execute",
                grant_id="g-unrelated",
                permission=permission_execute,
                approval_required=True,
                status="active",
                client_id=None,
            ),
        )
    )

    approved = server.approve_autonomy_execution_acceptance()
    result = server.autonomy_execution_acceptance_status()

    assert result["status"] == "succeeded"
    assert result["workload_principal"] == "jason-autonomy-worker"
    assert set(result["required_grants"]) == {
        "service.ticket.read",
        "service.ticket.note.create",
    }
    assert "automation.component.execute" not in result["required_grants"]
    assert result["promotion"]["approval_id"] == approved["approval_id"]
    assert result["target"] == {
        "ticket_id": 8870,
        "ticket_number": "T20191013.0001",
        "company_id": 1158,
        "company_name": "XYZ Test Company",
    }


def test_run_tool_uses_fixed_acceptance_spec_and_returns_bounded_result(owner, monkeypatch):
    runtime, store = owner
    server.approve_autonomy_execution_acceptance()

    captured = {}

    class FakeFactory:
        def __init__(self, **kwargs):
            captured["factory"] = kwargs

    class FakeReads:
        def __init__(self, **kwargs):
            captured["reads"] = kwargs

    class FakePilot:
        def __init__(self, **kwargs):
            captured["pilot"] = kwargs

        def run_once(self):
            return SimpleNamespace(
                status="succeeded",
                ticket_id=8870,
                ticket_number="T20191013.0001",
                company_id=1158,
                company_name="XYZ Test Company",
                note_title="Jason - Autonomous Execution Acceptance",
                ticket_note_id=77,
                provider="autotask_internal_note",
                correlation_id="corr-test",
                approval_id="approval-test",
                idempotency_key="idem-test",
                readback_verified=True,
                duplicate_write_avoided=False,
            )

    monkeypatch.setattr(server, "AutonomousRequestFactory", FakeFactory)
    monkeypatch.setattr(server, "GovernedAutonomyReadPort", FakeReads)
    monkeypatch.setattr(server, "ControlledAutonomyInternalNotePilot", FakePilot)
    monkeypatch.setattr(server, "_governed_execution_ledger", lambda: SimpleNamespace())

    result = server.run_autonomy_execution_acceptance()

    assert result == {
        "status": "succeeded",
        "pilot_status": "succeeded",
        "ticket_id": 8870,
        "ticket_number": "T20191013.0001",
        "company_id": 1158,
        "company_name": "XYZ Test Company",
        "note_title": "Jason - Autonomous Execution Acceptance",
        "ticket_note_id": 77,
        "provider": "autotask_internal_note",
        "correlation_id": "corr-test",
        "approval_id": "approval-test",
        "idempotency_key": "idem-test",
        "readback_verified": True,
        "duplicate_write_avoided": False,
    }

    spec = captured["pilot"]["spec"]
    assert spec.ticket_id == 8870
    assert spec.expected_ticket_number == "T20191013.0001"
    assert spec.company_id == 1158
    assert spec.expected_company_name == "XYZ Test Company"
    assert spec.playbook_id == "autonomy_execution_acceptance"
    assert spec.playbook_version == "1.0.0"
    assert spec.policy_id == "playbook-autonomy:autonomy_execution_acceptance"
    assert spec.note_title == "Jason - Autonomous Execution Acceptance"
    assert spec.note_body == (
        "Controlled autonomous service-principal acceptance test. "
        "No ticket fields or endpoint state changed."
    )
