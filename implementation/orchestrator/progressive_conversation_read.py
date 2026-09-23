"""Execute provider-independent conversation reads through governed evidence pools.

One primary governed read is performed for each structural target group. Any
specialized read acquired for one information need becomes available to every other
need in that same target group during the turn.

The engine never bypasses Central Orchestrator authority and contains no provider
field mappings or question-specific fact routing.
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
from .conversation_experience import (
    ConversationExperienceResolution,
)
from .conversation_kernel import (
    InformationNeed,
    InformationTarget,
)
from .conversation_resource_observation import (
    VerifiedConversationResourceObservation,
    observe_verified_resource,
)
from .contracts import (
    OrchestrationResult,
)
from .evidence_gap_fulfillment import (
    EvidenceGapFulfillmentPlanner,
)
from .information_fulfillment import (
    FulfillmentCapability,
    FulfillmentStep,
    RegistryBackedFulfillmentCatalog,
)
from .information_need_intent import (
    InformationNeedIntentBuilder,
    PlannedInformationNeed,
)
from .teams_conversation_flow import (
    ConversationIntent,
    ConversationIntentPlan,
)


class GovernedConversationIntentExecutor(
    Protocol
):
    """Execute one grounded intent through governed orchestration."""

    def execute(
        self,
        intent: ConversationIntent,
    ) -> OrchestrationResult:
        ...


class ConversationAnswerer(
    Protocol
):
    def answer(
        self,
        request: ConversationAnswerInput,
    ) -> ConversationAnswer:
        ...


@dataclass(frozen=True, slots=True)
class ProgressiveConversationReadResult:
    answer: ConversationAnswer
    verified_resources: tuple[
        VerifiedConversationResourceObservation,
        ...,
    ] = ()


@dataclass(frozen=True, slots=True)
class ProgressiveConversationReadEngine:
    evidence: ConversationEvidenceSupportExtractor
    gaps: EvidenceGapFulfillmentPlanner
    catalog: RegistryBackedFulfillmentCatalog
    intent_builder: InformationNeedIntentBuilder
    answerer: ConversationAnswerer
    max_specialized_reads_per_need: int = 8

    def __post_init__(self) -> None:
        if (
            self.max_specialized_reads_per_need
            < 0
        ):
            raise ValueError(
                "specialized read budget must not be negative"
            )

        if (
            self.max_specialized_reads_per_need
            > 32
        ):
            raise ValueError(
                "specialized read budget exceeds safety bound"
            )

    def fulfill(
        self,
        *,
        question: str,
        resolution: ConversationExperienceResolution,
        executor: GovernedConversationIntentExecutor,
    ) -> ConversationAnswer:
        return self.fulfill_result(
            question=question,
            resolution=resolution,
            executor=executor,
        ).answer

    def fulfill_result(
        self,
        *,
        question: str,
        resolution: ConversationExperienceResolution,
        executor: GovernedConversationIntentExecutor,
    ) -> ProgressiveConversationReadResult:
        if (
            resolution.decision.outcome
            != "information"
        ):
            raise ValueError(
                "progressive read engine requires an information outcome"
            )

        if (
            not resolution.planned_information
            or resolution.intent is None
        ):
            raise ValueError(
                "progressive read engine requires initial governed fulfillment"
            )

        groups = _planned_groups(
            resolution.planned_information
        )

        intents = _intent_sequence(
            resolution.intent
        )

        if len(groups) != len(intents):
            raise RuntimeError(
                "conversation intent grouping no longer matches planned information"
            )

        supports: list[
            ConversationSupport
        ] = []

        limitations: list[
            ConversationLimitation
        ] = []

        internal_identifiers: list[str] = []

        observations: list[
            VerifiedConversationResourceObservation
        ] = []

        available: dict[
            str,
            FulfillmentCapability,
        ] = {
            item.capability_name: item
            for item in (
                self.catalog.list_available()
            )
        }

        for (
            group_index,
            (
                group,
                intent,
            ),
        ) in enumerate(
            zip(
                groups,
                intents,
            ),
            start=1,
        ):
            primary_result = (
                executor.execute(
                    intent
                )
            )

            _record_internal_identifiers(
                internal_identifiers,
                intent=intent,
                result=primary_result,
            )

            primary_observation = (
                observe_verified_resource(
                    planned=group[0],
                    result=primary_result,
                )
            )

            if (
                primary_observation
                is not None
            ):
                observations.append(
                    primary_observation
                )

            # Shared by every information need for this same grounded target.
            evidence_results: list[
                OrchestrationResult
            ] = [
                primary_result
            ]

            attempted_capabilities: list[str] = [
                intent.capability_name
            ]

            for (
                need_index,
                planned,
            ) in enumerate(
                group,
                start=1,
            ):
                assessment = (
                    self._assess_evidence_pool(
                        planned=planned,
                        requested_facts=_requested_facts_from_intent(
                            intent
                        ),
                        results=(
                            evidence_results
                        ),
                        support_prefix=(
                            f"g{group_index}"
                            f"n{need_index}p"
                        ),
                    )
                )

                if (
                    assessment.status
                    == "supported"
                ):
                    supports.extend(
                        assessment.supports
                    )
                    continue

                (
                    recovered,
                    expansion_observations,
                ) = self._expand_need(
                    question=question,
                    planned=planned,
                    requested_facts=_requested_facts_from_intent(
                        intent
                    ),
                    first_assessment=assessment,
                    verified_resource=primary_observation,
                    evidence_results=(
                        evidence_results
                    ),
                    attempted_capabilities=(
                        attempted_capabilities
                    ),
                    executor=executor,
                    available=available,
                    internal_identifiers=(
                        internal_identifiers
                    ),
                    support_prefix=(
                        f"g{group_index}"
                        f"n{need_index}x"
                    ),
                )

                observations.extend(
                    expansion_observations
                )

                if (
                    recovered.status
                    == "supported"
                ):
                    supports.extend(
                        recovered.supports
                    )

                else:
                    limitations.append(
                        ConversationLimitation(
                            information_need=(
                                planned.need.need
                            ),
                            reason=(
                                recovered.reason
                                or (
                                    "the available governed evidence "
                                    "did not establish this information"
                                )
                            ),
                        )
                    )

        answer = self.answerer.answer(
            ConversationAnswerInput(
                question=question.strip(),
                supports=tuple(supports),
                limitations=tuple(
                    limitations
                ),
                internal_identifiers=tuple(
                    dict.fromkeys(
                        internal_identifiers
                    )
                ),
            )
        )

        by_ref = {
            item.entity.ref: item
            for item in observations
        }

        return ProgressiveConversationReadResult(
            answer=answer,
            verified_resources=tuple(
                by_ref.values()
            ),
        )

    def _assess_evidence_pool(
        self,
        *,
        planned: PlannedInformationNeed,
        requested_facts: tuple[str, ...],
        results: list[
            OrchestrationResult
        ],
        support_prefix: str,
    ) -> ConversationEvidenceAssessment:
        if len(results) == 1:
            return self.evidence.assess(
                need=planned.need,
                requested_facts=requested_facts,
                result=results[0],
                support_prefix=(
                    support_prefix
                ),
            )

        return self.evidence.assess_many(
            need=planned.need,
            requested_facts=requested_facts,
            results=tuple(results),
            support_prefix=(
                support_prefix
            ),
        )

    def _expand_need(
        self,
        *,
        question: str,
        planned: PlannedInformationNeed,
        requested_facts: tuple[str, ...],
        first_assessment: ConversationEvidenceAssessment,
        verified_resource: VerifiedConversationResourceObservation | None,
        evidence_results: list[
            OrchestrationResult
        ],
        attempted_capabilities: list[str],
        executor: GovernedConversationIntentExecutor,
        available: dict[
            str,
            FulfillmentCapability,
        ],
        internal_identifiers: list[str],
        support_prefix: str,
    ) -> tuple[
        ConversationEvidenceAssessment,
        tuple[
            VerifiedConversationResourceObservation,
            ...,
        ],
    ]:
        last_assessment = (
            first_assessment
        )

        observations: list[
            VerifiedConversationResourceObservation
        ] = []

        for expansion_index in range(
            1,
            self.max_specialized_reads_per_need
            + 1,
        ):
            attempted = tuple(
                dict.fromkeys(
                    attempted_capabilities
                )
            )

            step = self.gaps.next_step(
                need=planned.need,
                attempted_capabilities=(
                    attempted
                ),
            )

            if step is None:
                break

            if (
                step.capability_name
                in attempted_capabilities
            ):
                raise RuntimeError(
                    "evidence-gap planner repeated an already attempted capability"
                )

            attempted_capabilities.append(
                step.capability_name
            )

            capability = available.get(
                step.capability_name
            )

            if capability is None:
                raise LookupError(
                    "evidence-gap capability is no longer registered"
                )

            specialized = _specialized_planned_need(
                planned=planned,
                step=step,
                capability=capability,
                verified_resource=verified_resource,
            )

            # A specialized capability that cannot accept the already-grounded
            # literal selector may still be used when the primary governed read
            # established one durable provider-neutral resource identity and the
            # specialized capability explicitly accepts resource_id.
            #
            # If neither condition is true, this candidate is skipped rather
            # than weakening target grounding or crashing the whole turn.
            if specialized is None:
                continue

            intent = (
                self.intent_builder.build(
                    human_text=(
                        question.strip()
                    ),
                    planned=(
                        specialized,
                    ),
                )
            )

            if not isinstance(
                intent,
                ConversationIntent,
            ):
                raise RuntimeError(
                    "one specialized information need must produce one governed intent"
                )

            result = executor.execute(
                intent
            )

            _record_internal_identifiers(
                internal_identifiers,
                intent=intent,
                result=result,
            )

            observation = (
                observe_verified_resource(
                    planned=specialized,
                    result=result,
                )
            )

            if observation is not None:
                observations.append(
                    observation
                )

            evidence_results.append(
                result
            )

            last_assessment = (
                self._assess_evidence_pool(
                    planned=planned,
                    requested_facts=requested_facts,
                    results=(
                        evidence_results
                    ),
                    support_prefix=(
                        f"{support_prefix}"
                        f"{expansion_index}"
                    ),
                )
            )

            if (
                last_assessment.status
                == "supported"
            ):
                return (
                    last_assessment,
                    tuple(observations),
                )

        return (
            last_assessment,
            tuple(observations),
        )



def _specialized_planned_need(
    *,
    planned: PlannedInformationNeed,
    step: FulfillmentStep,
    capability: FulfillmentCapability,
    verified_resource: VerifiedConversationResourceObservation | None,
) -> PlannedInformationNeed | None:
    """Preserve a grounded selector or rebind to verified durable identity.

    Rebinding is structural and provider-neutral. It never translates one
    provider field into another and never changes the information need.
    """

    target = planned.need.target

    selector_keys = tuple(
        dict.fromkeys(
            key.strip()
            for key in capability.selector_keys
            if key.strip()
        )
    )

    # Capabilities with no selector contract need no target rebinding.
    if not selector_keys:
        return PlannedInformationNeed(
            need=planned.need,
            step=step,
            capability=capability,
        )

    # The original selector remains authoritative whenever the new
    # capability structurally supports it.
    if (
        target.selector is None
        or target.selector in selector_keys
    ):
        return PlannedInformationNeed(
            need=planned.need,
            step=step,
            capability=capability,
        )

    # Never relabel a literal value under a different selector name.
    # Only a previously verified durable resource identity may cross
    # this selector boundary.
    if (
        verified_resource is None
        or "resource_id" not in selector_keys
    ):
        return None

    entity = verified_resource.entity

    if entity.kind != target.kind:
        raise RuntimeError(
            "verified resource kind changed during specialized read rebinding"
        )

    durable_reference = str(
        entity.canonical_id
    ).strip()

    entity_ref = str(
        entity.ref
    ).strip()

    if (
        not durable_reference
        or not entity_ref
    ):
        return None

    rebound_target = InformationTarget(
        kind=target.kind,
        source="verified_entity",
        reference=durable_reference,
        entity_ref=entity_ref,
        selector="resource_id",
    )

    rebound_need = InformationNeed(
        target=rebound_target,
        need=planned.need.need,
        authority=planned.need.authority,
        temporal_scope=planned.need.temporal_scope,
        completeness=planned.need.completeness,
        relationship=planned.need.relationship,
    )

    rebound_step = FulfillmentStep(
        capability_name=step.capability_name,
        target_reference=durable_reference,
        target_source="verified_entity",
        information_need=planned.need.need,
        authority=planned.need.authority,
    )

    return PlannedInformationNeed(
        need=rebound_need,
        step=rebound_step,
        capability=capability,
    )

def _planned_groups(
    planned: tuple[
        PlannedInformationNeed,
        ...,
    ],
) -> tuple[
    tuple[
        PlannedInformationNeed,
        ...,
    ],
    ...,
]:
    groups: dict[
        tuple[
            str,
            str,
            str,
            str,
        ],
        list[
            PlannedInformationNeed
        ],
    ] = {}

    order: list[
        tuple[
            str,
            str,
            str,
            str,
        ]
    ] = []

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

        groups[key].append(
            item
        )

    return tuple(
        tuple(groups[key])
        for key in order
    )


def _intent_sequence(
    value: (
        ConversationIntent
        | ConversationIntentPlan
    ),
) -> tuple[
    ConversationIntent,
    ...,
]:
    if isinstance(
        value,
        ConversationIntent,
    ):
        return (value,)

    return tuple(
        value.intents
    )


def _record_internal_identifiers(
    target: list[str],
    *,
    intent: ConversationIntent,
    result: OrchestrationResult,
) -> None:
    target.append(
        intent.capability_name
    )

    if result.provider_id:
        target.append(
            result.provider_id
        )



def _requested_facts_from_intent(
    intent: ConversationIntent,
) -> tuple[str, ...]:
    """Preserve the governed canonical fact obligation established in planning."""

    raw = intent.arguments.get(
        "requested_facts",
        (),
    )

    if isinstance(raw, str):
        value = raw.strip()
        return (value,) if value else ()

    if not isinstance(
        raw,
        (list, tuple),
    ):
        return ()

    return tuple(
        str(item).strip()
        for item in raw
        if str(item).strip()
    )
