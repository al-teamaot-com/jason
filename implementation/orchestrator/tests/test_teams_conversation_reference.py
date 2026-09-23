from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from orchestrator.teams_conversation_continuation import ConversationContinuationState
from orchestrator.teams_conversation_flow import (
    BoundConversationPrincipal,
    ConversationGuidanceRequiredError,
    TeamsConversationFlow,
    TeamsConversationPrincipalEvidence,
    TeamsConversationRequest,
)


NOW = datetime(2026, 8, 15, 18, 0, tzinfo=timezone.utc)


class Binder:
    def bind(self, evidence):
        return BoundConversationPrincipal(
            principal_id="person-al",
            organization_id="aot",
        )


class NeverResolver:
    def resolve(self, **kwargs):
        raise AssertionError("reference explanation must not start a new intent")


class GuidanceResolver:
    def resolve(self, **kwargs):
        raise ConversationGuidanceRequiredError(
            reason_code="governed_fact_not_available",
            guidance_text=(
                "I recognized that as a request for bitlocker recovery key, but Jason "
                "does not currently have a governed read capability that declares "
                "authority to retrieve that fact. No provider request was made."
            ),
            requested_facts=("bitlocker recovery key",),
        )


class NeverCalled:
    def __getattr__(self, name):
        raise AssertionError(f"{name} must not be called")


class CorrelationOnlyFactory:
    def new_correlation_id(self):
        return "corr-guidance"

    def build(self, **kwargs):
        raise AssertionError("build must not be called")


class MemoryStore:
    def __init__(self, state=None):
        self.state = state
        self.puts = []

    def get(self, **kwargs):
        return self.state

    def put(self, **kwargs):
        self.puts.append(kwargs)
        self.state = ConversationContinuationState(
            principal_id=kwargs["principal_id"],
            organization_id=kwargs["organization_id"],
            conversation_id=kwargs["conversation_id"],
            last_message_id=kwargs["last_message_id"],
            response_kind=kwargs["response_kind"],
            last_response_text=kwargs["last_response_text"],
            last_capability_name=kwargs["last_capability_name"],
            requested_facts=kwargs["requested_facts"],
            resource_selector=kwargs["resource_selector"],
            updated_at=NOW,
            expires_at=NOW + timedelta(minutes=20),
        )
        return self.state


def identity(message_id="message-2"):
    return TeamsConversationPrincipalEvidence(
        microsoft_tenant_id="tenant-1",
        microsoft_object_id="object-1",
        authentication_assurance="botframework-authenticated",
        conversation_id="conversation-1",
        message_id=message_id,
    )


def flow(*, resolver, store, request_factory=None):
    return TeamsConversationFlow(
        identity_binder=Binder(),
        intent_resolver=resolver,
        request_factory=request_factory or NeverCalled(),
        orchestrator=NeverCalled(),
        response_renderer=NeverCalled(),
        transport=NeverCalled(),
        continuation_store=store,
    )


def test_what_does_that_mean_uses_same_bound_conversation_state():
    store = MemoryStore(
        ConversationContinuationState(
            principal_id="person-al",
            organization_id="aot",
            conversation_id="conversation-1",
            last_message_id="message-1",
            response_kind="guidance",
            last_response_text="No provider request was made for the BitLocker recovery key.",
            last_capability_name="endpoint.device.search",
            requested_facts=("bitlocker recovery key",),
            resource_selector={"hostname": "AOT-50107"},
            updated_at=NOW,
            expires_at=NOW + timedelta(minutes=20),
        )
    )

    with pytest.raises(ConversationGuidanceRequiredError) as caught:
        flow(resolver=NeverResolver(), store=store).handle(
            TeamsConversationRequest(
                text="What does that mean?",
                identity=identity(),
            )
        )

    assert caught.value.reason_code == "conversation_reference_explained"
    assert "bitlocker recovery key" in caught.value.guidance_text.casefold()
    assert "No provider request was made" in caught.value.guidance_text


def test_unsupported_fact_guidance_replaces_previous_turn_but_preserves_safe_target():
    store = MemoryStore(
        ConversationContinuationState(
            principal_id="person-al",
            organization_id="aot",
            conversation_id="conversation-1",
            last_message_id="message-1",
            response_kind="result",
            last_response_text="AOT-50107 — bitlocker status: Encrypted. Source: datto_rmm.",
            last_capability_name="endpoint.device.search",
            requested_facts=("bitlocker status",),
            resource_selector={"hostname": "AOT-50107"},
            updated_at=NOW,
            expires_at=NOW + timedelta(minutes=20),
        )
    )

    conversation_flow = flow(
        resolver=GuidanceResolver(),
        store=store,
        request_factory=CorrelationOnlyFactory(),
    )
    with pytest.raises(ConversationGuidanceRequiredError):
        conversation_flow.handle(
            TeamsConversationRequest(
                text="Can you give me the bitlocker unlock code?",
                identity=identity(),
            )
        )

    assert len(store.puts) == 1
    saved = store.puts[0]
    assert saved["response_kind"] == "guidance"
    assert saved["requested_facts"] == ("bitlocker recovery key",)
    assert saved["resource_selector"] == {"hostname": "AOT-50107"}
