"""Execute open-world query plans through Jason's normal governed boundary."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from .governed_query import (
    DeterministicGovernedQueryEngine,
    GovernedQueryResult,
    QueryField,
    QueryLiteral,
    QueryRelativeTime,
)
from .open_world_evidence_materialization import (
    OpenWorldEvidenceMaterializer,
)
from .open_world_query_planning import (
    OpenWorldLookup,
    OpenWorldQueryPlan,
    OpenWorldQuerySource,
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
        execution_now = datetime.now(timezone.utc)

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
                source_alias=source.alias,
                plan=plan,
                now=execution_now,
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
            now=execution_now,
        )

        if plan.lookups:
            result = self._apply_lookups(
                result=result,
                lookups=plan.lookups,
                resources=resources,
                executor=executor,
                orchestrations=orchestrations,
            )

        return OpenWorldExecutionResult(
            query_result=result,
            orchestrations=tuple(
                orchestrations
            ),
        )

    def _apply_lookups(
        self,
        *,
        result: GovernedQueryResult,
        lookups: tuple[OpenWorldLookup, ...],
        resources: Mapping[str, DiscoveredResourceSchema],
        executor,
        orchestrations: list[Any],
    ) -> GovernedQueryResult:
        if len(result.rows) > 50:
            raise OpenWorldExecutionError(
                "post-query lookup requires a relational result bounded to 50 rows or fewer"
            )

        rows = [dict(row) for row in result.rows]
        columns = list(result.columns)
        evidence = list(result.evidence_references)

        for lookup in lookups:
            resource = resources.get(lookup.resource_handle)
            if resource is None or not resource.collection_supported:
                raise OpenWorldExecutionError("lookup references an unavailable collection resource")
            binding = next((
                argument for field, operator, argument in resource.query_filter_bindings
                if field == lookup.match_field and operator == "eq"
            ), None)
            if not binding:
                raise OpenWorldExecutionError("lookup field is not declared exact-match safe")

            field_paths = tuple(item.field_path for item in lookup.fields)
            source = OpenWorldQuerySource(
                alias=lookup.alias,
                resource_handle=lookup.resource_handle,
                field_paths=field_paths,
            )
            cache: dict[str, Mapping[str, Any] | None] = {}

            for row in rows:
                raw_value = row.get(lookup.input_output)
                if raw_value is None or str(raw_value).strip() == "":
                    facts = None
                else:
                    cache_key = str(raw_value)
                    if cache_key not in cache:
                        arguments: dict[str, Any] = {binding: raw_value}
                        if "page_size" in resource.selector_keys:
                            arguments["page_size"] = 2
                        intent = ConversationIntent(
                            capability_name=resource.capability_name,
                            arguments=arguments,
                            execution_mode="deterministic",
                            permission_mode="observe",
                            risk="low",
                        )
                        governed = executor.execute(intent)
                        orchestrations.append(governed)
                        dataset = self.materializer.materialize(
                            source=source, resource=resource, results=(governed,),
                        )
                        if len(dataset.records) > 1:
                            raise OpenWorldExecutionError(
                                "exact lookup returned multiple governed matches"
                            )
                        cache[cache_key] = (
                            dataset.records[0].facts if dataset.records else None
                        )
                        if dataset.records:
                            evidence.extend(dataset.records[0].evidence_references)
                    facts = cache[cache_key]

                for field in lookup.fields:
                    row[field.name] = (
                        None if facts is None else facts.get(field.field_path)
                    )
                    if field.name not in columns:
                        columns.append(field.name)

        return GovernedQueryResult(
            columns=tuple(columns),
            rows=tuple(rows),
            source_aliases=result.source_aliases,
            evidence_references=tuple(dict.fromkeys(evidence)),
        )

    def _intent(
        self,
        *,
        resource: DiscoveredResourceSchema,
        selector_reference: str | None,
        source_alias: str,
        plan: OpenWorldQueryPlan,
        now: datetime,
    ) -> ConversationIntent:
        arguments: dict[str, Any] = self._filter_arguments(
            resource=resource,
            source_alias=source_alias,
            plan=plan,
            now=now,
        )

        reference = (selector_reference or "").strip()

        if resource.collection_supported:
            if reference:
                arguments["selector"] = reference
        else:
            if not reference:
                raise OpenWorldExecutionError(
                    "selector-only resource requires a grounded selector"
                )
            arguments["selector"] = reference

        return ConversationIntent(
            capability_name=resource.capability_name,
            arguments=arguments,
            execution_mode="deterministic",
            permission_mode="observe",
            risk="low",
        )

    @staticmethod
    def _filter_arguments(
        *,
        resource: DiscoveredResourceSchema,
        source_alias: str,
        plan: OpenWorldQueryPlan,
        now: datetime,
    ) -> dict[str, Any]:
        """Push only registry-declared relational filters into a governed read.

        The model never supplies provider arguments directly. Runtime metadata
        declares which query fields/operators may narrow which capability
        arguments, and deterministic lowering resolves literals/relative time.
        The same filters still execute again in the relational engine.
        """
        bindings = {
            (field, operator): argument
            for field, operator, argument in resource.query_filter_bindings
        }
        if not bindings:
            return {}

        arguments: dict[str, Any] = {}
        inverse = {"gt": "lt", "gte": "lte", "lt": "gt", "lte": "gte", "eq": "eq"}

        for predicate in plan.relational_plan.filters:
            field = None
            value = None
            operator = predicate.operator

            if isinstance(predicate.left, QueryField) and predicate.left.source == source_alias:
                field = predicate.left.fact
                value = predicate.right
            elif isinstance(predicate.right, QueryField) and predicate.right.source == source_alias:
                field = predicate.right.fact
                value = predicate.left
                operator = inverse.get(operator, operator)
            else:
                continue

            argument_name = bindings.get((field, operator))
            if not argument_name:
                continue

            if isinstance(value, QueryLiteral):
                resolved = value.value
            elif isinstance(value, QueryRelativeTime):
                delta = timedelta(**{value.unit: value.amount})
                instant = now - delta if value.direction == "past" else now + delta
                resolved = instant.isoformat()
            else:
                continue

            if resolved is None:
                continue
            existing = arguments.get(argument_name)
            if existing is not None and existing != resolved:
                raise OpenWorldExecutionError(
                    "query filters produced conflicting governed source arguments"
                )
            arguments[argument_name] = resolved

        return arguments
