"""Coordinate arbitrary provider-neutral information queries through Jason governance.

Pipeline:

human question
    -> validated SemanticQueryPlan
    -> dynamic capability/provider discovery
    -> provider-neutral ConversationIntent
    -> existing governed request factory / Central Orchestrator
    -> verified evidence materialization
    -> deterministic relational query execution

This module never invokes a connector directly and contains no provider mappings,
question mappings, domain-specific routes, or operational fact interpretation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

from .conversation_kernel import (
    InformationNeed,
    InformationTarget,
)
from .governed_query import (
    DeterministicGovernedQueryEngine,
    GovernedQueryResult,
    VerifiedQueryDataset,
)
from .information_fulfillment import (
    FulfillmentCapability,
    FulfillmentStep,
)
from .information_need_intent import (
    InformationNeedIntentBuilder,
    PlannedInformationNeed,
)
from .query_evidence_materialization import (
    GovernedQueryEvidenceMaterializer,
)
from .query_source_discovery import (
    GovernedQuerySourceDiscovery,
    QuerySourceBinding,
    QuerySourceContribution,
)
from .semantic_query_planning import (
    SemanticQueryPlan,
    SemanticQuerySource,
)
from .teams_conversation_flow import (
    ConversationIntent,
    ConversationIntentPlan,
)


class GovernedQueryIntentExecutor(
    Protocol
):
    """Execute one intent through the normal governed orchestration boundary."""

    def execute(
        self,
        intent: ConversationIntent,
    ):
        ...


class GovernedQueryExecutionError(
    RuntimeError
):
    """A generic query could not complete safely."""


@dataclass(frozen=True, slots=True)
class GovernedQueryExecutionResult:
    semantic_plan: SemanticQueryPlan
    bindings: tuple[
        QuerySourceBinding,
        ...,
    ]
    datasets: tuple[
        VerifiedQueryDataset,
        ...,
    ]
    query_result: GovernedQueryResult
    orchestrations: tuple[object, ...]


@dataclass(frozen=True, slots=True)
class GovernedQueryExecutionCoordinator:
    """Execute a validated semantic query using only governed runtime contracts."""

    discovery: GovernedQuerySourceDiscovery
    intent_builder: InformationNeedIntentBuilder
    materializer: GovernedQueryEvidenceMaterializer
    query_engine: DeterministicGovernedQueryEngine

    def execute(
        self,
        *,
        human_text: str,
        plan: SemanticQueryPlan,
        executor: GovernedQueryIntentExecutor,
    ) -> GovernedQueryExecutionResult:
        question = human_text.strip()

        if not question:
            raise ValueError(
                "governed query human_text is required"
            )

        bindings = (
            self.discovery.discover_all(
                plan.sources
            )
        )

        datasets = []
        all_results = []

        for source, binding in zip(
            plan.sources,
            bindings,
            strict=True,
        ):
            source_results = []

            for contribution in (
                binding.contributions
            ):
                intent = self._build_intent(
                    human_text=question,
                    source=source,
                    contribution=contribution,
                )

                result = executor.execute(
                    intent
                )

                source_results.append(
                    result
                )
                all_results.append(
                    result
                )

            dataset = (
                self.materializer.materialize(
                    binding=binding,
                    results=tuple(
                        source_results
                    ),
                )
            )

            datasets.append(
                dataset
            )

        query_result = (
            self.query_engine.execute(
                plan=plan.relational_plan,
                datasets=tuple(
                    datasets
                ),
            )
        )

        return GovernedQueryExecutionResult(
            semantic_plan=plan,
            bindings=bindings,
            datasets=tuple(
                datasets
            ),
            query_result=query_result,
            orchestrations=tuple(
                all_results
            ),
        )

    def _build_intent(
        self,
        *,
        human_text: str,
        source: SemanticQuerySource,
        contribution: QuerySourceContribution,
    ) -> ConversationIntent:
        if (
            contribution.permission_mode
            != "observe"
        ):
            raise GovernedQueryExecutionError(
                "information query contribution "
                "is not observe-only"
            )

        requested = tuple(
            fact
            for fact
            in source.required_facts
            if fact
            in contribution.canonical_facts
        )

        if not requested:
            raise GovernedQueryExecutionError(
                "query contribution covers no "
                "required canonical facts"
            )

        if source.scope == "collection":
            if (
                contribution.selector_required
                or contribution.collection_scope
                is None
            ):
                raise GovernedQueryExecutionError(
                    "collection query contribution "
                    "does not authorize selectorless collection access"
                )

            return ConversationIntent(
                capability_name=(
                    contribution.capability_name
                ),
                arguments={
                    "requested_facts": list(
                        requested
                    ),
                },
                execution_mode="deterministic",
                permission_mode=(
                    contribution.permission_mode
                ),
                risk=contribution.risk,
            )

        if source.scope != "single":
            raise GovernedQueryExecutionError(
                "semantic query source scope is invalid"
            )

        reference = (
            source.selector_reference
            or ""
        ).strip()

        if not reference:
            raise GovernedQueryExecutionError(
                "single-resource query lacks "
                "grounded selector reference"
            )

        need = InformationNeed(
            target=InformationTarget(
                kind=source.resource_type,
                source="literal",
                reference=reference,
            ),
            need=(
                requested[0]
                if len(requested) == 1
                else ", ".join(requested)
            ),
            authority=(
                contribution.permission_mode
            ),
        )

        step = FulfillmentStep(
            capability_name=(
                contribution.capability_name
            ),
            target_reference=reference,
            target_source="literal",
            information_need=need.need,
            authority=need.authority,
        )

        capability = FulfillmentCapability(
            capability_name=(
                contribution.capability_name
            ),
            resource_types=(
                contribution.resource_type,
            ),
            operation=(
                contribution.operation
            ),
            selector_keys=(
                contribution.selector_keys
            ),
            role="primary",
            permission_mode=(
                contribution.permission_mode
            ),
            risk=contribution.risk,
            description=(
                contribution.description
            ),
            selector_required=(
                contribution.selector_required
            ),
            collection_scope=(
                contribution.collection_scope
            ),
        )

        built = self.intent_builder.build(
            human_text=human_text,
            planned=(
                PlannedInformationNeed(
                    need=need,
                    step=step,
                    capability=capability,
                ),
            ),
        )

        if isinstance(
            built,
            ConversationIntentPlan,
        ):
            raise GovernedQueryExecutionError(
                "one query contribution unexpectedly "
                "produced multiple governed intents"
            )

        return built
