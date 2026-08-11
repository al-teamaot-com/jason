from __future__ import annotations

from dataclasses import dataclass

import pytest

from jason_cap_007.kernel_registration import email_send_capability
from kernel.capabilities import CapabilityRegistryService, InMemoryCapabilityRegistry
from orchestrator.conversation_action_intent import GovernedActionConversationIntentResolver
from orchestrator.teams_conversation_flow import BoundConversationPrincipal


@dataclass
class FakeReasoner:
    proposal: dict | None

    def propose(self, **kwargs):
        return self.proposal


def registry():
    service = CapabilityRegistryService(registry=InMemoryCapabilityRegistry())
    service.register(email_send_capability())
    return service


def principal(email="al@example.com"):
    return BoundConversationPrincipal(
        principal_id="person-al",
        organization_id="aot",
        email_address=email,
    )


def test_action_resolver_maps_self_target_from_jason_identity_binding():
    resolver = GovernedActionConversationIntentResolver(
        registry=registry(),
        reasoner=FakeReasoner(
            {
                "capability_name": "communication.email.send",
                "arguments": {},
                "self_target": True,
            }
        ),
    )

    intent = resolver.resolve(text="send me an email", principal=principal())

    assert intent is not None
    assert intent.capability_name == "communication.email.send"
    assert intent.permission_mode == "execute"
    assert intent.execution_mode == "deterministic"
    assert intent.risk == "high"
    assert intent.arguments["to"] == ["al@example.com"]
    assert intent.arguments["subject"] == "Message from Jason"
    assert intent.arguments["text_body"] == "You asked Jason to send you an email."


def test_action_resolver_fails_closed_when_self_target_has_no_bound_address():
    resolver = GovernedActionConversationIntentResolver(
        registry=registry(),
        reasoner=FakeReasoner(
            {
                "capability_name": "communication.email.send",
                "arguments": {},
                "self_target": True,
            }
        ),
    )

    with pytest.raises(LookupError, match="no governed delivery address"):
        resolver.resolve(text="send me an email", principal=principal(email=None))


def test_action_resolver_rejects_arguments_outside_capability_contract():
    resolver = GovernedActionConversationIntentResolver(
        registry=registry(),
        reasoner=FakeReasoner(
            {
                "capability_name": "communication.email.send",
                "arguments": {"provider": "aws-ses"},
                "self_target": False,
            }
        ),
    )

    with pytest.raises(PermissionError, match="outside the governed contract"):
        resolver.resolve(text="send email", principal=principal())
