from __future__ import annotations

from datetime import datetime, timezone

import pytest

from kernel.capabilities import CapabilityRegistryService, InMemoryCapabilityRegistry
from orchestrator.governed_semantic_coverage import GovernedSemanticCoverageIntentResolver
from orchestrator.resource_capability_catalog import endpoint_device_search
from orchestrator.semantic_fact_resolver import DEFAULT_SEMANTIC_FACT_RESOLVER
from orchestrator.teams_conversation_flow import (
    BoundConversationPrincipal,
    ConversationGuidanceRequiredError,
)


NOW = datetime(2026, 8, 15, 18, 0, tzinfo=timezone.utc)


class Delegate:
    def __init__(self):
        self.calls = []

    def resolve(self, *, text, principal):
        self.calls.append((text, principal))
        return None


def principal():
    return BoundConversationPrincipal(
        principal_id="person-al",
        organization_id="aot",
    )


def registry():
    service = CapabilityRegistryService(registry=InMemoryCapabilityRegistry())
    service.register(endpoint_device_search(NOW))
    return service


def resolver(delegate):
    return GovernedSemanticCoverageIntentResolver(
        delegate=delegate,
        capabilities=registry(),
        fact_resolver=DEFAULT_SEMANTIC_FACT_RESOLVER,
    )


def test_bitlocker_recovery_key_fails_before_delegate_or_provider_planning():
    delegate = Delegate()

    with pytest.raises(ConversationGuidanceRequiredError) as caught:
        resolver(delegate).resolve(
            text="Can you give me the bitlocker unlock code",
            principal=principal(),
        )

    assert caught.value.reason_code == "governed_fact_not_available"
    assert caught.value.requested_facts == ("bitlocker recovery key",)
    assert "No provider request was made" in caught.value.guidance_text
    assert delegate.calls == []


def test_bitlocker_status_has_declared_coverage_and_reaches_delegate():
    delegate = Delegate()

    assert resolver(delegate).resolve(
        text="What is the bitlocker status for AOT-50107?",
        principal=principal(),
    ) is None
    assert len(delegate.calls) == 1


@pytest.mark.parametrize(
    "text",
    (
        "What is the IP address of AOT-50107?",
        "When was AOT-50107 last seen?",
    ),
)
def test_endpoint_semantic_facts_use_structural_resource_coverage(text):
    delegate = Delegate()

    assert resolver(delegate).resolve(text=text, principal=principal()) is None
    assert len(delegate.calls) == 1
