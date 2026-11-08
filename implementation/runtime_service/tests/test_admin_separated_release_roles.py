"""Security regression: regular Jason requester != privileged Entra approver.

V4 is a separately activated 0600 policy; ordinary V2/V3 behavior must remain
identical until explicitly reviewed, released and activated.  These tests use
only isolated test databases and simulated signed Teams evidence.
"""
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

from connectors.src.jason_connectors.approval_requests import (
    ApprovalRequestService, ApprovalRequestStatus, SQLiteApprovalRequestRepository,
)
from jason_runtime.composition import build_runtime_application
from jason_runtime.mobile_release_approval import (
    MobileReleaseApprovalFlow, MobileReleaseSignedEvidenceStore,
    create_mobile_release_request, read_eligible_release, read_mobile_release_policy,
)
from jason_runtime.playbook_autonomy_review import TeamsGatewayPlaybookApprovalSender

from implementation.runtime_service.tests.test_composition import _settings
from implementation.runtime_service.tests.test_mobile_release_approval import (
    NOW, RELEASE, SHA, FakeVerifier, HIGH_IMPACT_REVIEW,
    SimpleOwnerAuthority, click, mark_release_high_impact, policy_file,
    release_record, reviewed_policy_file,
)

TENANT = "f7054323-d52b-4863-8c2f-1898f0b6077c"
ADMIN = "c848022d-e13b-4457-84b0-e2f5c00dcaf6"
REGULAR = "bee80bdc-ffb0-4c50-b453-c09d4d411f5f"


def role_binding(object_id):
    return {"microsoft_tenant_id": TENANT, "microsoft_object_id": object_id}


def separated_policy_file(tmp_path, **updates):
    return policy_file(
        tmp_path,
        schema_version="4.0",
        policy_mode="admin_approver_separated",
        allowed_risk_profiles=[
            "normal", "production_control_core",
        ],
        ttl_seconds=600,
        high_impact_review=HIGH_IMPACT_REVIEW,
        admin_approver_binding=role_binding(ADMIN),
        regular_requester_binding=role_binding(REGULAR),
        **updates,
    )


def binding(object_id, *, tenant=TENANT, identity=None, client=None,
            status="active"):
    return SimpleNamespace(
        microsoft_tenant_id=tenant,
        microsoft_object_id=object_id,
        jason_identity_id=identity or "person-entra-" + UUID(object_id).hex,
        client_id=client,
        status=status,
        # Email can change and must not authorize either role.
        email_address="al_admin@teamaot.com" if object_id == ADMIN else "al@teamaot.com",
    )


def new_flow(tmp_path, *, object_id=ADMIN, tenant=TENANT, bound=None,
             identity_type="human", policy_path=None):
    path = policy_path or separated_policy_file(tmp_path)
    policy = read_mobile_release_policy(path)
    root, release_path = release_record(tmp_path)
    mark_release_high_impact(root)
    req = create_mobile_release_request(
        read_eligible_release(root, RELEASE, policy), policy, now=NOW,
    )
    repo = SQLiteApprovalRequestRepository(tmp_path / "v4-approvals.sqlite3")
    service = ApprovalRequestService(repo, SimpleOwnerAuthority())
    service.create(req, now=NOW)
    active_binding = bound or binding(object_id, tenant=tenant)
    get_binding = lambda **kw: active_binding
    identity = SimpleNamespace(
        identity_id=active_binding.jason_identity_id,
        identity_type=identity_type,
        organization_id="aot", status="active",
    )
    verifier = FakeVerifier(
        aid=req.approval_id, decision="approve", now=NOW,
        selections={"card_challenge": req.metadata["card_instance_challenge"]},
    )
    verifier.parsed.microsoft_tenant_id = tenant
    verifier.parsed.microsoft_object_id = object_id
    verifier.verify = lambda token: SimpleNamespace(
        tenant_id=tenant, object_id=object_id,
        authentication_evidence_hash="f" * 64,
    )
    flow = MobileReleaseApprovalFlow(
        service, repo, path, root,
        SimpleNamespace(find=get_binding),
        SimpleNamespace(get=lambda key: identity),
        verifier, MobileReleaseSignedEvidenceStore(tmp_path / "v4-approvals.sqlite3"),
        required_policy_version="4.0",
        owner_identity_email_fallbacks={"person-al": "al@teamaot.com"},
    )
    return flow, req, repo, release_path


def test_reviewed_v4_admin_and_regular_are_independent_immutable_ids(tmp_path):
    policy = read_mobile_release_policy(separated_policy_file(tmp_path))
    assert policy.admin_approver_binding == (TENANT, ADMIN)
    assert policy.regular_requester_binding == (TENANT, REGULAR)
    assert policy.owner_identity_ids == ("person-al",)
    assert policy.schema_version == "4.0"


@pytest.mark.parametrize("corruption", [
    {"admin_approver_binding": role_binding(REGULAR)},
    {"admin_approver_binding": {"microsoft_tenant_id": TENANT, "microsoft_object_id": "bad"}},
    {"admin_approver_binding": {"microsoft_tenant_id": "00000000-0000-4000-8000-000000000000",
                                "microsoft_object_id": ADMIN}},
    {"regular_requester_binding": {"microsoft_tenant_id": TENANT.upper(),
                                   "microsoft_object_id": REGULAR}},
    {"admin_approver_binding": {"microsoft_tenant_id": TENANT,
                                "microsoft_object_id": ADMIN, "email": "al_admin@teamaot.com"}},
    {"owner_identity_ids": ["person-entra-" + UUID(REGULAR).hex]},
    {"policy_mode": "owner_reviewed"},
])
def test_v4_policy_wrong_actor_or_schema_fails_closed(tmp_path, corruption):
    p = separated_policy_file(tmp_path)
    doc = json.loads(p.read_text())
    doc.update(corruption)
    p.write_text(json.dumps(doc))
    p.chmod(0o600)
    with pytest.raises(PermissionError):
        read_mobile_release_policy(p)


def test_exact_admin_signed_decision_succeeds_without_owner_binding_migration(tmp_path):
    flow, req, repo, original = new_flow(tmp_path)
    before = original.read_bytes()
    result = click(
        flow, req, microsoft_tenant_id=TENANT,
        microsoft_object_id=ADMIN,
    )
    assert result["approval_status"] == "approved"
    assert result["executed"] is False
    receipt = repo.accepted_decision(req.approval_id)
    assert receipt.decided_by == "person-al"
    assert receipt.channel == "microsoft_teams"
    assert repo.get(req.approval_id).status is ApprovalRequestStatus.APPROVED
    assert original.read_bytes() == before
    with pytest.raises(PermissionError, match="already terminal"):
        click(flow, req, microsoft_tenant_id=TENANT, microsoft_object_id=ADMIN)


@pytest.mark.parametrize("object_id,tenant,bound,identity_type", [
    (REGULAR, TENANT, None, "human"),
    (ADMIN, "00000000-0000-4000-8000-000000000000", None, "human"),
    (ADMIN, TENANT, binding(ADMIN, identity="person-al"), "human"),
    (ADMIN, TENANT, binding(ADMIN, client="1158"), "human"),
    (ADMIN, TENANT, binding(ADMIN, status="disabled"), "human"),
    (ADMIN, TENANT, binding(ADMIN), "service"),
    (ADMIN, TENANT, binding(REGULAR), "human"),
])
def test_v4_forged_wrong_or_regular_actor_never_approves(
        tmp_path, object_id, tenant, bound, identity_type):
    flow, req, repo, record = new_flow(
        tmp_path, object_id=object_id, tenant=tenant,
        bound=bound, identity_type=identity_type,
    )
    before = record.read_bytes()
    with pytest.raises(PermissionError):
        click(flow, req, microsoft_tenant_id=tenant, microsoft_object_id=object_id)
    assert repo.get(req.approval_id).status is ApprovalRequestStatus.PENDING
    assert repo.accepted_decision(req.approval_id) is None
    assert record.read_bytes() == before


def test_v4_policy_drift_denies_old_signed_card(tmp_path):
    flow, req, repo, record = new_flow(tmp_path)
    p = flow.policy_path
    payload = json.loads(p.read_text())
    payload["admin_approver_binding"] = role_binding(REGULAR)
    payload["regular_requester_binding"] = role_binding(ADMIN)
    p.write_text(json.dumps(payload))
    p.chmod(0o600)
    with pytest.raises(PermissionError):
        click(flow, req, microsoft_tenant_id=TENANT, microsoft_object_id=ADMIN)
    assert repo.get(req.approval_id).status is ApprovalRequestStatus.PENDING


class SenderBindings:
    def __init__(self, value):
        self.value = value
        self.lookup_calls = []
    def find(self, *, microsoft_tenant_id, microsoft_object_id):
        self.lookup_calls.append((microsoft_tenant_id, microsoft_object_id))
        return self.value
    def find_active_by_jason_identity(self, *, jason_identity_id):
        raise AssertionError("admin approval must not resolve a legacy Owner alias")
    def find_active_by_email(self, *, email_address):
        raise AssertionError("admin approval must not use personal email fallback")


def sender(bindings):
    return TeamsGatewayPlaybookApprovalSender(
        gateway_url="http://127.0.0.1:65500",
        token_file=Path("/tmp/no-teams-token-used"),
        bindings=bindings, owner_identity_ids=("person-al",),
        owner_identity_entra_bindings={"person-al": (TENANT, ADMIN)},
    )


def test_v4_sender_routes_only_to_admin_enrolled_object_without_email_fallback():
    pair = SenderBindings(binding(ADMIN))
    selected = sender(pair)._binding_for_identity("person-al")
    assert selected.microsoft_object_id == ADMIN
    assert pair.lookup_calls == [(TENANT, ADMIN)]


@pytest.mark.parametrize("actual", [
    binding(REGULAR), binding(ADMIN, client="1158"),
    binding(ADMIN, identity="person-al"), binding(ADMIN, status="disabled"),
    binding(ADMIN, tenant="00000000-0000-4000-8000-000000000000"),
    None,
])
def test_v4_sender_rejects_wrong_binding_before_any_transport(actual):
    with pytest.raises(PermissionError, match="admin Teams approval recipient"):
        sender(SenderBindings(actual))._binding_for_identity("person-al")


def test_v4_sender_rejects_mixed_mutable_fallback_even_if_admin_binding_present():
    with pytest.raises(PermissionError, match="mutable email fallback"):
        TeamsGatewayPlaybookApprovalSender(
            gateway_url="http://127.0.0.1:65500",
            token_file=Path("/tmp/unused-token"),
            bindings=SenderBindings(binding(ADMIN)),
            owner_identity_ids=("person-al",),
            owner_identity_email_fallbacks={"person-al": "al@teamaot.com"},
            owner_identity_entra_bindings={"person-al": (TENANT, ADMIN)},
        )


def test_v4_is_separately_opted_in_not_silently_enabled_by_old_mode(tmp_path):
    path = separated_policy_file(tmp_path)
    cfg = replace(
        _settings(tmp_path),
        release_mobile_approval_mode="owner_reviewed",
        release_mobile_approval_policy=path,
        release_mobile_approval_db=tmp_path / "approval.sqlite3",
        release_mobile_state_root=tmp_path / "release-root",
    )
    with pytest.raises(PermissionError, match="reviewed policy version"):
        build_runtime_application(cfg)
    cfg = replace(cfg, release_mobile_approval_mode="admin_approver_separated")
    cfg.validate()
    app = build_runtime_application(cfg)
    from jason_runtime.mobile_release_approval import MobileReleaseApprovalMaintenance
    workers = [x for x in app.maintenance.services
               if isinstance(x, MobileReleaseApprovalMaintenance)]
    assert len(workers) == 1
    assert workers[0].sender.owner_identity_email_fallbacks == {}
    assert workers[0].sender.owner_identity_entra_bindings == {
        "person-al": (TENANT, ADMIN),
    }
    assert not (cfg.release_mobile_state_root / "mobile-release-offers").exists()
    # A legacy V2 policy must not silently run in the new admin-separated mode.
    with pytest.raises(PermissionError, match="requires V4 approval policy"):
        build_runtime_application(replace(
            cfg, release_mobile_approval_policy=reviewed_policy_file(tmp_path),
        ))


def test_host_policy_validator_attests_same_v4_principal_pair(tmp_path):
    import sys
    # Runtime-service CI imports implementation only; the actual source-bound
    # Host Release Manager is a separate tools entrypoint, not on that PYTHONPATH.
    tools_dir = str(Path(__file__).resolve().parents[3] / "tools")
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)
    from release_manager_host_runner import (
        _validated_mobile_release_policy, ReleaseManagerError,
        _reviewed_mobile_release_mode,
    )
    p = separated_policy_file(tmp_path)
    result = _validated_mobile_release_policy(p, source_v2_required=True)
    assert result["schema_version"] == "4.0"
    assert result["mode"] == "admin_approver_separated"
    assert _reviewed_mobile_release_mode(read_mobile_release_policy(p)) == result["mode"]
    payload = json.loads(p.read_text())
    payload["regular_requester_binding"] = role_binding(ADMIN)
    p.write_text(json.dumps(payload))
    with pytest.raises(ReleaseManagerError):
        _validated_mobile_release_policy(p, source_v2_required=True)
