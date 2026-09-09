from __future__ import annotations

from types import SimpleNamespace

from kernel.capabilities import CapabilityLifecycle
from orchestrator.conversation_answer import ConversationAnswer
from orchestrator.conversation_evidence_support import ConversationEvidenceSupportExtractor
from orchestrator.conversation_experience import ConversationExperienceResolution
from orchestrator.conversation_kernel import (
    ConversationKernelDecision,
    InformationNeed,
    InformationTarget,
)
from orchestrator.contracts import (
    ExecutionStage,
    OrchestrationResult,
    OrchestrationStatus,
)
from orchestrator.dynamic_conversation_kernel import DynamicConversationContext
from orchestrator.dynamic_resource_response import DynamicEvidenceSelection
from orchestrator.evidence_gap_fulfillment import EvidenceGapFulfillmentPlanner
from orchestrator.information_fulfillment import (
    FulfillmentStep,
    RegistryBackedFulfillmentCatalog,
)
from orchestrator.information_need_intent import (
    InformationNeedIntentBuilder,
    PlannedInformationNeed,
)
from orchestrator.progressive_conversation_read import ProgressiveConversationReadEngine
from orchestrator.teams_conversation_flow import ConversationIntent


class FakeRegistry:
    def __init__(self, items):
        self.items = tuple(items)

    def list_all(self):
        return self.items


class NoModelCalls:
    def complete(self, **kwargs):
        raise AssertionError("model should not be called in this fixture")


class EmptyReasoningPool:
    # Only present to satisfy constructor type in paths that never call it.
    def complete_validated(self, **kwargs):
        raise AssertionError("reasoning pool should not be called in this fixture")


class EvidenceReasoner:
    def select(self, *, question, sanitized_data):
        return DynamicEvidenceSelection(
            answer_type="direct",
            evidence_paths=("/provider_data/value",),
        )


class Answerer:
    def answer(self, request):
        return ConversationAnswer(
            text="Natural supported answer.",
            support_ids=tuple(item.support_id for item in request.supports),
        )


class Executor:
    def execute(self, intent):
        return OrchestrationResult(
            execution_id="exec-verified-resource",
            correlation_id="corr-1",
            capability_name=intent.capability_name,
            status=OrchestrationStatus.SUCCEEDED,
            stage=ExecutionStage.COMPLETED,
            reason_codes=("test",),
            resolution=None,
            output={
                "provider": "provider-one",
                "data": {
                    "resource_matches": [
                        {"resource_id": "durable-node-77"}
                    ],
                    "resolved_resource_id": "durable-node-77",
                    "provider_data": {"value": "Example"},
                },
            },
            attempts=1,
            provider_id="provider-one",
        )


def capability():
    return SimpleNamespace(
        capability_name="endpoint.device.search",
        lifecycle_status=CapabilityLifecycle.ACTIVE,
        metadata={
            "provider_neutral": "true",
            "read_only": "true",
            "resource_types": "endpoint",
            "operation": "search",
            "selector_keys": "name",
            "resource_role": "primary",
        },
        risk_level=SimpleNamespace(value="low"),
        display_name="Endpoint Search",
        business_purpose="general endpoint read",
    )


def test_progressive_read_returns_verified_resource_observation_for_context_persistence():
    catalog = RegistryBackedFulfillmentCatalog(
        registry=FakeRegistry((capability(),))
    )
    target = InformationTarget(
        kind="endpoint",
        source="literal",
        reference="NODE-77",
    )
    need = InformationNeed(
        target=target,
        need="requested value",
        authority="observe",
    )
    offered = catalog.list_available()[0]
    planned = PlannedInformationNeed(
        need=need,
        step=FulfillmentStep(
            capability_name=offered.capability_name,
            target_reference=target.reference,
            target_source=target.source,
            information_need=need.need,
            authority=need.authority,
        ),
        capability=offered,
    )
    resolution = ConversationExperienceResolution(
        decision=ConversationKernelDecision(
            outcome="information",
            information_needs=(need,),
            topic="endpoint question",
        ),
        context=DynamicConversationContext(
            conversation_id="conversation-1",
            principal_id="person-al",
            organization_id="aot",
        ),
        reasoning_attempts=(),
        planned_information=(planned,),
        intent=ConversationIntent(
            capability_name=offered.capability_name,
            arguments={
                "name": "NODE-77",
                "requested_facts": ["What is the value for NODE-77?"],
            },
            permission_mode="observe",
            risk="low",
        ),
    )
    engine = ProgressiveConversationReadEngine(
        evidence=ConversationEvidenceSupportExtractor(reasoner=EvidenceReasoner()),
        gaps=EvidenceGapFulfillmentPlanner(
            catalog=catalog,
            reasoning=EmptyReasoningPool(),
        ),
        catalog=catalog,
        intent_builder=InformationNeedIntentBuilder(
            reasoning=EmptyReasoningPool()
        ),
        answerer=Answerer(),
    )

    result = engine.fulfill_result(
        question="What is the value for NODE-77?",
        resolution=resolution,
        executor=Executor(),
    )

    assert result.answer.text == "Natural supported answer."
    assert len(result.verified_resources) == 1
    observation = result.verified_resources[0]
    assert observation.entity.kind == "endpoint"
    assert observation.entity.canonical_id == "durable-node-77"
    assert observation.entity.display_name == "NODE-77"
    assert observation.resolution.mention == "NODE-77"
