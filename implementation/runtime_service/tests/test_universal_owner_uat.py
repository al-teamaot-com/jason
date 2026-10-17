"""Proof of a NONEXECUTING owner-approval Teams round trip, with real Ed25519.

No Teams provider call, release manager, devices, purchases or clients are
touched. A future live owner device test requires a separately authorized
preproduction deployment/registration and explicit owner confirmation.
"""
from __future__ import annotations

import base64
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from communication.audience.models import AudienceType, MessagePurpose
from connectors.src.jason_connectors.approval_requests import (
    ApprovalRequestService, ApprovalRequestStatus, SQLiteApprovalRequestRepository,
)
from jason_openclaw.signed_transport import (
    Ed25519TransportAuthenticator, canonical_signed_payload,
)
from jason_runtime.universal_teams_approval import SignedTeamsApprovalEvidenceVerifier
from jason_runtime.universal_interaction.owner_uat import (
    APPROVAL_PREFIX, CAPABILITY, MODE, OWNER, REQUESTER,
    OwnerUatAuthority, OwnerUatDecisionFlow, OwnerUatIssuer,
    create_nonexecuting_approval,
)
from jason_runtime.universal_interaction.service import (
    AuthorizedRoute, ChannelFeatures, InteractionDelivery,
    OrchestrationInteractionJournal, UniversalInteractionService,
    ExistingApprovalGuard,
)
from orchestrator.event_store import SQLiteOrchestrationEventStore

NOW = datetime.now(timezone.utc).replace(microsecond=0)
TENANT = "11111111-1111-4111-8111-111111111111"
OWNER_OBJECT = "22222222-2222-4222-8222-222222222222"
OTHER_OBJECT = "33333333-3333-4333-8333-333333333333"


class FakeTeamsChannel:
    channel_id = "teams"
    features = ChannelFeatures(notices=True, approvals=True, authenticated_responses=True)
    def __init__(self):
        self.sends = []
    def deliver(self, spec, route):
        self.sends.append((spec, route))
        return InteractionDelivery(spec.interaction_id, "teams", route.recipient_identity_id,
                                   "accepted:test-transport-only")


def signed(env, request, decision="approve", *, object_id=OWNER_OBJECT, **updates):
    payload = {
        "kind": "conversation.turn",
        "request_id": "owner-uat-transport:" + request.approval_id + ":" + decision,
        "correlation_id": "owner-uat-transport:" + request.approval_id,
        "issued_at": NOW.isoformat(),
        "expires_at": (NOW + timedelta(minutes=2)).isoformat(),
        "nonce": "owner-uat-unique:" + request.approval_id + ":" + decision,
        "channel": "msteams",
        "text": "TEST ONLY: signed owner choice",
        "transport_identity": {
            "microsoft_tenant_id": TENANT,
            "microsoft_object_id": object_id,
            "authentication_assurance": "botframework-authenticated",
        },
        "conversation_id": "teams-owner-chat",
        "message_id": "teams-click:" + decision,
        "interaction": {
            "kind": "approval.submit",
            "approval_id": request.approval_id,
            "decision": decision,
            "channel_response_id": "teams-click:" + decision,
            "selections": {},
        },
        "key_id": "synthetic-test-key",
    }
    payload.update(updates)
    payload["signature"] = base64.b64encode(
        env.private.sign(canonical_signed_payload(payload))
    ).decode("ascii")
    return payload


def click(flow, payload, **changes):
    args = {
        "approval_id": payload["interaction"]["approval_id"],
        "decision": payload["interaction"]["decision"],
        "microsoft_tenant_id": payload["transport_identity"]["microsoft_tenant_id"],
        "microsoft_object_id": payload["transport_identity"]["microsoft_object_id"],
        "conversation_id": payload["conversation_id"],
        "channel_response_id": payload["interaction"]["channel_response_id"],
        "decided_at": datetime.fromisoformat(payload["issued_at"]),
        "selections": {},
        "signed_envelope": payload,
    }
    args.update(changes)
    return flow.handle(**args)


@pytest.fixture
def env(tmp_path):
    repository = SQLiteApprovalRequestRepository(tmp_path / "existing_approval_repo.db")
    approvals = ApprovalRequestService(repository, OwnerUatAuthority())
    events = SQLiteOrchestrationEventStore(tmp_path / "existing_orchestration_events.db")
    route = AuthorizedRoute(
        recipient_identity_id=OWNER, organization_id="aot", client_id=None,
        audience_type=AudienceType.EXECUTIVE, purpose=MessagePurpose.APPROVAL_REQUEST,
        channels=("teams",), authorization_ref="jkd:uat:owner",
        allowed=True,
    )
    channel = FakeTeamsChannel()
    service = UniversalInteractionService(
        authority=SimpleNamespace(authorize=lambda spec: route),
        channels={"teams": channel}, audit=OrchestrationInteractionJournal(events),
        approvals=ExistingApprovalGuard(repository), approval_dispatch_enabled=True,
        clock=lambda: NOW,
    )
    issuer = OwnerUatIssuer(
        requests=approvals, universal_interactions=service,
        clock=lambda: NOW,
    )
    key = Ed25519PrivateKey.generate()
    pem = key.public_key().public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)
    authenticator = Ed25519TransportAuthenticator(
        {"synthetic-test-key": pem}, {"synthetic-test-key": "svc-test-gateway"}
    )
    verifier = SignedTeamsApprovalEvidenceVerifier(
        authenticator=authenticator,
        allowed_machine_identities=frozenset({"svc-test-gateway"}),
        allowed_approval_prefixes=(APPROVAL_PREFIX,),
        clock=lambda: NOW + timedelta(seconds=3),
    )
    bound = SimpleNamespace(jason_identity_id=OWNER, status="active")
    identity = SimpleNamespace(identity_id=OWNER, status="active", organization_id="aot")
    callback = OwnerUatDecisionFlow(
        approvals=approvals, signed_verifier=verifier,
        bindings=SimpleNamespace(find=lambda **kwargs: (
            bound if kwargs["microsoft_tenant_id"] == TENANT
                     and kwargs["microsoft_object_id"] == OWNER_OBJECT
            else None
        )),
        identities=SimpleNamespace(get=lambda person: identity if person == OWNER else None),
        clock=lambda: NOW + timedelta(seconds=3),
    )
    yield SimpleNamespace(
        repo=repository, approvals=approvals, events=events,
        route=route, channel=channel, issuer=issuer, callback=callback, private=key,
    )
    events.close()


def setup_issued(env, session_id="acceptance-October17"):
    env.issuer.enabled = True
    sent = env.issuer.issue(session_id=session_id)
    assert sent.state == "provider_accepted"
    request = env.repo.list_all()[-1]
    assert request.capability == CAPABILITY
    assert request.requested_mode == MODE
    assert request.metadata["execution_permitted"] == "false"
    return request


def test_issuance_and_callback_are_disabled_by_default(env):
    with pytest.raises(PermissionError, match="disabled"):
        env.issuer.issue(session_id="acceptance-October17")
    assert env.repo.list_all() == ()
    request = create_nonexecuting_approval(
        session_id="acceptance-October17", now=NOW
    )
    env.approvals.create(request, now=NOW)
    payload = signed(env, request)
    with pytest.raises(PermissionError, match="disabled"):
        click(env.callback, payload)
    assert env.repo.get(request.approval_id).status == ApprovalRequestStatus.PENDING


def test_issuer_is_one_shot_with_existing_universal_interaction(env):
    request = setup_issued(env)
    assert len(env.channel.sends) == 1
    spec, route = env.channel.sends[0]
    assert spec.approval_id == request.approval_id
    assert spec.kind.value == "approval"
    assert "NONEXECUTING" in spec.summary
    assert {a.intent.value for a in spec.actions} == {"approve", "deny"}
    assert route.recipient_identity_id == OWNER
    assert request.requested_by == REQUESTER
    with pytest.raises(PermissionError, match="already issued"):
        env.issuer.issue(session_id="acceptance-October17")
    assert len(env.channel.sends) == 1
    assert [e.stage for e in env.events.list_by_execution(spec.interaction_id)] == [
        "claimed", "provider_accepted",
    ]


@pytest.mark.parametrize("decision,expected", [
    ("approve", ApprovalRequestStatus.APPROVED),
    ("deny", ApprovalRequestStatus.DENIED),
])
def test_real_signed_owner_approve_or_deny_only_records_test_receipt(env, decision, expected):
    request = setup_issued(env)
    env.callback.enabled = True
    payload = signed(env, request, decision)
    result = click(env.callback, payload)
    assert result["status"] == "completed"
    assert result["executed"] is False
    assert result["approval_status"] == expected.value
    assert "No production, ticket, PO" in result["reply"]["text"]
    assert env.repo.get(request.approval_id).status == expected
    receipt = env.repo.accepted_decision(request.approval_id)
    assert receipt is not None
    assert receipt.authentication_evidence_hash is not None
    assert len(receipt.authentication_evidence_hash) == 64
    # Replayed SDK card clicks cannot record a second decision.
    with pytest.raises(PermissionError, match="not a pending"):
        click(env.callback, payload)


@pytest.mark.parametrize("change", [
    {"decision":"deny"},
    {"microsoft_object_id":OTHER_OBJECT},
    {"conversation_id":"wrong-conversation"},
    {"channel_response_id":"wrong-message"},
    {"decided_at":NOW-timedelta(hours=1)},
    {"selections":{"new_scope":"production"}},
    {"signed_envelope":None},
])
def test_callback_cannot_change_exact_signed_owner_decision(env, change):
    request = setup_issued(env)
    env.callback.enabled = True
    with pytest.raises(PermissionError):
        click(env.callback, signed(env, request), **change)
    assert env.repo.get(request.approval_id).status == ApprovalRequestStatus.PENDING


def test_tampered_signed_envelope_fails(env):
    request = setup_issued(env)
    env.callback.enabled = True
    payload = signed(env, request)
    payload["interaction"]["decision"] = "deny"
    with pytest.raises(PermissionError, match="signature"):
        click(env.callback, payload)
    assert env.repo.get(request.approval_id).status == ApprovalRequestStatus.PENDING


def test_other_signed_tenant_or_unbound_owner_cannot_approve(env):
    request = setup_issued(env)
    env.callback.enabled = True
    with pytest.raises(PermissionError, match="active owner"):
        click(env.callback, signed(env, request, object_id=OTHER_OBJECT))
    assert env.repo.get(request.approval_id).status == ApprovalRequestStatus.PENDING


def test_transport_expiry_denied_even_with_current_owner_binding(env):
    request = setup_issued(env)
    env.callback.enabled = True
    payload = signed(
        env, request,
        issued_at=(NOW-timedelta(minutes=5)).isoformat(),
        expires_at=(NOW-timedelta(minutes=3)).isoformat(),
    )
    with pytest.raises(PermissionError, match="expired"):
        click(env.callback, payload)
    assert env.repo.get(request.approval_id).status == ApprovalRequestStatus.PENDING


def test_approval_expiry_denied_by_existing_ledger_not_callback_clock(env):
    request = setup_issued(env)
    env.callback.enabled = True
    env.callback.clock = lambda: NOW + timedelta(hours=1)
    with pytest.raises(PermissionError, match="expired"):
        click(env.callback, signed(env, request))
    assert env.repo.get(request.approval_id).status == ApprovalRequestStatus.EXPIRED


@pytest.mark.parametrize("bad", [
    {"session_id":"../../../shell"},
    {"session_id":""},
    {"session_id":"-bad"},
    {"session_id":"too-long-"+"a"*200},
])
def test_malformed_session_never_creates_owner_approval(env, bad):
    env.issuer.enabled = True
    with pytest.raises(ValueError):
        env.issuer.issue(**bad)
    assert env.repo.list_all() == ()


def test_issuer_has_no_route_into_a_production_release(env):
    request = setup_issued(env)
    assert request.capability != "release.production.approve"
    assert request.requested_mode != "release:" + "a"*40
    assert request.client_id is None
    assert request.metadata == {"test_only": "true", "execution_permitted":"false"}


def test_existing_runtime_maintenance_issues_once_then_never_resends(env):
    from jason_runtime.universal_interaction.owner_uat import OwnerUatMaintenance
    worker = OwnerUatMaintenance(
        issuer=env.issuer,
        session_id="acceptance-one-time",
        enabled=False,
    )
    assert worker.tick() is False
    assert env.repo.list_all() == ()
    worker.enabled = True
    env.issuer.enabled = True
    assert worker.tick() is True
    assert worker.tick() is False
    assert len(env.channel.sends) == 1
    assert len(env.repo.list_all()) == 1


def test_uncertain_teams_send_is_not_blindly_reissued_by_worker(env):
    from jason_runtime.universal_interaction.owner_uat import OwnerUatMaintenance
    from jason_runtime.universal_interaction.service import InteractionRejected
    env.issuer.enabled = True

    def failed_send(spec, route):
        env.channel.sends.append((spec,route))
        raise TimeoutError("Teams acceptance unknown")
    env.channel.deliver = failed_send
    worker = OwnerUatMaintenance(
        issuer=env.issuer,
        session_id="acceptance-failure",
        enabled=True,
    )
    with pytest.raises(TimeoutError, match="unknown"):
        worker.tick()
    # Approval record and unique delivery claim remain; no blind resend.
    assert worker.tick() is False
    assert len(env.channel.sends) == 1
    record = env.repo.list_all()[0]
    assert record.status == ApprovalRequestStatus.PENDING
    stages = [e.stage for e in env.events.list_by_execution("uat."+record.approval_id)]
    assert stages == ["claimed", "reconciliation_required"]
