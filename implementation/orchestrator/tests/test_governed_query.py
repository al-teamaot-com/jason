from datetime import (
    datetime,
    timezone,
)

import pytest

from orchestrator.governed_query import (
    DeterministicGovernedQueryEngine,
    GovernedQueryError,
    GovernedQueryPlan,
    QueryAggregate,
    QueryField,
    QueryJoin,
    QueryLiteral,
    QueryOrder,
    QueryPredicate,
    QueryProjection,
    QueryRelativeTime,
    VerifiedQueryDataset,
    VerifiedQueryRecord,
)


def record(
    entity_id,
    resource_type,
    **facts,
):
    return VerifiedQueryRecord(
        entity_id=entity_id,
        resource_type=resource_type,
        facts=facts,
        evidence_references=(
            f"evidence:{resource_type}:{entity_id}",
        ),
    )


def dataset(
    alias,
    resource_type,
    *records,
):
    return VerifiedQueryDataset(
        alias=alias,
        resource_type=resource_type,
        records=tuple(records),
    )


ENGINE = DeterministicGovernedQueryEngine()


def test_generic_boolean_filter_and_count():
    source = dataset(
        "assets",
        "asset",
        record(
            "r1",
            "asset",
            enabled=True,
        ),
        record(
            "r2",
            "asset",
            enabled=False,
        ),
        record(
            "r3",
            "asset",
            enabled=True,
        ),
    )

    result = ENGINE.execute(
        plan=GovernedQueryPlan(
            sources=("assets",),
            filters=(
                QueryPredicate(
                    left=QueryField(
                        "assets",
                        "enabled",
                    ),
                    operator="eq",
                    right=QueryLiteral(
                        True
                    ),
                ),
            ),
            aggregates=(
                QueryAggregate(
                    name="matching_count",
                    operation="count",
                ),
            ),
        ),
        datasets=(source,),
    )

    assert result.rows == (
        {
            "matching_count": 2,
        },
    )


def test_generic_temporal_filter_uses_relative_execution_time():
    source = dataset(
        "objects",
        "object",
        record(
            "a",
            "object",
            observed_at="2026-01-01T00:00:00Z",
        ),
        record(
            "b",
            "object",
            observed_at="2026-08-20T00:00:00Z",
        ),
    )

    now = datetime(
        2026,
        8,
        28,
        tzinfo=timezone.utc,
    )

    result = ENGINE.execute(
        plan=GovernedQueryPlan(
            sources=("objects",),
            filters=(
                QueryPredicate(
                    left=QueryField(
                        "objects",
                        "observed_at",
                    ),
                    operator="lt",
                    right=QueryRelativeTime(
                        amount=30,
                        unit="days",
                        direction="past",
                    ),
                ),
            ),
            projections=(
                QueryProjection(
                    name="id",
                    expression=QueryField(
                        "objects",
                        "entity_id",
                    ),
                ),
            ),
        ),
        datasets=(source,),
        now=now,
    )

    assert result.rows == (
        {
            "id": "a",
        },
    )


def test_generic_grouping_and_numeric_aggregation():
    source = dataset(
        "measurements",
        "measurement",
        record(
            "1",
            "measurement",
            category="x",
            value=4,
        ),
        record(
            "2",
            "measurement",
            category="x",
            value=8,
        ),
        record(
            "3",
            "measurement",
            category="y",
            value=5,
        ),
    )

    result = ENGINE.execute(
        plan=GovernedQueryPlan(
            sources=("measurements",),
            group_by=(
                QueryProjection(
                    name="category",
                    expression=QueryField(
                        "measurements",
                        "category",
                    ),
                ),
            ),
            aggregates=(
                QueryAggregate(
                    name="total",
                    operation="sum",
                    expression=QueryField(
                        "measurements",
                        "value",
                    ),
                ),
                QueryAggregate(
                    name="average",
                    operation="avg",
                    expression=QueryField(
                        "measurements",
                        "value",
                    ),
                ),
            ),
        ),
        datasets=(source,),
    )

    assert {
        row["category"]: row
        for row in result.rows
    } == {
        "x": {
            "category": "x",
            "total": 12,
            "average": 6,
        },
        "y": {
            "category": "y",
            "total": 5,
            "average": 5,
        },
    }


def test_generic_cross_source_join_uses_canonical_values_only():
    left = dataset(
        "inventory",
        "thing",
        record(
            "a",
            "thing",
            serial="S-1",
            owner="alpha",
        ),
        record(
            "b",
            "thing",
            serial="S-2",
            owner="beta",
        ),
    )

    right = dataset(
        "observations",
        "observation",
        record(
            "o1",
            "observation",
            serial="S-2",
            score=91,
        ),
        record(
            "o2",
            "observation",
            serial="S-3",
            score=50,
        ),
    )

    result = ENGINE.execute(
        plan=GovernedQueryPlan(
            sources=(
                "inventory",
                "observations",
            ),
            joins=(
                QueryJoin(
                    left=QueryField(
                        "inventory",
                        "serial",
                    ),
                    right=QueryField(
                        "observations",
                        "serial",
                    ),
                ),
            ),
            projections=(
                QueryProjection(
                    name="owner",
                    expression=QueryField(
                        "inventory",
                        "owner",
                    ),
                ),
                QueryProjection(
                    name="score",
                    expression=QueryField(
                        "observations",
                        "score",
                    ),
                ),
            ),
        ),
        datasets=(
            left,
            right,
        ),
    )

    assert result.rows == (
        {
            "owner": "beta",
            "score": 91,
        },
    )


def test_disconnected_sources_fail_closed():
    left = dataset(
        "left",
        "thing",
    )
    right = dataset(
        "right",
        "other",
    )

    with pytest.raises(
        GovernedQueryError,
        match="explicit governed joins",
    ):
        ENGINE.execute(
            plan=GovernedQueryPlan(
                sources=(
                    "left",
                    "right",
                ),
            ),
            datasets=(
                left,
                right,
            ),
        )


def test_unknown_source_fails_closed():
    with pytest.raises(
        GovernedQueryError,
        match="unavailable source aliases",
    ):
        ENGINE.execute(
            plan=GovernedQueryPlan(
                sources=("missing",),
            ),
            datasets=(),
        )


def test_type_incompatible_comparison_fails_closed():
    source = dataset(
        "records",
        "record",
        record(
            "x",
            "record",
            value=10,
        ),
    )

    with pytest.raises(
        GovernedQueryError,
        match="incompatible types",
    ):
        ENGINE.execute(
            plan=GovernedQueryPlan(
                sources=("records",),
                filters=(
                    QueryPredicate(
                        left=QueryField(
                            "records",
                            "value",
                        ),
                        operator="gt",
                        right=QueryLiteral(
                            "not-numeric"
                        ),
                    ),
                ),
            ),
            datasets=(source,),
        )


def test_count_distinct_is_generic_and_deterministic():
    source = dataset(
        "values",
        "value",
        record(
            "1",
            "value",
            category="a",
        ),
        record(
            "2",
            "value",
            category="a",
        ),
        record(
            "3",
            "value",
            category="b",
        ),
    )

    result = ENGINE.execute(
        plan=GovernedQueryPlan(
            sources=("values",),
            aggregates=(
                QueryAggregate(
                    name="distinct",
                    operation="count_distinct",
                    expression=QueryField(
                        "values",
                        "category",
                    ),
                ),
            ),
        ),
        datasets=(source,),
    )

    assert result.rows == (
        {
            "distinct": 2,
        },
    )


def test_query_limit_is_structural_not_domain_specific():
    source = dataset(
        "items",
        "item",
        *(
            record(
                str(index),
                "item",
                value=index,
            )
            for index in range(20)
        ),
    )

    result = ENGINE.execute(
        plan=GovernedQueryPlan(
            sources=("items",),
            projections=(
                QueryProjection(
                    name="id",
                    expression=QueryField(
                        "items",
                        "entity_id",
                    ),
                ),
            ),
            limit=4,
        ),
        datasets=(source,),
    )

    assert len(result.rows) == 4


def test_ordering_can_reference_named_projection_output():
    from orchestrator.governed_query import QueryOutput

    source = dataset(
        "items",
        "item",
        record(
            "a",
            "item",
            score=3,
        ),
        record(
            "b",
            "item",
            score=9,
        ),
        record(
            "c",
            "item",
            score=5,
        ),
    )

    result = ENGINE.execute(
        plan=GovernedQueryPlan(
            sources=("items",),
            projections=(
                QueryProjection(
                    name="identifier",
                    expression=QueryField(
                        "items",
                        "entity_id",
                    ),
                ),
                QueryProjection(
                    name="computed_value",
                    expression=QueryField(
                        "items",
                        "score",
                    ),
                ),
            ),
            order_by=(
                QueryOrder(
                    expression=QueryOutput(
                        "computed_value"
                    ),
                    direction="desc",
                ),
            ),
        ),
        datasets=(source,),
    )

    assert result.rows == (
        {
            "identifier": "b",
            "computed_value": 9,
        },
        {
            "identifier": "c",
            "computed_value": 5,
        },
        {
            "identifier": "a",
            "computed_value": 3,
        },
    )


def test_ordering_can_reference_named_aggregate_output():
    from orchestrator.governed_query import QueryOutput

    source = dataset(
        "measurements",
        "measurement",
        record(
            "1",
            "measurement",
            category="a",
            value=2,
        ),
        record(
            "2",
            "measurement",
            category="a",
            value=7,
        ),
        record(
            "3",
            "measurement",
            category="b",
            value=20,
        ),
    )

    result = ENGINE.execute(
        plan=GovernedQueryPlan(
            sources=("measurements",),
            group_by=(
                QueryProjection(
                    name="bucket",
                    expression=QueryField(
                        "measurements",
                        "category",
                    ),
                ),
            ),
            aggregates=(
                QueryAggregate(
                    name="combined",
                    operation="sum",
                    expression=QueryField(
                        "measurements",
                        "value",
                    ),
                ),
            ),
            order_by=(
                QueryOrder(
                    expression=QueryOutput(
                        "combined"
                    ),
                    direction="desc",
                ),
            ),
        ),
        datasets=(source,),
    )

    assert result.rows == (
        {
            "bucket": "b",
            "combined": 20,
        },
        {
            "bucket": "a",
            "combined": 9,
        },
    )
