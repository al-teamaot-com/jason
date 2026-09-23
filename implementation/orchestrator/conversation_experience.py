"""Interface-independent coordination for Jason's conversational experience.

This component joins the Conversation Kernel to backend progressive fulfillment without
invoking a provider. Human meaning stays above the boundary; capability/resource
selection stays below it. Existing request construction, Central Orchestrator authority,
provider resolution, execution, evidence, approvals, and audit remain unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from .conversation_kernel import (
    ConversationKernel,
    ConversationKernelDecision,
    ConversationKernelError,
    InformationNeed,
    InformationTarget,
    ReasoningAttempt,
)
from .dynamic_conversation_kernel import DynamicConversationContext
from .information_fulfillment import (
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
    resource_interpreter: object | None = None

    def resolve(
        self,
        *,
        text: str,
        context: DynamicConversationContext,
        principal=None,
    ) -> ConversationExperienceResolution:
        try:
            decision, attempts = self.kernel.interpret(text=text, context=context)
        except ConversationKernelError:
            decision = _recover_verified_observe_read(
                text=text,
                context=context,
            )

            if (
                decision is None
                and self.resource_interpreter is not None
                and principal is not None
            ):
                inquiry = self.resource_interpreter.interpret(
                    text=text,
                    principal=principal,
                )
                if inquiry is not None:
                    decision = _recover_literal_resource_observe_read(
                        text=text,
                        inquiry=inquiry,
                    )

            if decision is None:
                raise
            attempts = ()

        decision = _enrich_literal_resource_selector(
            decision=decision,
            text=text,
            principal=principal,
            resource_interpreter=self.resource_interpreter,
        )

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


def _enrich_literal_resource_selector(
    *,
    decision: ConversationKernelDecision,
    text: str,
    principal,
    resource_interpreter,
) -> ConversationKernelDecision:
    """Preserve selector identity for one already-grounded literal resource target.

    The Conversation Kernel remains authoritative for human meaning and the exact
    literal target. The resource interpreter may only add provider-neutral selector
    identity when it independently agrees on resource type and exact target value.
    It cannot rewrite the target, provider, capability, information need, or authority.
    """

    if (
        decision.outcome != "information"
        or principal is None
        or resource_interpreter is None
    ):
        return decision

    candidates = tuple(
        need
        for need in decision.information_needs
        if need.target.source == "literal"
        and need.target.selector is None
    )
    if not candidates:
        return decision

    targets = {
        (need.target.kind, need.target.reference)
        for need in candidates
    }
    if len(targets) != 1:
        return decision

    target_kind, target_reference = next(iter(targets))

    try:
        inquiry = resource_interpreter.interpret(
            text=text,
            principal=principal,
        )
    except Exception:
        # Selector enrichment is bounded metadata enrichment. Failure must not
        # rewrite or invalidate an otherwise valid kernel interpretation.
        return decision

    if inquiry is None:
        return decision
    if str(getattr(inquiry, "permission_mode", "")).strip() != "observe":
        return decision
    if str(getattr(inquiry, "execution_mode", "")).strip() != "deterministic":
        return decision
    if str(getattr(inquiry, "resource_type", "")).strip() != target_kind:
        return decision

    raw_selector = getattr(inquiry, "resource_selector", None)
    if not isinstance(raw_selector, dict):
        try:
            raw_selector = dict(raw_selector)
        except Exception:
            return decision

    selectors = tuple(
        (str(key).strip(), str(value).strip())
        for key, value in raw_selector.items()
        if str(key).strip() and str(value).strip()
    )
    if len(selectors) != 1:
        return decision

    selector_name, selector_value = selectors[0]
    if selector_value != target_reference:
        return decision

    enriched = tuple(
        replace(
            need,
            target=replace(need.target, selector=selector_name),
        )
        if (
            need.target.source == "literal"
            and need.target.selector is None
            and need.target.kind == target_kind
            and need.target.reference == target_reference
        )
        else need
        for need in decision.information_needs
    )

    return replace(decision, information_needs=enriched)


def _recover_literal_resource_observe_read(
    *,
    text: str,
    inquiry,
) -> ConversationKernelDecision | None:
    """Recover one safe literal resource read after kernel interpretation fails.

    The resource interpreter may establish only provider-neutral resource type
    and a human-grounded selector. It does not determine provider, capability,
    evidence path, or authoritative operational value.

    The original human request remains the information need so downstream
    governed evidence reasoning must prove the actual answer.
    """

    clean_text = text.strip()
    if not clean_text:
        return None

    if str(getattr(inquiry, "permission_mode", "")).strip() != "observe":
        return None

    if str(getattr(inquiry, "execution_mode", "")).strip() != "deterministic":
        return None

    resource_type = str(getattr(inquiry, "resource_type", "")).strip()
    if not resource_type:
        return None

    raw_selector = getattr(inquiry, "resource_selector", None)
    if not isinstance(raw_selector, dict):
        try:
            raw_selector = dict(raw_selector)
        except Exception:
            return None

    # The Conversation Experience target contract currently carries one
    # literal reference. Do not collapse compound selectors or choose one
    # arbitrarily.
    selectors = tuple(
        (str(key).strip(), str(value).strip())
        for key, value in raw_selector.items()
        if str(key).strip() and str(value).strip()
    )
    if len(selectors) != 1:
        return None

    selector_name, reference = selectors[0]

    completeness = str(
        getattr(inquiry, "completeness_requirement", "sufficient")
    ).strip()
    if completeness not in {"sufficient", "complete"}:
        completeness = "sufficient"

    return ConversationKernelDecision(
        outcome="information",
        information_needs=(
            InformationNeed(
                target=InformationTarget(
                    kind=resource_type,
                    source="literal",
                    reference=reference,
                    entity_ref=None,
                    selector=selector_name,
                ),
                need=clean_text,
                authority="observe",
                temporal_scope="unspecified",
                completeness=completeness,
                relationship=None,
            ),
        ),
        topic=None,
    )



def _recover_verified_observe_read(
    *,
    text: str,
    context: DynamicConversationContext,
) -> ConversationKernelDecision | None:
    """Recover a failed interpretation only from unambiguous verified identity.

    This is intentionally not semantic question handling. It does not interpret facts,
    actions, providers, capabilities, fields, or synonyms. It merely recognizes when
    the human explicitly named exactly one resource that Jason has already established
    through governed evidence.

    Recovery is always observe-only. Downstream governed fulfillment and evidence
    verification still determine whether the human's actual question can be answered.
    """

    clean_text = text.strip()
    if not clean_text:
        return None

    folded_text = clean_text.casefold()
    matches = {}

    for entity in context.entities:
        verified_names = (
            entity.canonical_id.strip(),
            entity.display_name.strip(),
        )
        if any(
            name and name.casefold() in folded_text
            for name in verified_names
        ):
            matches[entity.ref] = entity

    if len(matches) != 1:
        return None

    entity = next(iter(matches.values()))

    return ConversationKernelDecision(
        outcome="information",
        information_needs=(
            InformationNeed(
                target=InformationTarget(
                    kind=entity.kind,
                    source="verified_entity",
                    reference=entity.canonical_id,
                    entity_ref=entity.ref,
                ),
                # Preserve the human's actual request. Evidence reasoning determines
                # what, if anything, in the governed provider result supports it.
                need=clean_text,
                authority="observe",
                temporal_scope="unspecified",
                completeness="sufficient",
                relationship=None,
            ),
        ),
        topic=context.active_topic,
    )
