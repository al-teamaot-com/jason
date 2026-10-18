"""No-network parity and fail-closed tests for first Teams notification adapter."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from communication.audience.models import AudienceType, MessagePurpose
from jason_runtime.autonomous_completion_notification import _render
from jason_runtime.autonomous_completion_teams_compatibility import (
    ExistingOwnerStatusRouteGuard,
    GovernedAutonomyStatusInteractionPort,
    RECIPIENT, WORKFLOW, prepare_status_notice_preview,
)
from jason_runtime.universal_interaction.contracts import InteractionKind, VisualIntent
from jason_runtime.universal_interaction.service import (
    AuthorizedRoute, ChannelFeatures, ExistingApprovalGuard,
    InteractionDelivery, InteractionRejected, UniversalInteractionService,
)


def examples():
    common = {"work_id": "SUPPORT-OPS-1566", "work_title": "Verified disk cleanup",
              "summary": "Read-only evidence and verification completed."}
    return [
        ({"event_type": "work_started", **common},
         InteractionKind.PROGRESS, VisualIntent.INFORMATION, "Accent"),
        ({"event_type": "ticket_status_updated", **common},
         InteractionKind.PROGRESS, VisualIntent.INFORMATION, "Accent"),
        ({"event_type": "work_completed", **common},
         InteractionKind.NOTICE, VisualIntent.SUCCESS, "Good"),
    ]


def preview(arguments, **overrides):
    args = dict(
        arguments=arguments,
        execution_id="exec_autonomy_1566_001",
        correlation_id="corr_autonomy_1566_001",
        principal_id="jason-autonomy-worker",
        organization_id="aot",
        client_id=None,
    )
    args.update(overrides)
    return prepare_status_notice_preview(**args)


@pytest.mark.parametrize("arguments,kind,visual,color", examples())
def test_semantic_status_preview_is_full_legacy_content_not_a_new_message(
        arguments, kind, visual, color):
    legacy_event, legacy_text, old = _render(arguments)
    # Block the ONLY existing gateway POST even if a dependency were miswired.
    with patch("jason_runtime.teams_message_send.post_existing_teams_gateway",
               side_effect=AssertionError("shadow preview attempted Teams POST")) as gateway:
        result = preview(arguments)
    gateway.assert_not_called()
    spec = result.interaction
    assert result.event_type == legacy_event
    assert result.recipient_identity_id == RECIPIENT == "person-al"
    assert result.legacy_text == legacy_text
    assert result.legacy_card == old
    assert spec.summary == legacy_text
    assert spec.title == old["body"][0]["text"]
    assert spec.kind == kind
    assert spec.visual_intent == visual
    assert spec.workflow == WORKFLOW
    assert spec.requester_identity_id == "jason-autonomy-worker"
    assert spec.organization_id == "aot" and spec.client_id is None
    assert spec.interaction_id == "exec_autonomy_1566_001"
    assert spec.correlation_id == "corr_autonomy_1566_001"
    assert spec.approval_id is None and not spec.actions and not spec.fields
    assert result.canonical_card["type"] == "AdaptiveCard"
    assert result.canonical_card["version"] == "1.5"
    assert result.canonical_card["body"][0]["color"] == color
    assert result.canonical_card["body"][1]["text"] == legacy_text
    assert result.canonical_card["body"][2]["facts"] == old["body"][2]["facts"]
    assert "actions" not in result.canonical_card


@pytest.mark.parametrize("bad_event,bad_args", [
    ("work_blocked", {"work_id": "TODO-1", "work_title": "Repair",
                      "summary": "Needs owner", "owner_action": "Review this issue"}),
    ("production_owner_action_required", {"work_id": "release-abc",
                       "summary": "Release approval needed",
                       "candidate_sha": "a"*40,
                       "owner_action": "Approve exact SHA"}),
    ("self_heal_escalation", {"degraded_function": "jason-core",
                      "evidence_summary": "Unhealthy", "attempt_summary": "Rechecked",
                      "owner_action": "Investigate"}),
    ("deployment_completed", {"candidate_sha": "a"*40, "support_item": "SUPPORT-1"}),
    ("support_item_resolved", {"support_item": "SUPPORT-1",
                      "resolution_summary": "Passed verification"}),
])
def test_no_approval_blocked_work_release_or_escalation_presentation(
        bad_event, bad_args):
    with pytest.raises(PermissionError, match="separately reviewed"):
        preview({"event_type": bad_event, **bad_args})


@pytest.mark.parametrize("bad", [
    {"principal_id": "person-al"},
    {"principal_id": "jason-prod-owner"},
    {"organization_id": "other-tenant"},
    {"client_id": "customer-1"},
])
def test_adapter_keeps_same_sender_organization_and_no_external_client(bad):
    with pytest.raises(PermissionError, match="cannot broaden"):
        preview(examples()[0][0], **bad)


def test_no_arbitrary_fields_or_unbounded_or_unstable_ids():
    with pytest.raises(ValueError, match="unsupported"):
        preview({**examples()[0][0], "recipient": "somebody"})
    with pytest.raises(ValueError, match="interaction_id"):
        preview(examples()[0][0], execution_id="unsafe id")
    with pytest.raises(ValueError, match="correlation_id"):
        preview(examples()[0][0], correlation_id="unsafe id")
    with pytest.raises(TypeError):
        preview(None)


class Route:
    def __init__(self, *, recipient=RECIPIENT, purpose=MessagePurpose.OPERATIONAL,
                 org="aot", audience=AudienceType.EXECUTIVE, channels=("teams",)):
        self.recipient, self.purpose = recipient, purpose
        self.org, self.audience, self.channels = org, audience, channels
        self.called = 0

    def authorize(self, spec):
        self.called += 1
        return AuthorizedRoute(
            recipient_identity_id=self.recipient, organization_id=self.org,
            client_id=None, audience_type=self.audience, purpose=self.purpose,
            channels=self.channels, authorization_ref="existing-owner-status-readback",
            allowed=True,
        )


class Journal:
    def __init__(self):
        self.claimed, self.accepted_receipts, self.uncertain_ids = set(), [], []

    def claim(self, spec, route):
        if spec.interaction_id in self.claimed:
            raise InteractionRejected("delivery already claimed")
        self.claimed.add(spec.interaction_id)

    def accepted(self, spec, receipt):
        self.accepted_receipts.append(receipt)

    def uncertain(self, spec):
        self.uncertain_ids.append(spec.interaction_id)


class Adapter:
    channel_id = "teams"
    features = ChannelFeatures(notices=True)
    def __init__(self):
        self.calls = []
    def deliver(self, spec, route):
        self.calls.append((spec, route))
        return InteractionDelivery(
            interaction_id=spec.interaction_id, channel_id="teams",
            recipient_identity_id=route.recipient_identity_id,
            message_id="accepted:fixture", state="provider_accepted",
        )


def service(route=None):
    route = route or Route()
    channel, journal = Adapter(), Journal()
    uis = UniversalInteractionService(
        authority=route, channels={"teams": channel}, audit=journal,
        approvals=ExistingApprovalGuard(requests=None),
        approval_dispatch_enabled=False,
        clock=lambda: datetime(2026, 10, 18, 10, 0, tzinfo=timezone.utc),
    )
    return uis, route, channel, journal


def test_canonical_single_sender_dispatch_uses_existing_service_and_claim():
    uis, route, channel, journal = service()
    port = GovernedAutonomyStatusInteractionPort(uis)
    prepared = preview(examples()[0][0])
    assert channel.calls == []
    assert journal.claimed == set()
    receipt = port.dispatch_prepared(prepared)
    assert receipt.state == "provider_accepted"
    assert receipt.message_id == "accepted:fixture"
    assert len(channel.calls) == len(journal.accepted_receipts) == 1
    assert route.called == 1  # no pre-check / post-check route race
    with pytest.raises(InteractionRejected, match="already claimed"):
        port.dispatch_prepared(prepared)
    assert len(channel.calls) == 1  # no duplicate provider delivery
    assert route.called == 2


@pytest.mark.parametrize("route", [
    Route(recipient="person-other"),
    Route(org="other-tenant"),
    Route(audience=AudienceType.CLIENT_END_USER),
    Route(channels=("email",)),
    Route(purpose=MessagePurpose.APPROVAL_REQUEST),
])
def test_existing_authority_must_reconfirm_fixed_owner_teams_route(route):
    uis, _, channel, journal = service(route)
    with pytest.raises(InteractionRejected, match="existing AOT owner Teams route"):
        GovernedAutonomyStatusInteractionPort(uis).dispatch_prepared(preview(examples()[0][0]))
    assert channel.calls == [] and not journal.claimed


def test_ticket_route_requires_ticket_update_purpose():
    item = preview(examples()[1][0])
    uis, _, channel, journal = service(Route(purpose=MessagePurpose.TICKET_UPDATE))
    assert GovernedAutonomyStatusInteractionPort(uis).dispatch_prepared(item).state == "provider_accepted"
    assert len(channel.calls) == 1
    uis, _, channel, journal = service(Route(purpose=MessagePurpose.OPERATIONAL))
    with pytest.raises(InteractionRejected, match="existing AOT owner Teams route"):
        GovernedAutonomyStatusInteractionPort(uis).dispatch_prepared(item)
    assert channel.calls == [] and not journal.claimed


def test_tampered_preview_can_never_change_recipient():
    item = replace(preview(examples()[0][0]), recipient_identity_id="person-other")
    uis, _, channel, journal = service()
    with pytest.raises(PermissionError, match="cannot broaden"):
        GovernedAutonomyStatusInteractionPort(uis).dispatch_prepared(item)
    assert channel.calls == [] and not journal.claimed
