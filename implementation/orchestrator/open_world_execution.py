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
                field_paths=source.field_paths,
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
        field_paths: tuple[str, ...] = (),
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

        # Provider-discovered resources carry an opaque binding that came from
        # trusted connector metadata, never from model output.  The selected
        # field paths were already validated against the opaque resource schema
        # by the open-world planner.  Pass both forward only for that generic
        # resource contract; legacy capability-backed intents remain unchanged.
        if resource.provider_resource_handle is not None:
            if not field_paths:
                raise OpenWorldExecutionError(
                    "provider-discovered resource requires a bounded field projection"
                )
            available_fields = {field.path for field in resource.fields}
            invalid_fields = tuple(
                path for path in field_paths if path not in available_fields
            )
            if invalid_fields:
                raise OpenWorldExecutionError(
                    "provider-discovered execution references fields outside the governed schema"
                )
            arguments[
                "provider_resource_handle"
            ] = resource.provider_resource_handle
            arguments[
                "field_paths"
            ] = tuple(dict.fromkeys(field_paths))

        return ConversationIntent(
            capability_name=(
                resource.capability_name
            ),
            arguments=arguments,
            execution_mode="deterministic",
            permission_mode="observe",
            risk="low",
        )
