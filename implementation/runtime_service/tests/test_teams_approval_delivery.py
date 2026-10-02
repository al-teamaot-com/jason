from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json

import pytest

from orchestrator.approval_requests import ApprovalPresentation, ApprovalRequest
from jason_runtime.teams_approval_delivery import TeamsGatewayApprovalSender
import jason_runtime.teams_gateway_transport as transport


NOW = datetime(2026, 10, 2, 18, 0, tzinfo=timezone.utc)


class Binding:
    status = "active"
    microsoft_object_id = "object-owner"
    microsoft_tenant_id = "tenant-a"


class Bindings:
    def __init__(self, found=True):
        self.found = found

    def find_active_by_jason_identity(self, *, jason_identity_id):
        if self.found and jason_identity_id == "person-owner":
            return Binding()
        return None


class Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def request():
    return ApprovalRequest(
        approval_id="approval-1",
        request_id="request-1",
        correlation_id="corr-1",
        organization_id="aot",
        client_id=None,
        requested_by="jason-test",
        capability="playbook.autonomy.promote",
        requested_mode="promote:demo",
        requested_at=NOW,
        expires_at=NOW + timedelta(hours=1),
        authorized_approver_ids=("person-owner",),
        presentation=ApprovalPresentation(
            title="Approve demo",
            summary="Approve exact demo scope",
            facts=(("Playbook", "demo"),),
        ),
    )


def test_shared_teams_approval_sender_delivers_exact_bound_recipient(tmp_path, monkeypatch):
    token = tmp_path / "token"
    token.write_text("secret-token", encoding="utf-8")
    captured = {}

    def fake_urlopen(http_request, timeout):
        captured["url"] = http_request.full_url
        captured["timeout"] = timeout
        captured["payload"] = json.loads(http_request.data.decode("utf-8"))
        return Response({"status": "succeeded", "message_id": "teams-1"})

    monkeypatch.setattr(transport, "urlopen", fake_urlopen)
    sender = TeamsGatewayApprovalSender(
        gateway_url="http://teams-gateway:3979",
        token_file=token,
        bindings=Bindings(),
        recipient_identity_ids=("person-owner",),
    )

    assert sender.send(request()) == ("teams-1",)
    assert captured["url"].endswith("/internal/proactive/send")
    assert captured["payload"]["aadObjectId"] == "object-owner"
    assert captured["payload"]["tenantId"] == "tenant-a"
    assert captured["payload"]["text"] == "Approve exact demo scope"
    assert captured["payload"]["card"]["type"] == "AdaptiveCard"


def test_shared_teams_approval_sender_fails_closed_on_missing_binding(tmp_path):
    token = tmp_path / "token"
    token.write_text("secret-token", encoding="utf-8")
    sender = TeamsGatewayApprovalSender(
        gateway_url="http://teams-gateway:3979",
        token_file=token,
        bindings=Bindings(found=False),
        recipient_identity_ids=("person-owner",),
    )

    with pytest.raises(PermissionError, match="binding unavailable"):
        sender.send(request())
