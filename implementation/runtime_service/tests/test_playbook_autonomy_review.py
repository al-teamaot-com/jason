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
