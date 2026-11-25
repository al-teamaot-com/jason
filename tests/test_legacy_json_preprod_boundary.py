"""Owner/target test boundary must fail closed before ANY real action."""
from copy import deepcopy
import pytest
from tools.legacy_json_acceptance_ledger import build
from tools.legacy_json_preprod_boundary import (
    evaluate_preprod_boundary, redacted_boundary_summary,
)

SHA = "510243494efcd592a1585c681a3fa28a29296e17"
ROW = next(r for r in build()["entries"] if r["id"] == "gpt_insights_tech_assist")
OWNER = {"status": "rejected", "error_code": "AUTHORITY_GRANT_ADMIN_OWNER_REQUIRED"}
REG = {"status": "succeeded", "generation": 0, "playbooks": []}


def manifest():
    return {
        "boundary_version": "json-preprod-v1",
        "mode": "isolated_preproduction",
        "reviewed_main_sha": SHA,
        "production_activation_allowed": False,
        "legacy_retirement_allowed": False,
        "cases": [],
    }


def exact_case(action_kind="readonly"):
    return {
        "playbook_id": ROW["id"], "version": ROW["json_version"],
        "json_fingerprint": ROW["json_fingerprint"],
        "client_test_scope": "explicit_isolated_test_tenant",
        "client_id": "SYNTHETIC-TEST-CLIENT",
        "provider_test_tenant_id": "SYNTHETIC-PROVIDER-TENANT",
        "target_id": "SYNTHETIC-TARGET",
        "target_nonproduction_verified": True,
        "provider_same_client_binding_verified": True,
        "source_legacy_dispatch_disabled_for_target": True,
        "action_kind": action_kind,
        "exact_action_arguments_sha256": "a" * 64,
        "owner_approval_receipt_id": "SYNTHETIC-RECEIPT-NOT-A-REAL-GRANT",
        "approval_exact_action_verified": True,
    }


def evaluate(m=None, *, kind="readonly", owner=OWNER, reg=REG, main=SHA):
    return evaluate_preprod_boundary(
        m or manifest(), playbook_id=ROW["id"], action_kind=kind,
        known_main_sha=main, live_owner_status=owner, live_registry=reg,
    )


def test_no_targets_and_owner_denial_are_not_approvals():
    result = evaluate()
    assert not result.allowed
    assert "ADMIN_OWNER_SESSION_NOT_VERIFIED" in result.reasons
    assert "EXACT_PLAYBOOK_CASE_NOT_PRESENT" in result.reasons
    assert not result.production_activation_allowed
    assert not result.legacy_retirement_allowed


def test_even_a_made_up_test_target_cannot_bypass_owner_boundary():
    m = manifest(); m["cases"] = [exact_case()]
    result = evaluate(m)
    assert not result.allowed
    assert result.reasons == ("ADMIN_OWNER_SESSION_NOT_VERIFIED",)


@pytest.mark.parametrize("change,expected", [
    ({"production_activation_allowed": True}, "PRODUCTION_ACTIVATION_MUST_BE_DENIED"),
    ({"legacy_retirement_allowed": True}, "LEGACY_RETIREMENT_MUST_BE_DENIED"),
    ({"reviewed_main_sha": "0" * 40}, "EXACT_REVIEWED_MAIN_SHA_MISMATCH"),
    ({"mode": "production"}, "ISOLATED_PREPRODUCTION_MODE_UNVERIFIED"),
])
def test_global_boundary_fails_closed(change, expected):
    m = manifest(); m["cases"] = [exact_case()]; m.update(change)
    assert expected in evaluate(m).reasons


@pytest.mark.parametrize("field,value,expected", [
    ("client_id", "", "EXACT_TEST_TARGET_MISSING:client_id"),
    ("target_id", "", "EXACT_TEST_TARGET_MISSING:target_id"),
    ("target_nonproduction_verified", False, "NONPRODUCTION_TARGET_UNVERIFIED"),
    ("provider_same_client_binding_verified", False, "PROVIDER_TEST_TENANT_BINDING_UNVERIFIED"),
    ("source_legacy_dispatch_disabled_for_target", False, "DUPLICATE_LEGACY_DISPATCH_NOT_EXCLUDED"),
    ("json_fingerprint", "changed", "JSON_FINGERPRINT_CHANGED"),
    ("action_kind", "modifying", "EXACT_ACTION_KIND_CHANGED"),
])
def test_exact_target_failures(field,value,expected):
    m=manifest(); c=exact_case(); c[field]=value; m["cases"]=[c]
    assert expected in evaluate(m).reasons


def test_production_registry_must_remain_empty():
    m=manifest();m["cases"]=[exact_case()]
    result=evaluate(m, reg={"status":"succeeded", "generation":1,"playbooks":[{}]})
    assert "PRODUCTION_REGISTRY_BASELINE_CHANGED" in result.reasons


def test_modifying_action_fails_without_independent_receipt():
    m=manifest(); m["cases"]=[exact_case("modifying")]
    missing={"status":"succeeded","owner_identity_verified":True,
             "exact_action_approval_verified":False}
    result=evaluate(m,kind="modifying",owner=missing)
    assert not result.allowed
    assert "EXACT_ACTION_APPROVAL_NOT_CONFIRMED_BY_JASON" in result.reasons


def test_redacted_summary_never_contains_target_or_receipt():
    m=manifest(); m["cases"]=[exact_case("modifying")]
    summary=redacted_boundary_summary(m,main_sha=SHA,owner_status=OWNER,registry_status=REG)
    assert summary["live_provider_authorized_playbooks"]==0
    assert summary["live_provider_blocked_playbooks"]==19
    assert summary["production_activation_allowed"] is False
    assert summary["legacy_retirement_allowed"] is False
    assert "SYNTHETIC-RECEIPT" not in str(summary)
    assert "SYNTHETIC-TARGET" not in str(summary)
