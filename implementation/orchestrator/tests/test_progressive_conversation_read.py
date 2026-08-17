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
    ReasoningAttempt,
    ReasoningBackend,
    ValidatedReasoningPool,
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


class FakeClient:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def complete(self, *, system, user, schema, max_output_tokens=160):
        self.calls.append((system, user, schema, max_output_tokens))
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


class FakeEvidenceReasoner:
    def __init__(self, *selections):
        self.selections = list(selections)
        self.calls = []

    def select(self, *, question, sanitized_data):
        self.calls.append((question, sanitized_data))
        return self.selections.pop(0)


class FakeRegistry:
    def __init__(self, items):
        self.items = tuple(items)

    def list_all(self):
        return self.items


class FakeExecutor:
    def __init__(self, outputs):
        self.outputs = dict(outputs)
        self.calls = []

    def execute(self, intent):
        self.calls.append(intent)
        data = self.outputs[intent.capability_name]
        return OrchestrationResult(
            execution_id=f"exec-{len(self.calls)}",
            correlation_id="corr-1",
            capability_name=intent.capability_name,
            status=OrchestrationStatus.SUCCEEDED,
            stage=ExecutionStage.COMPLETED,
            reason_codes=("test",),
            resolution=None,
            output={
                "provider": "provider-one",
                "data": data,
            },
            attempts=1,
            provider_id="provider-one",
        )


class CapturingAnswerer:
    def __init__(self):
        self.requests = []

    def answer(self, request):
        self.requests.append(request)
        return ConversationAnswer(
            text="final governed conversational answer",
            support_ids=tuple(item.support_id for item in request.supports),
        )


def capability(name, *, types, role, purpose):
    return SimpleNamespace(
        capability_name=name,
        lifecycle_status=CapabilityLifecycle.ACTIVE,
        metadata={
            "provider_neutral": "true",
            "read_only": "true",
            "resource_types": types,
            "operation": "search",
            "selector_keys": "name",
            "resource_role": role,
        },
        risk_level=SimpleNamespace(value="low"),
        display_name=name,
        business_purpose=purpose,
    )


def registry_catalog():
    return RegistryBackedFulfillmentCatalog(
        registry=FakeRegistry(
            (
                capability(
                    "endpoint.device.search",
                    types="endpoint",
                    role="primary",
                    purpose="general endpoint read",
                ),
                capability(
                    "endpoint.software.search",
                    types="endpoint_software,endpoint",
                    role="specialized",
                    purpose="software inventory",
                ),
                capability(
                    "endpoint.history.search",
                    types="endpoint_history,endpoint",
                    role="specialized",
                    purpose="historical endpoint evidence",
                ),
            )
        )
    )


def need(description="requested endpoint information"):
    return InformationNeed(
        target=InformationTarget(
            kind="endpoint",
            source="literal",
            reference="NODE-77",
        ),
        need=description,
        authority="observe",
    )


def resolution(catalog, *needs):
    available = {item.capability_name: item for item in catalog.list_available()}
    planned = tuple(
        PlannedInformationNeed(
            need=item,
            step=FulfillmentStep(
                capability_name="endpoint.device.search",
                target_reference=item.target.reference,
                target_source=item.target.source,
                information_need=item.need,
                authority=item.authority,
            ),
            capability=available["endpoint.device.search"],
        )
        for item in needs
    )
    return ConversationExperienceResolution(
        decision=ConversationKernelDecision(
            outcome="information",
            information_needs=tuple(needs),
            topic="endpoint question",
        ),
        context=DynamicConversationContext(
            conversation_id="conv-1",
            principal_id="person-al",
            organization_id="aot",
        ),
        reasoning_attempts=(
            ReasoningAttempt(
                backend="conversation-model",
                attempt=1,
                outcome="accepted",
            ),
        ),
        planned_information=planned,
        intent=ConversationIntent(
            capability_name="endpoint.device.search",
            arguments={
                "name": "NODE-77",
                "requested_facts": ["original human question"],
            },
            permission_mode="observe",
            risk="low",
        ),
    )


def reasoning_pool(client):
    return ValidatedReasoningPool(
        backends=(ReasoningBackend(name="backend-model", client=client),)
    )


def engine(*, catalog, evidence_reasoner, gap_client, answerer):
    no_binding_calls_expected = FakeClient()
    binding_pool = reasoning_pool(no_binding_calls_expected)
    return ProgressiveConversationReadEngine(
        evidence=ConversationEvidenceSupportExtractor(reasoner=evidence_reasoner),
        gaps=EvidenceGapFulfillmentPlanner(
            catalog=catalog,
            reasoning=reasoning_pool(gap_client),
        ),
        catalog=catalog,
        intent_builder=InformationNeedIntentBuilder(reasoning=binding_pool),
        answerer=answerer,
    )


def test_primary_support_stops_immediately_without_specialized_reads():
    catalog = registry_catalog()
    evidence = FakeEvidenceReasoner(
        DynamicEvidenceSelection(
            answer_type="direct",
            evidence_paths=("/answer",),
        )
    )
    gaps = FakeClient()
    answerer = CapturingAnswerer()
    service = engine(
        catalog=catalog,
        evidence_reasoner=evidence,
        gap_client=gaps,
        answerer=answerer,
    )
    executor = FakeExecutor(
        {
            "endpoint.device.search": {"answer": "Primary Value"},
        }
    )

    answer = service.fulfill(
        question="What is the requested endpoint information for NODE-77?",
        resolution=resolution(catalog, need()),
        executor=executor,
    )

    assert answer.text == "final governed conversational answer"
    assert [item.capability_name for item in executor.calls] == [
        "endpoint.device.search"
    ]
    assert gaps.calls == []
    assert answerer.requests[0].supports[0].value == "Primary Value"


def test_poor_specialized_order_only_adds_latency_and_cannot_become_the_answer():
    catalog = registry_catalog()
    evidence = FakeEvidenceReasoner(
        DynamicEvidenceSelection(answer_type="unavailable"),
        DynamicEvidenceSelection(answer_type="unavailable"),
        DynamicEvidenceSelection(
            answer_type="direct",
            evidence_paths=("/answer",),
        ),
    )
    # The backend deliberately chooses the wrong specialized resource first.
    gaps = FakeClient({"capability_name": "endpoint.software.search"})
    answerer = CapturingAnswerer()
    service = engine(
        catalog=catalog,
        evidence_reasoner=evidence,
        gap_client=gaps,
        answerer=answerer,
    )
    executor = FakeExecutor(
        {
            "endpoint.device.search": {"unrelated": "primary"},
            "endpoint.software.search": {"unrelated": "software"},
            "endpoint.history.search": {"answer": "Recovered Value"},
        }
    )

    service.fulfill(
        question="What historical condition applies to NODE-77?",
        resolution=resolution(catalog, need("historical condition")),
        executor=executor,
    )

    assert [item.capability_name for item in executor.calls] == [
        "endpoint.device.search",
        "endpoint.software.search",
        "endpoint.history.search",
    ]
    assert answerer.requests[0].supports[0].value == "Recovered Value"
    assert answerer.requests[0].limitations == ()


def test_two_needs_on_same_primary_resource_use_one_provider_read():
    catalog = registry_catalog()
    evidence = FakeEvidenceReasoner(
        DynamicEvidenceSelection(
            answer_type="direct",
            evidence_paths=("/first",),
        ),
        DynamicEvidenceSelection(
            answer_type="direct",
            evidence_paths=("/second",),
        ),
    )
    answerer = CapturingAnswerer()
    service = engine(
        catalog=catalog,
        evidence_reasoner=evidence,
        gap_client=FakeClient(),
        answerer=answerer,
    )
    executor = FakeExecutor(
        {
            "endpoint.device.search": {
                "first": "One",
                "second": "Two",
            }
        }
    )

    service.fulfill(
        question="Give me both pieces of information for NODE-77.",
        resolution=resolution(
            catalog,
            need("first information need"),
            need("second information need"),
        ),
        executor=executor,
    )

    assert len(executor.calls) == 1
    assert {item.value for item in answerer.requests[0].supports} == {"One", "Two"}


def test_exhausted_evidence_becomes_bounded_limitation_not_invented_support():
    catalog = registry_catalog()
    evidence = FakeEvidenceReasoner(
        DynamicEvidenceSelection(answer_type="unavailable"),
        DynamicEvidenceSelection(answer_type="unavailable"),
        DynamicEvidenceSelection(answer_type="unavailable"),
    )
    gaps = FakeClient({"capability_name": "endpoint.software.search"})
    answerer = CapturingAnswerer()
    service = engine(
        catalog=catalog,
        evidence_reasoner=evidence,
        gap_client=gaps,
        answerer=answerer,
    )
    executor = FakeExecutor(
        {
            "endpoint.device.search": {"x": 1},
            "endpoint.software.search": {"y": 2},
            "endpoint.history.search": {"z": 3},
        }
    )

    service.fulfill(
        question="Tell me the unavailable information for NODE-77.",
        resolution=resolution(catalog, need("unavailable information")),
        executor=executor,
    )

    request = answerer.requests[0]
    assert request.supports == ()
    assert len(request.limitations) == 1
    assert "did not establish" in request.limitations[0].reason


def test_internal_capability_and_provider_identifiers_are_kept_for_answer_guarding():
    catalog = registry_catalog()
    evidence = FakeEvidenceReasoner(
        DynamicEvidenceSelection(
            answer_type="direct",
            evidence_paths=("/answer",),
        )
    )
    answerer = CapturingAnswerer()
    service = engine(
        catalog=catalog,
        evidence_reasoner=evidence,
        gap_client=FakeClient(),
        answerer=answerer,
    )
    executor = FakeExecutor(
        {"endpoint.device.search": {"answer": "Value"}}
    )

    service.fulfill(
        question="What is the value for NODE-77?",
        resolution=resolution(catalog, need()),
        executor=executor,
    )

    assert set(answerer.requests[0].internal_identifiers) == {
        "endpoint.device.search",
        "provider-one",
    }
