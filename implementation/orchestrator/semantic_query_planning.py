"""Provider-neutral semantic planning for arbitrary governed information queries.

This layer describes WHAT the human is asking Jason to compute.

It does not:
- select a provider
- select a connector
- choose an API
- access credentials
- retrieve operational evidence
- assert operational values
- contain domain/question-specific control logic

The planner may only compose bounded generic relational operations over resource
types and canonical semantic facts made available by the runtime.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence

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


_MAX_SOURCES = 16
_MAX_FACTS_PER_SOURCE = 64
_MAX_FILTERS = 64
_MAX_JOINS = 16
_MAX_PROJECTIONS = 64
_MAX_GROUPS = 16
_MAX_AGGREGATES = 32
_MAX_ORDERS = 16
_MAX_LIMIT = 10000


class SemanticQueryPlanningError(ValueError):
    """A semantic query proposal was malformed or exceeded its authority."""


class StructuredSemanticQueryClient(Protocol):
    def complete(
        self,
        *,
        system: str,
        user: str,
        schema: Mapping[str, Any],
        max_output_tokens: int = 160,
    ) -> Mapping[str, Any]:
        ...


@dataclass(frozen=True, slots=True)
class SemanticQueryFact:
    """One provider-neutral canonical fact available for planning."""

    name: str
    expected_shape: str | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError(
                "semantic query fact name is required"
            )
        if (
            self.expected_shape is not None
            and not self.expected_shape.strip()
        ):
            raise ValueError(
                "semantic query fact expected_shape "
                "must be non-empty when supplied"
            )


@dataclass(frozen=True, slots=True)
class SemanticQueryResource:
    """One resource type the governed runtime says is queryable.

    This contract deliberately exposes no provider identity.
    """

    resource_type: str
    facts: tuple[SemanticQueryFact, ...]
    collection_supported: bool
    selector_supported: bool = True

    def __post_init__(self) -> None:
        if not self.resource_type.strip():
            raise ValueError(
                "semantic query resource_type is required"
            )
        if len(self.facts) > _MAX_FACTS_PER_SOURCE:
            raise ValueError(
                "semantic query resource exceeds fact bound"
            )
        names = [
            item.name
            for item in self.facts
        ]
        if len(names) != len(set(names)):
            raise ValueError(
                "semantic query resource facts must be unique"
            )


@dataclass(frozen=True, slots=True)
class SemanticQueryUniverse:
    """Bounded planning universe derived from current governed runtime truth."""

    resources: tuple[SemanticQueryResource, ...]

    def __post_init__(self) -> None:
        if not self.resources:
            raise ValueError(
                "semantic query universe requires resources"
            )
        if len(self.resources) > _MAX_SOURCES:
            raise ValueError(
                "semantic query universe exceeds resource bound"
            )
        kinds = [
            item.resource_type
            for item in self.resources
        ]
        if len(kinds) != len(set(kinds)):
            raise ValueError(
                "semantic query resource types must be unique"
            )

    def as_model_context(
        self,
    ) -> tuple[Mapping[str, Any], ...]:
        return tuple(
            {
                "resource_type": item.resource_type,
                "collection_supported": (
                    item.collection_supported
                ),
                "selector_supported": (
                    item.selector_supported
                ),
                "facts": [
                    {
                        "name": fact.name,
                        "expected_shape": (
                            fact.expected_shape
                        ),
                    }
                    for fact in item.facts
                ],
            }
            for item in self.resources
        )


@dataclass(frozen=True, slots=True)
class SemanticQuerySource:
    alias: str
    resource_type: str
    scope: str
    required_facts: tuple[str, ...]
    selector_reference: str | None = None

    def __post_init__(self) -> None:
        if not self.alias.strip():
            raise ValueError(
                "semantic query source alias is required"
            )
        if not self.resource_type.strip():
            raise ValueError(
                "semantic query source resource_type is required"
            )
        if self.scope not in {
            "collection",
            "single",
        }:
            raise ValueError(
                "semantic query source scope is invalid"
            )
        if not self.required_facts:
            raise ValueError(
                "semantic query source requires facts"
            )
        if any(
            not item.strip()
            for item in self.required_facts
        ):
            raise ValueError(
                "semantic query facts must be non-empty"
            )
        if (
            self.scope == "single"
            and not (
                self.selector_reference
                or ""
            ).strip()
        ):
            raise ValueError(
                "single-resource semantic query "
                "requires selector_reference"
            )
        if (
            self.scope == "collection"
            and self.selector_reference is not None
        ):
            raise ValueError(
                "collection semantic query cannot "
                "carry selector_reference"
            )


@dataclass(frozen=True, slots=True)
class SemanticQueryPlan:
    """Provider-neutral semantic plan before capability/provider binding."""

    sources: tuple[SemanticQuerySource, ...]
    relational_plan: GovernedQueryPlan
    answer_mode: str = "table"

    def __post_init__(self) -> None:
        if not self.sources:
            raise ValueError(
                "semantic query plan requires sources"
            )

        aliases = tuple(
            item.alias
            for item in self.sources
        )

        if aliases != self.relational_plan.sources:
            raise ValueError(
                "semantic query sources and relational "
                "plan sources must match exactly"
            )

        if self.answer_mode not in {
            "scalar",
            "boolean",
            "table",
            "summary",
        }:
            raise ValueError(
                "semantic query answer mode is invalid"
            )


@dataclass(frozen=True, slots=True)
class SemanticQueryPlanner:
    """Use structured reasoning only to construct generic semantic query plans."""

    client: StructuredSemanticQueryClient

    def plan(
        self,
        *,
        human_text: str,
        universe: SemanticQueryUniverse,
    ) -> SemanticQueryPlan:
        question = human_text.strip()

        if not question:
            raise ValueError(
                "semantic query human_text is required"
            )

        proposal = self.client.complete(
            system=_SYSTEM_INSTRUCTIONS,
            user=json.dumps(
                {
                    "question": question,
                    "query_universe": (
                        universe.as_model_context()
                    ),
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            schema=_planning_schema(
                universe
            ),
            max_output_tokens=1800,
        )

        return _validate_proposal(
            proposal=proposal,
            universe=universe,
        )


def _planning_schema(
    universe: SemanticQueryUniverse,
) -> Mapping[str, Any]:
    resource_types = [
        item.resource_type
        for item in universe.resources
    ]

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
                "maxItems": _MAX_SOURCES,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "alias",
                        "resource_type",
                        "scope",
                        "required_facts",
                        "selector_reference",
                    ],
                    "properties": {
                        "alias": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 64,
                        },
                        "resource_type": {
                            "type": "string",
                            "enum": resource_types,
                        },
                        "scope": {
                            "type": "string",
                            "enum": [
                                "collection",
                                "single",
                            ],
                        },
                        "required_facts": {
                            "type": "array",
                            "minItems": 1,
                            "maxItems": (
                                _MAX_FACTS_PER_SOURCE
                            ),
                            "items": {
                                "type": "string",
                                "minLength": 1,
                            },
                        },
                        "selector_reference": {
                            "type": [
                                "string",
                                "null",
                            ],
                        },
                    },
                },
            },
            "joins": {
                "type": "array",
                "maxItems": _MAX_JOINS,
                "items": _join_schema(),
            },
            "filters": {
                "type": "array",
                "maxItems": _MAX_FILTERS,
                "items": _predicate_schema(),
            },
            "projections": {
                "type": "array",
                "maxItems": _MAX_PROJECTIONS,
                "items": _projection_schema(),
            },
            "group_by": {
                "type": "array",
                "maxItems": _MAX_GROUPS,
                "items": _projection_schema(),
            },
            "aggregates": {
                "type": "array",
                "maxItems": _MAX_AGGREGATES,
                "items": _aggregate_schema(),
            },
            "order_by": {
                "type": "array",
                "maxItems": _MAX_ORDERS,
                "items": _order_schema(),
            },
            "limit": {
                "type": [
                    "integer",
                    "null",
                ],
                "minimum": 1,
                "maximum": _MAX_LIMIT,
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


def _expression_schema() -> Mapping[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "kind",
            "source",
            "fact",
            "output",
            "value",
            "amount",
            "unit",
            "direction",
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
            "fact": {
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
            "value": {
                    "anyOf": [
                        {
                            "type": "string",
                        },
                        {
                            "type": "number",
                        },
                        {
                            "type": "integer",
                        },
                        {
                            "type": "boolean",
                        },
                        {
                            "type": "null",
                        },
                    ],
                },
            "amount": {
                "type": [
                    "integer",
                    "null",
                ],
                "minimum": 0,
            },
            "unit": {
                "type": [
                    "string",
                    "null",
                ],
                "enum": [
                    "minutes",
                    "hours",
                    "days",
                    "weeks",
                    None,
                ],
            },
            "direction": {
                "type": [
                    "string",
                    "null",
                ],
                "enum": [
                    "past",
                    "future",
                    None,
                ],
            },
        },
    }


def _predicate_schema() -> Mapping[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "left",
            "operator",
            "right",
        ],
        "properties": {
            "left": _expression_schema(),
            "operator": {
                "type": "string",
                "enum": [
                    "eq",
                    "ne",
                    "lt",
                    "lte",
                    "gt",
                    "gte",
                ],
            },
            "right": _expression_schema(),
        },
    }


def _join_schema() -> Mapping[str, Any]:
    field = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "source",
            "fact",
        ],
        "properties": {
            "source": {
                "type": "string",
            },
            "fact": {
                "type": "string",
            },
        },
    }

    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "left",
            "right",
            "join_type",
        ],
        "properties": {
            "left": field,
            "right": field,
            "join_type": {
                "type": "string",
                "enum": [
                    "inner",
                    "left",
                ],
            },
        },
    }


def _projection_schema() -> Mapping[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "name",
            "expression",
        ],
        "properties": {
            "name": {
                "type": "string",
                "minLength": 1,
            },
            "expression": (
                _expression_schema()
            ),
        },
    }


def _aggregate_schema() -> Mapping[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "name",
            "operation",
            "expression",
        ],
        "properties": {
            "name": {
                "type": "string",
                "minLength": 1,
            },
            "operation": {
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
                    _expression_schema(),
                    {
                        "type": "null",
                    },
                ],
            },
        },
    }


def _order_schema() -> Mapping[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "expression",
            "direction",
        ],
        "properties": {
            "expression": (
                _expression_schema()
            ),
            "direction": {
                "type": "string",
                "enum": [
                    "asc",
                    "desc",
                ],
            },
        },
    }


def _validate_proposal(
    *,
    proposal: Mapping[str, Any],
    universe: SemanticQueryUniverse,
) -> SemanticQueryPlan:
    if not isinstance(
        proposal,
        Mapping,
    ):
        raise SemanticQueryPlanningError(
            "semantic query proposal must be an object"
        )

    resource_map = {
        item.resource_type: item
        for item in universe.resources
    }

    raw_sources = proposal.get(
        "sources",
        (),
    )

    if not isinstance(
        raw_sources,
        Sequence,
    ) or isinstance(
        raw_sources,
        (str, bytes),
    ):
        raise SemanticQueryPlanningError(
            "semantic query sources must be an array"
        )

    sources: list[
        SemanticQuerySource
    ] = []

    for raw in raw_sources:
        if not isinstance(
            raw,
            Mapping,
        ):
            raise SemanticQueryPlanningError(
                "semantic query source must be an object"
            )

        alias = str(
            raw.get(
                "alias",
                "",
            )
        ).strip()

        resource_type = str(
            raw.get(
                "resource_type",
                "",
            )
        ).strip()

        scope = str(
            raw.get(
                "scope",
                "",
            )
        ).strip()

        selector_reference = raw.get(
            "selector_reference"
        )

        if selector_reference is not None:
            selector_reference = str(
                selector_reference
            ).strip()

        requested = tuple(
            dict.fromkeys(
                str(item).strip()
                for item in raw.get(
                    "required_facts",
                    (),
                )
                if str(item).strip()
            )
        )

        contract = resource_map.get(
            resource_type
        )

        if contract is None:
            raise SemanticQueryPlanningError(
                "semantic query selected an "
                "unavailable resource type"
            )

        available_facts = {
            item.name
            for item in contract.facts
        }

        unknown_facts = set(
            requested
        ).difference(
            available_facts
        )

        if unknown_facts:
            raise SemanticQueryPlanningError(
                "semantic query selected facts "
                "outside the governed planning universe: "
                + ", ".join(
                    sorted(
                        unknown_facts
                    )
                )
            )

        if (
            scope == "collection"
            and not contract.collection_supported
        ):
            raise SemanticQueryPlanningError(
                "semantic query requested unsupported "
                "collection scope"
            )

        if (
            scope == "single"
            and not contract.selector_supported
        ):
            raise SemanticQueryPlanningError(
                "semantic query requested unsupported "
                "single-resource scope"
            )

        sources.append(
            SemanticQuerySource(
                alias=alias,
                resource_type=resource_type,
                scope=scope,
                required_facts=requested,
                selector_reference=(
                    selector_reference
                ),
            )
        )

    if not sources:
        raise SemanticQueryPlanningError(
            "semantic query requires sources"
        )

    aliases = tuple(
        item.alias
        for item in sources
    )

    if len(aliases) != len(
        set(aliases)
    ):
        raise SemanticQueryPlanningError(
            "semantic query source aliases "
            "must be unique"
        )

    facts_by_alias = {
        item.alias: set(
            item.required_facts
        )
        | {
            "entity_id",
            "resource_type",
        }
        for item in sources
    }

    joins = tuple(
        _parse_join(
            raw,
            facts_by_alias=facts_by_alias,
        )
        for raw in proposal.get(
            "joins",
            (),
        )
    )

    filters = tuple(
        _parse_predicate(
            raw,
            facts_by_alias=facts_by_alias,
        )
        for raw in proposal.get(
            "filters",
            (),
        )
    )

    projections = tuple(
        _parse_projection(
            raw,
            facts_by_alias=facts_by_alias,
        )
        for raw in proposal.get(
            "projections",
            (),
        )
    )

    group_by = tuple(
        _parse_projection(
            raw,
            facts_by_alias=facts_by_alias,
        )
        for raw in proposal.get(
            "group_by",
            (),
        )
    )

    aggregates = tuple(
        _parse_aggregate(
            raw,
            facts_by_alias=facts_by_alias,
        )
        for raw in proposal.get(
            "aggregates",
            (),
        )
    )

    output_names = {
        item.name
        for item in (
            tuple(projections)
            + tuple(group_by)
            + tuple(aggregates)
        )
    }

    order_by = tuple(
        _parse_order(
            raw,
            facts_by_alias=facts_by_alias,
            output_names=output_names,
        )
        for raw in proposal.get(
            "order_by",
            (),
        )
    )

    limit = proposal.get(
        "limit"
    )

    if limit is not None:
        if (
            not isinstance(
                limit,
                int,
            )
            or isinstance(
                limit,
                bool,
            )
        ):
            raise SemanticQueryPlanningError(
                "semantic query limit must be an integer"
            )

    relational = GovernedQueryPlan(
        sources=aliases,
        joins=joins,
        filters=filters,
        projections=projections,
        group_by=group_by,
        aggregates=aggregates,
        order_by=order_by,
        limit=limit,
    )

    return SemanticQueryPlan(
        sources=tuple(sources),
        relational_plan=relational,
        answer_mode=str(
            proposal.get(
                "answer_mode",
                "table",
            )
        ).strip(),
    )


def _parse_expression(
    raw: Mapping[str, Any],
    *,
    facts_by_alias: Mapping[
        str,
        set[str],
    ],
    output_names: set[str] | None = None,
):
    if not isinstance(
        raw,
        Mapping,
    ):
        raise SemanticQueryPlanningError(
            "semantic query expression "
            "must be an object"
        )

    kind = str(
        raw.get(
            "kind",
            "",
        )
    ).strip()

    if kind == "literal":
        return QueryLiteral(
            raw.get(
                "value"
            )
        )

    if kind == "output":
        name = str(
            raw.get(
                "output",
                "",
            )
        ).strip()

        if (
            not name
            or output_names is None
            or name not in output_names
        ):
            raise SemanticQueryPlanningError(
                "semantic query references an "
                "unknown query output"
            )

        return QueryOutput(
            name=name
        )

    if kind == "relative_time":
        amount = raw.get(
            "amount"
        )

        if (
            not isinstance(
                amount,
                int,
            )
            or isinstance(
                amount,
                bool,
            )
        ):
            raise SemanticQueryPlanningError(
                "relative time amount "
                "must be an integer"
            )

        return QueryRelativeTime(
            amount=amount,
            unit=str(
                raw.get(
                    "unit",
                    "",
                )
            ).strip(),
            direction=str(
                raw.get(
                    "direction",
                    "",
                )
            ).strip(),
        )

    if kind != "field":
        raise SemanticQueryPlanningError(
            "semantic query expression kind "
            "is invalid"
        )

    source = str(
        raw.get(
            "source",
            "",
        )
    ).strip()

    fact = str(
        raw.get(
            "fact",
            "",
        )
    ).strip()

    _require_field(
        source=source,
        fact=fact,
        facts_by_alias=facts_by_alias,
    )

    return QueryField(
        source=source,
        fact=fact,
    )


def _require_field(
    *,
    source: str,
    fact: str,
    facts_by_alias: Mapping[
        str,
        set[str],
    ],
) -> None:
    if source not in facts_by_alias:
        raise SemanticQueryPlanningError(
            "semantic query references an "
            "unknown source alias"
        )

    if fact not in facts_by_alias[
        source
    ]:
        raise SemanticQueryPlanningError(
            "semantic query references a fact "
            "not requested from that source"
        )


def _parse_predicate(
    raw,
    *,
    facts_by_alias,
):
    if not isinstance(
        raw,
        Mapping,
    ):
        raise SemanticQueryPlanningError(
            "semantic query predicate "
            "must be an object"
        )

    return QueryPredicate(
        left=_parse_expression(
            raw.get(
                "left",
                {},
            ),
            facts_by_alias=facts_by_alias,
        ),
        operator=str(
            raw.get(
                "operator",
                "",
            )
        ).strip(),
        right=_parse_expression(
            raw.get(
                "right",
                {},
            ),
            facts_by_alias=facts_by_alias,
        ),
    )


def _parse_join(
    raw,
    *,
    facts_by_alias,
):
    if not isinstance(
        raw,
        Mapping,
    ):
        raise SemanticQueryPlanningError(
            "semantic query join must be an object"
        )

    left = raw.get(
        "left",
        {},
    )
    right = raw.get(
        "right",
        {},
    )

    if not isinstance(
        left,
        Mapping,
    ) or not isinstance(
        right,
        Mapping,
    ):
        raise SemanticQueryPlanningError(
            "semantic query join fields "
            "must be objects"
        )

    left_source = str(
        left.get(
            "source",
            "",
        )
    ).strip()
    left_fact = str(
        left.get(
            "fact",
            "",
        )
    ).strip()

    right_source = str(
        right.get(
            "source",
            "",
        )
    ).strip()
    right_fact = str(
        right.get(
            "fact",
            "",
        )
    ).strip()

    _require_field(
        source=left_source,
        fact=left_fact,
        facts_by_alias=facts_by_alias,
    )

    _require_field(
        source=right_source,
        fact=right_fact,
        facts_by_alias=facts_by_alias,
    )

    return QueryJoin(
        left=QueryField(
            source=left_source,
            fact=left_fact,
        ),
        right=QueryField(
            source=right_source,
            fact=right_fact,
        ),
        join_type=str(
            raw.get(
                "join_type",
                "",
            )
        ).strip(),
    )


def _parse_projection(
    raw,
    *,
    facts_by_alias,
):
    if not isinstance(
        raw,
        Mapping,
    ):
        raise SemanticQueryPlanningError(
            "semantic query projection "
            "must be an object"
        )

    return QueryProjection(
        name=str(
            raw.get(
                "name",
                "",
            )
        ).strip(),
        expression=_parse_expression(
            raw.get(
                "expression",
                {},
            ),
            facts_by_alias=facts_by_alias,
        ),
    )


def _parse_aggregate(
    raw,
    *,
    facts_by_alias,
):
    if not isinstance(
        raw,
        Mapping,
    ):
        raise SemanticQueryPlanningError(
            "semantic query aggregate "
            "must be an object"
        )

    expression = raw.get(
        "expression"
    )

    return QueryAggregate(
        name=str(
            raw.get(
                "name",
                "",
            )
        ).strip(),
        operation=str(
            raw.get(
                "operation",
                "",
            )
        ).strip(),
        expression=(
            None
            if expression is None
            else _parse_expression(
                expression,
                facts_by_alias=(
                    facts_by_alias
                ),
            )
        ),
    )


def _parse_order(
    raw,
    *,
    facts_by_alias,
    output_names,
):
    if not isinstance(
        raw,
        Mapping,
    ):
        raise SemanticQueryPlanningError(
            "semantic query order "
            "must be an object"
        )

    return QueryOrder(
        expression=_parse_expression(
            raw.get(
                "expression",
                {},
            ),
            facts_by_alias=facts_by_alias,
            output_names=output_names,
        ),
        direction=str(
            raw.get(
                "direction",
                "",
            )
        ).strip(),
    )


_SYSTEM_INSTRUCTIONS = """
You are Jason's provider-neutral semantic query planner.

Translate the human's information request into the supplied structured query
schema using only resource types and canonical facts present in query_universe.

You are planning meaning, not choosing implementation.

Hard requirements:
- Never name or infer a provider, vendor, connector, API, credential, database,
  script, service, or capability id.
- Never invent a resource type or canonical fact outside query_universe.
- Never invent operational values.
- Never answer the question yourself.
- A source represents a provider-neutral resource set.
- Use scope=collection when the question applies across a resource collection.
- Use scope=single only when the human identifies one specific resource.
- required_facts must contain every canonical fact needed by filters, joins,
  projections, grouping, aggregation, or ordering.
- Use generic comparison, relative-time, join, aggregation, ordering, and limit
  operations when the requested result requires them.
- When ordering by a named projection, group value, or aggregate result, use an
  output expression referencing that output name rather than inventing a source fact.
- Do not turn an internal evidence/provider choice into a human clarification.
- Produce only the structured object required by the schema.
""".strip()


@dataclass(frozen=True, slots=True)
class UniversalSemanticQueryResolution:
    """Result of model-first information-query applicability resolution."""

    is_information_query: bool
    plan: SemanticQueryPlan | None

    def __post_init__(self) -> None:
        if (
            self.is_information_query
            and self.plan is None
        ):
            raise ValueError(
                "information query resolution requires a plan"
            )

        if (
            not self.is_information_query
            and self.plan is not None
        ):
            raise ValueError(
                "non-information resolution cannot carry a query plan"
            )


@dataclass(frozen=True, slots=True)
class UniversalSemanticQueryResolver:
    """Resolve information applicability and plan in one bounded model call.

    The model receives only:
    - human language
    - provider-neutral resource types
    - canonical facts
    - generic query operations

    It receives no provider ids, connector handles, credentials, or execution
    authority.
    """

    client: StructuredSemanticQueryClient

    def resolve(
        self,
        *,
        human_text: str,
        universe: SemanticQueryUniverse,
    ) -> UniversalSemanticQueryResolution:
        question = human_text.strip()

        if not question:
            raise ValueError(
                "universal semantic query human_text is required"
            )

        proposal = self.client.complete(
            system=_UNIVERSAL_SYSTEM_INSTRUCTIONS,
            user=json.dumps(
                {
                    "question": question,
                    "query_universe": (
                        universe.as_model_context()
                    ),
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            schema=_universal_schema(
                universe
            ),
            max_output_tokens=1900,
        )

        if not isinstance(
            proposal,
            Mapping,
        ):
            raise SemanticQueryPlanningError(
                "universal semantic resolution must be an object"
            )

        mode = str(
            proposal.get(
                "mode",
                "",
            )
        ).strip()

        raw_plan = proposal.get(
            "query"
        )

        if mode == "not_information":
            if raw_plan is not None:
                raise SemanticQueryPlanningError(
                    "non-information resolution "
                    "must not contain a query"
                )

            return UniversalSemanticQueryResolution(
                is_information_query=False,
                plan=None,
            )

        if mode != "information":
            raise SemanticQueryPlanningError(
                "universal semantic resolution mode is invalid"
            )

        if not isinstance(
            raw_plan,
            Mapping,
        ):
            raise SemanticQueryPlanningError(
                "information resolution requires query object"
            )

        return UniversalSemanticQueryResolution(
            is_information_query=True,
            plan=_validate_proposal(
                proposal=raw_plan,
                universe=universe,
            ),
        )


def _universal_schema(
    universe: SemanticQueryUniverse,
) -> Mapping[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "mode",
            "query",
        ],
        "properties": {
            "mode": {
                "type": "string",
                "enum": [
                    "information",
                    "not_information",
                ],
            },
            "query": {
                "anyOf": [
                    _planning_schema(
                        universe
                    ),
                    {
                        "type": "null",
                    },
                ],
            },
        },
    }


_UNIVERSAL_SYSTEM_INSTRUCTIONS = """
You are Jason's provider-neutral semantic information resolver.

Decide whether the human is asking for information that can be established from
the supplied governed query universe.

If yes:
- mode must be information.
- Build the complete generic query plan in query.
- Use only resource types and canonical facts present in query_universe.
- Use generic filtering, temporal comparison, joining, projection, grouping,
  aggregation, ordering, and limits as needed.
- Never name or infer a provider, vendor, connector, API, script, database,
  credential, capability id, or execution implementation.
- Never invent operational evidence or answer the question yourself.
- Do not require the question to match a known phrasing or known workflow.

If the request is ordinary conversation, writing, opinion, explanation, or
otherwise does not require governed operational evidence from query_universe:
- mode must be not_information.
- query must be null.

A question may involve one resource, a collection of resources, multiple
resource types, or facts supplied by multiple implementations. Those are all
ordinary information queries when the universe supports the required facts.

Return only the structured object required by the schema.
""".strip()
