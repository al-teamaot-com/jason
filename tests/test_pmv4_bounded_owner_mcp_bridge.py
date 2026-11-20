"""MCP identity-bound one-Owner decision -> durable signed whole plan.

All JWT, Owner, approvals, keys and source are disposable synthetic evidence.
No production MCP endpoint registration or native root deployment occurs.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
import pytest

from kernel.signed_owner_release import OWNER_PRINCIPAL
from implementation.mcp_service.src.jason_mcp.pmv4_bounded_owner_bridge import (
    PMv4McpBoundedOwnerDenied,
    authorize_one_bounded_objective_from_mcp,
)
from test_pmv4_owner_objective_end_to_end import (
    AT, APPROVAL_ID, enrolled,
)


def issue(env, **overrides):
    reviewed = []
    args = dict(
        bearer_token=env["token"],
        verified_owner_principal=OWNER_PRINCIPAL,
        verified_organization="aot",
        verify_entra_bearer=env["verifier"],
        exact_owner_consent=lambda present: reviewed.append(present) or True,
        protected_main_check=lambda sha: sha == env["objective"].candidate_sha,
        objective=env["objective"], ledger=env["ledger"],
        signing_key=env["owner_key"], approval_id=APPROVAL_ID,
        affirmative_decision="approve_exact_one_pmv4_objective",
        at=AT,
    )
    args.update(overrides)
    result = authorize_one_bounded_objective_from_mcp(**args)
    return result, reviewed


def test_one_mcp_owner_consent_signs_full_exact_four_stage_objective(enrolled):
    result, reviewed = issue(enrolled)
    assert result["status"] == "source_only_owner_full_objective_signed"
    assert result["human_decision_count"] == 1
    assert len(reviewed) == 1
    assert reviewed[0]["full_reviewed_objective"] == enrolled["objective"].review_material()
    assert reviewed[0]["plan_fingerprint"] == enrolled["objective"].fingerprint
    assert result["parent_plan_fingerprint"] == enrolled["objective"].fingerprint
    assert result["production_authorized"] is False
    assert result["production_installation_queued"] is False
    assert result["root_mutation"] is False
    assert result["standing_authority"] is False
    with enrolled["ledger"]._connection() as conn:
        assert conn.execute("SELECT count(*) FROM plan_grants").fetchone()[0] == 1
        assert conn.execute(
            "SELECT count(*) FROM signed_owner_objective_receipts"
        ).fetchone()[0] == 1


def test_recovery_from_same_enrolled_parent_never_prompts_again(enrolled):
    first, consent = issue(enrolled)
    assert len(consent) == 1
    recovered, second_consent = issue(
        enrolled, at=AT + timedelta(seconds=12),
        exact_owner_consent=lambda _: pytest.fail("Owner second approval prompt"),
    )
    assert second_consent == []
    assert recovered["signed_parent"] == first["signed_parent"]
    assert recovered["parent_signed_sha256"] == first["parent_signed_sha256"]


@pytest.mark.parametrize("override,reason", [
    ({"verified_organization": "another"}, "EXACT_SESSION_REQUIRED"),
    ({"verified_owner_principal": "unlicensed-other"}, "EXACT_SESSION_REQUIRED"),
    ({"affirmative_decision": "yes"}, "EXACT_SESSION_REQUIRED"),
    ({"affirmative_decision": ""}, "EXACT_SESSION_REQUIRED"),
    ({"bearer_token": ""}, "EXACT_SESSION_REQUIRED"),
    ({"verify_entra_bearer": None}, "EXACT_SESSION_REQUIRED"),
    ({"exact_owner_consent": None}, "EXACT_SESSION_REQUIRED"),
    ({"protected_main_check": None}, "EXACT_SESSION_REQUIRED"),
    ({"production": True}, "NATIVE_ROOT_NOT_DEPLOYED"),
])
def test_mcp_rejects_invalid_login_or_nonexact_action(enrolled, override, reason):
    with pytest.raises(PMv4McpBoundedOwnerDenied, match=reason):
        issue(enrolled, **override)
    assert enrolled["ledger"].decision_receipt(APPROVAL_ID) is None


@pytest.mark.parametrize("jwt_change", [
    {"oid": "unauthorized-subject"},
    {"tid": "wrong-tenant"},
    {"aud": "wrong-audience"},
    {"nbf": int(AT.timestamp()) + 3600},
    {"exp": int(AT.timestamp()) - 30},
])
def test_failed_microsoft_entra_identity_never_mints_grant(enrolled, jwt_change):
    with pytest.raises(PermissionError):
        issue(enrolled, bearer_token=enrolled["make_token"](jwt_change))
    assert enrolled["ledger"].decision_receipt(APPROVAL_ID) is None


def test_owner_denied_never_mints_plan_or_proof(enrolled):
    with pytest.raises(PermissionError, match="CONSENT_DENIED"):
        issue(enrolled, exact_owner_consent=lambda _: False)
    assert enrolled["ledger"].decision_receipt(APPROVAL_ID) is None


def test_source_ci_denial_never_presents_owner_approval(enrolled):
    asked = []
    with pytest.raises(PermissionError, match="PROTECTED_MAIN_UNVERIFIED"):
        issue(enrolled, protected_main_check=lambda _: False,
              exact_owner_consent=lambda _: asked.append(True) or True)
    assert asked == []
    assert enrolled["ledger"].decision_receipt(APPROVAL_ID) is None


def test_changed_objective_digest_after_original_consent_denied(enrolled):
    initial, reviewed = issue(enrolled)
    changed = replace(enrolled["objective"],
                      actions=(replace(enrolled["objective"].actions[0],
                                       rollback_sha="f" * 40),)
                              + enrolled["objective"].actions[1:])
    with pytest.raises(PermissionError):
        issue(enrolled, objective=changed, at=AT + timedelta(seconds=1))
    assert len(reviewed) == 1
    assert initial["signed_parent"] == enrolled["ledger"].authenticated_owner_objective_receipt(
        plan_id=enrolled["objective"].plan_id, approval_id=APPROVAL_ID
    )


def test_revoked_objective_never_reuses_consumed_decision(enrolled):
    issue(enrolled)
    enrolled["ledger"].revoke(
        enrolled["objective"].plan_id, at=AT + timedelta(seconds=1),
        reason="revoked",
    )
    with pytest.raises(PermissionError, match="revoked"):
        issue(enrolled, at=AT + timedelta(seconds=2),
              exact_owner_consent=lambda _: pytest.fail("should not ask again"))
