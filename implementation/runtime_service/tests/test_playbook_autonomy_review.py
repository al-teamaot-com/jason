from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json

import pytest

from autonomous_remediation.playbook_autonomy_approval import SQLitePlaybookAutonomyApprovalStore
from autonomous_remediation.playbook_autonomy_review import PlaybookAutonomyReviewService
from connectors.src.jason_connectors.approval_requests import (
    ApprovalRequestService,
    SQLiteApprovalRequestRepository,
)
from orchestrator.teams_identity_binding import MicrosoftIdentityBinding
from jason_runtime.playbook_autonomy_review import (
    OwnerOnlyPlaybookAutonomyAuthority,
    PlaybookAutonomyApprovalInteractionFlow,
    load_playbook_owner_approval_policy,
    PlaybookAutonomyReviewMaintenance,
)

NOW = datetime(2026, 9, 26, 15, 0, tzinfo=timezone.utc)


def write_registry(path, version="1.0.0"):
    path.write_text(json.dumps({
        "schema_version": 2,
        "playbooks": [{
            "id": "demo",
            "name": "Demo",
            "version": version,
            "lifecycle": "production",
            "enabled": True,
            "source": "docs/playbooks/demo.md",
            "review_status": "diagnostic_autonomous_cleanup_gated",
            "autonomy": {
                "activation": "autonomous",
                "required_gates": ["identity"],
                "allowed_capabilities": ["service.ticket.note.create"],
                "policy_id": "playbook-autonomy:demo",
            },
        }],
    }), encoding="utf-8")


class Sender:
    def __init__(self):
        self.requests = []

    def send(self, request):
        self.requests.append(request)
        return (f"teams-{len(self.requests)}",)


class Bindings:
    def __init__(self, owner=True):
        self.owner = owner
        self.binding = MicrosoftIdentityBinding(
            microsoft_tenant_id="tenant-a",
            microsoft_object_id="object-owner" if owner else "object-tech",
            jason_identity_id="person-owner" if owner else "person-tech",
        )

    def find_active_by_jason_identity(self, *, jason_identity_id):
        if jason_identity_id == "person-owner":
            return MicrosoftIdentityBinding(
                microsoft_tenant_id="tenant-a",
                microsoft_object_id="object-owner",
                jason_identity_id="person-owner",
            )
        return None

    def find(self, *, microsoft_tenant_id, microsoft_object_id):
        if microsoft_tenant_id == self.binding.microsoft_tenant_id and microsoft_object_id == self.binding.microsoft_object_id:
            return self.binding
        return None


def build(tmp_path):
    registry = tmp_path / "registry.json"
    write_registry(registry)
    promotions = SQLitePlaybookAutonomyApprovalStore(tmp_path / "promotions.sqlite3")
    requests = SQLiteApprovalRequestRepository(tmp_path / "requests.sqlite3")
    review = PlaybookAutonomyReviewService(
        registry_path=registry,
        promotion_store=promotions,
        owner_identity_ids=frozenset({"person-owner"}),
        audit_path=tmp_path / "audit.jsonl",
    )
    approval_service = ApprovalRequestService(
        repository=requests,
        authority=OwnerOnlyPlaybookAutonomyAuthority({"person-owner"}),
    )
    return registry, promotions, requests, review, approval_service


def test_maintenance_sends_one_owner_card_for_unpromoted_scope(tmp_path):
    registry, promotions, requests, review, _ = build(tmp_path)
    sender = Sender()
    maintenance = PlaybookAutonomyReviewMaintenance(
        enabled=True,
        registry_path=registry,
        request_repository=requests,
        approval_service=ApprovalRequestService(
            repository=requests,
            authority=OwnerOnlyPlaybookAutonomyAuthority({"person-owner"}),
        ),
        review_service=review,
        sender=sender,
        promotion_store=promotions,
        interval_seconds=300,
        now=lambda: NOW,
    )
    assert maintenance.tick() is True
    assert len(sender.requests) == 1
    stored = requests.list_all()
    assert len(stored) == 1
    assert stored[0].metadata["playbook_id"] == "demo"
    assert stored[0].metadata["delivery_message_ids"] == "teams-1"
    assert maintenance.tick() is False
    assert len(sender.requests) == 1


def test_owner_card_approval_creates_durable_promotion(tmp_path):
    registry, promotions, requests, review, approval_service = build(tmp_path)
    request = review.build_request(
        playbook_id="demo", requested_by="person-tech", now=NOW,
        approval_id="pbautreq-1", request_id="req-1", correlation_id="corr-1",
    )
    approval_service.create(request, now=NOW)
    flow = PlaybookAutonomyApprovalInteractionFlow(
        bindings=Bindings(owner=True),
        approval_service=approval_service,
        review_service=review,
    )
    result = flow.handle(
        approval_id=request.approval_id,
        decision="approve",
        microsoft_tenant_id="tenant-a",
        microsoft_object_id="object-owner",
        conversation_id="conversation-1",
        channel_response_id="teams-message-1",
        decided_at=NOW + timedelta(minutes=1),
    )
    assert result["status"] == "completed"
    assert "promoted" in result["reply"]["text"].lower()
    promotion = promotions.find_scope_approved(
        playbook_id="demo", playbook_version="1.0.0",
        policy_id="playbook-autonomy:demo",
        required_capabilities=("service.ticket.note.create",),
    )
    assert promotion is not None
    assert promotion.approved_by == "person-owner"


def test_technician_card_click_cannot_promote(tmp_path):
    _, promotions, _, review, approval_service = build(tmp_path)
    request = review.build_request(
        playbook_id="demo", requested_by="person-tech", now=NOW,
        approval_id="pbautreq-1", request_id="req-1", correlation_id="corr-1",
    )
    approval_service.create(request, now=NOW)
    flow = PlaybookAutonomyApprovalInteractionFlow(
        bindings=Bindings(owner=False),
        approval_service=approval_service,
        review_service=review,
    )
    with pytest.raises(PermissionError):
        flow.handle(
            approval_id=request.approval_id,
            decision="approve",
            microsoft_tenant_id="tenant-a",
            microsoft_object_id="object-tech",
            conversation_id="conversation-1",
            channel_response_id="teams-message-1",
            decided_at=NOW + timedelta(minutes=1),
        )
    assert promotions.list_all() == ()


def test_request_changes_does_not_promote_and_suppresses_same_fingerprint_rerequest(tmp_path):
    registry, promotions, requests, review, approval_service = build(tmp_path)
    request = review.build_request(
        playbook_id="demo", requested_by="person-tech", now=NOW,
        approval_id="pbautreq-1", request_id="req-1", correlation_id="corr-1",
    )
    approval_service.create(request, now=NOW)
    flow = PlaybookAutonomyApprovalInteractionFlow(
        bindings=Bindings(owner=True),
        approval_service=approval_service,
        review_service=review,
    )
    result = flow.handle(
        approval_id=request.approval_id,
        decision="request_changes",
        microsoft_tenant_id="tenant-a",
        microsoft_object_id="object-owner",
        conversation_id="conversation-1",
        channel_response_id="teams-message-1",
        decided_at=NOW + timedelta(minutes=1),
    )
    assert "not promoted" in result["reply"]["text"].lower()
    assert promotions.list_all() == ()

    sender = Sender()
    maintenance = PlaybookAutonomyReviewMaintenance(
        enabled=True,
        registry_path=registry,
        request_repository=requests,
        approval_service=ApprovalRequestService(
            repository=requests,
            authority=OwnerOnlyPlaybookAutonomyAuthority({"person-owner"}),
        ),
        review_service=review,
        sender=sender,
        promotion_store=promotions,
        interval_seconds=300,
        now=lambda: NOW + timedelta(minutes=10),
    )
    assert maintenance.tick() is False
    assert sender.requests == []



def owner_pilot_policy_fixture(tmp_path, *, values=None, mode=0o600):
    record = {
        "schema_version": "1.0",
        "organization_id": "aot",
        "capability": "playbook.autonomy.promote",
        "policy_mode": "owner_only_test",
        "owner_identity_ids": ["person-owner"],
        "allowed_requested_modes": ["promote:backupiq_endpoint_backup@1.2.0"],
    }
    if values:
        record.update(values)
    policy = tmp_path / "owner.json"
    policy.write_text(json.dumps(record), encoding="utf-8")
    policy.chmod(mode)
    return policy


def test_owner_pilot_missing_file_preserves_legacy_gate(tmp_path):
    result = load_playbook_owner_approval_policy(
        path=tmp_path / "absent.json",
        legacy_owner_identity_ids=("person-legacy",),
    )
    assert result.owner_identity_ids == frozenset({"person-legacy"})
    assert result.allowed_requested_modes is None


def test_owner_pilot_one_actor_one_exact_mode(tmp_path):
    policy = owner_pilot_policy_fixture(tmp_path)
    result = load_playbook_owner_approval_policy(
        path=policy, legacy_owner_identity_ids=("person-other",),
    )
    assert result.owner_identity_ids == frozenset({"person-owner"})
    assert result.allowed_requested_modes == frozenset({"promote:backupiq_endpoint_backup@1.2.0"})
    authority = OwnerOnlyPlaybookAutonomyAuthority(
        result.owner_identity_ids,
        allowed_requested_modes=result.allowed_requested_modes,
    )
    common = dict(organization_id="aot", client_id=None, capability="playbook.autonomy.promote")
    assert authority.can_approve(approver_identity_id="person-owner",
                                 requested_mode="promote:backupiq_endpoint_backup@1.2.0", **common)
    assert not authority.can_approve(approver_identity_id="person-other",
                                     requested_mode="promote:backupiq_endpoint_backup@1.2.0", **common)
    assert not authority.can_approve(approver_identity_id="person-owner",
                                     requested_mode="promote:unrelated@1.0.0", **common)
    assert not authority.can_approve(approver_identity_id="person-owner",
                                     organization_id="other", client_id=None,
                                     capability="playbook.autonomy.promote",
                                     requested_mode="promote:backupiq_endpoint_backup@1.2.0")


@pytest.mark.parametrize("modification", [
    {"owner_identity_ids": ["person-owner", "person-other"]},
    {"allowed_requested_modes": ["promote:backupiq_endpoint_backup@1.2.0", "promote:other@1.0.0"]},
    {"organization_id": "other"},
    {"capability": "service.ticket.update"},
    {"policy_mode": "production"},
    {"schema_version": "2.0"},
    {"unexpected_key": True},
])
def test_owner_pilot_rejects_broad_or_unreviewed_scope(tmp_path, modification):
    policy = owner_pilot_policy_fixture(tmp_path, values=modification)
    with pytest.raises(PermissionError):
        load_playbook_owner_approval_policy(path=policy, legacy_owner_identity_ids=("person-legacy",))


def test_owner_pilot_rejects_insecure_mode_and_symlink(tmp_path):
    policy = owner_pilot_policy_fixture(tmp_path, mode=0o644)
    with pytest.raises(PermissionError, match="0600"):
        load_playbook_owner_approval_policy(path=policy, legacy_owner_identity_ids=())
    policy.chmod(0o600)
    link = tmp_path / "link.json"
    link.symlink_to(policy)
    with pytest.raises(PermissionError, match="regular file"):
        load_playbook_owner_approval_policy(path=link, legacy_owner_identity_ids=())



def test_owner_only_pilot_fails_closed_without_preexisting_promotion(tmp_path):
    registry, promotions, requests, review, _ = build(tmp_path)
    service = ApprovalRequestService(
        repository=requests,
        authority=OwnerOnlyPlaybookAutonomyAuthority(
            {"person-owner"},
            allowed_requested_modes=frozenset({"promote:demo@1.0.0"}),
        ),
    )
    request = review.build_request(
        playbook_id="demo", requested_by="svc-test",
        now=NOW, ttl=timedelta(minutes=10),
    )
    service.create(request, now=NOW)
    flow = PlaybookAutonomyApprovalInteractionFlow(
        bindings=Bindings(owner=True),
        approval_service=service,
        review_service=review,
    )
    with pytest.raises(PermissionError, match="requires existing exact promotion"):
        flow.handle(
            approval_id=request.approval_id,
            decision="approve",
            microsoft_tenant_id="tenant-a",
            microsoft_object_id="object-owner",
            conversation_id="test-conversation",
            channel_response_id="test-owner-click",
            decided_at=NOW + timedelta(minutes=1),
        )
    assert requests.get(request.approval_id).status.value == "pending"
    assert requests.accepted_decision(request.approval_id) is None
    assert promotions.list_all() == ()
