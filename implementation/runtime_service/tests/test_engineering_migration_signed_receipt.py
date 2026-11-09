"""Real retained request and durable ledger acceptance, no mocked fingerprints."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import sqlite3

import pytest

from kernel.execution_policy import DataHandlingPolicy, ExecutionBudget
from orchestrator.contracts import OrchestrationMode, OrchestrationRequest
from orchestrator.approval_plan_grants import PlanGrantLedger, VerifiedPlanDecision
from orchestrator.approval_plan_scope import ApprovedPlanScope
from orchestrator.teams_plan_grant_bridge import ServerOwnedPlanProposal
from orchestrator.teams_plan_request_repository import PlanRequestRepository, plan_fingerprint
from jason_runtime.engineering_migration_approval import EngineeringMigrationApprovalError
from jason_runtime.engineering_migration_signed_receipt import require_signed_migration_grant

NOW = datetime(2026, 11, 9, 20, 0, tzinfo=timezone.utc)
APPROVAL = "planapproval-test-valid"
CAPABILITY = "engineering.migration.activate"
ADMIN = "person-entra-c848022de13b445784b0e2f5c00dcaf6"
REGULAR = "person-entra-bee80bdcffb04c50b453c09d4d411f5f"


def fixture(tmp_path, *, altered_scope=None, revoked=False, register_decision=True):
    scope = ApprovedPlanScope(
        plan_id="plan-pmv3-1", organization_id="aot", policy_digest="policy-v1",
        allowed_capabilities=frozenset({CAPABILITY}), allowed_clients=frozenset(),
        max_risk=3, production_allowed=True, expires_at=NOW + timedelta(minutes=15),
    )
    if altered_scope:
        scope = replace(scope, **altered_scope)
    request = OrchestrationRequest(
        execution_id="migration-test", correlation_id="migration-correlation",
        principal_id="aot-owner", organization_id="aot", capability_name=CAPABILITY,
        capability_version="1.0", requested_mode="deterministic",
        orchestration_mode=OrchestrationMode.EXECUTE,
        authority_allowed=False, approval_present=False, risk="critical",
        data_handling=DataHandlingPolicy("internal", False, retention_allowed=True),
        budget=ExecutionBudget(Decimal("0")), permission_mode="execute",
        arguments={
            "candidate_sha": "a" * 40, "rollback_sha": "b" * 40,
            "reviewed_scope_sha256": "c" * 64,
            "continuity_evidence_sha256": "d" * 64,
            "migration_phase": "independent_engineering_lanes",
        },
    )
    fingerprint = plan_fingerprint((request,), scope)
    proposal = ServerOwnedPlanProposal(
        approval_id=APPROVAL, organization_id="aot", client_id=None,
        requester_id="aot-owner", capability=CAPABILITY,
        plan_fingerprint=fingerprint, scope=scope,
    )
    class Proposals:
        def require(self, identifier):
            assert identifier == APPROVAL
            return proposal
    requests = PlanRequestRepository(tmp_path / "requests.sqlite3",
                                     current_policy_digest="policy-v1")
    requests.store(proposal, (request,), now=NOW)
    ledger = PlanGrantLedger(tmp_path / "grants.sqlite3")
    if register_decision:
        ledger.record(scope, VerifiedPlanDecision(
            approval_id=APPROVAL, approver_identity_id=ADMIN,
            authenticated=True, authorized=True, approved=True,
            plan_fingerprint=fingerprint, decided_at=NOW,
        ))
        if revoked:
            ledger.revoke(scope.plan_id, at=NOW + timedelta(seconds=1),
                          reason="privileged approver revoked")
    return Proposals(), requests, ledger


def verify(tmp_path, **options):
    proposals, requests, grants = fixture(tmp_path, **options)
    return require_signed_migration_grant(
        approval_id=APPROVAL, proposals=proposals, requests=requests,
        grants=grants, now=NOW + timedelta(minutes=1),
        privileged_approver_identity_id=ADMIN,
    )


def test_real_persisted_plan_and_signed_grant_bind_exact_sha_without_release_authority(tmp_path):
    result = verify(tmp_path)
    assert result.candidate_sha == "a" * 40
    assert result.rollback_sha == "b" * 40
    assert len(result.signed_plan_fingerprint) == 64
    assert not result.native_release_authorized


def test_unsigned_or_missing_grant_denied(tmp_path):
    with pytest.raises(EngineeringMigrationApprovalError):
        verify(tmp_path, register_decision=False)


def test_revoked_grant_denied(tmp_path):
    with pytest.raises(EngineeringMigrationApprovalError):
        verify(tmp_path, revoked=True)


def test_wrong_capability_in_plan_denied(tmp_path):
    with pytest.raises(EngineeringMigrationApprovalError):
        verify(tmp_path, altered_scope={
            "allowed_capabilities": frozenset({"service.ticket.update"})
        })


def test_wrong_approval_id_fails_closed(tmp_path):
    proposals, requests, grants = fixture(tmp_path)
    with pytest.raises(EngineeringMigrationApprovalError):
        require_signed_migration_grant(
            approval_id="chat-approved", proposals=proposals, requests=requests,
            grants=grants, now=NOW, privileged_approver_identity_id=ADMIN,
        )


def test_regular_account_cannot_satisfy_privileged_approval(tmp_path):
    proposals, requests, grants = fixture(tmp_path)
    with pytest.raises(EngineeringMigrationApprovalError):
        require_signed_migration_grant(
            approval_id=APPROVAL, proposals=proposals, requests=requests,
            grants=grants, now=NOW + timedelta(minutes=1),
            privileged_approver_identity_id=REGULAR,
        )


def test_missing_trusted_admin_identity_denied(tmp_path):
    proposals, requests, grants = fixture(tmp_path)
    with pytest.raises(EngineeringMigrationApprovalError):
        require_signed_migration_grant(
            approval_id=APPROVAL, proposals=proposals, requests=requests,
            grants=grants, now=NOW, privileged_approver_identity_id="",
        )


def test_expired_signed_grant_denied(tmp_path):
    proposals, requests, grants = fixture(tmp_path)
    with pytest.raises(EngineeringMigrationApprovalError):
        require_signed_migration_grant(
            approval_id=APPROVAL, proposals=proposals, requests=requests,
            grants=grants, now=NOW + timedelta(minutes=16),
            privileged_approver_identity_id=ADMIN,
        )


def test_mutated_retained_scope_fails_real_fingerprint_readback(tmp_path):
    proposals, requests, grants = fixture(tmp_path)
    with sqlite3.connect(requests.path) as db:
        material = json.loads(db.execute(
            "SELECT material_json FROM universal_plan_requests"
        ).fetchone()[0])
        material["requests"][0]["arguments"]["candidate_sha"] = "e" * 40
        db.execute("UPDATE universal_plan_requests SET material_json=?",
                   (json.dumps(material),))
    with pytest.raises(EngineeringMigrationApprovalError):
        require_signed_migration_grant(
            approval_id=APPROVAL, proposals=proposals, requests=requests,
            grants=grants, now=NOW + timedelta(minutes=1),
            privileged_approver_identity_id=ADMIN,
        )
