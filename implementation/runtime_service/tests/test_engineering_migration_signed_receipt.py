"""Real retained plan, signed ledger and protected V4 administrator policy tests."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
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
from jason_runtime.engineering_migration_signed_receipt import require_signed_migration_grant as native_signed_migration_grant

def require_signed_migration_grant(*, protected_approver_policy_path, **kwargs):
    # Only tests may replace the canonical root policy path. The production API
    # does not accept a caller-selected path or untrusted approver ID.
    with patch("jason_runtime.engineering_migration_signed_receipt.PROTECTED_POLICY_PATH",
               protected_approver_policy_path):
        return native_signed_migration_grant(**kwargs)


NOW = datetime(2026, 11, 9, 20, 0, tzinfo=timezone.utc)
APPROVAL = "planapproval-test-valid"
CAPABILITY = "engineering.migration.activate"
ADMIN = "person-entra-c848022de13b445784b0e2f5c00dcaf6"
REGULAR = "person-entra-bee80bdcffb04c50b453c09d4d411f5f"


def fixture(tmp_path, *, altered_scope=None, revoked=False, register_decision=True,
            signed_actor=ADMIN, bound_actor=ADMIN, policy_mode="4.0"):
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
            approval_id=APPROVAL, approver_identity_id=signed_actor,
            authenticated=True, authorized=True, approved=True,
            plan_fingerprint=fingerprint, decided_at=NOW,
        ))
        if revoked:
            ledger.revoke(scope.plan_id, at=NOW + timedelta(seconds=1),
                          reason="privileged approver revoked")

    policy_path = tmp_path / "release-policy.json"
    source_policy = Path(__file__).resolve().parents[3] / "config" / "mobile-release-approval-policy.json"
    policy_data = json.loads(source_policy.read_text())
    if policy_mode != "4.0":
        policy_data["schema_version"] = policy_mode
    policy_path.write_text(json.dumps(policy_data))
    policy_path.chmod(0o600)

    class Bindings:
        def find(self, *, microsoft_tenant_id, microsoft_object_id):
            assert microsoft_tenant_id == "f7054323-d52b-4863-8c2f-1898f0b6077c"
            assert microsoft_object_id == "c848022d-e13b-4457-84b0-e2f5c00dcaf6"
            return (SimpleNamespace(jason_identity_id=bound_actor, status="active")
                    if bound_actor is not None else None)

    return Proposals(), requests, ledger, policy_path, Bindings()


def require(tmp_path, **options):
    proposals, requests, ledger, policy, bindings = fixture(tmp_path, **options)
    return require_signed_migration_grant(
        approval_id=APPROVAL, proposals=proposals, requests=requests,
        grants=ledger, now=NOW + timedelta(minutes=1),
        protected_approver_policy_path=policy,
        active_identity_bindings=bindings,
    )


def test_real_persisted_plan_grant_and_admin_binding_not_native_release_authority(tmp_path):
    result = require(tmp_path)
    assert result.candidate_sha == "a" * 40
    assert result.rollback_sha == "b" * 40
    assert len(result.signed_plan_fingerprint) == 64
    assert not result.native_release_authorized


def test_missing_grant_rejected(tmp_path):
    with pytest.raises(EngineeringMigrationApprovalError):
        require(tmp_path, register_decision=False)


def test_revoked_grant_rejected(tmp_path):
    with pytest.raises(EngineeringMigrationApprovalError):
        require(tmp_path, revoked=True)


def test_wrong_capability_rejected_by_canonical_store(tmp_path):
    with pytest.raises(PermissionError, match="plan capabilities must exactly match"):
        require(tmp_path, altered_scope={
            "allowed_capabilities": frozenset({"service.ticket.update"})
        })


def test_regular_signed_account_cannot_pass_admin_policy(tmp_path):
    with pytest.raises(EngineeringMigrationApprovalError):
        require(tmp_path, signed_actor=REGULAR)


def test_missing_admin_binding_fails_closed(tmp_path):
    with pytest.raises(EngineeringMigrationApprovalError):
        require(tmp_path, bound_actor=None)


def test_wrong_policy_version_fails_closed(tmp_path):
    with pytest.raises((EngineeringMigrationApprovalError, PermissionError)):
        require(tmp_path, policy_mode="3.0")


def test_expired_signed_grant_denied(tmp_path):
    proposals, requests, grants, policy, bindings = fixture(tmp_path)
    with pytest.raises(EngineeringMigrationApprovalError):
        require_signed_migration_grant(
            approval_id=APPROVAL, proposals=proposals, requests=requests,
            grants=grants, now=NOW + timedelta(minutes=16),
            protected_approver_policy_path=policy,
            active_identity_bindings=bindings,
        )


def test_fake_chat_approval_denied(tmp_path):
    proposals, requests, grants, policy, bindings = fixture(tmp_path)
    with pytest.raises(EngineeringMigrationApprovalError):
        require_signed_migration_grant(
            approval_id="chat-approved", proposals=proposals, requests=requests,
            grants=grants, now=NOW,
            protected_approver_policy_path=policy,
            active_identity_bindings=bindings,
        )


def test_retained_request_tampering_is_detected_without_fingerprint_mock(tmp_path):
    proposals, requests, grants, policy, bindings = fixture(tmp_path)
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
            protected_approver_policy_path=policy,
            active_identity_bindings=bindings,
        )


def test_world_readable_policy_is_denied(tmp_path):
    proposals, requests, grants, policy, bindings = fixture(tmp_path)
    policy.chmod(0o644)
    with pytest.raises((EngineeringMigrationApprovalError, PermissionError)):
        require_signed_migration_grant(
            approval_id=APPROVAL, proposals=proposals, requests=requests,
            grants=grants, now=NOW + timedelta(minutes=1),
            protected_approver_policy_path=policy,
            active_identity_bindings=bindings,
        )
