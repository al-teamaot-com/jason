from __future__ import annotations

from datetime import datetime, timedelta, timezone
from threading import Event, Thread

from jason_openclaw.conversation_ingress import GovernedOpenClawTeamsConversationIngress
from orchestrator.contracts import ExecutionStage, OrchestrationResult, OrchestrationStatus
from orchestrator.teams_conversation_flow import (
    ConversationIntentUnresolvedError,
    TeamsConversationFlowResult,
)


class Authenticator:
    def __init__(self, identity="machine:openclaw-jason", fail=False):
        self.identity = identity
        self.fail = fail

    def authenticate(self, envelope):
        if self.fail:
            raise ValueError("bad signature")
        return self.identity


class Replay:
    def __init__(self):
        self.claimed = set()

    def claim(self, request_id):
        if request_id in self.claimed:
            return False
        self.claimed.add(request_id)
        return True


class Audit:
    def __init__(self):
        self.events = []

    def append(self, event_type, payload):
        self.events.append((event_type, dict(payload)))


class Flow:
    def __init__(self, error=None):
        self.requests = []
        self.error = error

    def handle(self, request):
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        orchestration = OrchestrationResult(
            execution_id="exec-1",
            correlation_id="corr-1",
            capability_name="endpoint.device.search",
            status=OrchestrationStatus.SUCCEEDED,
            stage=ExecutionStage.COMPLETED,
            reason_codes=("capability_completed",),
            resolution=None,
            output={"provider": "datto_rmm", "data": {"devices": []}},
            provider_id="datto_rmm",
            attempts=1,
        )
        return TeamsConversationFlowResult(
            orchestration=orchestration,
            transport_message_id="teams-response-1",
        )


def envelope(**overrides):
    now = datetime.now(timezone.utc)
    value = {
        "kind": "conversation.turn",
        "request_id": "req-conversation-1",
        "correlation_id": "corr-conversation-1",
        "issued_at": (now - timedelta(seconds=1)).isoformat(),
        "expires_at": (now + timedelta(minutes=2)).isoformat(),
        "nonce": "nonce-1",
        "channel": "msteams",
        "text": "Who is logged into AOT-50282?",
        "transport_identity": {
            "microsoft_tenant_id": "tenant-aot",
            "microsoft_object_id": "object-al",
            "authentication_assurance": "botframework-authenticated",
        },
        "conversation_id": "teams-conversation-1",
        "message_id": "teams-message-1",
        "key_id": "openclaw-key-1",
        "signature": "signed-by-test-authenticator",
    }
    value.update(overrides)
    return value


def ingress(*, authenticator=None, replay=None, audit=None, flow=None):
    return GovernedOpenClawTeamsConversationIngress(
        authenticator=authenticator or Authenticator(),
        replay=replay or Replay(),
        audit=audit or Audit(),
        flow=flow or Flow(),
        allowed_machine_identities=frozenset({"machine:openclaw-jason"}),
    )


def test_authenticated_turn_passes_only_text_and_microsoft_evidence_to_jason_flow():
    flow = Flow()
    audit = Audit()
    handler = ingress(flow=flow, audit=audit)

    result = handler.handle(envelope())

    assert result == {
        "request_id": "req-conversation-1",
        "correlation_id": "corr-conversation-1",
        "status": "completed",
        "transport_message_id": "teams-response-1",
        "orchestration_status": "succeeded",
    }
    assert len(flow.requests) == 1
    submitted = flow.requests[0]
    assert submitted.text == "Who is logged into AOT-50282?"
    assert submitted.identity.microsoft_tenant_id == "tenant-aot"
    assert submitted.identity.microsoft_object_id == "object-al"
    assert submitted.identity.authentication_assurance == "botframework-authenticated"
    assert submitted.identity.conversation_id == "teams-conversation-1"
    assert submitted.identity.message_id == "teams-message-1"
    assert audit.events[-1][0] == "openclaw.teams_conversation_completed"


def test_conversation_envelope_cannot_assert_jason_principal_or_capability():
    flow = Flow()
    handler = ingress(flow=flow)

    with_principal = envelope(principal_id="person-al")
    result = handler.handle(with_principal)
    assert result["status"] == "rejected"
    assert result["error_code"] == "transport_authority_assertion_forbidden"
    assert flow.requests == []

    second = envelope(request_id="req-conversation-2", capability="datto_rmm.device.search")
    result = handler.handle(second)
    assert result["status"] == "rejected"
    assert result["error_code"] == "transport_authority_assertion_forbidden"
    assert flow.requests == []


def test_transport_identity_cannot_smuggle_organization_or_provider():
    flow = Flow()
    value = envelope(request_id="req-conversation-3")
    value["transport_identity"] = {
        **value["transport_identity"],
        "organization_id": "aot",
        "provider": "datto_rmm",
    }

    result = ingress(flow=flow).handle(value)

    assert result["status"] == "rejected"
    assert result["error_code"] == "transport_authority_assertion_forbidden"
    assert flow.requests == []


def test_untrusted_machine_identity_fails_before_conversation_flow():
    flow = Flow()
    result = ingress(
        authenticator=Authenticator(identity="machine:other"),
        flow=flow,
    ).handle(envelope())

    assert result["status"] == "rejected"
    assert result["error_code"] == "machine_identity_not_allowed"
    assert flow.requests == []


def test_signature_authentication_failure_fails_before_contract_processing():
    flow = Flow()
    value = envelope(principal_id="transport-should-never-be-read")
    result = ingress(
        authenticator=Authenticator(fail=True),
        flow=flow,
    ).handle(value)

    assert result["status"] == "rejected"
    assert result["error_code"] == "transport_authentication_failed"
    assert flow.requests == []


def test_botframework_assurance_is_required():
    flow = Flow()
    value = envelope(request_id="req-conversation-4")
    value["transport_identity"] = {
        **value["transport_identity"],
        "authentication_assurance": "external_authenticated",
    }

    result = ingress(flow=flow).handle(value)

    assert result["status"] == "rejected"
    assert result["error_code"] == "transport_authority_assertion_forbidden"
    assert flow.requests == []


def test_replay_is_rejected_before_second_execution():
    flow = Flow()
    replay = Replay()
    handler = ingress(flow=flow, replay=replay)

    assert handler.handle(envelope())["status"] == "completed"
    second = handler.handle(envelope())

    assert second["status"] == "rejected"
    assert second["error_code"] == "replay_detected"
    assert len(flow.requests) == 1


def test_same_authenticated_teams_message_with_new_request_id_is_suppressed():
    flow = Flow()
    replay = Replay()
    audit = Audit()
    handler = ingress(flow=flow, replay=replay, audit=audit)

    first = handler.handle(
        envelope(
            request_id="req-message-first",
            correlation_id="corr-message-first",
        )
    )
    duplicate = handler.handle(
        envelope(
            request_id="req-message-duplicate",
            correlation_id="corr-message-duplicate",
            nonce="nonce-duplicate",
        )
    )

    assert first["status"] == "completed"
    assert duplicate == {
        "request_id": "req-message-duplicate",
        "correlation_id": "corr-message-duplicate",
        "status": "duplicate",
        "error_code": "duplicate_message",
        "message_id": "teams-message-1",
    }
    assert len(flow.requests) == 1
    assert audit.events[-1][0] == (
        "openclaw.teams_conversation_duplicate_suppressed"
    )
    assert audit.events[-1][1]["message_id"] == "teams-message-1"



def test_duplicate_is_suppressed_while_first_message_is_still_in_flight():
    started = Event()
    release = Event()
    calls = []
    first_result = []

    class BlockingFlow:
        def handle(self, request):
            calls.append(request)
            started.set()

            if not release.wait(timeout=5):
                raise TimeoutError("test flow was not released")

            return Flow().handle(request)

    replay = Replay()
    audit = Audit()
    handler = ingress(
        flow=BlockingFlow(),
        replay=replay,
        audit=audit,
    )

    def run_first():
        first_result.append(
            handler.handle(
                envelope(
                    request_id="req-inflight-first",
                    correlation_id="corr-inflight-first",
                    message_id="teams-message-inflight",
                )
            )
        )

    worker = Thread(target=run_first)
    worker.start()

    assert started.wait(timeout=5)

    duplicate = handler.handle(
        envelope(
            request_id="req-inflight-duplicate",
            correlation_id="corr-inflight-duplicate",
            nonce="nonce-inflight-duplicate",
            message_id="teams-message-inflight",
        )
    )

    assert duplicate == {
        "request_id": "req-inflight-duplicate",
        "correlation_id": "corr-inflight-duplicate",
        "status": "duplicate",
        "error_code": "duplicate_message",
        "message_id": "teams-message-inflight",
    }

    assert len(calls) == 1

    duplicate_events = [
        payload
        for event_type, payload in audit.events
        if event_type
        == "openclaw.teams_conversation_duplicate_suppressed"
    ]

    assert len(duplicate_events) == 1
    assert duplicate_events[0]["message_id"] == (
        "teams-message-inflight"
    )

    release.set()
    worker.join(timeout=5)

    assert not worker.is_alive()
    assert len(first_result) == 1
    assert first_result[0]["status"] == "completed"



def test_same_text_in_new_teams_message_is_not_suppressed():
    flow = Flow()
    replay = Replay()
    handler = ingress(flow=flow, replay=replay)

    first = handler.handle(
        envelope(
            request_id="req-new-message-1",
            correlation_id="corr-new-message-1",
            message_id="teams-message-new-1",
        )
    )
    second = handler.handle(
        envelope(
            request_id="req-new-message-2",
            correlation_id="corr-new-message-2",
            nonce="nonce-new-message-2",
            message_id="teams-message-new-2",
        )
    )

    assert first["status"] == "completed"
    assert second["status"] == "completed"
    assert len(flow.requests) == 2


def test_expired_turn_fails_before_replay_claim_and_flow():
    flow = Flow()
    replay = Replay()
    now = datetime.now(timezone.utc)
    value = envelope(
        request_id="req-expired",
        issued_at=(now - timedelta(minutes=5)).isoformat(),
        expires_at=(now - timedelta(minutes=3)).isoformat(),
    )

    result = ingress(flow=flow, replay=replay).handle(value)

    assert result["status"] == "rejected"
    assert result["error_code"] == "request_expired"
    assert replay.claimed == set()
    assert flow.requests == []


def test_flow_identity_or_authority_denial_is_sanitized():
    flow = Flow(error=PermissionError("internal authority details"))

    result = ingress(flow=flow).handle(envelope(request_id="req-denied"))

    assert result == {
        "request_id": "req-denied",
        "correlation_id": "corr-conversation-1",
        "status": "denied",
        "error_code": "conversation_denied",
    }


def test_only_explicit_intent_resolution_failure_is_reported_as_unresolved():
    audit = Audit()
    flow = Flow(
        error=ConversationIntentUnresolvedError(
            "no governed Jason capability intent could be resolved"
        )
    )

    result = ingress(flow=flow, audit=audit).handle(
        envelope(request_id="req-unresolved")
    )

    assert result == {
        "request_id": "req-unresolved",
        "correlation_id": "corr-conversation-1",
        "status": "rejected",
        "error_code": "conversation_unresolved",
    }
    assert audit.events[-1][0] == "openclaw.teams_conversation_rejected"


def test_downstream_lookup_failure_is_reported_as_failed_not_unresolved():
    audit = Audit()
    flow = Flow(error=LookupError("provider evidence pointer does not exist"))

    result = ingress(flow=flow, audit=audit).handle(
        envelope(request_id="req-evidence-failed")
    )

    assert result == {
        "request_id": "req-evidence-failed",
        "correlation_id": "corr-conversation-1",
        "status": "failed",
        "error_code": "conversation_failed",
    }
    assert audit.events[-1][0] == "openclaw.teams_conversation_failed"
