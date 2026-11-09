"""V5 AOT pilot policy: regular Teams notice, separate unlicensed admin signer.

The root policy remains V4 in production. These tests use only ephemeral
0600 policies, release records and SQLite state. Nothing is deployed.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from jason_runtime.mobile_release_approval import (
    create_mobile_release_request, read_mobile_release_policy,
    read_eligible_release,
)
from implementation.runtime_service.tests.v5_synthetic_identity import (
    AOT_TENANT, AOT_ADMIN_OID,
    AOT_REQUESTER_OID, AOT_ADMIN_UPN, AOT_REQUESTER_UPN,
)
from jason_runtime.release_v5_aot_policy import AotV5BrowserPolicy
from implementation.runtime_service.tests.test_mobile_release_approval import (
    NOW, RELEASE, policy_file, release_record, mark_release_high_impact,
)


def base_payload():
    return {
        "schema_version": "5.0",
        "policy_mode": "admin_browser_stepup_regular_teams_notice",
        "allowed_risk_profiles": ["normal", "production_control_core"],
        "ttl_seconds": 600,
        "high_impact_review": {
            "owner_exact_sha_required": True,
            "signed_teams_identity_required": False,
            "signed_admin_browser_identity_required": True,
            "independent_ccc_required": True,
            "protected_release_gates_unchanged": True,
        },
        "admin_approver_binding": {
            "microsoft_tenant_id": AOT_TENANT,
            "microsoft_object_id": AOT_ADMIN_OID,
        },
        "regular_requester_binding": {
            "microsoft_tenant_id": AOT_TENANT,
            "microsoft_object_id": AOT_REQUESTER_OID,
        },
        "entra_browser_approval": {
            "browser_client_id": "267b5641-cea0-4251-95c5-685178e0e087",
            "auth_context_id": "c1",
            "ca_enforcement_receipt_sha256": "a" * 64,
            "signer_public_key_sha256": "b" * 64,
            "callback_uri": "https://approvals.example.org/admin/release-approval/callback",
            "notice_uri": "https://approvals.example.org/admin/release-approval",
            "channel": "microsoft_entra_browser_stepup",
            "teams_notice_only": True,
            "separate_admin_browser_login": True,
            "owner_role": "person-al",
            "no_admin_teams_license": True,
        },
    }


def new_policy(tmp_path, payload=None):
    return policy_file(tmp_path, **(payload or base_payload()))


def test_v5_policy_requires_exact_root_0600_pins(tmp_path):
    policy = read_mobile_release_policy(new_policy(tmp_path))
    assert policy.schema_version == "5.0"
    assert policy.owner_identity_ids == ("person-al",)
    assert policy.admin_approver_binding == (AOT_TENANT, AOT_ADMIN_OID)
    assert policy.regular_requester_binding == (AOT_TENANT, AOT_REQUESTER_OID)
    assert policy.browser_policy.auth_context_id == "c1"
    assert AOT_ADMIN_UPN == "admin@example.org"
    assert AOT_REQUESTER_UPN == "requester@example.org"


@pytest.mark.parametrize("mutation", [
    lambda x: x["admin_approver_binding"].__setitem__(
        "microsoft_object_id", AOT_REQUESTER_OID),
    lambda x: x["regular_requester_binding"].__setitem__(
        "microsoft_object_id", AOT_ADMIN_OID),
    lambda x: x["entra_browser_approval"].__setitem__(
        "notice_uri", "https://attacker.example/admin/release-approval"),
    lambda x: x["entra_browser_approval"].__setitem__(
        "callback_uri", "https://attacker.example/admin/release-approval/callback"),
    lambda x: x["entra_browser_approval"].__setitem__("teams_notice_only", False),
    lambda x: x["entra_browser_approval"].__setitem__("no_admin_teams_license", False),
    lambda x: x["entra_browser_approval"].__setitem__(
        "ca_enforcement_receipt_sha256", "0" * 64),
    lambda x: x["entra_browser_approval"].__setitem__(
        "signer_public_key_sha256", "0" * 64),
    lambda x: x["high_impact_review"].__setitem__("signed_teams_identity_required", True),
    lambda x: x["owner_identity_ids"].append("person-eve"),
])
def test_v5_policy_rejects_unauthorized_route_or_weakened_controls(tmp_path, mutation):
    payload = base_payload()
    # Existing policy_file injects canonical shared fields unless provided.
    if "owner_identity_ids" not in payload:
        payload["owner_identity_ids"] = ["person-al"]
    mutation(payload)
    with pytest.raises(PermissionError):
        read_mobile_release_policy(new_policy(tmp_path, payload))


def test_v5_request_is_exact_pending_browser_authority_not_teams_button(tmp_path):
    policy = read_mobile_release_policy(new_policy(tmp_path))
    root, _ = release_record(tmp_path)
    mark_release_high_impact(root)
    import json
    path = root / "records" / (RELEASE + ".json")
    record = json.loads(path.read_text())
    record["manual_scope_review"] = {"scope_sha256": "f" * 64}
    path.write_text(json.dumps(record))
    evidence = read_eligible_release(root, RELEASE, policy)
    req = create_mobile_release_request(evidence, policy, now=NOW)
    assert req.authorized_approver_ids == ("person-al",)
    assert req.metadata["approval_channel"] == "microsoft_entra_browser_stepup"
    assert req.metadata["notice_to_entra_oid"] == AOT_REQUESTER_OID
    assert req.metadata["admin_approver_entra_oid"] == AOT_ADMIN_OID
    assert "card_instance_challenge" not in req.metadata
    assert req.metadata["scope_sha256"] == "f" * 64


def test_v4_root_policy_remains_valid_and_unchanged(tmp_path):
    from implementation.runtime_service.tests.test_admin_separated_release_roles import separated_policy_file
    policy=read_mobile_release_policy(separated_policy_file(tmp_path))
    assert policy.schema_version == "4.0"
    assert policy.browser_policy is None


def test_v5_policy_rotates_reviewed_admin_and_owner_for_second_organization(tmp_path):
    """Tenant, admin, owner, callback and requester live in the 0600 policy."""
    from implementation.runtime_service.tests.test_mobile_release_approval import policy_file
    from copy import deepcopy
    first=base_payload()
    second=deepcopy(first)
    second["organization_id"]="secondco"
    second["owner_identity_ids"]=["owner-second"]
    second["admin_approver_binding"]={
        "microsoft_tenant_id":"44444444-4444-4444-8444-444444444444",
        "microsoft_object_id":"55555555-5555-4555-8555-555555555555",
    }
    second["regular_requester_binding"]={
        "microsoft_tenant_id":"44444444-4444-4444-8444-444444444444",
        "microsoft_object_id":"66666666-6666-4666-8666-666666666666",
    }
    new_origin="https://review.secondco.example"
    second["entra_browser_approval"].update({
        "owner_role":"owner-second",
        "notice_uri":new_origin+"/admin/release-approval",
        "callback_uri":new_origin+"/admin/release-approval/callback",
    })
    path=policy_file(tmp_path,**second)
    loaded=read_mobile_release_policy(path)
    assert loaded.organization_id=="secondco"
    assert loaded.owner_identity_ids==("owner-second",)
    assert loaded.browser_policy.tenant_id==second["admin_approver_binding"]["microsoft_tenant_id"]
    assert loaded.browser_policy.admin_approver_oid==second["admin_approver_binding"]["microsoft_object_id"]
    assert loaded.browser_policy.requester_oid==second["regular_requester_binding"]["microsoft_object_id"]
    assert loaded.browser_policy.notice_uri==new_origin+"/admin/release-approval"
    assert loaded.browser_policy.owner_identity_id=="owner-second"


def test_v5_other_tenant_cannot_swap_admin_without_matching_reviewed_policy(tmp_path):
    payload=base_payload()
    payload["admin_approver_binding"]["microsoft_tenant_id"]="44444444-4444-4444-8444-444444444444"
    with pytest.raises(PermissionError):
        read_mobile_release_policy(new_policy(tmp_path,payload))
