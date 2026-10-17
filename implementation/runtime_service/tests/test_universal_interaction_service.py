"""True Jason sender + event-store integration tests. No provider writes."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from communication.audience.engine import AudiencePolicyEngine
from communication.audience.models import AudienceType, MessagePurpose, ReviewDecision
from connectors.src.jason_connectors.approval_requests import (
    ApprovalPresentation, ApprovalRequest, InMemoryApprovalRequestRepository,
)
from jason_runtime.teams_communication_service import (
    JasonTeamsCommunicationService, TeamsDeliveryReceipt,
)
from jason_runtime.universal_interaction import (
    Action, ActionType, AuthorizedRoute, ChannelFeatures, Condition,
    ExistingApprovalGuard, ExistingTeamsInteractionAdapter,
    Fact, Field, FieldType, Interaction, InteractionDelivery, InteractionKind,
    InteractionRejected, Option, OrchestrationInteractionJournal,
    UniversalInteractionService, VisualIntent, validate_answers,
)
from orchestrator.event_store import SQLiteOrchestrationEventStore

NOW = datetime.now(timezone.utc).replace(microsecond=0)


class Transport:
    def __init__(self):
        self.calls = []
        self.raise_error = None

    def send(self, *, binding, text, card=None):
        self.calls.append((binding, text, card))
        if self.raise_error:
            raise self.raise_error
        return TeamsDeliveryReceipt("accepted:test-provider-reference", "chat-test", binding.jason_identity_id)


class Authority:
    def __init__(self, route):
        self.route = route
        self.calls = 0

    def authorize(self, spec):
        self.calls += 1
        return self.route


class Portal:
    channel_id = "portal"
    features = ChannelFeatures(
        notices=True, forms=True, approvals=False,
        authenticated_responses=True, supported_fields=frozenset(FieldType),
    )
    def __init__(self):
        self.calls = []

    def deliver(self, spec, route):
        self.calls.append((spec, route))
        return InteractionDelivery(spec.interaction_id, self.channel_id,
                                   route.recipient_identity_id, "portal-accepted")


def notice(**updates):
    args = dict(
        interaction_id="ui.notice.1", workflow="ops_status",
        correlation_id="trace.ops.1", organization_id="aot",
        requester_identity_id="svc-jason", kind=InteractionKind.NOTICE,
        title="Endpoint status", summary="Investigation complete",
        visual_intent=VisualIntent.SUCCESS,
        facts=(Fact("Affected device", "claw2-pc"), Fact("State", "healthy")),
    )
    args.update(updates)
    return Interaction(**args)


def po(**updates):
    args = dict(
        interaction_id="ui.po.1", workflow="procurement",
        correlation_id="trace.po.1", organization_id="aot",
        requester_identity_id="svc-procurement",
        kind=InteractionKind.QUESTIONNAIRE, title="PO information",
        summary="Supply the requested purchasing information",
        visual_intent=VisualIntent.ACTION_REQUIRED,
        facts=(Fact("Vendor", "Existing supplier"),),
        fields=(
            Field("item", "Item description", FieldType.TEXT, required=True),
            Field("quantity", "Quantity", FieldType.NUMBER, required=True,
                  minimum="1", maximum="100"),
            Field("unit_price", "Unit price", FieldType.CURRENCY, required=True,
                  currency="USD", minimum="0.01", maximum="9999.99"),
            Field("ticket", "Related ticket", FieldType.SELECT, required=True,
                  options=(Option("none", "No ticket"), Option("T20261017.0001", "Existing ticket"))),
            Field("create_quote", "Client quote needed?", FieldType.BOOLEAN),
            Field("contact", "Client contact", FieldType.TEXT, required=True,
                  show_when=Condition("create_quote", True)),
        ),
        actions=(Action("send", "Submit PO request", ActionType.SUBMIT),),
    )
    args.update(updates)
    return Interaction(**args)


def persisted_approval():
    return ApprovalRequest(
        approval_id="approval.test.1", request_id="work.one",
        correlation_id="trace.approval.1",
        organization_id="aot", client_id=None,
        requested_by="svc-release", capability="test.nonexecuting.approval",
        requested_mode="harmless:test", requested_at=NOW,
        expires_at=NOW + timedelta(hours=1),
        authorized_approver_ids=("owner-al",),
        presentation=ApprovalPresentation(
            title="Harmless test request", summary="Review only, no execution",
            facts=(("Scope", "No systems affected"),),
        ),
    )


def approval(existing):
    return notice(
        interaction_id="ui.approval.1", workflow="owner_release",
        correlation_id=existing.correlation_id,
        requester_identity_id=existing.requested_by,
        kind=InteractionKind.APPROVAL, title="Harmless test request",
        summary=existing.presentation.summary,
        visual_intent=VisualIntent.ACTION_REQUIRED,
        facts=(Fact("Scope", "No systems affected"),),
        actions=(
            Action("yes", "Approve", ActionType.APPROVE),
            Action("no", "Deny", ActionType.DENY),
        ),
        approval_id=existing.approval_id, expires_at=existing.expires_at,
    )


def route(*, channel="teams", purpose=MessagePurpose.OPERATIONAL, **changes):
    args = dict(
        recipient_identity_id="owner-al", organization_id="aot", client_id=None,
        audience_type=AudienceType.INTERNAL_TECHNICIAN,
        purpose=purpose, channels=(channel,), authorization_ref="jkd:route:1",
        allowed=True,
    )
    args.update(changes)
    return AuthorizedRoute(**args)


@pytest.fixture
def harness(tmp_path):
    events = SQLiteOrchestrationEventStore(tmp_path / "existing-orchestration.db")
    tr = Transport()
    approvals = InMemoryApprovalRequestRepository()
    identity = SimpleNamespace(identity_id="owner-al", status="active", organization_id="aot")
    binding = SimpleNamespace(status="active", jason_identity_id="owner-al",
                              microsoft_tenant_id="f7054323-d52b-4863-8c2f-1898f0b6077c",
                              microsoft_object_id="bee80bdc-ffb0-4c50-b453-c09d4d411f5f")
    sender = JasonTeamsCommunicationService(
        transport=tr,
        bindings=SimpleNamespace(find_active_by_jason_identity=lambda **kw: binding),
        identities=SimpleNamespace(get=lambda identity_id: identity),
        workflow_authority=SimpleNamespace(can_communicate=lambda **kw: True),
        approval_requests=approvals, audience=AudiencePolicyEngine(),
    )
    teams = ExistingTeamsInteractionAdapter(sender)
    auth = Authority(route())
    svc = UniversalInteractionService(
        authority=auth, channels={"teams": teams},
        audit=OrchestrationInteractionJournal(events=events),
        approvals=ExistingApprovalGuard(approvals),
    )
    yield SimpleNamespace(svc=svc, transport=tr, approvals=approvals,
                          events=events, auth=auth, teams=teams, sender=sender)
    events.close()


def test_real_existing_teams_sender_creates_status_card_and_audits(harness):
    result = harness.svc.dispatch(notice())
    assert result.state == "provider_accepted"
    assert result.message_id == "accepted:test-provider-reference"
    assert len(harness.transport.calls) == 1
    _, text, card = harness.transport.calls[0]
    assert "claw2-pc" in text  # facts also pass existing audience review
    assert card["type"] == "AdaptiveCard"
    assert card["body"][0]["color"] == "Good"
    assert "actions" not in card
    stages = [e.stage for e in harness.events.list_by_execution("ui.notice.1")]
    assert stages == ["claimed", "provider_accepted"]


def test_journal_prevents_duplicate_delivery_even_across_service_recreation(harness):
    harness.svc.dispatch(notice())
    svc2 = replace(harness.svc)
    with pytest.raises(InteractionRejected, match="already claimed"):
        svc2.dispatch(notice())
    assert len(harness.transport.calls) == 1


def test_ambiguous_teams_send_stays_claimed_without_retry(harness):
    harness.transport.raise_error = TimeoutError("unknown provider acceptance")
    with pytest.raises(TimeoutError):
        harness.svc.dispatch(notice())
    with pytest.raises(InteractionRejected, match="already claimed"):
        harness.svc.dispatch(notice())
    assert len(harness.transport.calls) == 1
    assert [e.stage for e in harness.events.list_by_execution("ui.notice.1")] == [
        "claimed", "reconciliation_required",
    ]


@pytest.mark.parametrize("override", [
    {"allowed": False}, {"organization_id": "foreign"},
    {"client_id": "other"}, {"authorization_ref": ""},
    {"recipient_identity_id": ""}, {"channels": ()},
])
def test_no_authorized_route_means_no_send(harness, override):
    harness.auth.route = replace(harness.auth.route, **override)
    with pytest.raises(InteractionRejected):
        harness.svc.dispatch(notice())
    assert harness.transport.calls == []


def test_expired_interaction_fails_before_authority_or_delivery(harness):
    with pytest.raises(InteractionRejected, match="expired"):
        harness.svc.dispatch(notice(expires_at=NOW-timedelta(seconds=10)))
    assert harness.auth.calls == 0


def test_unrecognized_channel_requires_safe_handoff_or_rejection(harness):
    harness.auth.route = route(channel="sms")
    with pytest.raises(InteractionRejected, match="no authorized channel"):
        harness.svc.dispatch(notice())
    assert harness.transport.calls == []


def test_synthetic_second_channel_proves_contract_is_channel_neutral(harness):
    portal = Portal()
    harness.svc.channels = {"portal": portal, "teams": harness.teams}
    harness.auth.route = route(channels=("portal", "teams"))
    receipt = harness.svc.dispatch(notice())
    assert receipt.channel_id == "portal"
    assert len(portal.calls) == 1
    assert harness.transport.calls == []


def test_portal_can_accept_po_form_without_new_teams_or_business_engine(harness):
    portal = Portal()
    harness.svc.channels = {"portal": portal}
    harness.auth.route = route(channel="portal", purpose=MessagePurpose.FINANCIAL)
    result = harness.svc.dispatch(po())
    assert result.channel_id == "portal"
    assert portal.calls[0][0].fields[2].currency == "USD"


def test_registered_po_card_uses_existing_sender_and_callback_registry(harness):
    # Explicit registered procurement callback; NOT a new generic Teams
    # submission endpoint. Existing financial audience policy still rules.
    rendered = []
    def renderer(spec):
        rendered.append(spec.workflow)
        return {"type": "AdaptiveCard", "version": "1.5",
                "body": [{"type": "TextBlock", "text": spec.title}],
                "actions": [{"type": "Action.Submit", "title": "Send",
                             "data": {"procurement_submission": "registered-existing"}}]}
    harness.teams.registered_questionnaire_callbacks = frozenset({"procurement"})
    harness.teams.questionnaire_renderers = {"procurement": renderer}
    harness.auth.route = route(purpose=MessagePurpose.FINANCIAL)
    with pytest.raises(PermissionError, match="content review"):
        harness.svc.dispatch(po())
    assert rendered == ["procurement"]
    assert harness.transport.calls == []  # financial audience was not approved


def test_registered_po_form_with_authorized_financial_audience(harness):
    harness.sender.audience = SimpleNamespace(
        review=lambda draft: SimpleNamespace(decision=ReviewDecision.ALLOW))
    harness.teams.registered_questionnaire_callbacks = frozenset({"procurement"})
    harness.teams.questionnaire_renderers = {"procurement": lambda spec: {
        "type": "AdaptiveCard", "version": "1.5", "body": [{"type": "TextBlock",
        "text": "Existing procurement form"}], "actions": [{"type": "Action.Submit",
        "title": "Continue", "data": {"procurement_submission": "registered-existing"}}],
    }}
    harness.auth.route = route(purpose=MessagePurpose.FINANCIAL)
    result = harness.svc.dispatch(po())
    assert result.state == "provider_accepted"
    assert "unit_price" not in harness.transport.calls[0][1]
    assert "Unit price" in harness.transport.calls[0][1]
    assert harness.transport.calls[0][2]["actions"][0]["type"] == "Action.Submit"


def test_unregistered_po_workflow_must_fail_before_delivery_claim(harness):
    with pytest.raises(InteractionRejected, match="no authorized channel"):
        harness.svc.dispatch(po())
    assert harness.events.list_by_execution("ui.po.1") == ()


def test_bounded_po_conditional_questions_and_decimal_values():
    spec = po()
    supplied = dict(item="Dock", quantity="2", unit_price="99.90", ticket="none",
                    create_quote=True, contact="Cindy")
    validated = validate_answers(spec, supplied)
    assert validated["unit_price"] == "99.90"
    with pytest.raises(ValueError, match="required"):
        validate_answers(spec, {**supplied, "contact": ""})
    with pytest.raises(ValueError, match="hidden"):
        validate_answers(spec, {**supplied, "create_quote": False})
    with pytest.raises(ValueError, match="unknown"):
        validate_answers(spec, {**supplied, "owner_approval": "yes"})
    with pytest.raises(ValueError, match="maximum"):
        validate_answers(spec, {**supplied, "unit_price": "10000.00"})
    with pytest.raises(ValueError, match="nonfinite"):
        validate_answers(spec, {**supplied, "unit_price": "NaN"})


def test_approval_requires_existing_record_and_is_off_by_default(harness):
    existing = persisted_approval()
    harness.approvals.put(existing)
    harness.auth.route = route(purpose=MessagePurpose.APPROVAL_REQUEST)
    harness.teams.approval_callbacks_registered = True
    with pytest.raises(InteractionRejected, match="suspended"):
        harness.svc.dispatch(approval(existing))
    assert harness.transport.calls == []


def test_nonexecuting_approval_uses_persisted_card_renderer_only_in_opt_in_test(harness):
    existing = persisted_approval()
    harness.approvals.put(existing)
    harness.auth.route = route(purpose=MessagePurpose.APPROVAL_REQUEST)
    harness.teams.approval_callbacks_registered = True
    harness.svc.approval_dispatch_enabled = True
    result = harness.svc.dispatch(approval(existing))
    assert result.state == "provider_accepted"
    assert harness.transport.calls[0][2]["type"] == "AdaptiveCard"
    assert harness.transport.calls[0][2]["actions"]
    assert harness.approvals.get(existing.approval_id).status.value == "pending"


def test_expired_or_wrong_approver_cannot_dispatch_approval(harness):
    existing = persisted_approval()
    harness.approvals.put(existing)
    harness.teams.approval_callbacks_registered = True
    harness.svc.approval_dispatch_enabled = True
    harness.auth.route = route(purpose=MessagePurpose.APPROVAL_REQUEST,
                               recipient_identity_id="wrong-principal")
    with pytest.raises(InteractionRejected, match="mismatched"):
        harness.svc.dispatch(approval(existing))
    assert harness.transport.calls == []


def test_status_cannot_smuggle_approval_actions():
    with pytest.raises(ValueError, match="only existing approvals"):
        notice(actions=(Action("yes", "Approve", ActionType.APPROVE),))


def test_form_condition_must_reference_prior_field():
    with pytest.raises(ValueError, match="earlier field"):
        po(fields=(Field("later", "Should not work", FieldType.TEXT,
                         show_when=Condition("future", True)),
                   Field("future", "Later", FieldType.BOOLEAN)))


def test_receipt_mismatch_never_creates_false_success(harness):
    original = harness.teams.deliver
    harness.teams.deliver = lambda spec, route: InteractionDelivery(
        spec.interaction_id, "other", route.recipient_identity_id, "tampered")
    with pytest.raises(InteractionRejected, match="mismatches"):
        harness.svc.dispatch(notice())
    assert [e.stage for e in harness.events.list_by_execution("ui.notice.1")] == [
        "claimed", "reconciliation_required",
    ]
    harness.teams.deliver = original
