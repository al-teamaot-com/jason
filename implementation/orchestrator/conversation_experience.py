"""Interface-independent coordination for Jason's conversational experience.

This component joins the Conversation Kernel to backend progressive fulfillment without
invoking a provider. Human meaning stays above the boundary; capability/resource
selection stays below it. Existing request construction, Central Orchestrator authority,
provider resolution, execution, evidence, approvals, and audit remain unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .conversation_kernel import (
    ConversationKernel,
    ConversationKernelDecision,
    DynamicConversationContext,
    ReasoningAttempt,
)
from .information_fulfillment import (
    FulfillmentCapability,
    GovernedInitialFulfillmentPlanner,
    RegistryBackedFulfillmentCatalog,
)
from .information_need_intent import (
    InformationNeedIntentBuilder,
    PlannedInformationNeed,
)
from .teams_conversation_flow import ConversationIntent, ConversationIntentPlan


class ConversationActionFulfillmentRequired(LookupError):
    """The turn requests authority handled by the governed action fulfillment path."""


@dataclass(frozen=True, slots=True)
class ConversationExperienceResolution:
    """One validated conversational decision before provider execution."""

    decision: ConversationKernelDecision
    context: DynamicConversationContext
    reasoning_attempts: tuple[ReasoningAttempt, ...]
    planned_information: tuple[PlannedInformationNeed, ...] = ()
    intent: ConversationIntent | ConversationIntentPlan | None = None

    def __post_init__(self) -> None:
        if self.decision.outcome == "information":
            if not self.planned_information or self.intent is None:
                raise ValueError(
                    "information outcome requires planned fulfillment and governed intent"
                )
        elif self.planned_information or self.intent is not None:
            raise ValueError(
                "non-information outcome cannot carry executable fulfillment state"
            )


@dataclass(frozen=True, slots=True)
class ConversationExperienceCoordinator:
    """Interpret a turn and prepare the minimum governed backend work required."""

    kernel: ConversationKernel
    fulfillment: GovernedInitialFulfillmentPlanner
    catalog: RegistryBackedFulfillmentCatalog
    intent_builder: InformationNeedIntentBuilder

    def resolve(
        self,
        *,
        text: str,
        context: DynamicConversationContext,
    ) -> ConversationExperienceResolution:
        decision, attempts = self.kernel.interpret(text=text, context=context)
        updated_context = context.with_verified_entities((), topic=decision.topic)

        if decision.outcome != "information":
            return ConversationExperienceResolution(
                decision=decision,
                context=updated_context,
                reasoning_attempts=attempts,
            )

        if any(need.authority != "observe" for need in decision.information_needs):
            raise ConversationActionFulfillmentRequired(
                "non-observe conversation need requires governed action fulfillment"
            )

        available = {
            item.capability_name: item
            for item in self.catalog.list_available()
        }
        planned: list[PlannedInformationNeed] = []
        for need in decision.information_needs:
            plan = self.fulfillment.plan(need)
            if len(plan.steps) != 1:
                raise RuntimeError(
                    "initial progressive fulfillment must produce exactly one primary step"
                )
            step = plan.steps[0]
            capability = available.get(step.capability_name)
            if capability is None:
                raise LookupError(
                    "planned fulfillment capability is no longer registered"
                )
            planned.append(
                PlannedInformationNeed(
                    need=need,
                    step=step,
                    capability=capability,
                )
            )

        intent = self.intent_builder.build(
            human_text=text.strip(),
            planned=tuple(planned),
        )
        return ConversationExperienceResolution(
            decision=decision,
            context=updated_context,
            reasoning_attempts=attempts,
            planned_information=tuple(planned),
            intent=intent,
        )
