from dataclasses import replace
from pathlib import Path
import json

import pytest

from jason_runtime.service_originated_owner_approval_policy import (
    OwnerTeamsRoleError, read_owner_role_policy,
)

TENANT = "f7054323-d52b-4863-8c2f-1898f0b6077c"
REGULAR = "bee80bdc-ffb0-4c50-b453-c09d4d411f5f"
ADMIN = "c848022d-e13b-4457-84b0-e2f5c00dcaf6"
SOURCE = {
    "schema_version": "5.0",
    "policy_mode": "service_requester_regular_owner_teams",
    "organization_id": "aot",
    "microsoft_tenant_id": TENANT,
    "owner_approver_object_id": REGULAR,
    "privileged_admin_object_id": ADMIN,
    "release_requester_principal_id": "svc-jason-release-manager",
    "requester_kind": "service",
    "requires_signed_teams": True,
    "requires_native_release_manager": True,
    "forbid_self_approval": True,
    "production_freeze_preserved": True,
}


def policy(tmp_path, **edits):
    p = tmp_path / "reviewed-policy.json"
    p.write_text(json.dumps(dict(SOURCE, **edits)))
    p.chmod(0o600)
    return p


def verified_request(**changes):
    values = {
        "requester_principal_id": "svc-jason-release-manager",
        "requester_kind": "service",
        "approver_tenant_id": TENANT,
        "approver_object_id": REGULAR,
        "candidate_sha": "a"*40,
        "rollback_sha": "b"*40,
        "scope_sha256": "c"*64,
        "signed_original_decision_verified": True,
        "native_release_eligible": True,
    }
    values.update(changes)
    return values


def test_exact_regular_owner_is_separate_from_system_requester_and_admin(tmp_path):
    p = read_owner_role_policy(policy(tmp_path))
    r = p.require_service_originated_release(**verified_request())
    assert r["owner_approver_object_id"] == REGULAR
    assert r["native_mutation_authorized"] == "false"


@pytest.mark.parametrize("change", [
    {"requester_kind": "human"}, {"requester_principal_id": "person-al"},
    {"approver_object_id": ADMIN}, {"approver_object_id": "wrong"},
    {"approver_tenant_id": "wrong"}, {"candidate_sha": "x"*40},
    {"rollback_sha": "a"*40}, {"scope_sha256": "wrong"},
    {"signed_original_decision_verified": False},
    {"native_release_eligible": False},
])
def test_mismatched_identity_authority_and_release_fail_closed(tmp_path, change):
    p = read_owner_role_policy(policy(tmp_path))
    with pytest.raises(OwnerTeamsRoleError):
        p.require_service_originated_release(**verified_request(**change))


@pytest.mark.parametrize("change", [
    {"policy_mode": "admin_approver_separated"},
    {"release_requester_principal_id": "person-al"},
    {"owner_approver_object_id": ADMIN},
    {"schema_version": "4.0"},
    {"requires_signed_teams": False},
    {"requires_native_release_manager": False},
    {"forbid_self_approval": False},
    {"production_freeze_preserved": False},
    {"microsoft_tenant_id": "wrong"},
])
def test_policy_downgrade_and_account_substitution_rejected(tmp_path, change):
    with pytest.raises(OwnerTeamsRoleError):
        read_owner_role_policy(policy(tmp_path, **change))


def test_world_readable_policy_rejected(tmp_path):
    p = policy(tmp_path)
    p.chmod(0o644)
    with pytest.raises(OwnerTeamsRoleError):
        read_owner_role_policy(p)


def test_unknown_policy_key_rejected(tmp_path):
    p = policy(tmp_path, allow_unsigned=True)
    with pytest.raises(OwnerTeamsRoleError):
        read_owner_role_policy(p)
