import pytest

from orchestrator.semantic_query_planning import (
    SemanticQueryFact,
    SemanticQueryPlanningError,
    SemanticQueryResource,
    SemanticQueryUniverse,
    UniversalSemanticQueryResolver,
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
                resource_type="resource_a",
                collection_supported=True,
                selector_supported=True,
                facts=(
                    SemanticQueryFact(
                        "fact_alpha",
                        "number",
                    ),
                    SemanticQueryFact(
                        "fact_beta",
                        "boolean",
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


def generic_plan():
    return {
        "sources": [
            {
                "alias": "r",
                "resource_type": "resource_a",
                "scope": "collection",
                "required_facts": [
                    "fact_alpha",
                ],
                "selector_reference": None,
            }
        ],
        "joins": [],
        "filters": [],
        "projections": [
            {
                "name": "value",
                "expression": expression(
                    kind="field",
                    source="r",
                    fact="fact_alpha",
                ),
            }
        ],
        "group_by": [],
        "aggregates": [],
        "order_by": [],
        "limit": None,
        "answer_mode": "table",
    }


def test_information_resolution_builds_validated_generic_plan():
    client = FakeClient(
        {
            "mode": "information",
            "query": generic_plan(),
        }
    )

    result = (
        UniversalSemanticQueryResolver(
            client=client
        ).resolve(
            human_text="unseen synthetic text",
            universe=universe(),
        )
    )

    assert (
        result.is_information_query
        is True
    )

    assert result.plan is not None

    assert (
        result.plan.sources[0].resource_type
        == "resource_a"
    )


def test_non_information_resolution_has_no_query():
    result = (
        UniversalSemanticQueryResolver(
            client=FakeClient(
                {
                    "mode": "not_information",
                    "query": None,
                }
            )
        ).resolve(
            human_text="unseen synthetic text",
            universe=universe(),
        )
    )

    assert (
        result.is_information_query
        is False
    )

    assert result.plan is None


def test_information_mode_without_query_fails_closed():
    with pytest.raises(
        SemanticQueryPlanningError,
        match="requires query object",
    ):
        UniversalSemanticQueryResolver(
            client=FakeClient(
                {
                    "mode": "information",
                    "query": None,
                }
            )
        ).resolve(
            human_text="unseen synthetic text",
            universe=universe(),
        )


def test_non_information_mode_cannot_smuggle_query():
    with pytest.raises(
        SemanticQueryPlanningError,
        match="must not contain a query",
    ):
        UniversalSemanticQueryResolver(
            client=FakeClient(
                {
                    "mode": "not_information",
                    "query": generic_plan(),
                }
            )
        ).resolve(
            human_text="unseen synthetic text",
            universe=universe(),
        )


def test_resolver_context_contains_no_provider_or_connector_identity():
    client = FakeClient(
        {
            "mode": "not_information",
            "query": None,
        }
    )

    UniversalSemanticQueryResolver(
        client=client
    ).resolve(
        human_text="unseen synthetic text",
        universe=universe(),
    )

    supplied = client.calls[
        0
    ]["user"].casefold()

    assert "provider_id" not in supplied
    assert "connector" not in supplied
    assert "credential" not in supplied


def test_unknown_fact_in_model_plan_fails_deterministic_validation():
    proposal = generic_plan()

    proposal["sources"][0][
        "required_facts"
    ] = [
        "invented_fact"
    ]

    with pytest.raises(
        SemanticQueryPlanningError,
        match="outside the governed planning universe",
    ):
        UniversalSemanticQueryResolver(
            client=FakeClient(
                {
                    "mode": "information",
                    "query": proposal,
                }
            )
        ).resolve(
            human_text="unseen synthetic text",
            universe=universe(),
        )
