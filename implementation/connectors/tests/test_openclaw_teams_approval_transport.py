from datetime import datetime, timedelta, timezone

import pytest

from connectors.microsoft_graph.openclaw_teams_approval_transport import (
    InMemoryOpenClawTeamsApprovalTargetResolver,
    OpenClawTeamsApprovalDeliveryChannel,
    OpenClawTeamsApprovalTarget,
)
from connectors.src.jason_connectors.approval_requests import ApprovalRequest


NOW = datetime(2026, 8, 10, 15, 0, tzinfo=timezone.utc)


class Gateway:
    def __init__(self, response=None):
        self.calls = []
        self.response = response or {"messageId": "teams-message-1", "channel": "msteams"}

    def request(self, *, method, params):
        self.calls.append((method, params))
        return self.response


def request(org="org-a"):
    return ApprovalRequest(
        approval_id="approval-1",
        request_id="exec-1",
        correlation_id="corr-1",
        organization_id=org,
        client_id="client-1",
        requested_by="user-1",
        capability="autotask.ticket.update",
        requested_mode="execute",
        requested_at=NOW,
        expires_at=NOW + timedelta(minutes=10),
        authorized_approver_ids=("approver-1",),
    )


def channel(*, org="org-a", target_org="org-a", response=None):
    gateway = Gateway(response=response)
    targets = InMemoryOpenClawTeamsApprovalTargetResolver(
        {org: OpenClawTeamsApprovalTarget(target_org, "conversation-ref-1")}
    )
    return OpenClawTeamsApprovalDeliveryChannel(gateway=gateway, targets=targets), gateway


def test_delivers_through_openclaw_send_with_deterministic_idempotency_key():
    delivery, gateway = channel()
    receipt = delivery.deliver(request())

    assert receipt.channel == "microsoft_teams"
    assert receipt.channel_reference_id == "teams-message-1"
    method, params = gateway.calls[0]
    assert method == "send"
    assert params["channel"] == "msteams"
    assert params["to"] == "conversation-ref-1"
    assert params["idempotencyKey"] == "jason-approval:org-a:approval-1"
    card = params["payload"]["channelData"]["msteams"]["presentationCard"]
    assert card["actions"][0]["data"] == {
        "approval_id": "approval-1",
        "organization_id": "org-a",
        "decision": "approve",
    }
    assert "requested_by" not in str(params)
    assert "client_id" not in str(params)


def test_missing_target_fails_before_gateway():
    gateway = Gateway()
    delivery = OpenClawTeamsApprovalDeliveryChannel(
        gateway=gateway,
        targets=InMemoryOpenClawTeamsApprovalTargetResolver({}),
    )
    with pytest.raises(PermissionError):
        delivery.deliver(request())
    assert gateway.calls == []


def test_cross_organization_target_fails_before_gateway():
    delivery, gateway = channel(target_org="org-b")
    with pytest.raises(PermissionError):
        delivery.deliver(request())
    assert gateway.calls == []


def test_missing_message_id_fails_closed():
    delivery, _ = channel(response={"channel": "msteams"})
    with pytest.raises(RuntimeError):
        delivery.deliver(request())


def test_unexpected_delivery_channel_fails_closed():
    delivery, _ = channel(response={"messageId": "m-1", "channel": "slack"})
    with pytest.raises(RuntimeError):
        delivery.deliver(request())
