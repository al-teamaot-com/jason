"""Bounded generic investigation loop.

The model chooses only the next information observation.
Every observation executes through Jason's existing governed boundary.

The loop owns no provider mappings, question handlers, field mappings, or
authority decisions.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Any

from .dynamic_conversation_kernel import (
    DynamicConversationContext,
)
from .investigation_decision import (
    InvestigationDecision,
    InvestigationDecisionEngine,
    InvestigationDecisionKind,
)
from .investigation_execution import (
    GovernedConversationIntentExecutor,
    GovernedInvestigationExecutor,
    InvestigationEvidenceWorkspace,
)


class InvestigationLoopStatus(str, Enum):
    ANSWER = "answer"
    CANNOT_ESTABLISH = "cannot_establish"
    EXHAUSTED = "exhausted"


@dataclass(frozen=True, slots=True)
class InvestigationLoopResult:
    status: InvestigationLoopStatus
    final_decision: InvestigationDecision
    workspace: InvestigationEvidenceWorkspace
    steps: int
    context: DynamicConversationContext


@dataclass(frozen=True, slots=True)
class BoundedInvestigationLoop:
    decisions: InvestigationDecisionEngine
    execution: GovernedInvestigationExecutor
    maximum_reads: int = 4

    def __post_init__(self) -> None:
        if self.maximum_reads < 1:
            raise ValueError(
                "maximum_reads must be positive"
            )

    def run(
        self,
        *,
        human_text: str,
        context: DynamicConversationContext,
        executor: GovernedConversationIntentExecutor,
        workspace: InvestigationEvidenceWorkspace | None = None,
    ) -> InvestigationLoopResult:
        working = (
            workspace
            if workspace is not None
            else InvestigationEvidenceWorkspace()
        )

        reads = 0
        working_context = context
        completed_operation_refs: set[str] = set()

        while True:
            decision = self.decisions.decide(
                human_text=human_text,
                broker=self.execution.broker,
                context=working_context,
                evidence=working.model_evidence(),
                excluded_operation_refs=tuple(
                    completed_operation_refs
                ),
            )

            if (
                decision.kind
                is InvestigationDecisionKind.ANSWER
            ):
                return InvestigationLoopResult(
                    status=InvestigationLoopStatus.ANSWER,
                    final_decision=decision,
                    workspace=working,
                    steps=reads,
                    context=working_context,
                )

            if (
                decision.kind
                is InvestigationDecisionKind.CANNOT_ESTABLISH
            ):
                return InvestigationLoopResult(
                    status=(
                        InvestigationLoopStatus.CANNOT_ESTABLISH
                    ),
                    final_decision=decision,
                    workspace=working,
                    steps=reads,
                    context=working_context,
                )

            if reads >= self.maximum_reads:
                return InvestigationLoopResult(
                    status=InvestigationLoopStatus.EXHAUSTED,
                    final_decision=decision,
                    workspace=working,
                    steps=reads,
                    context=working_context,
                )

            evidence = self.execution.execute(
                decision=decision,
                human_text=human_text,
                context=working_context,
                executor=executor,
                workspace=working,
            )

            completed_operation_refs.add(
                evidence.operation_ref
            )

            if evidence.verified_resource is not None:
                observation = evidence.verified_resource

                working_context = (
                    working_context.with_verified_entities(
                        (
                            observation.entity,
                        ),
                        active_kinds={
                            observation.active_kind: (
                                observation.entity.ref
                            ),
                        },
                        resolutions=(
                            observation.resolution,
                        ),
                    )
                )

            reads += 1


