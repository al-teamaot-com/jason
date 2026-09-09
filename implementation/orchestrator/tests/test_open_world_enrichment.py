from dataclasses import dataclass

from orchestrator.governed_schema_probe import (
    GovernedSchemaProbe,
)
from orchestrator.open_world_enrichment import (
    OpenWorldCatalogEnricher,
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
            output={
                "data": {
                    "resource_matches": [
                        {
                            "unseen": {
                                "field_x": 10,
                                "field_y": "value",
                            }
                        }
                    ]
                }
            },
        )


def test_live_fields_are_merged_even_when_declared_hints_exist():
    catalog = OpenWorldResourceCatalog(
        resources=(
            DiscoveredResourceSchema(
                provider_id="p1",
                capability_name="generic.search",
                resource_type="generic_resource",
                operation="search",
                collection_supported=True,
                selector_keys=(),
                fields=(
                    DiscoveredField(
                        name="known_hint",
                        path="known_hint",
                    ),
                ),
            ),
        )
    )

    executor = Executor()

    result = OpenWorldCatalogEnricher(
        probe=GovernedSchemaProbe()
    ).enrich(
        catalog=catalog,
        executor=executor,
    )

    paths = {
        field.path
        for field
        in result.resources[0].fields
    }

    assert "known_hint" in paths
    assert "unseen.field_x" in paths
    assert "unseen.field_y" in paths

    assert (
        "schema_probe"
        not in executor.intents[0]
        .arguments
    )
