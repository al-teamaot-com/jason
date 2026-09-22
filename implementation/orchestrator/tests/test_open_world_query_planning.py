import pytest

from orchestrator.open_world_query_planning import (
    OpenWorldQueryPlanner,
    OpenWorldQueryPlanningError,
)
from orchestrator.open_world_schema import (
    DiscoveredField,
    DiscoveredResourceSchema,
    OpenWorldResourceCatalog,
)


class Client:
    def __init__(self, response):
        self.response = response

    def complete(
        self,
        *,
        system,
        user,
        schema,
        max_output_tokens,
    ):
        del system
        del user
        del schema
        del max_output_tokens
        return self.response


class SequenceClient:
    def __init__(self, responses):
        self.responses = list(
            responses
        )
        self.calls = []

    def complete(
        self,
        *,
        system,
        user,
        schema,
        max_output_tokens,
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

        if not self.responses:
            raise AssertionError(
                "unexpected planner model call"
            )

        return self.responses.pop(0)


def catalog():
    return OpenWorldResourceCatalog(
        resources=(
            DiscoveredResourceSchema(
                provider_id="provider-a",
                capability_name="generic.search",
                resource_type="generic",
                operation="search",
                collection_supported=True,
                selector_keys=(),
                fields=(
                    DiscoveredField(
                        name="alpha",
                        path="branch.alpha",
                        value_type="number",
                    ),
                    DiscoveredField(
                        name="beta",
                        path="branch.beta",
                        value_type="string",
                    ),
                ),
            ),
        )
    )


def expression(
    kind,
    *,
    source=None,
    field_path=None,
    value=None,
    amount=None,
    unit=None,
    direction=None,
    output=None,
):
    return {
        "kind": kind,
        "source": source,
        "field_path": field_path,
        "value": value,
        "amount": amount,
        "unit": unit,
        "direction": direction,
        "output": output,
    }


def proposal(handle):
    return {
        "sources": [
            {
                "alias": "r",
                "resource_handle": handle,
                "field_paths": [
                    "branch.alpha",
                    "branch.beta",
                ],
                "selector_reference": None,
            }
        ],
        "joins": [],
        "filters": [
            {
                "left": expression(
                    "field",
                    source="r",
                    field_path="branch.alpha",
                ),
                "operator": "gt",
                "right": expression(
                    "literal",
                    value=5,
                ),
            }
        ],
        "projections": [
            {
                "name": "label",
                "expression": expression(
                    "field",
                    source="r",
                    field_path="branch.beta",
                ),
            }
        ],
        "group_by": [],
        "aggregates": [],
        "order_by": [],
        "limit": 10,
        "answer_mode": "table",
    }


def test_plans_against_discovered_paths_without_canonical_facts():
    value = catalog()
    handle = (
        value.resources[0]
        .resource_handle
    )

    result = OpenWorldQueryPlanner(
        client=Client(
            proposal(
                handle
            )
        )
    ).plan(
        human_text="unseen request",
        catalog=value,
    )

    assert (
        result.sources[0]
        .field_paths
        == (
            "branch.alpha",
            "branch.beta",
        )
    )


def test_invented_path_fails_closed():
    value = catalog()
    handle = (
        value.resources[0]
        .resource_handle
    )

    bad = proposal(
        handle
    )

    bad["sources"][0][
        "field_paths"
    ] = [
        "not.real"
    ]

    with pytest.raises(
        OpenWorldQueryPlanningError,
        match="outside",
    ):
        OpenWorldQueryPlanner(
            client=Client(
                bad
            )
        ).plan(
            human_text="unseen request",
            catalog=value,
        )

def test_invalid_first_plan_is_repaired_against_same_catalog():
    value = catalog()

    handle = (
        value.resources[0]
        .resource_handle
    )

    bad = proposal(
        handle
    )

    bad["sources"][0][
        "field_paths"
    ] = [
        "not.real"
    ]

    repaired = proposal(
        handle
    )

    client = SequenceClient(
        [
            bad,
            repaired,
        ]
    )

    result = OpenWorldQueryPlanner(
        client=client
    ).plan(
        human_text=(
            "an unseen information request"
        ),
        catalog=value,
    )

    assert (
        result.sources[0]
        .field_paths
        == (
            "branch.alpha",
            "branch.beta",
        )
    )

    assert len(
        client.calls
    ) == 2

    second_user = client.calls[
        1
    ][
        "user"
    ]

    assert (
        "previous_proposal"
        in second_user
    )

    assert (
        "validation_error"
        in second_user
    )

    assert (
        "not.real"
        in second_user
    )


def test_invalid_repair_still_fails_closed():
    value = catalog()

    handle = (
        value.resources[0]
        .resource_handle
    )

    bad = proposal(
        handle
    )

    bad["sources"][0][
        "field_paths"
    ] = [
        "not.real"
    ]

    client = SequenceClient(
        [
            bad,
            bad,
        ]
    )

    with pytest.raises(
        OpenWorldQueryPlanningError,
        match="outside",
    ):
        OpenWorldQueryPlanner(
            client=client
        ).plan(
            human_text=(
                "another unseen information request"
            ),
            catalog=value,
        )

    assert len(
        client.calls
    ) == 2

def test_repair_receives_exact_invalid_field_path():
    value = catalog()

    handle = (
        value.resources[0]
        .resource_handle
    )

    bad = proposal(
        handle
    )

    bad["sources"][0][
        "field_paths"
    ] = [
        "not.real"
    ]

    repaired = proposal(
        handle
    )

    client = SequenceClient(
        [
            bad,
            repaired,
        ]
    )

    OpenWorldQueryPlanner(
        client=client
    ).plan(
        human_text=(
            "unseen information request"
        ),
        catalog=value,
    )

    assert len(
        client.calls
    ) == 2

    repair_payload = client.calls[
        1
    ][
        "user"
    ]

    assert (
        "invalid_field_paths"
        in repair_payload
    )

    assert (
        "not.real"
        in repair_payload
    )

    assert (
        handle
        in repair_payload
    )



def test_query_planner_cannot_supply_resource_selector():
    value = catalog()

    handle = (
        value.resources[0]
        .resource_handle
    )

    bad = proposal(
        handle
    )

    bad["sources"][0][
        "selector_reference"
    ] = "invented-selector"

    with pytest.raises(
        OpenWorldQueryPlanningError,
        match=(
            "cannot supply resource selectors"
        ),
    ):
        OpenWorldQueryPlanner(
            client=Client(
                bad
            )
        ).plan(
            human_text=(
                "unseen information request"
            ),
            catalog=value,
        )


def test_model_schema_binds_fields_to_selected_resource():
    value = catalog()

    handle = (
        value.resources[0]
        .resource_handle
    )

    client = SequenceClient(
        [
            proposal(
                handle
            ),
        ]
    )

    OpenWorldQueryPlanner(
        client=client
    ).plan(
        human_text=(
            "completely unseen information request"
        ),
        catalog=value,
    )

    assert len(
        client.calls
    ) == 1

    schema = client.calls[
        0
    ][
        "schema"
    ]

    variants = (
        schema[
            "properties"
        ][
            "sources"
        ][
            "items"
        ][
            "anyOf"
        ]
    )

    matching = [
        item
        for item in variants
        if item[
            "properties"
        ][
            "resource_handle"
        ][
            "enum"
        ]
        == [
            handle
        ]
    ]

    assert len(
        matching
    ) == 1

    allowed = set(
        matching[
            0
        ][
            "properties"
        ][
            "field_paths"
        ][
            "items"
        ][
            "enum"
        ]
    )

    assert allowed == {
        "branch.alpha",
        "branch.beta",
    }

    assert "name" not in allowed
    assert "site" not in allowed


def test_expression_schema_is_bounded_to_discovered_fields():
    value = catalog()

    handle = (
        value.resources[0]
        .resource_handle
    )

    client = SequenceClient(
        [
            proposal(
                handle
            ),
        ]
    )

    OpenWorldQueryPlanner(
        client=client
    ).plan(
        human_text=(
            "another unseen information request"
        ),
        catalog=value,
    )

    schema = client.calls[
        0
    ][
        "schema"
    ]

    expression = (
        schema[
            "properties"
        ][
            "filters"
        ][
            "items"
        ][
            "properties"
        ][
            "left"
        ]
    )

    field_options = (
        expression[
            "properties"
        ][
            "field_path"
        ][
            "anyOf"
        ][
            0
        ][
            "enum"
        ]
    )

    assert set(
        field_options
    ) == {
        "branch.alpha",
        "branch.beta",
    }


def test_unused_multiple_sources_are_minimized_without_model_repair():
    value = catalog()

    handle = (
        value.resources[0]
        .resource_handle
    )

    bad = proposal(
        handle
    )

    second_source = dict(
        bad["sources"][0]
    )

    second_source[
        "alias"
    ] = "secondary"

    bad[
        "sources"
    ] = [
        bad["sources"][0],
        second_source,
    ]

    bad[
        "joins"
    ] = []

    repaired = proposal(
        handle
    )

    client = SequenceClient(
        [
            bad,
            repaired,
        ]
    )

    result = OpenWorldQueryPlanner(
        client=client
    ).plan(
        human_text=(
            "completely unseen relational request"
        ),
        catalog=value,
    )

    assert len(
        result.sources
    ) == 1

    assert len(
        client.calls
    ) == 1


def test_repeated_unused_multiple_sources_do_not_require_repair():
    value = catalog()

    handle = (
        value.resources[0]
        .resource_handle
    )

    bad = proposal(
        handle
    )

    second_source = dict(
        bad["sources"][0]
    )

    second_source[
        "alias"
    ] = "secondary"

    bad[
        "sources"
    ] = [
        bad["sources"][0],
        second_source,
    ]

    bad[
        "joins"
    ] = []

    client = SequenceClient(
        [
            bad,
            bad,
        ]
    )

    result = OpenWorldQueryPlanner(
        client=client
    ).plan(
        human_text=(
            "another unseen relational request"
        ),
        catalog=value,
    )

    assert len(
        result.sources
    ) == 1

    assert len(
        client.calls
    ) == 1


def test_unused_second_source_is_removed_before_topology_validation():
    value = catalog()

    handle = (
        value.resources[0]
        .resource_handle
    )

    proposed = proposal(
        handle
    )

    second = dict(
        proposed["sources"][0]
    )

    second["alias"] = "unused"

    proposed["sources"] = [
        proposed["sources"][0],
        second,
    ]

    proposed["joins"] = []

    client = SequenceClient(
        [
            proposed,
        ]
    )

    result = OpenWorldQueryPlanner(
        client=client
    ).plan(
        human_text=(
            "unseen single-resource information request"
        ),
        catalog=value,
    )

    assert len(
        result.sources
    ) == 1

    assert result.sources[
        0
    ].alias != "unused"

    assert len(
        client.calls
    ) == 1


def test_two_actually_used_sources_still_require_governed_join():
    value = catalog()

    handle = (
        value.resources[0]
        .resource_handle
    )

    bad = proposal(
        handle
    )

    second = dict(
        bad["sources"][0]
    )

    second["alias"] = "secondary"

    bad["sources"] = [
        bad["sources"][0],
        second,
    ]

    # Make both aliases semantically active without providing a join.
    first_projection = dict(
        bad["projections"][0]
    )

    second_projection = {
        "name": "secondary_value",
        "expression": {
            "kind": "field",
            "source": "secondary",
            "field_path": "branch.alpha",
            "value": None,
            "unit": None,
            "direction": None,
            "output": None,
        },
    }

    bad["projections"] = [
        first_projection,
        second_projection,
    ]

    bad["joins"] = []

    client = SequenceClient(
        [
            bad,
            bad,
        ]
    )

    with pytest.raises(
        OpenWorldQueryPlanningError,
        match="explicit governed joins",
    ):
        OpenWorldQueryPlanner(
            client=client
        ).plan(
            human_text=(
                "unseen true multi-source request"
            ),
            catalog=value,
        )

    assert len(
        client.calls
    ) == 2


def test_explicit_multi_source_join_lowers_to_governed_query_join():
    value = catalog()

    handle = (
        value.resources[0]
        .resource_handle
    )

    proposed = proposal(
        handle
    )

    second = dict(
        proposed["sources"][0]
    )
    second["alias"] = "secondary"

    proposed["sources"] = [
        proposed["sources"][0],
        second,
    ]

    proposed["joins"] = [
        {
            "kind": "inner",
            "left": {
                "kind": "field",
                "source": "r",
                "field_path": "branch.alpha",
                "value": None,
                "unit": None,
                "direction": None,
                "output": None,
            },
            "right": {
                "kind": "field",
                "source": "secondary",
                "field_path": "branch.alpha",
                "value": None,
                "unit": None,
                "direction": None,
                "output": None,
            },
        }
    ]

    client = SequenceClient(
        [
            proposed,
        ]
    )

    result = OpenWorldQueryPlanner(
        client=client
    ).plan(
        human_text=(
            "unseen governed multi-source comparison"
        ),
        catalog=value,
    )

    assert len(
        result.sources
    ) == 2

    assert len(
        result.relational_plan.joins
    ) == 1

    join = (
        result.relational_plan.joins[0]
    )

    assert join.left.source == "r"
    assert (
        join.right.source
        == "secondary"
    )
    assert join.left.fact == "branch.alpha"
    assert join.right.fact == "branch.alpha"
    assert join.join_type == "inner"


def test_source_minimality_synchronizes_outer_and_relational_sources():
    value = catalog()

    handle = (
        value.resources[0]
        .resource_handle
    )

    proposed = proposal(
        handle
    )

    unused = dict(
        proposed["sources"][0]
    )

    unused["alias"] = "endpoint_b"

    proposed["sources"] = [
        proposed["sources"][0],
        unused,
    ]

    proposed["joins"] = []

    client = SequenceClient(
        [
            proposed,
        ]
    )

    result = OpenWorldQueryPlanner(
        client=client
    ).plan(
        human_text=(
            "unseen single-source request "
            "with model source over-selection"
        ),
        catalog=value,
    )

    outer_aliases = tuple(
        source.alias
        for source in result.sources
    )

    assert len(
        outer_aliases
    ) == 1

    assert (
        result.relational_plan.sources
        == outer_aliases
    )

    assert (
        "endpoint_b"
        not in result.relational_plan.sources
    )


def test_true_multi_source_plan_keeps_source_sets_synchronized():
    value = catalog()

    handle = (
        value.resources[0]
        .resource_handle
    )

    proposed = proposal(
        handle
    )

    second = dict(
        proposed["sources"][0]
    )

    second["alias"] = "endpoint_b"

    proposed["sources"] = [
        proposed["sources"][0],
        second,
    ]

    proposed["joins"] = [
        {
            "kind": "inner",
            "left": {
                "kind": "field",
                "source": "r",
                "field_path": "branch.alpha",
                "value": None,
                "unit": None,
                "direction": None,
                "output": None,
            },
            "right": {
                "kind": "field",
                "source": "endpoint_b",
                "field_path": "branch.alpha",
                "value": None,
                "unit": None,
                "direction": None,
                "output": None,
            },
        }
    ]

    client = SequenceClient(
        [
            proposed,
        ]
    )

    result = OpenWorldQueryPlanner(
        client=client
    ).plan(
        human_text=(
            "unseen true multi-source request"
        ),
        catalog=value,
    )

    outer_aliases = tuple(
        source.alias
        for source in result.sources
    )

    assert (
        result.relational_plan.sources
        == outer_aliases
    )

    assert set(
        outer_aliases
    ) == {
        "r",
        "endpoint_b",
    }


def test_unknown_expression_alias_repairs_using_declared_alias_set():
    value = catalog()

    handle = (
        value.resources[0]
        .resource_handle
    )

    bad = proposal(
        handle
    )

    bad["projections"][0][
        "expression"
    ]["source"] = "invented_source"

    repaired = proposal(
        handle
    )

    client = SequenceClient(
        [
            bad,
            repaired,
        ]
    )

    result = OpenWorldQueryPlanner(
        client=client
    ).plan(
        human_text=(
            "completely unseen information request"
        ),
        catalog=value,
    )

    assert len(
        result.sources
    ) == 1

    assert (
        result.sources[0].alias
        == "r"
    )

    assert len(
        client.calls
    ) == 2

    repair_payload = __import__(
        "json"
    ).loads(
        client.calls[1]["user"]
    )

    assert repair_payload[
        "declared_source_aliases"
    ] == [
        "r",
    ]

    assert (
        "invented_source"
        in repair_payload[
            "validation_error"
        ]
    )

    assert (
        "declared_source_aliases"
        in repair_payload[
            "validation_error"
        ]
    )


def test_join_schema_has_single_source_of_truth_for_aliases():
    value = catalog()

    client = SequenceClient(
        [
            proposal(
                value.resources[0]
                .resource_handle
            )
        ]
    )

    OpenWorldQueryPlanner(
        client=client
    ).plan(
        human_text="unseen request",
        catalog=value,
    )

    schema = client.calls[0][
        "schema"
    ]

    join_item = schema[
        "properties"
    ][
        "joins"
    ][
        "items"
    ]

    assert (
        "left_source"
        not in join_item[
            "properties"
        ]
    )

    assert (
        "right_source"
        not in join_item[
            "properties"
        ]
    )

    assert set(
        join_item[
            "required"
        ]
    ) == {
        "kind",
        "left",
        "right",
    }
