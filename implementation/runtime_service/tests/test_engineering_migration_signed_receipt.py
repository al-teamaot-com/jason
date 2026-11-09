from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from orchestrator.approval_plan_grants import PlanGrantLedger, VerifiedPlanDecision
from orchestrator.approval_plan_scope import ApprovedPlanScope
from orchestrator.teams_plan_grant_bridge import ServerOwnedPlanProposal
from jason_runtime.engineering_migration_approval import EngineeringMigrationApprovalError
from jason_runtime.engineering_migration_signed_receipt import require_signed_migration_grant

NOW = datetime(2026, 11, 9, 20, 0, tzinfo=timezone.utc)
APPROVAL = "planapproval-test-valid"
FINGERPRINT = "f" * 64
CAPABILITY = "engineering.migration.activate"


def fixture(tmp_path, *, altered_scope=None, revoked=False, register_decision=True):
    scope = ApprovedPlanScope(
        plan_id="plan-pmv3-1", organization_id="aot", policy_digest="policy-v1",
        allowed_capabilities=frozenset({CAPABILITY}), allowed_clients=frozenset(),
        max_risk=3, production_allowed=True, expires_at=NOW + timedelta(minutes=15),
    )
    if altered_scope:
        scope = replace(scope, **altered_scope)
    proposal = ServerOwnedPlanProposal(
        approval_id=APPROVAL, organization_id="aot", client_id=None,
        requester_id="aot-owner", capability=CAPABILITY,
        plan_fingerprint=FINGERPRINT, scope=scope,
    )
    request = SimpleNamespace(
        organization_id="aot", client_id=None, capability_name=CAPABILITY,
        capability_version="1.0", permission_mode="execute",
        requested_mode="deterministic", approval_present=False, authority_allowed=False,
        orchestration_mode=__import__("orchestrator.contracts", fromlist=["OrchestrationMode"]).OrchestrationMode.EXECUTE,
        principal_id="aot-owner",
        arguments={
            "candidate_sha": "a"*40, "rollback_sha": "b"*40,
            "reviewed_scope_sha256": "c"*64,
            "continuity_evidence_sha256": "d"*64,
            "migration_phase": "independent_engineering_lanes",
        },
    )
    class Proposals:
        def require(self, identifier):
            assert identifier == APPROVAL
            return proposal
    class Requests:
        def verify_proposal(self, proposal):
            assert proposal.approval_id == APPROVAL
        def steps(self, identifier):
            assert identifier == APPROVAL
            return (request,)
    ledger = PlanGrantLedger(tmp_path / "plans.sqlite3")
    if register_decision:
        ledger.record(scope, VerifiedPlanDecision(
            approval_id=APPROVAL, approver_identity_id="trusted-owner",
            authenticated=True, authorized=True, approved=True,
            plan_fingerprint=FINGERPRINT, decided_at=NOW,
        ))
        if revoked:
            ledger.revoke(scope.plan_id, at=NOW + timedelta(seconds=1), reason="owner revoked")
    return Proposals(), Requests(), ledger


def verify(tmp_path, **options):
    proposals, requests, grants = fixture(tmp_path, **options)
    with patch("jason_runtime.engineering_migration_signed_receipt.plan_fingerprint",
               return_value=FINGERPRINT):
        return require_signed_migration_grant(
            approval_id=APPROVAL, proposals=proposals, requests=requests,
            grants=grants, now=NOW + timedelta(minutes=1),
        )


def test_signed_existing_ledger_grant_binds_exact_sha_without_deployment_authority(tmp_path):
    result = verify(tmp_path)
    assert result.candidate_sha == "a"*40
    assert result.rollback_sha == "b"*40
    assert not result.native_release_authorized


def test_unsigned_or_missing_grant_denied(tmp_path):
    with pytest.raises(EngineeringMigrationApprovalError):
        verify(tmp_path, register_decision=False)


def test_revoked_grant_denied(tmp_path):
    with pytest.raises(EngineeringMigrationApprovalError):
        verify(tmp_path, revoked=True)


def test_wrong_capability_in_plan_denied(tmp_path):
    with pytest.raises(EngineeringMigrationApprovalError):
        verify(tmp_path, altered_scope={"allowed_capabilities": frozenset({"service.ticket.update"})})


def test_wrong_approval_id_fails_closed(tmp_path):
    proposals, requests, grants = fixture(tmp_path)
    with pytest.raises(EngineeringMigrationApprovalError):
        require_signed_migration_grant(
            approval_id="chat-approved", proposals=proposals, requests=requests,
            grants=grants, now=NOW,
        )
