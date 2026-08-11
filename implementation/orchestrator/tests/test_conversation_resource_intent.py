from __future__ import annotations

from datetime import datetime, timezone

import pytest

from kernel.capabilities import CapabilityRegistryService, InMemoryCapabilityRegistry
from kernel.execution_providers import (
    ExecutionProviderRegistryService,
    InMemoryExecutionProviderRegistry,
)
from orchestrator.conversation_resource_intent import (
    GovernedResourceConversationIntentResolver,
    ReasonedResourceInquiryInterpreter,
)
from orchestrator.resource_capability_catalog import register_endpoint_resource_foundation
from orchestrator.resource_inquiry import GovernedResourceInquiryPlanner
from orchestrator.resource_reasoner import MetadataResourceCapabilityReasoner
from orchestrator.teams_conversation_flow import BoundConversationPrincipal


NOW = datetime(2026, 8, 10, tzinfo=timezone.utc)


class Reasoner:
    def __init__(self, proposal):
        self.proposal = proposal
        self.calls = []

    def propose(self, *, text, organization_id, client_id):
        self.calls.append(
            {
                "text": text,
                "organization_id": organization_id,
                "client_id": client_id,
            }
        )
        return self.proposal


def principal():
    return BoundConversationPrincipal(
        principal_id="person-al",
        organization_id="aot",
        client_id=None,
    )


def resolver(proposal):
    capabilities = CapabilityRegistryService(registry=InMemoryCapabilityRegistry())
    providers = ExecutionProviderRegistryService(registry=InMemoryExecutionProviderRegistry())
    register_endpoint_resource_foundation(
        capabilities=capabilities,
        providers=providers,
        now=NOW,
    )
    reasoner = Reasoner(proposal)
    return (
        GovernedResourceConversationIntentResolver(
            interpreter=ReasonedResourceInquiryInterpreter(reasoner),
            planner=GovernedResourceInquiryPlanner(
                registry=capabilities,
                reasoner=MetadataResourceCapabilityReasoner(),
            ),
        ),
        reasoner,
    )


def test_human_question_becomes_resource_inquiry_then_broad_capability():
    intent_resolver, reasoner = resolver(
        {
            "resource_type": "endpoint",
            "resource_selector": {"hostname": "AOT-50282"},
            "requested_facts": ["last logged in user"],
        }
    )

    intent = intent_resolver.resolve(
        text="Who is logged into AOT-50282?",
        principal=principal(),
    )

    assert intent is not None
    assert intent.capability_name == "endpoint.device.search"
    assert intent.arguments == {
        "hostname": "AOT-50282",
        "requested_facts": ("last logged in user",),
    }
    assert intent.execution_mode == "deterministic"
    assert intent.permission_mode == "observe"
    assert reasoner.calls == [
        {
            "text": "Who is logged into AOT-50282?",
            "organization_id": "aot",
            "client_id": None,
        }
    ]
    # The language reasoner never receives a Datto/provider selection.
    assert "datto" not in repr(reasoner.calls).lower()


def test_language_reasoner_cannot_select_provider_or_capability():
    intent_resolver, _ = resolver(
        {
            "resource_type": "endpoint",
            "resource_selector": {"hostname": "AOT-50282"},
            "requested_facts": ["last logged in user"],
            "provider": "datto_rmm",
            "capability_name": "datto_rmm.device.search",
        }
    )

    with pytest.raises(PermissionError, match="provider/execution selection"):
        intent_resolver.resolve(
            text="Who is logged into AOT-50282?",
            principal=principal(),
        )


def test_language_reasoner_cannot_smuggle_provider_through_selector():
    intent_resolver, _ = resolver(
        {
            "resource_type": "endpoint",
            "resource_selector": {
                "hostname": "AOT-50282",
                "provider_id": "datto_rmm",
            },
            "requested_facts": ["last logged in user"],
        }
    )

    with pytest.raises(PermissionError, match="resource selector"):
        intent_resolver.resolve(
            text="Who is logged into AOT-50282?",
            principal=principal(),
        )


def test_language_reasoner_cannot_smuggle_nested_selector_operators():
    intent_resolver, _ = resolver(
        {
            "resource_type": "endpoint",
            "resource_selector": {"hostname": {"exact": "AOT-50282"}},
            "requested_facts": ["last logged in user"],
        }
    )

    with pytest.raises(ValueError, match="scalar strings"):
        intent_resolver.resolve(
            text="Who is logged into AOT-50282?",
            principal=principal(),
        )


def test_language_reasoner_cannot_turn_read_question_into_execute_authority():
    intent_resolver, _ = resolver(
        {
            "resource_type": "endpoint",
            "resource_selector": {"hostname": "AOT-50282"},
            "requested_facts": ["last logged in user"],
            "permission_mode": "execute",
        }
    )

    with pytest.raises(PermissionError, match="read-only"):
        intent_resolver.resolve(
            text="Who is logged into AOT-50282?",
            principal=principal(),
        )


def test_unrecognized_language_can_return_no_resource_inquiry():
    intent_resolver, _ = resolver(None)

    assert (
        intent_resolver.resolve(
            text="Tell me a joke.",
            principal=principal(),
        )
        is None
    )
