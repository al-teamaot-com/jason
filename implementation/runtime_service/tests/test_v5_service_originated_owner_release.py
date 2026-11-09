"""V5 exact signed regular Owner release approval; no deployment authority."""
import json
from pathlib import Path

import pytest

from connectors.src.jason_connectors.approval_requests import ApprovalRequestStatus
from jason_runtime.mobile_release_approval import read_mobile_release_policy
from jason_runtime.playbook_autonomy_review import TeamsGatewayPlaybookApprovalSender

from implementation.runtime_service.tests.test_admin_separated_release_roles import (
    ADMIN, REGULAR, TENANT, SenderBindings, binding, new_flow, role_binding,
)
from implementation.runtime_service.tests.test_mobile_release_approval import (
    HIGH_IMPACT_REVIEW, click, policy_file,
)


def v5(tmp_path):
    return policy_file(
        tmp_path, schema_version="5.0",
        policy_mode="service_requester_regular_owner_teams",
        allowed_risk_profiles=["normal", "production_control_core"],
        ttl_seconds=600, high_impact_review=HIGH_IMPACT_REVIEW,
        admin_approver_binding=role_binding(ADMIN),
        regular_requester_binding=role_binding(REGULAR),
        release_requester_principal_id="svc-jason-release-manager",
    )


def test_v5_policy_separates_requester_owner_and_administrator(tmp_path):
    policy = read_mobile_release_policy(v5(tmp_path))
    assert policy.schema_version == "5.0"
    assert policy.service_release_requester_id == "svc-jason-release-manager"
    assert policy.admin_approver_binding == (TENANT, ADMIN)
    assert policy.regular_requester_binding == (TENANT, REGULAR)


def test_v5_regular_account_can_sign_original_service_requested_card(tmp_path):
    flow, req, repo, record = new_flow(
        tmp_path, object_id=REGULAR, policy_path=v5(tmp_path),
    )
    flow.required_policy_version = "5.0"
    original = record.read_bytes()
    result = click(flow, req, microsoft_tenant_id=TENANT, microsoft_object_id=REGULAR)
    assert result["approval_status"] == "approved"
    assert result["executed"] is False
    assert repo.get(req.approval_id).status is ApprovalRequestStatus.APPROVED
    assert record.read_bytes() == original


@pytest.mark.parametrize("actual", [
    binding(ADMIN),
    binding(REGULAR, client="1158"),
    binding(REGULAR, status="disabled"),
    binding(REGULAR, identity="person-al"),
])
def test_v5_admin_and_malformed_regular_never_sign(tmp_path, actual):
    flow, req, repo, record = new_flow(
        tmp_path, object_id=actual.microsoft_object_id, bound=actual,
        policy_path=v5(tmp_path),
    )
    flow.required_policy_version = "5.0"
    original = record.read_bytes()
    with pytest.raises(PermissionError):
        click(flow, req, microsoft_tenant_id=TENANT, microsoft_object_id=actual.microsoft_object_id)
    assert repo.get(req.approval_id).status is ApprovalRequestStatus.PENDING
    assert record.read_bytes() == original


def test_v5_sender_uses_exact_regular_entra_binding_no_email_fallback():
    lookup = SenderBindings(binding(REGULAR))
    sender = TeamsGatewayPlaybookApprovalSender(
        gateway_url="http://127.0.0.1:65500",
        token_file=Path("/tmp/unread-token"),
        bindings=lookup, owner_identity_ids=("person-al",),
        owner_identity_entra_bindings={"person-al": (TENANT, REGULAR)},
    )
    assert sender._binding_for_identity("person-al").microsoft_object_id == REGULAR
    assert lookup.lookup_calls == [(TENANT, REGULAR)]


def test_v5_cannot_mutate_existing_v4_policy_without_explicit_opt_in(tmp_path):
    flow, req, repo, record = new_flow(
        tmp_path, object_id=REGULAR, policy_path=v5(tmp_path),
    )
    # Old production V4 runtime refuses the V5 policy, even if a card exists.
    assert flow.required_policy_version == "4.0"
    with pytest.raises(PermissionError, match="reviewed runtime activation"):
        click(flow, req, microsoft_tenant_id=TENANT, microsoft_object_id=REGULAR)
    assert repo.get(req.approval_id).status is ApprovalRequestStatus.PENDING


def test_v5_policy_requires_native_service_requester(tmp_path):
    path = v5(tmp_path)
    doc = json.loads(path.read_text())
    doc["release_requester_principal_id"] = "person-entra-" + REGULAR.replace("-", "")
    path.write_text(json.dumps(doc))
    path.chmod(0o600)
    with pytest.raises(PermissionError):
        read_mobile_release_policy(path)
