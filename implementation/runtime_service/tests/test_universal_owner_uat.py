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
TENANT = "f7054323-d52b-4863-8c2f-1898f0b6077c"
OWNER_OBJECT = "bee80bdc-ffb0-4c50-b453-c09d4d411f5f"
ADMIN_OBJECT = "c848022d-e13b-4457-84b0-e2f5c00dcaf6"
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
    bound = SimpleNamespace(jason_identity_id=OWNER, status="active", client_id=None,
                            microsoft_tenant_id=TENANT, microsoft_object_id=OWNER_OBJECT)
    identity = SimpleNamespace(identity_id=OWNER, status="active", organization_id="aot")
    callback = OwnerUatDecisionFlow(
        approvals=approvals, signed_verifier=verifier,
        bindings=SimpleNamespace(find=lambda **kwargs: (
            bound if kwargs["microsoft_tenant_id"] == TENANT
                     and kwargs["microsoft_object_id"] == OWNER_OBJECT
            else None
        ), find_active_by_jason_identity=lambda **kwargs: bound),
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


@pytest.mark.parametrize("session,decision,expected", [
    ("acceptance-October17", "deny", ApprovalRequestStatus.DENIED),
    ("acceptance-October17.approve", "approve", ApprovalRequestStatus.APPROVED),
])
def test_real_signed_owner_approve_or_deny_only_records_test_receipt(env, session, decision, expected):
    request = setup_issued(env, session_id=session)
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
        click(env.callback, signed(env, request, decision="deny"))
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
        release_ready=lambda: True,
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
        release_ready=lambda: True,
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


def test_owner_campaign_requires_denial_then_separate_signed_approval(env):
    from jason_runtime.universal_interaction.owner_uat import OwnerUatMaintenance

    env.issuer.enabled = True
    env.callback.enabled = True
    worker = OwnerUatMaintenance(
        issuer=env.issuer, session_id="OwnerUAT20261017Pilot", enabled=True,
        release_ready=lambda: True,
    )
    assert worker.tick() is True
    first = env.repo.list_all()[0]
    assert "DENY" in first.presentation.title
    assert "Click DENY" in dict(first.presentation.facts)["Next action"]
    assert worker.tick() is False  # no second card merely from delivery
    click(env.callback, signed(env, first, decision="deny"))
    assert env.repo.get(first.approval_id).status == ApprovalRequestStatus.DENIED
    assert worker.tick() is True
    assert len(env.channel.sends) == 2
    second = next(r for r in env.repo.list_all() if r.approval_id != first.approval_id)
    assert second.request_id == "owner-uat:OwnerUAT20261017Pilot.approve"
    assert "APPROVE" in second.presentation.title
    assert "Click APPROVE" in dict(second.presentation.facts)["Next action"]
    assert second.metadata == {"test_only": "true", "execution_permitted": "false"}
    assert worker.tick() is False
    click(env.callback, signed(env, second, decision="approve"))
    assert env.repo.get(second.approval_id).status == ApprovalRequestStatus.APPROVED
    assert worker.tick() is False
    assert len(env.channel.sends) == 2
    for request in (first, second):
        receipt = env.repo.accepted_decision(request.approval_id)
        assert receipt is not None
        assert receipt.authentication_evidence_hash is not None


def test_wrong_first_approve_is_noncommitting_and_real_deny_then_approve_completes(env):
    from jason_runtime.universal_interaction.owner_uat import OwnerUatMaintenance

    env.issuer.enabled = True
    env.callback.enabled = True
    worker = OwnerUatMaintenance(
        issuer=env.issuer, session_id="OwnerUATWrongButton", enabled=True,
        release_ready=lambda: True,
    )
    assert worker.tick() is True
    first = env.repo.list_all()[0]
    wrong = click(env.callback, signed(env, first, decision="approve"))
    assert wrong["status"] == "denied"
    assert wrong["executed"] is False
    assert "DENY only" in wrong["reply"]["text"]
    assert env.repo.get(first.approval_id).status == ApprovalRequestStatus.PENDING
    assert env.repo.accepted_decision(first.approval_id) is None
    assert worker.tick() is False
    assert len(env.repo.list_all()) == len(env.channel.sends) == 1

    # The original request is still pending: a real Deny can complete it.
    denied = click(env.callback, signed(env, first, decision="deny"))
    assert denied["status"] == "completed"
    assert env.repo.get(first.approval_id).status == ApprovalRequestStatus.DENIED
    assert worker.tick() is True
    second = next(x for x in env.repo.list_all() if x.approval_id != first.approval_id)
    assert second.request_id.endswith(".approve")

    wrong_second = click(env.callback, signed(env, second, decision="deny"))
    assert wrong_second["status"] == "denied"
    assert wrong_second["executed"] is False
    assert "APPROVE only" in wrong_second["reply"]["text"]
    assert env.repo.get(second.approval_id).status == ApprovalRequestStatus.PENDING
    assert env.repo.accepted_decision(second.approval_id) is None
    assert worker.tick() is False

    approved = click(env.callback, signed(env, second, decision="approve"))
    assert approved["status"] == "completed"
    assert env.repo.get(second.approval_id).status == ApprovalRequestStatus.APPROVED
    assert worker.tick() is False
    assert len(env.channel.sends) == len(env.repo.list_all()) == 2


def test_uat_worker_fails_closed_without_release_gate(env):
    from jason_runtime.universal_interaction.owner_uat import OwnerUatMaintenance
    env.issuer.enabled = True
    worker = OwnerUatMaintenance(
        issuer=env.issuer, session_id="OwnerUATNotReleased", enabled=True,
    )
    assert worker.tick() is False
    assert env.repo.list_all() == ()
    assert env.channel.sends == []


def test_root_verified_exact_sha_closeout_required_for_uat(tmp_path):
    from jason_runtime.universal_interaction.owner_uat import OwnerUatReleaseGate

    sha = "0dceb0af7498e14fedb35aca71b35ed0a95e2526"
    root = tmp_path / "release-manager"
    record_path = root / "records" / ("release-" + sha[:16] + ".json")
    snapshot = root / "protected-readback" / "production-control-state.json"

    def write(path, payload):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
        path.chmod(0o600)

    production = {
        "live_sha": sha, "runtime_revision": sha, "mcp_revision": sha,
        "host_revision": sha, "release_manager_source_revision": sha,
        "ccc_post_mutation": {
            "status": "PASS", "source_revision": sha, "runtime_revision": sha,
        },
    }
    record = {
        "schema_version": "2.0",
        "release_id": "release-" + sha[:16],
        "state": "closed",
        "release_candidate": {"candidate_sha": sha},
        "owner_approval": {"approved": True, "candidate_sha": sha},
        "production": production,
    }
    state = {
        "schema_version": "1.0",
        "circuit_breaker": {"state": "closed"},
        "last_known_good": {"manifest": {
            "revision": sha, "runtime_revision": sha,
            "mcp_revision": sha, "host_revision": sha,
        }},
    }
    gate = OwnerUatReleaseGate(root, sha)
    assert gate.ready() is False
    write(record_path, record)
    assert gate.ready() is False
    write(snapshot, state)
    assert gate.ready() is True
    record["state"] = "production"
    write(record_path, record)
    assert gate.ready() is False
    record["state"] = "closed"
    record["production"]["ccc_post_mutation"]["status"] = "FAIL"
    write(record_path, record)
    assert gate.ready() is False
    record["production"]["ccc_post_mutation"]["status"] = "PASS"
    write(record_path, record)
    state["circuit_breaker"]["state"] = "open"
    write(snapshot, state)
    assert gate.ready() is False
    state["circuit_breaker"]["state"] = "closed"
    state["last_known_good"]["manifest"]["revision"] = "f" * 40
    write(snapshot, state)
    assert gate.ready() is False
    state["last_known_good"]["manifest"]["revision"] = sha
    write(snapshot, state)
    assert gate.ready() is True
    snapshot.chmod(0o644)
    assert gate.ready() is False


def test_signed_owner_phase_mismatch_does_not_change_any_acceptance_record(env):
    from jason_runtime.universal_interaction.owner_uat import expected_owner_uat_decision
    first = setup_issued(env, session_id="OwnerUATPhaseBound01")
    assert expected_owner_uat_decision(first) == "deny"
    env.callback.enabled = True
    wrong = click(env.callback, signed(env, first, decision="approve"))
    assert wrong["status"] == "denied"
    assert env.repo.get(first.approval_id).status == ApprovalRequestStatus.PENDING
    assert env.repo.accepted_decision(first.approval_id) is None
    followup = create_nonexecuting_approval(
        session_id="OwnerUATPhaseBound01.approve", now=NOW
    )
    assert expected_owner_uat_decision(followup) == "approve"

    # Tampering the persisted phase/title is never authority for either path.
    from dataclasses import replace as replace_record
    tampered = replace_record(first, request_id="owner-uat:AlteredSession")
    with pytest.raises(PermissionError, match="immutable phase"):
        expected_owner_uat_decision(tampered)
    tampered_title = replace_record(
        first,
        presentation=replace_record(first.presentation, title="TEST ONLY: changed phase")
    )
    with pytest.raises(PermissionError, match="immutable phase"):
        expected_owner_uat_decision(tampered_title)


def test_chatgpt_fallback_and_signed_teams_share_one_terminal_receipt(env):
    request = setup_issued(env, "acceptance-Coordinated.fallback")
    flow = replace(env.callback, enabled=True, chatgpt_ready=lambda: True)
    actor = dict(principal_id=OWNER, tenant_id=TENANT, object_id=OWNER_OBJECT)
    _, digest = flow.chatgpt_review(approval_id=request.approval_id, **actor)
    args = dict(approval_id=request.approval_id, decision="deny", **actor,
                channel_response_id="mcp-uat-fixture", authentication_evidence_hash="e" * 64)
    with pytest.raises(PermissionError, match="exact reviewed"):
        flow.handle_authenticated(reviewed_scope_sha256="0" * 64, **args)
    with pytest.raises(PermissionError):
        flow.chatgpt_review(approval_id=request.approval_id, **dict(actor, object_id=OTHER_OBJECT))
    result = flow.handle_authenticated(reviewed_scope_sha256=digest, **args)
    assert result["approval_status"] == "denied" and not result["executed"]
    assert env.repo.accepted_decision(request.approval_id).channel == "jason_mcp_entra"
    with pytest.raises(PermissionError):
        click(flow, signed(env, request, "deny"))
    with pytest.raises(PermissionError):
        flow.handle_authenticated(reviewed_scope_sha256=digest, **args)


def test_coordinated_readiness_requires_exact_component_and_fresh_root_evidence(monkeypatch):
    from jason_runtime.universal_interaction.owner_uat import OwnerUatReleaseGate

    release = "release-" + "a" * 16
    anchor = "b" * 40
    readback = {
        "schema_version": "3.0", "status": "verified_component_release",
        "release_id": release, "host_revision": anchor,
        "manifest_sha256": "7" * 64, "scope_sha256": "8" * 64, "release_policy_sha256": "9" * 64,
        "components": {
            name: {"revision": digit * 40, "image_id": "sha256:" + digit * 64,
                   "container_id": digit * 64}
            for name, digit in (("jason-runtime", "a"), ("jason-mcp-pilot", "c"), ("jason-teams-gateway", "d"))
        },
    }
    control = {"schema_version": "1.0", "circuit_breaker": {"state": "closed"},
               "last_known_good": {"manifest": {"complete": True, "revision": anchor}}}
    drift = {"status": "pass", "problems": [], "observed_at": NOW.isoformat()}
    monkeypatch.setattr(OwnerUatReleaseGate, "read_coordinated_receipt", staticmethod(lambda: readback))
    monkeypatch.setattr(OwnerUatReleaseGate, "_private_json", staticmethod(
        lambda path, **_: drift if path.name == "production-drift.json" else control))
    gate = OwnerUatReleaseGate(Path("/unused"), "a" * 40, release,
                               campaign_expires_at=(NOW + timedelta(hours=1)).isoformat())
    assert gate.ready()
    assert replace(gate, source_revision="c" * 40, component="jason-mcp-pilot").ready()
    assert not replace(gate, source_revision="c" * 40).ready()
    assert not replace(gate, coordinated_release_id="release-" + "b" * 16).ready()
    assert not replace(gate, campaign_expires_at=(NOW - timedelta(minutes=1)).isoformat()).ready()
    drift["observed_at"] = (NOW - timedelta(minutes=5)).isoformat()
    assert not gate.ready()


def test_coordinated_campaign_issues_fallback_only_after_two_teams_receipts(env):
    from jason_runtime.universal_interaction.owner_uat import OwnerUatMaintenance

    session = "CoordinatedOwnerCampaign"
    env.issuer.enabled = True
    flow = replace(env.callback, enabled=True, chatgpt_ready=lambda: True)
    worker = OwnerUatMaintenance(
        env.issuer, session, enabled=True, release_ready=lambda: True, include_chatgpt_fallback=True)
    assert worker.tick() and not worker.tick()
    first = create_nonexecuting_approval(session_id=session, now=NOW)
    click(flow, signed(env, first, "deny"))
    assert worker.tick() and not worker.tick()
    second = create_nonexecuting_approval(session_id=session + ".approve", now=NOW)
    click(flow, signed(env, second, "approve"))
    assert worker.tick() and not worker.tick()
    fallback = create_nonexecuting_approval(session_id=session + ".fallback", now=NOW)
    assert env.repo.get(fallback.approval_id).status == ApprovalRequestStatus.PENDING
    assert len(env.channel.sends) == 3


def test_licensed_owner_delivery_and_decision_reject_legacy_admin_even_with_misbound_identity(env):
    assert OWNER == "person-entra-bee80bdcffb04c50b453c09d4d411f5f"
    assert env.callback.recipient_ready()
    request = setup_issued(env)
    assert request.authorized_approver_ids == (OWNER,)
    env.callback.enabled = True
    good = env.callback.bindings.find(microsoft_tenant_id=TENANT, microsoft_object_id=OWNER_OBJECT)
    # Even a bad local alias cannot authorize the administrator or cause a new card.
    wrong = SimpleNamespace(**{**vars(good), "microsoft_object_id": ADMIN_OBJECT})
    env.callback.bindings.find = lambda **kwargs: wrong
    env.callback.bindings.find_active_by_jason_identity = lambda **kwargs: wrong
    assert not env.callback.recipient_ready()
    with pytest.raises(PermissionError, match="active owner"):
        click(env.callback, signed(env, request, decision="deny", object_id=ADMIN_OBJECT))
    assert env.repo.accepted_decision(request.approval_id) is None
    assert env.repo.get(request.approval_id).status == ApprovalRequestStatus.PENDING
