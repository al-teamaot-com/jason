from __future__ import annotations

from types import SimpleNamespace

from orchestrator.open_world_teams_query_flow import OpenWorldTeamsQueryFlow
from orchestrator.teams_conversation_flow import (
    BoundConversationPrincipal,
    TeamsConversationPrincipalEvidence,
    TeamsConversationRequest,
)
from usage_attribution.runtime_context import current_attribution_context


class FixedRequestFactory:
    def __init__(self) -> None:
        self.calls = 0

    def new_correlation_id(self) -> str:
        self.calls += 1
        return "corr-open-world-1"


class BoundIdentity:
    def bind(self, evidence):
        return BoundConversationPrincipal(
            principal_id="user-al",
            organization_id="aot",
            client_id="client-1",
            email_address="al@teamaot.com",
        )


class Transport:
    def send(self, *, conversation_id: str, text: str, correlation_id: str) -> str:
        return "transport-message-1"


class ContextStore:
    def get(self, **kwargs):
        return None


class Discovery:
    def discover(self):
        return object()


class Classifier:
    def __init__(self) -> None:
        self.attribution = None

    def map(self, *, human_text: str, catalog):
        self.attribution = current_attribution_context()
        return SimpleNamespace(information_request=True)


class Grounder:
    def __init__(self) -> None:
        self.attribution = None

    def ground(self, *, human_text: str, context, catalog):
        self.attribution = current_attribution_context()
        raise RuntimeError("stop after attribution proof")


class Fallback:
    def __init__(self, request_factory: FixedRequestFactory) -> None:
        self.request_factory = request_factory
        self.identity_binder = BoundIdentity()
        self.orchestrator = object()
        self.transport = Transport()


def test_open_world_classification_is_traceable_before_identity_and_correlates_after_binding(monkeypatch):
    monkeypatch.setenv("JASON_ORGANIZATION_ID", "aot")
    request_factory = FixedRequestFactory()
    classifier = Classifier()
    grounder = Grounder()
    flow = OpenWorldTeamsQueryFlow(
        fallback=Fallback(request_factory),
        context_store=ContextStore(),
        discovery=Discovery(),
        enricher=object(),
        classifier=classifier,
        selector_grounder=grounder,
        planner=object(),
        coordinator=object(),
    )
    request = TeamsConversationRequest(
        text="Who is logged into AOT-50282?",
        identity=TeamsConversationPrincipalEvidence(
            microsoft_tenant_id="tenant-1",
            microsoft_object_id="object-1",
            authentication_assurance="botframework-authenticated",
            conversation_id="conversation-1",
            message_id="message-1",
        ),
    )

    result = flow.handle(request)

    assert classifier.attribution is not None
    assert classifier.attribution.actor_type.value == "unknown"
    assert classifier.attribution.actor_id == "unknown"
    assert classifier.attribution.source_channel == "teams"
    assert classifier.attribution.capability == "conversation.classify"
    assert classifier.attribution.purpose == (
        "Classify Teams turn for governed information handling"
    )
    assert classifier.attribution.correlation_id == "corr-open-world-1"

    assert grounder.attribution is not None
    assert grounder.attribution.actor_type.value == "human"
    assert grounder.attribution.actor_id == "user-al"
    assert grounder.attribution.email_address == "al@teamaot.com"
    assert grounder.attribution.source_channel == "teams"
    assert grounder.attribution.capability == "conversation.reason"
    assert grounder.attribution.correlation_id == classifier.attribution.correlation_id

    assert result.correlation_id == "corr-open-world-1"
    assert request_factory.calls == 1
    assert current_attribution_context() is None
