"""Execute provider-independent conversation reads progressively through governed intents.

The engine uses the Central-Orchestrator-facing intent contract but never bypasses it.
One primary resource is read first. Unsupported information needs may add one specialized
read at a time, re-evaluating governed evidence after each attempt. A weak backend model
can therefore increase latency by choosing a poor search order, but it cannot make an
unsupported fact become a human-facing answer or trigger speculative fan-out.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .conversation_answer import (
    ConversationAnswer,
    ConversationAnswerInput,
    ConversationLimitation,
    ConversationSupport,
)
from .conversation_evidence_support import (
    ConversationEvidenceAssessment,
    ConversationEvidenceSupportExtractor,
)
from .conversation_experience import ConversationExperienceResolution
from .contracts import OrchestrationResult
from .evidence_gap_fulfillment import EvidenceGapFulfillmentPlanner
from .information_fulfillment import RegistryBackedFulfillmentCatalog
from .information_need_intent import (
    InformationNeedIntentBuilder,
    PlannedInformationNeed,
)
from .teams_conversation_flow import ConversationIntent, ConversationIntentPlan


class GovernedConversationIntentExecutor(Protocol):
    """Execute one already-grounded intent through Jason's governed orchestration path."""

    def execute(self, intent: ConversationIntent) -> OrchestrationResult: ...


class ConversationAnswerer(Protocol):
    def answer(self, request: ConversationAnswerInput) -> ConversationAnswer: ...


@dataclass(frozen=True, slots=True)
class ProgressiveConversationReadEngine:
    """Trade backend work/latency for reliable evidence before conversational delivery."""

    evidence: ConversationEvidenceSupportExtractor
    gaps: EvidenceGapFulfillmentPlanner
    catalog: RegistryBackedFulfillmentCatalog
    intent_builder: InformationNeedIntentBuilder
    answerer: ConversationAnswerer
    max_specialized_reads_per_need: int = 8

    def __post_init__(self) -> None:
        if self.max_specialized_reads_per_need < 0:
            raise ValueError("specialized read budget must not be negative")
        if self.max_specialized_reads_per_need > 32:
            raise ValueError("specialized read budget exceeds safety bound")

    def fulfill(
        self,
        *,
        question: str,
        resolution: ConversationExperienceResolution,
        executor: GovernedConversationIntentExecutor,
    ) -> ConversationAnswer:
        if resolution.decision.outcome != "information":
            raise ValueError("progressive read engine requires an information outcome")
        if not resolution.planned_information or resolution.intent is None:
            raise ValueError("progressive read engine requires initial governed fulfillment")

        groups = _planned_groups(resolution.planned_information)
        intents = _intent_sequence(resolution.intent)
        if len(groups) != len(intents):
            raise RuntimeError(
                "conversation intent grouping no longer matches planned information"
            )

        supports: list[ConversationSupport] = []
        limitations: list[ConversationLimitation] = []
        internal_identifiers: list[str] = []
        available = {
            item.capability_name: item
            for item in self.catalog.list_available()
        }

        for group_index, (group, intent) in enumerate(zip(groups, intents), start=1):
            result = executor.execute(intent)
            _record_internal_identifiers(
                internal_identifiers,
                intent=intent,
                result=result,
            )
            for need_index, planned in enumerate(group, start=1):
                assessment = self.evidence.assess(
                    need=planned.need,
                    result=result,
                    support_prefix=f"g{group_index}n{need_index}p",
                )
                if assessment.status == "supported":
                    supports.extend(assessment.supports)
                    continue

                recovered = self._expand_need(
                    question=question,
                    planned=planned,
                    first_assessment=assessment,
                    executor=executor,
                    available=available,
                    internal_identifiers=internal_identifiers,
                    support_prefix=f"g{group_index}n{need_index}x",
                )
                if recovered.status == "supported":
                    supports.extend(recovered.supports)
                else:
                    limitations.append(
                        ConversationLimitation(
                            information_need=planned.need.need,
                            reason=recovered.reason
                            or "the available governed evidence did not establish this information",
                        )
                    )

        return self.answerer.answer(
            ConversationAnswerInput(
                question=question.strip(),
                supports=tuple(supports),
                limitations=tuple(limitations),
                internal_identifiers=tuple(dict.fromkeys(internal_identifiers)),
            )
        )

    def _expand_need(
        self,
        *,
        question: str,
        planned: PlannedInformationNeed,
        first_assessment: ConversationEvidenceAssessment,
        executor: GovernedConversationIntentExecutor,
        available: dict[str, object],
        internal_identifiers: list[str],
        support_prefix: str,
    ) -> ConversationEvidenceAssessment:
        attempted = [planned.capability.capability_name]
        last_assessment = first_assessment
        for expansion_index in range(1, self.max_specialized_reads_per_need + 1):
            step = self.gaps.next_step(
                need=planned.need,
                attempted_capabilities=tuple(attempted),
            )
            if step is None:
                break
            attempted.append(step.capability_name)
            capability = available.get(step.capability_name)
            if capability is None:
                raise LookupError(
                    "evidence-gap capability is no longer registered"
                )
            specialized = PlannedInformationNeed(
                need=planned.need,
                step=step,
                capability=capability,  # type: ignore[arg-type]
            )
            intent = self.intent_builder.build(
                human_text=question.strip(),
                planned=(specialized,),
            )
            if not isinstance(intent, ConversationIntent):
                raise RuntimeError(
                    "one specialized information need must produce one governed intent"
                )
            result = executor.execute(intent)
            _record_internal_identifiers(
                internal_identifiers,
                intent=intent,
                result=result,
            )
            last_assessment = self.evidence.assess(
                need=planned.need,
                result=result,
                support_prefix=f"{support_prefix}{expansion_index}",
            )
            if last_assessment.status == "supported":
                return last_assessment
        return last_assessment


def _planned_groups(
    planned: tuple[PlannedInformationNeed, ...],
) -> tuple[tuple[PlannedInformationNeed, ...], ...]:
    groups: dict[tuple[str, str, str, str], list[PlannedInformationNeed]] = {}
    order: list[tuple[str, str, str, str]] = []
    for item in planned:
        key = (
            item.capability.capability_name,
            item.need.target.source,
            item.need.target.reference,
            item.need.authority,
        )
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(item)
    return tuple(tuple(groups[key]) for key in order)


def _intent_sequence(
    value: ConversationIntent | ConversationIntentPlan,
) -> tuple[ConversationIntent, ...]:
    if isinstance(value, ConversationIntent):
        return (value,)
    return tuple(value.intents)


def _record_internal_identifiers(
    target: list[str],
    *,
    intent: ConversationIntent,
    result: OrchestrationResult,
) -> None:
    target.append(intent.capability_name)
    if result.provider_id:
        target.append(result.provider_id)
