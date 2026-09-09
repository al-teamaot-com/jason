import pytest

from orchestrator.governed_query import (
    QueryAggregate,
    QueryField,
    QueryLiteral,
    QueryOrder,
    QueryPredicate,
    QueryProjection,
    QueryRelativeTime,
)
from orchestrator.semantic_query_planning import (
    SemanticQueryFact,
    SemanticQueryPlanner,
    SemanticQueryPlanningError,
    SemanticQueryResource,
    SemanticQueryUniverse,
)


class FakeClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def complete(
        self,
        *,
        system,
        user,
        schema,
        max_output_tokens=160,
    ):
        self.calls.append(
            {
                "system": system,
                "user": user,
                "schema": schema,
                "max_output_tokens": (
                    max_output_tokens
                ),
            }
        )
        return self.response


def universe():
    return SemanticQueryUniverse(
        resources=(
            SemanticQueryResource(
                resource_type="alpha_resource",
                collection_supported=True,
                selector_supported=True,
                facts=(
                    SemanticQueryFact(
                        "flag_state",
                        "boolean",
                    ),
                    SemanticQueryFact(
                        "observed_time",
                        "timestamp",
                    ),
                    SemanticQueryFact(
                        "metric_value",
                        "number",
                    ),
                    SemanticQueryFact(
                        "join_key",
                        "descriptive_string",
                    ),
                ),
            ),
            SemanticQueryResource(
                resource_type="beta_resource",
                collection_supported=True,
                selector_supported=True,
                facts=(
                    SemanticQueryFact(
                        "join_key",
                        "descriptive_string",
                    ),
                    SemanticQueryFact(
                        "category_value",
                        "descriptive_string",
                    ),
                ),
            ),
        )
    )


def expression(
    *,
    kind,
    source=None,
    fact=None,
    output=None,
    value=None,
    amount=None,
    unit=None,
    direction=None,
):
    return {
        "kind": kind,
        "source": source,
        "fact": fact,
        "output": output,
        "value": value,
        "amount": amount,
        "unit": unit,
        "direction": direction,
    }


def empty_plan(**updates):
    value = {
        "sources": [
            {
                "alias": "a",
                "resource_type": (
                    "alpha_resource"
                ),
                "scope": "collection",
                "required_facts": [
                    "flag_state",
                ],
                "selector_reference": None,
            }
        ],
        "joins": [],
        "filters": [],
        "projections": [],
        "group_by": [],
        "aggregates": [],
        "order_by": [],
        "limit": None,
        "answer_mode": "table",
    }
    value.update(updates)
    return value


def test_planner_accepts_generic_collection_aggregation():
    proposal = empty_plan(
        filters=[
            {
                "left": expression(
                    kind="field",
                    source="a",
                    fact="flag_state",
                ),
                "operator": "eq",
                "right": expression(
                    kind="literal",
                    value=True,
                ),
            }
        ],
        aggregates=[
            {
                "name": "result_count",
                "operation": "count",
                "expression": None,
            }
        ],
        answer_mode="scalar",
    )

    client = FakeClient(
        proposal
    )

    plan = SemanticQueryPlanner(
        client=client
    ).plan(
        human_text="synthetic request",
        universe=universe(),
    )

    assert plan.sources[0].scope == (
        "collection"
    )
    assert plan.sources[
        0
    ].required_facts == (
        "flag_state",
    )
    assert plan.relational_plan.filters == (
        QueryPredicate(
            left=QueryField(
                "a",
                "flag_state",
            ),
            operator="eq",
            right=QueryLiteral(
                True
            ),
        ),
    )
    assert plan.relational_plan.aggregates == (
        QueryAggregate(
            name="result_count",
            operation="count",
            expression=None,
        ),
    )
    assert plan.answer_mode == "scalar"


def test_planner_accepts_generic_relative_time_expression():
    proposal = empty_plan(
        sources=[
            {
                "alias": "a",
                "resource_type": (
                    "alpha_resource"
                ),
                "scope": "collection",
                "required_facts": [
                    "observed_time",
                ],
                "selector_reference": None,
            }
        ],
        filters=[
            {
                "left": expression(
                    kind="field",
                    source="a",
                    fact="observed_time",
                ),
                "operator": "lt",
                "right": expression(
                    kind="relative_time",
                    amount=11,
                    unit="days",
                    direction="past",
                ),
            }
        ],
    )

    plan = SemanticQueryPlanner(
        client=FakeClient(
            proposal
        )
    ).plan(
        human_text="synthetic request",
        universe=universe(),
    )

    predicate = (
        plan.relational_plan.filters[0]
    )

    assert isinstance(
        predicate.right,
        QueryRelativeTime,
    )
    assert predicate.right.amount == 11


def test_planner_accepts_cross_resource_join_without_provider_identity():
    proposal = empty_plan(
        sources=[
            {
                "alias": "a",
                "resource_type": (
                    "alpha_resource"
                ),
                "scope": "collection",
                "required_facts": [
                    "join_key",
                    "metric_value",
                ],
                "selector_reference": None,
            },
            {
                "alias": "b",
                "resource_type": (
                    "beta_resource"
                ),
                "scope": "collection",
                "required_facts": [
                    "join_key",
                    "category_value",
                ],
                "selector_reference": None,
            },
        ],
        joins=[
            {
                "left": {
                    "source": "a",
                    "fact": "join_key",
                },
                "right": {
                    "source": "b",
                    "fact": "join_key",
                },
                "join_type": "inner",
            }
        ],
        projections=[
            {
                "name": "metric",
                "expression": expression(
                    kind="field",
                    source="a",
                    fact="metric_value",
                ),
            },
            {
                "name": "category",
                "expression": expression(
                    kind="field",
                    source="b",
                    fact="category_value",
                ),
            },
        ],
    )

    client = FakeClient(
        proposal
    )

    plan = SemanticQueryPlanner(
        client=client
    ).plan(
        human_text="synthetic request",
        universe=universe(),
    )

    assert len(plan.sources) == 2
    assert len(
        plan.relational_plan.joins
    ) == 1

    call = client.calls[0]

    assert "provider_id" not in (
        call["user"]
    )
    assert "capability_id" not in (
        call["user"]
    )


def test_planner_rejects_fact_not_present_in_governed_universe():
    proposal = empty_plan(
        sources=[
            {
                "alias": "a",
                "resource_type": (
                    "alpha_resource"
                ),
                "scope": "collection",
                "required_facts": [
                    "invented_fact",
                ],
                "selector_reference": None,
            }
        ],
    )

    with pytest.raises(
        SemanticQueryPlanningError,
        match="outside the governed planning universe",
    ):
        SemanticQueryPlanner(
            client=FakeClient(
                proposal
            )
        ).plan(
            human_text="synthetic request",
            universe=universe(),
        )


def test_planner_rejects_field_not_requested_from_source():
    proposal = empty_plan(
        projections=[
            {
                "name": "value",
                "expression": expression(
                    kind="field",
                    source="a",
                    fact="metric_value",
                ),
            }
        ],
    )

    with pytest.raises(
        SemanticQueryPlanningError,
        match="not requested from that source",
    ):
        SemanticQueryPlanner(
            client=FakeClient(
                proposal
            )
        ).plan(
            human_text="synthetic request",
            universe=universe(),
        )


def test_planner_rejects_unavailable_resource_type():
    proposal = empty_plan(
        sources=[
            {
                "alias": "a",
                "resource_type": (
                    "unknown_resource"
                ),
                "scope": "collection",
                "required_facts": [
                    "flag_state",
                ],
                "selector_reference": None,
            }
        ],
    )

    with pytest.raises(
        SemanticQueryPlanningError,
        match="unavailable resource type",
    ):
        SemanticQueryPlanner(
            client=FakeClient(
                proposal
            )
        ).plan(
            human_text="synthetic request",
            universe=universe(),
        )


def test_planner_cannot_claim_collection_scope_when_contract_disallows_it():
    local_universe = (
        SemanticQueryUniverse(
            resources=(
                SemanticQueryResource(
                    resource_type="alpha_resource",
                    collection_supported=False,
                    selector_supported=True,
                    facts=(
                        SemanticQueryFact(
                            "flag_state",
                            "boolean",
                        ),
                    ),
                ),
            )
        )
    )

    proposal = empty_plan()

    with pytest.raises(
        SemanticQueryPlanningError,
        match="unsupported collection scope",
    ):
        SemanticQueryPlanner(
            client=FakeClient(
                proposal
            )
        ).plan(
            human_text="synthetic request",
            universe=local_universe,
        )


def test_single_scope_requires_literal_reference():
    proposal = empty_plan(
        sources=[
            {
                "alias": "a",
                "resource_type": (
                    "alpha_resource"
                ),
                "scope": "single",
                "required_facts": [
                    "flag_state",
                ],
                "selector_reference": None,
            }
        ],
    )

    with pytest.raises(
        ValueError,
        match="selector_reference",
    ):
        SemanticQueryPlanner(
            client=FakeClient(
                proposal
            )
        ).plan(
            human_text="synthetic request",
            universe=universe(),
        )


def test_schema_exposes_only_current_resource_types():
    client = FakeClient(
        empty_plan()
    )

    SemanticQueryPlanner(
        client=client
    ).plan(
        human_text="synthetic request",
        universe=universe(),
    )

    schema = client.calls[
        0
    ]["schema"]

    enum = (
        schema["properties"]
        ["sources"]["items"]
        ["properties"]
        ["resource_type"]["enum"]
    )

    assert enum == [
        "alpha_resource",
        "beta_resource",
    ]


def test_model_context_contains_no_provider_or_connector_fields():
    context = (
        universe().as_model_context()
    )

    text = repr(
        context
    ).casefold()

    assert "provider" not in text
    assert "connector" not in text
    assert "credential" not in text


def test_planner_can_order_by_named_aggregate_output():
    from orchestrator.governed_query import QueryOutput

    proposal = empty_plan(
        sources=[
            {
                "alias": "a",
                "resource_type": (
                    "alpha_resource"
                ),
                "scope": "collection",
                "required_facts": [
                    "metric_value",
                ],
                "selector_reference": None,
            }
        ],
        aggregates=[
            {
                "name": "computed_total",
                "operation": "sum",
                "expression": expression(
                    kind="field",
                    source="a",
                    fact="metric_value",
                ),
            }
        ],
        order_by=[
            {
                "expression": expression(
                    kind="output",
                    output="computed_total",
                ),
                "direction": "desc",
            }
        ],
    )

    plan = SemanticQueryPlanner(
        client=FakeClient(
            proposal
        )
    ).plan(
        human_text="synthetic request",
        universe=universe(),
    )

    assert plan.relational_plan.order_by == (
        QueryOrder(
            expression=QueryOutput(
                "computed_total"
            ),
            direction="desc",
        ),
    )


def test_planner_rejects_unknown_output_reference():
    proposal = empty_plan(
        order_by=[
            {
                "expression": expression(
                    kind="output",
                    output="not_produced",
                ),
                "direction": "asc",
            }
        ],
    )

    with pytest.raises(
        SemanticQueryPlanningError,
        match="unknown query output",
    ):
        SemanticQueryPlanner(
            client=FakeClient(
                proposal
            )
        ).plan(
            human_text="synthetic request",
            universe=universe(),
        )
