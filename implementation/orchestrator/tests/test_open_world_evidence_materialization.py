from dataclasses import dataclass

from orchestrator.open_world_evidence_materialization import (
    OpenWorldEvidenceMaterializer,
)
from orchestrator.open_world_query_planning import (
    OpenWorldQuerySource,
)
from orchestrator.open_world_schema import (
    DiscoveredField,
    DiscoveredResourceSchema,
)


@dataclass
class Result:
    status: str
    provider_id: str
    capability_name: str
    execution_id: str
    output: dict


def resource(provider):
    return DiscoveredResourceSchema(
        provider_id=provider,
        capability_name="generic.search",
        resource_type="generic",
        operation="search",
        collection_supported=True,
        selector_keys=(),
        fields=(
            DiscoveredField(
                name="value",
                path="nested.value",
                value_type="number",
            ),
        ),
    )


def test_raw_discovered_path_becomes_verified_query_fact():
    r = resource(
        "p1"
    )

    source = OpenWorldQuerySource(
        alias="x",
        resource_handle=(
            r.resource_handle
        ),
        field_paths=(
            "nested.value",
        ),
    )

    result = (
        OpenWorldEvidenceMaterializer()
        .materialize(
            source=source,
            resource=r,
            results=(
                Result(
                    status="succeeded",
                    provider_id="p1",
                    capability_name="generic.search",
                    execution_id="e1",
                    output={
                        "data": {
                            "resource_matches": [
                                {
                                    "resource_id": "42",
                                    "nested": {
                                        "value": 17
                                    },
                                }
                            ]
                        }
                    },
                ),
            ),
        )
    )

    assert (
        result.records[0]
        .facts[
            "nested.value"
        ]
        == 17
    )


def test_same_local_id_from_two_providers_is_not_same_entity():
    first = resource(
        "p1"
    )

    second = resource(
        "p2"
    )

    source_first = OpenWorldQuerySource(
        alias="a",
        resource_handle=(
            first.resource_handle
        ),
        field_paths=(
            "nested.value",
        ),
    )

    source_second = OpenWorldQuerySource(
        alias="b",
        resource_handle=(
            second.resource_handle
        ),
        field_paths=(
            "nested.value",
        ),
    )

    materializer = (
        OpenWorldEvidenceMaterializer()
    )

    one = materializer.materialize(
        source=source_first,
        resource=first,
        results=(
            Result(
                status="succeeded",
                provider_id="p1",
                capability_name="generic.search",
                execution_id="e1",
                output={
                    "data": {
                        "resource_id": "same",
                        "nested": {
                            "value": 1
                        },
                    }
                },
            ),
        ),
    )

    two = materializer.materialize(
        source=source_second,
        resource=second,
        results=(
            Result(
                status="succeeded",
                provider_id="p2",
                capability_name="generic.search",
                execution_id="e2",
                output={
                    "data": {
                        "resource_id": "same",
                        "nested": {
                            "value": 2
                        },
                    }
                },
            ),
        ),
    )

    assert (
        one.records[0].entity_id
        != two.records[0].entity_id
    )
