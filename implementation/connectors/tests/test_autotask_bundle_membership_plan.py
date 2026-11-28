"""Fail-closed source-only bundle composition checks (no provider I/O)."""
import copy

import pytest

from connectors.autotask.bundle_membership_plan import (
    BundleMembershipPlanDenied,
    ENTITY_PATH,
    PROVIDER_OPERATION,
    plan_inactive_bundle_membership,
)
from connectors.autotask.operations import AUTOTASK_OPERATIONS
from connectors.autotask.procurement_mutation_connector import (
    AUTOTASK_PROCUREMENT_MUTATION_OPERATIONS,
)


def sample():
    return {
        "bundle": {
            "id": 5, "name": "AOT-MSA - Inactive Component Pilot",
            "isActive": False, "billingCodeID": 29682901, "unitPrice": 0,
        },
        "service": {"id": 133, "name": "IT-MSA-Datto RMM", "isActive": True},
        "existing_links": [{"id": 101, "serviceBundleID": 5, "serviceID": 48}],
        "native_sum_pricing_observed": False,
        "bundle_read_evidence": "governed bundle ID 5 read",
        "service_read_evidence": "governed service ID 133 read",
        "links_read_evidence": "complete bundle ID 5 membership search",
        "pricing_setting_evidence": "independent native UI configuration review",
    }


def test_prepare_only_and_no_runtime_registration():
    proposal = plan_inactive_bundle_membership(**sample())
    assert proposal["status"] == "SOURCE_ONLY_NOT_AUTHORIZED"
    assert proposal["execution_authorized"] is False
    assert proposal["method"] == "POST"
    assert proposal["path"] == ENTITY_PATH
    assert proposal["payload"] == {"serviceBundleID": 5, "serviceID": 133}
    assert proposal["authenticated_exact_action_approval_required"]
    assert proposal["automatic_retry_permitted"] is False
    assert proposal["bundle_price_must_be_reverified_after_create"] is True
    assert PROVIDER_OPERATION not in AUTOTASK_OPERATIONS
    assert PROVIDER_OPERATION not in AUTOTASK_PROCUREMENT_MUTATION_OPERATIONS


@pytest.mark.parametrize("bundle_id", [1, 2, 3, 4])
def test_legacy_bundles_never_mutated(bundle_id):
    args = sample()
    args["bundle"]["id"] = bundle_id
    with pytest.raises(BundleMembershipPlanDenied, match="LEGACY_BUNDLE_PROTECTED"):
        plan_inactive_bundle_membership(**args)


@pytest.mark.parametrize("invalid", [True, False, 0, -1, "5", 5.0, None])
def test_requires_exact_positive_integral_ids(invalid):
    args = sample()
    args["service"]["id"] = invalid
    with pytest.raises(BundleMembershipPlanDenied, match="SERVICE_ID_INVALID"):
        plan_inactive_bundle_membership(**args)


def test_existing_link_refuses_duplicate():
    args = sample()
    args["existing_links"][0]["serviceID"] = 133
    with pytest.raises(BundleMembershipPlanDenied, match="MEMBERSHIP_ALREADY_EXISTS"):
        plan_inactive_bundle_membership(**args)


def test_refuses_incomplete_or_foreign_link_set():
    args = sample()
    args["existing_links"][0]["serviceBundleID"] = 6
    with pytest.raises(BundleMembershipPlanDenied, match="CROSS_BUNDLE_LINK_SET"):
        plan_inactive_bundle_membership(**args)
    args = sample()
    args["existing_links"] = None
    with pytest.raises(BundleMembershipPlanDenied, match="COMPLETE_LINK_SET_REQUIRED"):
        plan_inactive_bundle_membership(**args)


def test_refuses_ambiguous_duplicate_rows():
    args = sample()
    args["existing_links"].append({"id": 102, "serviceBundleID": 5, "serviceID": 48})
    with pytest.raises(BundleMembershipPlanDenied, match="AMBIGUOUS_DUPLICATE_EXISTING_LINKS"):
        plan_inactive_bundle_membership(**args)


@pytest.mark.parametrize("flag", [True, None, "false", 0, 1])
def test_auto_sum_price_or_unverified_setting_blocks_all_proposals(flag):
    args = sample()
    args["native_sum_pricing_observed"] = flag
    with pytest.raises(BundleMembershipPlanDenied, match="NATIVE_SUM_PRICING_UNKNOWN_OR_PRICE_MUTATING"):
        plan_inactive_bundle_membership(**args)


@pytest.mark.parametrize("price", [1, -1, "0.01", None, True, "NaN"])
def test_financial_value_must_be_proven_zero(price):
    args = sample()
    args["bundle"]["unitPrice"] = price
    with pytest.raises(BundleMembershipPlanDenied, match="BUNDLE_(FINANCIAL_VALUE_NOT_ZERO|PRICE_UNVERIFIED)"):
        plan_inactive_bundle_membership(**args)


def test_inactive_bundle_active_component_and_approved_billing_code_required():
    for field, value, reason in (
        ("isActive", True, "ACTIVE_BUNDLE_DENIED"),
        ("billingCodeID", 29682871, "BILLING_CODE_UNVERIFIED"),
        ("name", "AOT IT Essentials", "NON_AOT_MSA_BUNDLE_DENIED"),
    ):
        args = sample()
        args["bundle"][field] = value
        with pytest.raises(BundleMembershipPlanDenied, match=reason):
            plan_inactive_bundle_membership(**args)
    args = sample()
    args["service"]["isActive"] = False
    with pytest.raises(BundleMembershipPlanDenied, match="SERVICE_NOT_VERIFIED_ACTIVE"):
        plan_inactive_bundle_membership(**args)


def test_missing_evidence_fails_closed():
    args = sample()
    args["pricing_setting_evidence"] = ""
    with pytest.raises(BundleMembershipPlanDenied, match="PRICING_SETTING_EVIDENCE_MISSING"):
        plan_inactive_bundle_membership(**args)


def test_plan_does_not_modify_inputs():
    args = sample()
    original = copy.deepcopy(args)
    plan_inactive_bundle_membership(**args)
    assert args == original
