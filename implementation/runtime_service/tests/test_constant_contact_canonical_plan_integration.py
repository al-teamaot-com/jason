"""Integration: real Jason plan storage + real verified-grant ledger, no Teams mock."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import sqlite3
import json

import pytest

from connectors.constant_contact.import_authorization import (
    ExactImportIntent, ImportAuthorizationError,
)
from kernel.execution_policy import DataHandlingPolicy, ExecutionBudget
from orchestrator.approval_plan_grants import (
    PlanGrantLedger, VerifiedPlanDecision,
)
from orchestrator.approval_plan_scope import ApprovedPlanScope
from orchestrator.contracts import OrchestrationMode, OrchestrationRequest
from orchestrator.teams_plan_grant_bridge import ServerOwnedPlanProposal
from orchestrator.teams_plan_proposal_repository import PlanProposalRepository
from orchestrator.teams_plan_request_repository import (
    PlanRequestRepository, plan_fingerprint,
)
from jason_runtime.constant_contact_teams_approval import ExistingVerifiedPlanGrantAdapter

NOW = datetime(2026, 11, 11, 18, 0, tzinfo=timezone.utc)
APPROVAL_ID = "planapproval-integration-verified"
WORK_ID = "trusted-bound-work-record-123456789"
LIST_ID = "11111111-2222-3333-4444-555555555555"


def fixture(tmp_path):
    db = tmp_path / "original-plans.sqlite3"
    i = ExactImportIntent(
        "a" * 64, "b" * 64, "c" * 64, "d" * 64, (LIST_ID,), 1,
    )
    args = {
        "work_id": WORK_ID, "intent_digest": i.digest(),
        "account_binding_sha256": i.account_binding_sha256,
        "specification_sha256": i.specification_sha256,
        "preview_digest": i.preview_digest,
        "suppression_receipt_sha256": i.suppression_receipt_sha256,
        "list_ids": [LIST_ID], "contact_count": 1,
    }
    original = OrchestrationRequest(
        execution_id="cc-import-request-1",
        correlation_id="cc-import-correlation-1",
        principal_id="aot-owner",
        organization_id="aot",
        capability_name="marketing.contact.import",
        capability_version="1.0",
        requested_mode="deterministic",
        orchestration_mode=OrchestrationMode.EXECUTE,
        authority_allowed=False,
        approval_present=False,
        risk="high",
        data_handling=DataHandlingPolicy(
            "confidential", False, retention_allowed=True,
        ),
        budget=ExecutionBudget(Decimal("0")),
        arguments=args,
        permission_mode="execute",
    )
    scope = ApprovedPlanScope(
        plan_id="plan-" + APPROVAL_ID,
        organization_id="aot", policy_digest="policy-current",
        allowed_capabilities=frozenset({"marketing.contact.import"}),
        allowed_clients=frozenset(), max_risk=2,
        production_allowed=True, expires_at=NOW + timedelta(minutes=20),
    )
    fp = plan_fingerprint((original,), scope)
    assert fp != i.digest()
    p = ServerOwnedPlanProposal(
        APPROVAL_ID, "aot", None, "aot-owner",
        "marketing.contact.import", fp, scope,
    )
    request_store = PlanRequestRepository(
        db, current_policy_digest="policy-current",
    )
    request_store.store(p, (original,), now=NOW)
    proposals = PlanProposalRepository(db)
    proposals.store(p)
    grants = PlanGrantLedger(db)
    grants.record(scope, VerifiedPlanDecision(
        approval_id=APPROVAL_ID,
        approver_identity_id="verified-owner-identity",
        authenticated=True, authorized=True, approved=True,
        plan_fingerprint=fp, decided_at=NOW,
    ))
    adapter = ExistingVerifiedPlanGrantAdapter(
        ledger=grants, proposals=proposals, requests=request_store,
        server_owned_approval_id=APPROVAL_ID,
        server_owned_work_id=WORK_ID,
        clock=lambda: NOW + timedelta(minutes=1),
    )
    return adapter, i, grants, db


def test_original_immutable_plan_and_real_signed_grant_work_together(tmp_path):
    adapter, intent, ledger, _ = fixture(tmp_path)
    adapter.require_exact_signed_approval(
        requester_id="aot-owner", intent=intent,
    )
    ledger.revoke(
        "plan-" + APPROVAL_ID, at=NOW + timedelta(minutes=1),
        reason="Owner withdrew consent",
    )
    with pytest.raises(ImportAuthorizationError, match="revoked"):
        adapter.require_exact_signed_approval(
            requester_id="aot-owner", intent=intent,
        )


def test_tampering_original_request_invalidates_real_canonical_signature(tmp_path):
    adapter, intent, _, db = fixture(tmp_path)
    with sqlite3.connect(db) as conn:
        row = conn.execute(
            "SELECT material_json FROM universal_plan_requests WHERE approval_id=?",
            (APPROVAL_ID,),
        ).fetchone()
        material = json.loads(row[0])
        material["requests"][0]["arguments"]["contact_count"] = 4
        conn.execute(
            "UPDATE universal_plan_requests SET material_json=? WHERE approval_id=?",
            (json.dumps(material), APPROVAL_ID),
        )
    with pytest.raises(ImportAuthorizationError, match="missing"):
        adapter.require_exact_signed_approval(
            requester_id="aot-owner", intent=intent,
        )


def test_changed_import_target_does_not_inherit_canonical_grant(tmp_path):
    adapter, intent, _, _ = fixture(tmp_path)
    with pytest.raises(ImportAuthorizationError, match="mismatch"):
        adapter.require_exact_signed_approval(
            requester_id="aot-owner",
            intent=replace(
                intent,
                list_ids=("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",),
            ),
        )
