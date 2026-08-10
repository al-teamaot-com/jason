from datetime import datetime, timedelta, timezone
import unittest

from connectors.microsoft_graph.teams_approval_delivery import (
    InMemoryTeamsApprovalTargetResolver,
    TeamsApprovalDeliveryChannel,
    TeamsApprovalDeliveryTarget,
)
from connectors.src.jason_connectors.approval_requests import ApprovalRequest


NOW = datetime(2026, 8, 9, 17, 0, tzinfo=timezone.utc)


class Transport:
    def __init__(self, response=None):
        self.calls = []
        self.response = response or {"id": "msg-1", "createdDateTime": NOW.isoformat()}

    def post_channel_message(self, *, team_id, channel_id, message):
        self.calls.append((team_id, channel_id, message))
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


class TeamsApprovalDeliveryTests(unittest.TestCase):
    def channel(self, *, org="org-a", target_org="org-a", response=None):
        transport = Transport(response=response)
        resolver = InMemoryTeamsApprovalTargetResolver({
            org: TeamsApprovalDeliveryTarget(target_org, "team-1", "channel-1")
        })
        return TeamsApprovalDeliveryChannel(transport, resolver), transport

    def test_delivers_card_and_returns_opaque_receipt(self):
        channel, transport = self.channel()
        receipt = channel.deliver(request())
        self.assertEqual(receipt.channel, "microsoft_teams")
        self.assertEqual(receipt.channel_reference_id, "msg-1")
        self.assertEqual(receipt.delivered_at, NOW)
        team_id, channel_id, message = transport.calls[0]
        self.assertEqual((team_id, channel_id), ("team-1", "channel-1"))
        content = message["attachments"][0]["content"]
        self.assertEqual(content["actions"][0]["data"]["approval_id"], "approval-1")
        self.assertNotIn("requested_by", str(message))
        self.assertNotIn("client_id", str(message))

    def test_missing_target_fails_before_transport(self):
        transport = Transport()
        channel = TeamsApprovalDeliveryChannel(transport, InMemoryTeamsApprovalTargetResolver({}))
        with self.assertRaises(PermissionError):
            channel.deliver(request())
        self.assertEqual(transport.calls, [])

    def test_cross_tenant_target_fails_before_transport(self):
        channel, transport = self.channel(target_org="org-b")
        with self.assertRaises(PermissionError):
            channel.deliver(request())
        self.assertEqual(transport.calls, [])

    def test_missing_message_id_fails_closed(self):
        channel, _ = self.channel(response={"createdDateTime": NOW.isoformat()})
        with self.assertRaises(RuntimeError):
            channel.deliver(request())

    def test_invalid_response_time_fails_closed(self):
        channel, _ = self.channel(response={"id": "msg-1", "createdDateTime": "bad"})
        with self.assertRaises(RuntimeError):
            channel.deliver(request())


if __name__ == "__main__":
    unittest.main()
