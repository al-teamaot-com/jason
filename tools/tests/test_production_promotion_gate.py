from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

from tools.production_promotion_gate import (
    evaluate_production_promotion,
    promotion_plan_sha256,
)


NOW = datetime(2026, 10, 2, 14, 0, tzinfo=timezone.utc)
OWNER = "owner:al"


def _identity(source: str, digest_char: str = "a"):
    return {
        "release_version": "1.0.0",
        "source_sha": source,
        "artifact_digest": "sha256:" + digest_char * 64,
        "configuration_revision": "cfg-1",
        "policy_revision": "policy-1",
        "playbook_revision": "playbook-1",
        "schema_revision": "schema-1",
    }


def _plan():
    return {
        "schema_version": "1.0",
        "promotion_id": "promotion-1",
        "target_environment": "production",
        "current": _identity("1" * 40, "1"),
        "target": _identity("2" * 40, "2"),
        "affected_components": ["jason-runtime"],
        "configuration_changes": [],
        "policy_changes": [],
        "migrations": [],
        "expected_service_impact": "none expected",
        "preflight_evidence": ["preflight-1"],
        "verification": {"checks": ["deployment-manifest", "health", "governance"]},
        "rollback": {
            "target": _identity("1" * 40, "1"),
            "state_restore_required": False,
            "method": "restore prior immutable artifact",
        },
        "blockers": [],
    }


def _approval(plan):
    return {
        "schema_version": "1.0",
        "approval_id": "approval-1",
        "promotion_id": plan["promotion_id"],
        "target_environment": "production",
        "plan_sha256": promotion_plan_sha256(plan),
        "decision": "approved",
        "approver_principal_id": OWNER,
        "approver_authority": "owner",
        "approved_at": "2026-10-02T13:55:00Z",
        "expires_at": "2026-10-02T15:00:00Z",
        "state": "approved",
        "authority_record_id": "authority-record-1",
    }


def test_exact_owner_approval_allows_exact_plan():
    plan = _plan()
    result = evaluate_production_promotion(
        plan=plan,
        approval=_approval(plan),
        trusted_owner_principals={OWNER},
        now=NOW,
    )
    assert result.allowed is True
    assert result.reason_codes == ()


def test_missing_approval_fails_closed():
    result = evaluate_production_promotion(
        plan=_plan(),
        approval=None,
        trusted_owner_principals={OWNER},
        now=NOW,
    )
    assert result.allowed is False
    assert "OWNER_APPROVAL_MISSING" in result.reason_codes


def test_plan_mutation_after_approval_fails_closed():
    plan = _plan()
    approval = _approval(plan)
    mutated = deepcopy(plan)
    mutated["target"]["configuration_revision"] = "cfg-2"
    result = evaluate_production_promotion(
        plan=mutated,
        approval=approval,
        trusted_owner_principals={OWNER},
        now=NOW,
    )
    assert result.allowed is False
    assert "APPROVAL_PLAN_MISMATCH" in result.reason_codes


def test_untrusted_approver_fails_closed():
    plan = _plan()
    approval = _approval(plan)
    approval["approver_principal_id"] = "owner:someone-else"
    result = evaluate_production_promotion(
        plan=plan,
        approval=approval,
        trusted_owner_principals={OWNER},
        now=NOW,
    )
    assert result.allowed is False
    assert "APPROVER_NOT_TRUSTED" in result.reason_codes


def test_expired_approval_fails_closed():
    plan = _plan()
    approval = _approval(plan)
    approval["expires_at"] = "2026-10-02T13:59:59Z"
    result = evaluate_production_promotion(
        plan=plan,
        approval=approval,
        trusted_owner_principals={OWNER},
        now=NOW,
    )
    assert result.allowed is False
    assert "APPROVAL_EXPIRED" in result.reason_codes


def test_reserved_or_consumed_approval_is_not_reusable():
    plan = _plan()
    approval = _approval(plan)
    approval["state"] = "reserved"
    result = evaluate_production_promotion(
        plan=plan,
        approval=approval,
        trusted_owner_principals={OWNER},
        now=NOW,
    )
    assert result.allowed is False
    assert "APPROVAL_NOT_AVAILABLE" in result.reason_codes


def test_unresolved_blockers_fail_closed_even_with_valid_approval():
    plan = _plan()
    approval = _approval(plan)
    plan["blockers"] = ["backup evidence missing"]
    approval["plan_sha256"] = promotion_plan_sha256(plan)
    result = evaluate_production_promotion(
        plan=plan,
        approval=approval,
        trusted_owner_principals={OWNER},
        now=NOW,
    )
    assert result.allowed is False
    assert "UNRESOLVED_BLOCKERS" in result.reason_codes
