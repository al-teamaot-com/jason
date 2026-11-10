"""Read-only candidate for existing role-bound admin MFA, never deployment."""
from copy import deepcopy

import pytest

from jason_runtime.release_v5_ca_attestation import (
    assess_existing_admin_role_browser_mfa,
)

TENANT="11111111-1111-4111-8111-111111111111"
ADMIN="22222222-2222-4222-8222-222222222222"
APP="33333333-3333-4333-8333-333333333333"
ROLE="44444444-4444-4444-8444-444444444444"
POLICY="55555555-5555-4555-8555-555555555555"


def evidence():
    policy={
        "id":POLICY,"displayName":"Require multifactor authentication for admins",
        "state":"enabled","conditions":{
            "clientAppTypes":["all"],
            "users":{"includeUsers":[],"excludeUsers":[],
                "includeGroups":[],"excludeGroups":[],
                "includeRoles":[ROLE],"excludeRoles":[]},
            "applications":{"includeApplications":["All"],
                "excludeApplications":[],
                "includeAuthenticationContextClassReferences":[]},
            "locations":None,"platforms":None,"devices":None,
            "userRiskLevels":[],"signInRiskLevels":[],
        },
        "grantControls":{"builtInControls":["mfa"],"operator":"OR"},
    }
    assignments=[{"principalId":ADMIN,"roleDefinitionId":ROLE,
                  "directoryScopeId":"/","principalOrganizationId":TENANT}]
    return [policy],assignments


def assess(policies,assignments):
    return assess_existing_admin_role_browser_mfa(
        policies=policies,role_assignments=assignments,
        tenant_id=TENANT,admin_oid=ADMIN,browser_client_id=APP,
    )


def test_existing_admin_mfa_preflight_requires_no_license_mutation_and_grants_none():
    policies,roles=evidence()
    result=assess(policies,roles)
    assert result["status"]=="candidate_requires_independent_root_review"
    assert result["provider_policy_id"]==POLICY
    assert result["matching_role_count"]==1
    assert len(result["provider_read_evidence_sha256"])==64
    assert result["approval_authorized"] is False
    assert result["requires_separate_privileged_oidc_mfa_token"] is True
    assert result["requires_teams_owner_release_authorization"] is True


@pytest.mark.parametrize("target,value",[
    ("state","enabledForReportingButNotEnforced"),
    ("conditions.clientAppTypes",["other"]),
    ("conditions.users.excludeUsers",[ADMIN]),
    ("conditions.users.excludeRoles",[ROLE]),
    ("conditions.users.excludeGroups",["group-one"]),
    ("conditions.applications.includeApplications",["Other"]),
    ("conditions.applications.excludeApplications",[APP]),
    ("conditions.applications.includeAuthenticationContextClassReferences",["c1"]),
    ("conditions.locations",{"includeLocations":["US"]}),
    ("grantControls.builtInControls",["mfa","compliantDevice"]),
    ("grantControls.builtInControls",["compliantDevice"]),
])
def test_scope_narrowing_or_optional_mfa_fails_closed(target,value):
    policies,roles=evidence()
    at=policies[0]
    parts=target.split(".")
    for key in parts[:-1]:
        at=at[key]
    at[parts[-1]]=value
    with pytest.raises(PermissionError,match="V5_EXISTING_ADMIN_ROLE_MFA_NOT_PROVEN"):
        assess(policies,roles)


def test_admin_membership_cannot_be_inferred_from_policy_role_name():
    policies,roles=evidence()
    roles[0]["principalId"]="66666666-6666-4666-8666-666666666666"
    with pytest.raises(PermissionError,match="NO_ADMIN_ROLE_PROOF"):
        assess(policies,roles)


def test_assignment_must_be_exact_tenant_and_root_scope():
    for key,value in [("directoryScopeId","/administrativeUnits/aaa"),
                      ("principalOrganizationId","66666666-6666-4666-8666-666666666666")]:
        policies,roles=evidence()
        roles[0][key]=value
        with pytest.raises(PermissionError,match="ROLE_EVIDENCE_INVALID"):
            assess(policies,roles)


def test_multiple_eligible_policies_require_independent_review():
    policies,roles=evidence()
    twin=deepcopy(policies[0])
    twin["id"]="77777777-7777-4777-8777-777777777777"
    with pytest.raises(PermissionError,match="V5_EXISTING_ADMIN_ROLE_MFA_NOT_PROVEN"):
        assess(policies+[twin],roles)
