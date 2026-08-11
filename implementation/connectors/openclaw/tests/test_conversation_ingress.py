from __future__ import annotations

from datetime import datetime, timedelta, timezone

from jason_openclaw.conversation_ingress import GovernedOpenClawTeamsConversationIngress
from orchestrator.contracts import ExecutionStage, OrchestrationResult, OrchestrationStatus
from orchestrator.teams_conversation_flow import TeamsConversationFlowResult


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
