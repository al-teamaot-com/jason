"""JSON instruction to existing governed action-port source-only integration.

This proves exact owner promotion and request binding on the *existing*
Central Orchestrator action gateway with fully mocked output. It does not
activate the migration candidate, call Datto/Autotask, or verify full parity.
"""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from autonomous_remediation.playbook_autonomy_approval import (
    PlaybookAutonomyApproval, SQLitePlaybookAutonomyApprovalStore,
)
from autonomous_remediation.playbook_document import validate_playbook_document
from autonomous_remediation.playbook_runtime import JsonPlaybookInterpreter
from jason_runtime.autonomy_worker_runtime import (
    GovernedAutonomyActionPort, OperationalAutonomyError, PlaybookScope,
)

ROOT = Path(__file__).resolve().parents[3]
CANDIDATE = ROOT / "docs/playbooks/json/migration/candidates/unsupported_triage_human_review.v1.json"
NOW = datetime.now(timezone.utc)
FACTS = {
    "ticket_id": 143305,
    "unique_current_ticket": True,
    "company_identity_exact": True,
    "owned_by_jason": True,
    "current_queue": "Jason",
    "current_status": "In Progress",
    "source_snapshot_unchanged": True,
    "review_reason": "needs_human_review",
    "internal_note_readback_verified": True,
    "exact_handoff_promotion_verified": True,
}


class RequestFactory:
    def __init__(self):
        self.calls = []

    def build(self, **kwargs):
        self.calls.append(dict(kwargs))
        return SimpleNamespace(
            approval_id="synthetic-mutation-approval",
            correlation_id="synthetic-json-plan",
            client_id=kwargs.get("client_id"),
            capability_name=kwargs["capability_name"],
            arguments=kwargs["arguments"],
            standing_policy=kwargs["standing_policy"],
        )


class SyntheticCentralOrchestrator:
    def __init__(self, *, verified=True, status="succeeded"):
        self.calls = []
        self.verified = verified
        self.status = status

    def execute(self, request):
        self.calls.append(request)
        assert request.capability_name == "service.ticket.update"
        assert request.arguments == {
            "payload": {"id": 143305, "queueID": "Help Desk I",
                        "status": "Human Review"}
        }
        assert request.standing_policy.playbook_id == "unsupported_triage_human_review"
        assert request.standing_policy.playbook_version == "1.0.0-migration.1"
        assert request.standing_policy.policy_id == (
            "playbook-autonomy:unsupported_triage_human_review"
        )
        assert request.client_id is None  # Existing worker action-port contract.
        return SimpleNamespace(
            status=SimpleNamespace(value=self.status),
            error_code="PROVIDER_FAILURE" if self.status != "succeeded" else None,
            reason_codes=("synthetic-denial",) if self.status != "succeeded" else (),
            output={"data": {"jasonVerification": {
                "readbackVerified": self.verified,
                "verifiedFields": ["queueID", "status"] if self.verified else [],
            }}},
        )


def setup(tmp_path, *, promoted=True, approved_version="1.0.0-migration.1",
          expired=False, result_status="succeeded", readback=True):
    doc = validate_playbook_document(json.loads(CANDIDATE.read_text()))
    instruction = JsonPlaybookInterpreter(doc).instruction(
        step_id="pilot_gate", facts=FACTS)
    assert instruction.step_id == "handoff_update"
    assert instruction.approval_classification == "modifying"
    assert instruction.approval_required is True
    store = SQLitePlaybookAutonomyApprovalStore(tmp_path / "synthetic-owner-scope.sqlite3")
    scope = PlaybookScope(
        playbook_id=doc.playbook_id,
        playbook_version=doc.version,
        policy_id=f"playbook-autonomy:{doc.playbook_id}",
        required_action_capabilities=(instruction.capability,),
    )
    if promoted:
        store.put(PlaybookAutonomyApproval(
            approval_id="fixture-only-not-a-real-owner-approval",
            playbook_id=doc.playbook_id,
            playbook_version=approved_version,
            policy_id=scope.policy_id,
            allowed_capabilities=(instruction.capability,),
            approved_by="synthetic-source-test",
            approved_at=NOW - timedelta(hours=3),
            expires_at=NOW - timedelta(hours=1) if expired else NOW + timedelta(hours=1),
        ))
    factory = RequestFactory()
    orchestrator = SyntheticCentralOrchestrator(
        verified=readback, status=result_status,
    )
    gateway = GovernedAutonomyActionPort(
        request_factory=factory, orchestrator=orchestrator,
        promotion_store=store,
    )
    return instruction, scope, gateway, factory, orchestrator, store


def test_exact_json_action_passes_existing_governed_port_with_fixture_promotion(tmp_path):
    instruction, scope, gateway, factory, orchestrator, store = setup(tmp_path)
    try:
        result = gateway.execute(scope, instruction.capability, instruction.arguments)
        verification = result["data"]["jasonVerification"]
        assert verification["readbackVerified"] is True
        assert set(verification["verifiedFields"]) >= {"queueID", "status"}
        assert len(factory.calls) == 1
        assert len(orchestrator.calls) == 1
        assert factory.calls[0]["standing_policy"].promotion_approval_id == (
            "fixture-only-not-a-real-owner-approval"
        )
    finally:
        store.close()


@pytest.mark.parametrize("kind", ["missing", "wrong_version", "expired"])
def test_missing_wrong_version_or_expired_owner_authority_fails_before_execution(tmp_path, kind):
    instruction, scope, gateway, factory, orchestrator, store = setup(
        tmp_path, promoted=kind != "missing",
        approved_version="1.0.0" if kind == "wrong_version" else "1.0.0-migration.1",
        expired=kind == "expired",
    )
    try:
        with pytest.raises(OperationalAutonomyError, match="lacks exact durable owner promotion"):
            gateway.execute(scope, instruction.capability, instruction.arguments)
        assert factory.calls == []
        assert orchestrator.calls == []
    finally:
        store.close()


def test_governed_provider_failure_is_not_treated_as_success(tmp_path):
    instruction, scope, gateway, factory, orchestrator, store = setup(
        tmp_path, result_status="denied")
    try:
        with pytest.raises(OperationalAutonomyError, match="PROVIDER_FAILURE"):
            gateway.execute(scope, instruction.capability, instruction.arguments)
        assert len(orchestrator.calls) == 1
    finally:
        store.close()


def test_provider_succeeded_but_incomplete_field_readback_is_not_acceptance(tmp_path):
    instruction, scope, gateway, factory, orchestrator, store = setup(
        tmp_path, readback=False)
    try:
        result = gateway.execute(scope, instruction.capability, instruction.arguments)
        assert result["data"]["jasonVerification"]["readbackVerified"] is False
        # Existing gateway returns an action result; the JSON runtime's
        # independent verification gate must inspect both queue and status.
        assert not result["data"]["jasonVerification"]["verifiedFields"]
        assert len(orchestrator.calls) == 1
    finally:
        store.close()
