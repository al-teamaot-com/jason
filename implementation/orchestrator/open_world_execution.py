"""Execute open-world query plans through Jason's normal governed boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .governed_query import (
    DeterministicGovernedQueryEngine,
    GovernedQueryResult,
)
from .open_world_evidence_materialization import (
    OpenWorldEvidenceMaterializer,
)
from .open_world_query_planning import (
    OpenWorldQueryPlan,
)
from .open_world_schema import (
    DiscoveredResourceSchema,
    OpenWorldResourceCatalog,
)
from .teams_conversation_flow import (
    ConversationIntent,
)


class OpenWorldExecutionError(
    RuntimeError
):
    pass


@dataclass(frozen=True, slots=True)
class OpenWorldExecutionResult:
    query_result: GovernedQueryResult
    orchestrations: tuple[Any, ...]


@dataclass(frozen=True, slots=True)
class OpenWorldExecutionCoordinator:
    materializer: OpenWorldEvidenceMaterializer
    query_engine: DeterministicGovernedQueryEngine

    def execute(
        self,
        *,
        plan: OpenWorldQueryPlan,
        catalog: OpenWorldResourceCatalog,
        executor,
    ) -> OpenWorldExecutionResult:
        resources = {
            resource.resource_handle: resource
            for resource in catalog.resources
        }

        datasets = []
        orchestrations = []

        for source in plan.sources:
            resource = resources.get(
                source.resource_handle
            )

            if resource is None:
                raise OpenWorldExecutionError(
                    "query references an unavailable "
                    "governed resource"
                )

            intent = self._intent(
                resource=resource,
                selector_reference=(
                    source.selector_reference
                ),
            )

            result = executor.execute(
                intent
            )

            orchestrations.append(
                result
            )

            datasets.append(
                self.materializer.materialize(
                    source=source,
                    resource=resource,
                    results=(
                        result,
                    ),
                )
            )

        result = self.query_engine.execute(
            plan=plan.relational_plan,
            datasets=tuple(
                datasets
            ),
        )

        return OpenWorldExecutionResult(
            query_result=result,
            orchestrations=tuple(
                orchestrations
            ),
        )

    def _intent(
        self,
        *,
        resource: DiscoveredResourceSchema,
        selector_reference: str | None,
    ) -> ConversationIntent:
        arguments: dict[
            str,
            Any,
        ] = {}

        reference = (
            selector_reference
            or ""
        ).strip()

        if resource.collection_supported:
            if reference:
                arguments[
                    "selector"
                ] = reference
        else:
            if not reference:
                raise OpenWorldExecutionError(
                    "selector-only resource requires "
                    "a grounded selector"
                )

            arguments[
                "selector"
            ] = reference

        return ConversationIntent(
            capability_name=(
                resource.capability_name
            ),
            arguments=arguments,
            execution_mode="deterministic",
            permission_mode="observe",
            risk="low",
        )
