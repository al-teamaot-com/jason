from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import pytest

from orchestrator.conversation_resource_intent import (
    GovernedResourceConversationIntentResolver,
    ReasonedResourceInquiryInterpreter,
)
from orchestrator.resource_capability_catalog import (
    register_endpoint_resource_foundation,
)
from orchestrator.resource_inquiry import GovernedResourceInquiryPlanner
from orchestrator.resource_reasoner import MetadataResourceCapabilityReasoner
from orchestrator.teams_conversation_flow import BoundConversationPrincipal
from kernel.capabilities import CapabilityRegistryService, InMemoryCapabilityRegistry
from kernel.execution_providers import (
    ExecutionProviderRegistryService,
    InMemoryExecutionProviderRegistry,
)
from datetime import datetime, timezone


@dataclass
class FakeReasoner:
    result: Mapping[str, Any] | None

    def __post_init__(self) -> None:
        self.calls: list[Mapping[str, Any]] = []

    def propose(
        self,
        *,
        text: str,
        organization_id: str,
        client_id: str | None,
    ) -> Mapping[str, Any] | None:
        self.calls.append(
            {
                "text": text,
                "organization_id": organization_id,
                "client_id": client_id,
            }
        )
        return self.result


def principal() -> BoundConversationPrincipal:
    return BoundConversationPrincipal(
        principal_id="person-al",
        organization_id="aot",
        client_id=None,
    )


def resolver(reasoner_result: Mapping[str, Any] | None):
    capabilities = CapabilityRegistryService(registry=InMemoryCapabilityRegistry())
    providers = ExecutionProviderRegistryService(registry=InMemoryExecutionProviderRegistry())
    register_endpoint_resource_foundation(
        capabilities=capabilities,
        providers=providers,
        now=datetime(2026, 8, 12, tzinfo=timezone.utc),
    )
    reasoner = FakeReasoner(reasoner_result)
    interpreter = ReasonedResourceInquiryInterpreter(reasoner)
    planner = GovernedResourceInquiryPlanner(
        registry=capabilities,
        reasoner=MetadataResourceCapabilityReasoner(),
    )
    return (
        GovernedResourceConversationIntentResolver(
            interpreter=interpreter,
            planner=planner,
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
        "result_intent": "summary",
        "completeness_requirement": "sufficient",
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
        }
    )

    with pytest.raises(PermissionError):
        intent_resolver.resolve(
            text="Who is logged into AOT-50282?",
            principal=principal(),
        )


def test_language_reasoner_selector_must_be_grounded_in_human_text():
    intent_resolver, _ = resolver(
        {
            "resource_type": "endpoint",
            "resource_selector": {"hostname": "AOT-99999"},
            "requested_facts": ["last logged in user"],
        }
    )

    with pytest.raises(ValueError):
        intent_resolver.resolve(
            text="Who is logged into AOT-50282?",
            principal=principal(),
        )
