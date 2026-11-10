"""No auth context policy, no privileged V5 browser approval."""
from copy import deepcopy
import pytest

from jason_runtime.release_v5_ca_attestation import (
    assess_exact_admin_auth_context_mfa,
)

ADMIN = "22222222-2222-4222-8222-222222222222"
POLICY = "33333333-3333-4333-8333-333333333333"


def real_mfa_policy():
    return {
        "id": POLICY,
        "display_name": "Sensitive approval step-up",
        "state": "enabled",
        "conditions": {
            "clientAppTypes": ["browser"],
            "users": {"includeUsers": [ADMIN], "excludeUsers": [],
                      "includeGroups": [], "excludeGroups": [],
                      "includeRoles": [], "excludeRoles": []},
            "applications": {
                "includeApplications": [],
                "includeAuthenticationContextClassReferences": ["c1"],
            },
        },
        "grant_controls": {"operator": "OR", "builtInControls": ["mfa"]},
    }


def test_raw_microsoft_graph_grant_controls_supported():
    p=real_mfa_policy()
    p["grantControls"]=p.pop("grant_controls")
    candidate=assess_exact_admin_auth_context_mfa(
        policies=[p], admin_oid=ADMIN, auth_context_id="c1")
    assert candidate["provider_policy_id"]==POLICY
    assert candidate["approval_authorized"] is False


def test_conflicting_graph_and_legacy_grants_rejected():
    p=real_mfa_policy()
    p["grantControls"]={"operator":"OR","builtInControls":[]}
    with pytest.raises(PermissionError, match="V5_CA_POLICY_READ_NOT_VERIFIABLE"):
        assess_exact_admin_auth_context_mfa(
            policies=[p], admin_oid=ADMIN, auth_context_id="c1")


def test_exact_context_mfa_candidate_is_not_release_approval():
    candidate = assess_exact_admin_auth_context_mfa(
        policies=[real_mfa_policy()], admin_oid=ADMIN, auth_context_id="c1")
    assert candidate["status"] == "candidate_requires_independent_root_review"
    assert candidate["provider_policy_id"] == POLICY
    assert len(candidate["provider_read_evidence_sha256"]) == 64
    assert candidate["approval_authorized"] is False


@pytest.mark.parametrize("field,value", [
    ("state", "enabledForReportingButNotEnforced"),
    ("state", "disabled"),
    ("conditions.clientAppTypes", ["other"]),
    ("conditions.users.includeUsers", ["All"]),
    ("conditions.users.includeUsers", ["another-user"]),
    ("conditions.users.excludeUsers", [ADMIN]),
    ("conditions.users.excludeGroups", ["some-group"]),
    ("conditions.applications.includeAuthenticationContextClassReferences", []),
    ("conditions.applications.includeAuthenticationContextClassReferences", ["c2"]),
    ("grant_controls.builtInControls", []),
])
def test_not_an_enforced_exact_admin_auth_context(field, value):
    policy = real_mfa_policy()
    target = policy
    parts = field.split(".")
    for key in parts[:-1]:
        target = target[key]
    target[parts[-1]] = value
    with pytest.raises(PermissionError, match="V5_CA_EXACT_AUTH_CONTEXT_MFA_NOT_PROVEN"):
        assess_exact_admin_auth_context_mfa(
            policies=[policy], admin_oid=ADMIN, auth_context_id="c1")


def test_broad_admin_mfa_policy_does_not_prove_specific_auth_context():
    policy = real_mfa_policy()
    policy["conditions"]["applications"]["includeAuthenticationContextClassReferences"] = []
    with pytest.raises(PermissionError, match="NOT_PROVEN"):
        assess_exact_admin_auth_context_mfa(
            policies=[policy], admin_oid=ADMIN, auth_context_id="c1")


def test_multiple_matching_policies_require_independent_review():
    with pytest.raises(PermissionError, match="NOT_PROVEN"):
        assess_exact_admin_auth_context_mfa(
            policies=[real_mfa_policy(), deepcopy(real_mfa_policy())],
            admin_oid=ADMIN, auth_context_id="c1")
