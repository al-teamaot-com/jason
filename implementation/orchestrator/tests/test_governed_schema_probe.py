from dataclasses import dataclass

import pytest

from orchestrator.governed_schema_probe import (
    GovernedSchemaProbe,
    GovernedSchemaProbeError,
)
from orchestrator.query_source_discovery import (
    QuerySourceContribution,
)


@dataclass
class Result:
    status: str
    provider_id: str
    capability_name: str
    output: dict


class Executor:
    def __init__(self, result):
        self.result = result
        self.intents = []

    def execute(self, intent):
        self.intents.append(
            intent
        )
        return self.result


def contribution(
    *,
    selector_required=False,
):
    return QuerySourceContribution(
        provider_id="synthetic-provider",
        capability_name="synthetic.search",
        resource_type="synthetic_resource",
        canonical_facts=(
            "__schema_probe__",
        ),
        operation=(
            "read"
            if selector_required
            else "search"
        ),
        selector_keys=("id",),
        selector_required=(
            selector_required
        ),
        collection_scope=(
            None
            if selector_required
            else "authorized"
        ),
        permission_mode="observe",
        risk="low",
        description="Synthetic governed read",
    )


def test_discovers_unknown_nested_fields_from_governed_output():
    executor = Executor(
        Result(
            status="succeeded",
            provider_id=(
                "synthetic-provider"
            ),
            capability_name=(
                "synthetic.search"
            ),
            output={
                "data": {
                    "resource_matches": [
                        {
                            "branch": {
                                "unknown_alpha": 7,
                                "unknown_beta": True,
                            }
                        }
                    ]
                }
            },
        )
    )

    result = GovernedSchemaProbe().probe(
        contribution=contribution(),
        executor=executor,
    )

    paths = {
        field.path
        for field in result.fields
    }

    assert (
        "branch.unknown_alpha"
        in paths
    )
    assert (
        "branch.unknown_beta"
        in paths
    )

    assert (
        executor.intents[0]
        .permission_mode
        == "observe"
    )


def test_probe_does_not_require_canonical_operational_fact():
    executor = Executor(
        Result(
            status="succeeded",
            provider_id=(
                "synthetic-provider"
            ),
            capability_name=(
                "synthetic.search"
            ),
            output={
                "data": {
                    "completely_new_field": 11
                }
            },
        )
    )

    result = GovernedSchemaProbe().probe(
        contribution=contribution(),
        executor=executor,
    )

    assert {
        field.path
        for field in result.fields
    } == {
        "completely_new_field"
    }


def test_selector_required_probe_fails_closed_without_reference():
    executor = Executor(
        Result(
            status="succeeded",
            provider_id=(
                "synthetic-provider"
            ),
            capability_name=(
                "synthetic.search"
            ),
            output={
                "data": {
                    "field": 1
                }
            },
        )
    )

    with pytest.raises(
        GovernedSchemaProbeError,
        match="requires a grounded reference",
    ):
        GovernedSchemaProbe().probe(
            contribution=contribution(
                selector_required=True
            ),
            executor=executor,
        )


def test_provider_provenance_mismatch_fails_closed():
    executor = Executor(
        Result(
            status="succeeded",
            provider_id="wrong-provider",
            capability_name=(
                "synthetic.search"
            ),
            output={
                "data": {
                    "field": 1
                }
            },
        )
    )

    with pytest.raises(
        GovernedSchemaProbeError,
        match="provenance mismatch",
    ):
        GovernedSchemaProbe().probe(
            contribution=contribution(),
            executor=executor,
        )
