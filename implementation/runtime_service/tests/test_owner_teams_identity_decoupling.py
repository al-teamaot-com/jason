"""V4.1 Owner release approvals use licensed Teams, not privileged admin Teams.

No new approval flow: signed immutable cards and the same host consumer remain
authoritative. Privileged Entra grant operations remain admin-separated.
"""
import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from connectors.src.jason_connectors.approval_requests import ApprovalRequestStatus
from jason_runtime.composition import build_runtime_application
from jason_runtime.mobile_release_approval import (
    MobileReleaseApprovalMaintenance, read_mobile_release_policy,
)
from jason_runtime.playbook_autonomy_review import TeamsGatewayPlaybookApprovalSender
from implementation.runtime_service.tests.test_composition import _settings
from implementation.runtime_service.tests.test_admin_separated_release_roles import (
    TENANT, ADMIN, REGULAR, SenderBindings, binding, new_flow,
    role_binding, separated_policy_file,
)
from implementation.runtime_service.tests.test_mobile_release_approval import click


def owner_teams_policy_file(tmp_path, version="4.1"):
    p = separated_policy_file(tmp_path)
    doc = json.loads(p.read_text())
    doc["schema_version"] = version
    if version == "3.2":
        doc["policy_mode"] = "owner_reviewed"
        doc["teams_owner_binding"] = doc.pop("regular_requester_binding")
        doc.pop("admin_approver_binding")
        doc["high_impact_review"] = {
            "owner_exact_sha_required": True,
            "authenticated_entra_owner_decision_required": True,
            "signed_teams_owner_allowed": True,
            "independent_native_release_health_required": True,
            "protected_release_gates_unchanged": True,
        }
    p.write_text(json.dumps(doc))
    p.chmod(0o600)
    return p


def owner_flow(tmp_path, version="4.1", **kwargs):
    p = owner_teams_policy_file(tmp_path, version)
    flow, req, repo, record = new_flow(tmp_path, policy_path=p, **kwargs)
    flow.required_policy_version = version
    return flow, req, repo, record


@pytest.mark.parametrize("version", ["4.1", "3.2"])
def test_regular_licensed_owner_signed_release_approval_is_one_use(tmp_path, version):
    flow, req, repo, original = owner_flow(tmp_path, version=version, object_id=REGULAR)
    before = original.read_bytes()
    result = click(flow, req, microsoft_tenant_id=TENANT, microsoft_object_id=REGULAR)
    assert result["approval_status"] == "approved"
    assert result["executed"] is False
    receipt = repo.accepted_decision(req.approval_id)
    assert receipt.decided_by == "person-al"
    assert receipt.channel == "microsoft_teams"
    assert repo.get(req.approval_id).status is ApprovalRequestStatus.APPROVED
    assert original.read_bytes() == before
    with pytest.raises(PermissionError, match="already terminal"):
        click(flow, req, microsoft_tenant_id=TENANT, microsoft_object_id=REGULAR)


@pytest.mark.parametrize("object_id, tenant, active_binding, identity_type", [
    (ADMIN, TENANT, None, "human"),
    (REGULAR, "00000000-0000-4000-8000-000000000000", None, "human"),
    (REGULAR, TENANT, binding(REGULAR, client="1158"), "human"),
    (REGULAR, TENANT, binding(REGULAR, status="disabled"), "human"),
    (REGULAR, TENANT, binding(REGULAR, identity="person-al"), "human"),
    (REGULAR, TENANT, binding(REGULAR), "service"),
])
@pytest.mark.parametrize("version", ["4.1", "3.2"])
def test_wrong_or_privileged_actor_cannot_approve_owner_release(
    tmp_path, object_id, tenant, active_binding, identity_type, version,
):
    flow, req, repo, original = owner_flow(
        tmp_path, version=version, object_id=object_id, tenant=tenant,
        bound=active_binding, identity_type=identity_type,
    )
    before = original.read_bytes()
    with pytest.raises(PermissionError):
        click(flow, req, microsoft_tenant_id=tenant, microsoft_object_id=object_id)
    assert repo.get(req.approval_id).status is ApprovalRequestStatus.PENDING
    assert repo.accepted_decision(req.approval_id) is None
    assert original.read_bytes() == before


def test_regular_owner_card_routes_by_exact_object_id_not_email(tmp_path):
    policy = read_mobile_release_policy(owner_teams_policy_file(tmp_path))
    assert policy.schema_version == "4.1"
    assert policy.regular_requester_binding == (TENANT, REGULAR)
    assert policy.admin_approver_binding == (TENANT, ADMIN)
    candidates = SenderBindings(binding(REGULAR))
    sender = TeamsGatewayPlaybookApprovalSender(
        gateway_url="http://127.0.0.1:65500",
        token_file=tmp_path / "not_used",
        bindings=candidates, owner_identity_ids=policy.owner_identity_ids,
        owner_identity_entra_bindings={"person-al": policy.regular_requester_binding},
    )
    assert sender._binding_for_identity("person-al").microsoft_object_id == REGULAR
    assert candidates.lookup_calls == [(TENANT, REGULAR)]
    with pytest.raises(PermissionError, match="recipient"):
        sender_bad = TeamsGatewayPlaybookApprovalSender(
            gateway_url="http://127.0.0.1:65500",
            token_file=tmp_path / "not_used",
            bindings=SenderBindings(binding(ADMIN)),
            owner_identity_ids=("person-al",),
            owner_identity_entra_bindings={"person-al": (TENANT, REGULAR)},
        )
        sender_bad._binding_for_identity("person-al")


@pytest.mark.parametrize("version", ["4.1", "3.2"])
def test_host_rechecks_exact_normal_owner_and_does_not_trust_mutable_email(tmp_path, version):
    # The host source is not on the runtime-only CI PYTHONPATH.
    import sys
    from pathlib import Path
    tools_dir = str(Path(__file__).resolve().parents[3] / "tools")
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)
    from release_mobile_approval_consumer import _authorized_policy_owner_identity
    policy = read_mobile_release_policy(owner_teams_policy_file(tmp_path, version))
    regular = binding(REGULAR)
    regular.email_address = "changed-alias@teamaot.com"
    owner = SimpleNamespace(
        identity_id=regular.jason_identity_id, organization_id="aot",
        identity_type="human", status="active",
    )
    assert _authorized_policy_owner_identity(
        binding=regular, owner=owner, policy=policy,
        receipt_identity_id="person-al",
    ) == "person-al"
    for wrong in (
        binding(ADMIN),
        binding(REGULAR, client="1158"),
        binding(REGULAR, identity="person-al"),
        binding(REGULAR, status="disabled"),
        binding(REGULAR, tenant="00000000-0000-4000-8000-000000000000"),
    ):
        with pytest.raises(PermissionError):
            _authorized_policy_owner_identity(
                binding=wrong, owner=owner, policy=policy,
                receipt_identity_id="person-al",
            )
    with pytest.raises(PermissionError):
        _authorized_policy_owner_identity(
            binding=regular, owner=owner, policy=policy,
            receipt_identity_id="person-unknown",
        )


@pytest.mark.parametrize("version", ["4.1", "3.2"])
def test_runtime_keeps_admin_grants_but_sends_to_regular_owner(tmp_path, version):
    policy = owner_teams_policy_file(tmp_path, version)
    config = replace(
        _settings(tmp_path),
        release_mobile_approval_mode="owner_reviewed" if version == "3.2" else "admin_approver_separated",
        release_mobile_approval_policy=policy,
        release_mobile_approval_db=tmp_path / "approval.sqlite3",
        release_mobile_state_root=tmp_path / "releases",
    )
    application = build_runtime_application(config)
    workers = [
        worker for worker in application.maintenance.services
        if isinstance(worker, MobileReleaseApprovalMaintenance)
    ]
    assert len(workers) == 1
    assert workers[0].required_policy_version == version
    assert workers[0].sender.owner_identity_entra_bindings == {
        "person-al": (TENANT, REGULAR)
    }
    assert workers[0].sender.owner_identity_email_fallbacks == {}


def test_host_and_runtime_validate_same_policy_and_reject_mutation(tmp_path):
    import sys
    from pathlib import Path
    tools_dir = str(Path(__file__).resolve().parents[3] / "tools")
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)
    from release_manager_host_runner import (
        ReleaseManagerError, _validated_mobile_release_policy,
        _reviewed_mobile_release_mode,
    )
    path = owner_teams_policy_file(tmp_path)
    policy = read_mobile_release_policy(path)
    assert _validated_mobile_release_policy(path, source_v2_required=True)["mode"] == (
        "admin_approver_separated"
    )
    assert _reviewed_mobile_release_mode(policy) == "admin_approver_separated"
    doc = json.loads(path.read_text())
    doc["regular_requester_binding"] = role_binding(ADMIN)
    path.write_text(json.dumps(doc))
    with pytest.raises((PermissionError, ReleaseManagerError)):
        read_mobile_release_policy(path)
    with pytest.raises(ReleaseManagerError):
        _validated_mobile_release_policy(path, source_v2_required=True)

def test_optional_teams_policy_keeps_native_review_and_never_restores_admin_mode(tmp_path):
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[3]
    for directory in (root, root / "tools"):
        if str(directory) not in sys.path:
            sys.path.insert(0, str(directory))
    from tools.tests.test_admin_separated_deploy_contract import RUNTIME, run_validator
    from release_manager_host_runner import (
        _validated_mobile_release_policy, _reviewed_mobile_release_mode,
        signed_owner_offer_purpose,
    )
    p = owner_teams_policy_file(tmp_path, "3.2")
    policy = read_mobile_release_policy(p)
    assert policy.teams_owner_binding == (TENANT, REGULAR)
    assert policy.admin_approver_binding is None
    assert _validated_mobile_release_policy(p, source_v2_required=True)["mode"] == "owner_reviewed"
    assert _reviewed_mobile_release_mode(policy) == "owner_reviewed"
    run = run_validator(RUNTIME, 'SOURCE_RELEASE_APPROVAL_MODE="$(python3', 'PY2', p)
    assert run.returncode == 0, run.stderr
    assert run.stdout.strip() == "owner_reviewed"
    record = {"risk_profile": "production_control_core"}
    assert signed_owner_offer_purpose(record, "a" * 40, policy, "owner_reviewed", ccc_root=tmp_path)
    record["owner_approval"] = {"approved": True, "candidate_sha": "a" * 40}
    assert signed_owner_offer_purpose(record, "a" * 40, policy, "owner_reviewed", ccc_root=tmp_path) is None
    good = json.loads(p.read_text())
    for field, value in (
        ("teams_owner_binding", {"microsoft_tenant_id": TENANT, "microsoft_object_id": "wrong"}),
        ("admin_approver_binding", role_binding(ADMIN)),
        ("high_impact_review", {"signed_teams_owner_allowed": True}),
    ):
        p.write_text(json.dumps({**good, field:value}))
        with pytest.raises(PermissionError):
            read_mobile_release_policy(p)
        with pytest.raises(Exception, match="policy|binding|role identity"):
            _validated_mobile_release_policy(p, source_v2_required=True)
        assert run_validator(RUNTIME, 'SOURCE_RELEASE_APPROVAL_MODE="$(python3', 'PY2', p).returncode != 0
