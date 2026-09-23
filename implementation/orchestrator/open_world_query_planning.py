"""Compile arbitrary human information questions over discovered field paths.

The planner operates on opaque resources and structural field paths. It does not
depend on canonical fact vocabulary, provider names, or question templates.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import json
from typing import Any, Mapping, Protocol

from .governed_query import (
    GovernedQueryPlan,
    QueryAggregate,
    QueryField,
    QueryJoin,
    QueryLiteral,
    QueryOrder,
    QueryOutput,
    QueryPredicate,
    QueryProjection,
    QueryRelativeTime,
)
from .open_world_schema import (
    OpenWorldResourceCatalog,
)


class OpenWorldQueryPlanningError(
    RuntimeError
):
    pass


class StructuredOpenWorldPlanningClient(
    Protocol
):
    def complete(
        self,
        *,
        system: str,
        user: str,
        schema: Mapping[str, Any],
        max_output_tokens: int,
    ):
        ...


@dataclass(frozen=True, slots=True)
class OpenWorldQuerySource:
    alias: str
    resource_handle: str
    field_paths: tuple[str, ...]
    selector_reference: str | None = None


@dataclass(frozen=True, slots=True)
class OpenWorldQueryPlan:
    sources: tuple[
        OpenWorldQuerySource,
        ...
    ]
    relational_plan: GovernedQueryPlan
    answer_mode: str


@dataclass(frozen=True, slots=True)
class OpenWorldQueryPlanner:
    client: StructuredOpenWorldPlanningClient

    def plan(
        self,
        *,
        human_text: str,
        catalog: OpenWorldResourceCatalog,
    ) -> OpenWorldQueryPlan:
        resources = (
            catalog.model_context()
        )

        previous_proposal = None
        validation_error = None

        for attempt in range(2):
            user_payload = {
                "question": human_text,
                "resources": resources,
            }

            system = _SYSTEM

            if attempt > 0:
                user_payload[
                    "previous_proposal"
                ] = previous_proposal

                user_payload[
                    "validation_error"
                ] = validation_error

                user_payload[
                    "declared_source_aliases"
                ] = _proposal_aliases(
                    previous_proposal
                )

                system = (
                    _SYSTEM
                    + "\n\n"
                    + _REPAIR
                )

            proposal = self.client.complete(
                system=system,
                user=json.dumps(
                    user_payload,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                schema=_schema(catalog),
                max_output_tokens=2400,
            )

            try:
                if not isinstance(
                    proposal,
                    Mapping,
                ):
                    raise OpenWorldQueryPlanningError(
                        "open-world query proposal "
                        "must be an object"
                    )

                lowered = _lower(
                    proposal=proposal,
                    catalog=catalog,
                )

                lowered = _minimize_query_sources(
                    lowered
                )

                _validate_relational_topology(
                    lowered
                )

                return lowered

            except OpenWorldQueryPlanningError as error:
                previous_proposal = proposal
                validation_error = str(
                    error
                )

                if attempt == 1:
                    raise

        raise OpenWorldQueryPlanningError(
            "open-world query planning exhausted "
            "its bounded repair attempts"
        )


def _proposal_aliases(
    proposal: Mapping[str, Any] | None,
) -> tuple[str, ...]:
    if not isinstance(
        proposal,
        Mapping,
    ):
        return ()

    sources = proposal.get(
        "sources",
        (),
    )

    if not isinstance(
        sources,
        list,
    ):
        return ()

    return tuple(
        dict.fromkeys(
            str(
                item.get(
                    "alias",
                    "",
                )
            ).strip()
            for item in sources
            if (
                isinstance(
                    item,
                    Mapping,
                )
                and str(
                    item.get(
                        "alias",
                        "",
                    )
                ).strip()
            )
        )
    )


def _minimize_query_sources(
    plan: OpenWorldQueryPlan,
) -> OpenWorldQueryPlan:
    """Remove model-selected sources that cannot affect the relational result.

    Source selection is advisory model output. A source becomes semantically
    necessary only when the lowered deterministic query references its alias.
    Removing a completely unreferenced source cannot change the query result
    and prevents unnecessary governed reads.

    Sources participating in joins are always retained. If multiple actually
    used sources remain, normal explicit-join validation still applies.
    """

    if len(plan.sources) <= 1:
        return plan

    used_aliases = set()

    relational = plan.relational_plan

    def observe_expression(expression):
        if expression is None:
            return

        source = getattr(
            expression,
            "source",
            None,
        )

        if source:
            used_aliases.add(
                str(source)
            )

    for join in relational.joins:
        left_source = getattr(
            join,
            "left_source",
            None,
        )
        right_source = getattr(
            join,
            "right_source",
            None,
        )

        if left_source:
            used_aliases.add(
                str(left_source)
            )

        if right_source:
            used_aliases.add(
                str(right_source)
            )

        observe_expression(
            getattr(
                join,
                "left",
                None,
            )
        )
        observe_expression(
            getattr(
                join,
                "right",
                None,
            )
        )

    for predicate in relational.filters:
        observe_expression(
            getattr(
                predicate,
                "left",
                None,
            )
        )
        observe_expression(
            getattr(
                predicate,
                "right",
                None,
            )
        )

    for projection in relational.projections:
        observe_expression(
            getattr(
                projection,
                "expression",
                None,
            )
        )

    for grouping in relational.group_by:
        observe_expression(
            getattr(
                grouping,
                "expression",
                grouping,
            )
        )

    for aggregate in relational.aggregates:
        observe_expression(
            getattr(
                aggregate,
                "expression",
                None,
            )
        )

    for ordering in relational.order_by:
        observe_expression(
            getattr(
                ordering,
                "expression",
                None,
            )
        )

    if not used_aliases:
        # A scalar count-style query can legitimately carry no field expression.
        # In that situation preserve exactly one deterministic source rather than
        # allowing model over-selection to create meaningless multi-source reads.
        retained_sources = (
            plan.sources[0],
        )

        retained_aliases = tuple(
            source.alias
            for source in retained_sources
        )

        return replace(
            plan,
            sources=retained_sources,
            relational_plan=replace(
                plan.relational_plan,
                sources=retained_aliases,
            ),
        )

    retained = tuple(
        source
        for source in plan.sources
        if source.alias in used_aliases
    )

    if not retained:
        raise OpenWorldQueryPlanningError(
            "query expressions reference no "
            "selected governed source"
        )

    retained_aliases = tuple(
        source.alias
        for source in retained
    )

    return replace(
        plan,
        sources=retained,
        relational_plan=replace(
            plan.relational_plan,
            sources=retained_aliases,
        ),
    )


def _validate_relational_topology(
    plan: OpenWorldQueryPlan,
) -> None:
    """Validate generic relational invariants before governed execution.

    The deterministic query engine remains authoritative and performs its
    own validation again. This earlier boundary exists so invalid model
    proposals can use the bounded planner-repair path instead of failing
    only after governed provider reads have already occurred.
    """

    source_count = len(
        plan.sources
    )

    joins = tuple(
        plan.relational_plan.joins
    )

    if (
        source_count > 1
        and not joins
    ):
        raise OpenWorldQueryPlanningError(
            "multiple query sources require "
            "explicit governed joins; "
            "remove unnecessary sources or "
            "provide explicit field-to-field joins"
        )


def _lower(
    *,
    proposal: Mapping[str, Any],
    catalog: OpenWorldResourceCatalog,
) -> OpenWorldQueryPlan:
    known = {
        resource.resource_handle: resource
        for resource in catalog.resources
    }

    source_items = proposal.get(
        "sources",
        []
    )

    if not source_items:
        raise OpenWorldQueryPlanningError(
            "open-world query requires at least one source"
        )

    sources = []
    aliases = set()
    allowed_fields = {}

    for item in source_items:
        alias = str(
            item["alias"]
        ).strip()

        handle = str(
            item["resource_handle"]
        ).strip()

        if not alias or alias in aliases:
            raise OpenWorldQueryPlanningError(
                "source aliases must be unique and non-empty"
            )

        resource = known.get(
            handle
        )

        if resource is None:
            raise OpenWorldQueryPlanningError(
                "query selected an unknown resource handle"
            )

        selected = tuple(
            str(path)
            for path in item[
                "field_paths"
            ]
        )

        available = {
            field.path
            for field in resource.fields
        }

        if not selected:
            raise OpenWorldQueryPlanningError(
                "query source selected no fields "
                f"for resource_handle={handle}"
            )

        invalid_fields = tuple(
            path
            for path in selected
            if path not in available
        )

        if invalid_fields:
            raise OpenWorldQueryPlanningError(
                "query selected field paths outside "
                "the discovered governed schema: "
                f"resource_handle={handle}; "
                f"invalid_field_paths={invalid_fields}"
            )

        aliases.add(
            alias
        )

        allowed_fields[
            alias
        ] = set(
            selected
        )

        proposed_selector = (
            item.get(
                "selector_reference"
            )
        )

        if proposed_selector not in (
            None,
            "",
        ):
            raise OpenWorldQueryPlanningError(
                "query planner cannot supply "
                "resource selectors"
            )

        sources.append(
            OpenWorldQuerySource(
                alias=alias,
                resource_handle=handle,
                field_paths=selected,
                selector_reference=None,
            )
        )

    def expression(
        raw,
    ):
        kind = raw["kind"]

        if kind == "field":
            alias = raw["source"]
            field = raw["field_path"]

            if alias not in allowed_fields:
                raise OpenWorldQueryPlanningError(
                    "expression references an unknown "
                    "query-local source alias: "
                    f"source={alias}; "
                    "declared_source_aliases="
                    f"{tuple(sorted(allowed_fields))}"
                )

            if (
                field
                not in allowed_fields[
                    alias
                ]
            ):
                raise OpenWorldQueryPlanningError(
                    "expression references a field "
                    "outside selected source schema: "
                    f"source={alias}; "
                    f"invalid_field_path={field}"
                )

            return QueryField(
                source=alias,
                fact=field,
            )

        if kind == "literal":
            return QueryLiteral(
                value=raw.get(
                    "value"
                )
            )

        if kind == "relative_time":
            return QueryRelativeTime(
                amount=int(
                    raw["amount"]
                ),
                unit=raw["unit"],
                direction=raw[
                    "direction"
                ],
            )

        if kind == "output":
            return QueryOutput(
                name=raw[
                    "output"
                ]
            )

        raise OpenWorldQueryPlanningError(
            "unsupported expression kind"
        )

    joins = tuple(
        QueryJoin(
            left=expression(
                item["left"]
            ),
            right=expression(
                item["right"]
            ),
            join_type=item["kind"],
        )
        for item in proposal.get(
            "joins",
            []
        )
    )

    filters = tuple(
        QueryPredicate(
            left=expression(
                item["left"]
            ),
            operator=item[
                "operator"
            ],
            right=expression(
                item["right"]
            ),
        )
        for item in proposal.get(
            "filters",
            []
        )
    )

    projections = tuple(
        QueryProjection(
            name=item["name"],
            expression=expression(
                item["expression"]
            ),
        )
        for item in proposal.get(
            "projections",
            []
        )
    )

    groups = tuple(
        QueryProjection(
            name=item["name"],
            expression=expression(
                item["expression"]
            ),
        )
        for item in proposal.get(
            "group_by",
            []
        )
    )

    aggregates = tuple(
        QueryAggregate(
            name=item["name"],
            function=item[
                "function"
            ],
            expression=(
                None
                if item[
                    "expression"
                ] is None
                else expression(
                    item[
                        "expression"
                    ]
                )
            ),
        )
        for item in proposal.get(
            "aggregates",
            []
        )
    )

    orders = tuple(
        QueryOrder(
            expression=expression(
                item["expression"]
            ),
            direction=item[
                "direction"
            ],
        )
        for item in proposal.get(
            "order_by",
            []
        )
    )

    relational = GovernedQueryPlan(
        sources=tuple(
            source.alias
            for source in sources
        ),
        joins=joins,
        filters=filters,
        projections=projections,
        group_by=groups,
        aggregates=aggregates,
        order_by=orders,
        limit=proposal.get(
            "limit"
        ),
    )

    return OpenWorldQueryPlan(
        sources=tuple(
            sources
        ),
        relational_plan=relational,
        answer_mode=proposal[
            "answer_mode"
        ],
    )


def _expression_schema(
    *,
    field_paths: tuple[str, ...] | None = None,
):
    field_path_schema = {
        "type": [
            "string",
            "null",
        ],
    }

    if field_paths:
        field_path_schema = {
            "anyOf": [
                {
                    "type": "string",
                    "enum": list(
                        field_paths
                    ),
                },
                {
                    "type": "null",
                },
            ],
        }

    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "kind",
            "source",
            "field_path",
            "value",
            "amount",
            "unit",
            "direction",
            "output",
        ],
        "properties": {
            "kind": {
                "type": "string",
                "enum": [
                    "field",
                    "literal",
                    "relative_time",
                    "output",
                ],
            },
            "source": {
                "type": [
                    "string",
                    "null",
                ],
            },
            "field_path": (
                field_path_schema
            ),
            "value": {
                "type": [
                    "string",
                    "number",
                    "boolean",
                    "null",
                ],
            },
            "amount": {
                "type": [
                    "integer",
                    "null",
                ],
            },
            "unit": {
                "type": [
                    "string",
                    "null",
                ],
            },
            "direction": {
                "type": [
                    "string",
                    "null",
                ],
            },
            "output": {
                "type": [
                    "string",
                    "null",
                ],
            },
        },
    }


def _schema(
    catalog: OpenWorldResourceCatalog,
):
    """Build the model contract from current governed catalog truth.

    Resource handles and source field paths are constrained together so the
    language model cannot emit a field that does not belong to its selected
    governed resource. Deterministic lowering still validates the proposal.
    """

    all_fields = tuple(
        dict.fromkeys(
            field.path
            for resource in catalog.resources
            for field in resource.fields
            if field.path.strip()
        )
    )

    if not all_fields:
        raise OpenWorldQueryPlanningError(
            "governed planning catalog exposes "
            "no queryable fields"
        )

    expression = _expression_schema(
        field_paths=all_fields,
    )

    named_expression = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "name",
            "expression",
        ],
        "properties": {
            "name": {
                "type": "string",
            },
            "expression": expression,
        },
    }

    source_variants = []

    for resource in catalog.resources:
        fields = tuple(
            dict.fromkeys(
                field.path
                for field in resource.fields
                if field.path.strip()
            )
        )

        if not fields:
            continue

        source_variants.append(
            {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "alias",
                    "resource_handle",
                    "field_paths",
                    "selector_reference",
                ],
                "properties": {
                    "alias": {
                        "type": "string",
                    },
                    "resource_handle": {
                        "type": "string",
                        "enum": [
                            resource.resource_handle
                        ],
                    },
                    "field_paths": {
                        "type": "array",
                        "minItems": 1,
                        "items": {
                            "type": "string",
                            "enum": list(
                                fields
                            ),
                        },
                    },
                    "selector_reference": {
                        "type": "null",
                    },
                },
            }
        )

    if not source_variants:
        raise OpenWorldQueryPlanningError(
            "governed planning catalog exposes "
            "no executable query sources"
        )

    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "sources",
            "joins",
            "filters",
            "projections",
            "group_by",
            "aggregates",
            "order_by",
            "limit",
            "answer_mode",
        ],
        "properties": {
            "sources": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "anyOf": (
                        source_variants
                    ),
                },
            },
            "joins": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "kind",
                        "left",
                        "right",
                    ],
                    "properties": {
                        "kind": {
                            "type": "string",
                            "enum": [
                                "inner",
                                "left",
                            ],
                        },
                        "left": expression,
                        "right": expression,
                    },
                },
            },
            "filters": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "left",
                        "operator",
                        "right",
                    ],
                    "properties": {
                        "left": expression,
                        "operator": {
                            "type": "string",
                            "enum": [
                                "eq",
                                "ne",
                                "gt",
                                "gte",
                                "lt",
                                "lte",
                                "contains",
                                "in",
                            ],
                        },
                        "right": expression,
                    },
                },
            },
            "projections": {
                "type": "array",
                "items": (
                    named_expression
                ),
            },
            "group_by": {
                "type": "array",
                "items": (
                    named_expression
                ),
            },
            "aggregates": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "name",
                        "function",
                        "expression",
                    ],
                    "properties": {
                        "name": {
                            "type": "string",
                        },
                        "function": {
                            "type": "string",
                            "enum": [
                                "count",
                                "count_distinct",
                                "sum",
                                "min",
                                "max",
                                "avg",
                            ],
                        },
                        "expression": {
                            "anyOf": [
                                expression,
                                {
                                    "type": "null",
                                },
                            ],
                        },
                    },
                },
            },
            "order_by": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "expression",
                        "direction",
                    ],
                    "properties": {
                        "expression": (
                            expression
                        ),
                        "direction": {
                            "type": "string",
                            "enum": [
                                "asc",
                                "desc",
                            ],
                        },
                    },
                },
            },
            "limit": {
                "type": [
                    "integer",
                    "null",
                ],
            },
            "answer_mode": {
                "type": "string",
                "enum": [
                    "scalar",
                    "boolean",
                    "table",
                    "summary",
                ],
            },
        },
    }


_REPAIR = """
The previous structured query proposal failed deterministic validation.

Repair the proposal using only the supplied live resource catalog.

Rules:
- Preserve the meaning of the human question.
- Treat the validation error as feedback, not as evidence.
- Do not invent resource handles, field paths, or source aliases.
- Use only resource handles and field paths present in the supplied catalog.
- Every field expression source must reference an alias declared in sources.
- If declared_source_aliases is supplied, use it as the query-local alias set
  unless the repaired sources array deliberately changes that set.
- Do not remove a required concept merely to make validation succeed.
- If the requested information cannot be represented by the supplied schema,
  return the closest valid query that preserves the requested meaning without
  inventing data or relationships.
- The repaired proposal will be deterministically validated again.

Return only the repaired structured query object.
""".strip()


_SYSTEM = """
You are Jason's open-world governed query planner.

Translate the human information request into a relational query over the live
resource schemas supplied to you.

Rules:
- Use only opaque resource_handle values supplied in the resource catalog.
- Use only field paths actually supplied for that resource.
- Do not infer providers, vendors, APIs, capabilities, databases, or credentials.
- Do not answer the question.
- Do not invent evidence.
- Select all fields needed for filtering, joining, grouping, ordering, projection,
  or aggregation.
- Multiple resources may be joined only when the question and available schema
  justify an explicit field-to-field relationship.
- Provider-local entity identifiers are not globally equivalent.
- Use generic relational operators rather than question-specific procedures.
- Every source alias must be declared exactly once in sources.
- Every field expression source must reference one of those declared aliases.
- Join source identity comes only from the left and right field expressions.
- Never invent an undeclared alias from a resource type, label, or field name.
- Always set selector_reference to null. Resource selectors are grounded and
  authorized outside the language-model planning stage.

Return only the structured query object.
""".strip()
