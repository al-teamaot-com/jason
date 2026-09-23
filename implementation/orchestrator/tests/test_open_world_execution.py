from dataclasses import dataclass

from orchestrator.governed_query import (
    DeterministicGovernedQueryEngine,
    GovernedQueryPlan,
    QueryField,
    QueryProjection,
)
from orchestrator.open_world_evidence_materialization import (
    OpenWorldEvidenceMaterializer,
)
from orchestrator.open_world_execution import (
    OpenWorldExecutionCoordinator,
)
from orchestrator.open_world_query_planning import (
    OpenWorldQueryPlan,
    OpenWorldQuerySource,
)
from orchestrator.open_world_schema import (
    DiscoveredField,
    DiscoveredResourceSchema,
    OpenWorldResourceCatalog,
)


@dataclass
class Result:
    status: str
    provider_id: str
    capability_name: str
    execution_id: str
    output: dict


class Executor:
    def __init__(self):
        self.intents = []

    def execute(self, intent):
        self.intents.append(
            intent
        )

        return Result(
            status="succeeded",
            provider_id="p1",
            capability_name="generic.search",
            execution_id="e1",
            output={
                "data": {
                    "resource_matches": [
                        {
                            "new_branch": {
                                "new_value": 23
                            }
                        }
                    ]
                }
            },
        )


def test_open_world_execution_uses_discovered_raw_field():
    resource = DiscoveredResourceSchema(
        provider_id="p1",
        capability_name="generic.search",
        resource_type="generic",
        operation="search",
        collection_supported=True,
        selector_keys=(),
        fields=(
            DiscoveredField(
                name="new_value",
                path="new_branch.new_value",
                value_type="number",
            ),
        ),
    )

    source = OpenWorldQuerySource(
        alias="r",
        resource_handle=(
            resource.resource_handle
        ),
        field_paths=(
            "new_branch.new_value",
        ),
    )

    plan = OpenWorldQueryPlan(
        sources=(
            source,
        ),
        relational_plan=GovernedQueryPlan(
            sources=("r",),
            projections=(
                QueryProjection(
                    name="value",
                    expression=QueryField(
                        source="r",
                        fact="new_branch.new_value",
                    ),
                ),
            ),
        ),
        answer_mode="table",
    )

    executor = Executor()

    result = OpenWorldExecutionCoordinator(
        materializer=(
            OpenWorldEvidenceMaterializer()
        ),
        query_engine=(
            DeterministicGovernedQueryEngine()
        ),
    ).execute(
        plan=plan,
        catalog=OpenWorldResourceCatalog(
            resources=(
                resource,
            )
        ),
        executor=executor,
    )

    assert (
        result.query_result.rows[0][
            "value"
        ]
        == 23
    )

    assert len(
        executor.intents
    ) == 1


def test_collection_execution_does_not_invent_schema_probe_argument():
    resource = DiscoveredResourceSchema(
        provider_id="p1",
        capability_name="generic.search",
        resource_type="generic",
        operation="search",
        collection_supported=True,
        selector_keys=(),
        fields=(
            DiscoveredField(
                name="new_value",
                path="new_branch.new_value",
            ),
        ),
    )

    source = OpenWorldQuerySource(
        alias="r",
        resource_handle=(
            resource.resource_handle
        ),
        field_paths=(
            "new_branch.new_value",
        ),
    )

    plan = OpenWorldQueryPlan(
        sources=(source,),
        relational_plan=GovernedQueryPlan(
            sources=("r",),
        ),
        answer_mode="table",
    )

    executor = Executor()

    OpenWorldExecutionCoordinator(
        materializer=(
            OpenWorldEvidenceMaterializer()
        ),
        query_engine=(
            DeterministicGovernedQueryEngine()
        ),
    ).execute(
        plan=plan,
        catalog=OpenWorldResourceCatalog(
            resources=(resource,)
        ),
        executor=executor,
    )

    assert (
        "schema_probe"
        not in executor.intents[0]
        .arguments
    )
