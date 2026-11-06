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


def test_open_world_execution_pushes_declared_relative_time_filter(monkeypatch):
    from datetime import datetime, timezone
    from orchestrator.governed_query import QueryPredicate, QueryRelativeTime
    import orchestrator.open_world_execution as module

    fixed_now = datetime(2026, 11, 5, 20, 0, tzinfo=timezone.utc)

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed_now if tz is not None else fixed_now.replace(tzinfo=None)

    monkeypatch.setattr(module, "datetime", FixedDateTime)

    resource = DiscoveredResourceSchema(
        provider_id="p1",
        capability_name="generic.search",
        resource_type="usage",
        operation="search",
        collection_supported=True,
        selector_keys=("start",),
        fields=(
            DiscoveredField(name="period_start", path="period_start", value_type="string"),
            DiscoveredField(name="value", path="value", value_type="number"),
        ),
        query_filter_bindings=(("period_start", "gte", "start"),),
    )
    source = OpenWorldQuerySource(
        alias="u", resource_handle=resource.resource_handle,
        field_paths=("period_start", "value"),
    )
    plan = OpenWorldQueryPlan(
        sources=(source,),
        relational_plan=GovernedQueryPlan(
            sources=("u",),
            filters=(QueryPredicate(
                left=QueryField(source="u", fact="period_start"),
                operator="gte",
                right=QueryRelativeTime(amount=10, unit="days", direction="past"),
            ),),
            projections=(QueryProjection(
                name="value", expression=QueryField(source="u", fact="value"),
            ),),
        ),
        answer_mode="table",
    )

    class TimeExecutor(Executor):
        def execute(self, intent):
            self.intents.append(intent)
            return Result(
                status="succeeded", provider_id="p1",
                capability_name="generic.search", execution_id="e1",
                output={"data": {"records": [{
                    "period_start": intent.arguments["start"], "value": 9,
                }]}}
            )

    executor = TimeExecutor()
    result = OpenWorldExecutionCoordinator(
        materializer=OpenWorldEvidenceMaterializer(),
        query_engine=DeterministicGovernedQueryEngine(),
    ).execute(
        plan=plan,
        catalog=OpenWorldResourceCatalog(resources=(resource,)),
        executor=executor,
    )

    assert executor.intents[0].arguments == {
        "start": "2026-10-26T20:00:00+00:00"
    }
    assert result.query_result.rows == ({"value": 9},)


def test_post_query_exact_lookups_chain_serial_to_configuration_to_company():
    from orchestrator.open_world_query_planning import OpenWorldLookup, OpenWorldLookupField

    usage = DiscoveredResourceSchema(
        provider_id="kfs", capability_name="print.meter.usage.search",
        resource_type="print_usage", operation="search", collection_supported=True,
        selector_keys=(), fields=(
            DiscoveredField(name="serial_number", path="serial_number"),
            DiscoveredField(name="total_impressions", path="total_impressions", value_type="integer"),
        ),
    )
    configs = DiscoveredResourceSchema(
        provider_id="autotask", capability_name="service.configuration.search",
        resource_type="service_configuration", operation="search", collection_supported=True,
        selector_keys=("serial_number", "page_size"), fields=(
            DiscoveredField(name="companyID", path="companyID", value_type="integer"),
            DiscoveredField(name="referenceNumber", path="referenceNumber"),
        ),
        query_filter_bindings=(("serialNumber", "eq", "serial_number"),),
    )
    companies = DiscoveredResourceSchema(
        provider_id="autotask", capability_name="service.company.search",
        resource_type="service_company", operation="search", collection_supported=True,
        selector_keys=("resource_id", "page_size"), fields=(
            DiscoveredField(name="companyName", path="companyName"),
        ),
        query_filter_bindings=(("id", "eq", "resource_id"),),
    )
    source = OpenWorldQuerySource(
        alias="u", resource_handle=usage.resource_handle,
        field_paths=("serial_number", "total_impressions"),
    )
    plan = OpenWorldQueryPlan(
        sources=(source,),
        relational_plan=GovernedQueryPlan(
            sources=("u",), projections=(
                QueryProjection("serial", QueryField("u", "serial_number")),
                QueryProjection("total", QueryField("u", "total_impressions")),
            ),
        ),
        answer_mode="table",
        lookups=(
            OpenWorldLookup(
                alias="cfg", resource_handle=configs.resource_handle,
                input_output="serial", match_field="serialNumber",
                fields=(
                    OpenWorldLookupField("company_id", "companyID"),
                    OpenWorldLookupField("device", "referenceNumber"),
                ),
            ),
            OpenWorldLookup(
                alias="company", resource_handle=companies.resource_handle,
                input_output="company_id", match_field="id",
                fields=(OpenWorldLookupField("company", "companyName"),),
            ),
        ),
    )

    class LookupExecutor:
        def __init__(self): self.intents=[]
        def execute(self, intent):
            self.intents.append(intent)
            if intent.capability_name == "print.meter.usage.search":
                return Result("succeeded", "kfs", intent.capability_name, "u1", {
                    "data":{"records":[{"serial_number":"SER1","total_impressions":250}]}
                })
            if intent.capability_name == "service.configuration.search":
                assert intent.arguments == {"serial_number":"SER1", "page_size":2}
                return Result("succeeded", "autotask", intent.capability_name, "c1", {
                    "data":{"items":[{"companyID":278,"referenceNumber":"1207 Teachers Work Room BIG -"}]}
                })
            assert intent.capability_name == "service.company.search"
            assert intent.arguments == {"resource_id":278, "page_size":2}
            return Result("succeeded", "autotask", intent.capability_name, "co1", {
                "data":{"items":[{"companyName":"St. Matthews Catholic School"}]}
            })

    executor=LookupExecutor()
    result=OpenWorldExecutionCoordinator(
        materializer=OpenWorldEvidenceMaterializer(), query_engine=DeterministicGovernedQueryEngine(),
    ).execute(
        plan=plan, catalog=OpenWorldResourceCatalog(resources=(usage,configs,companies)), executor=executor,
    )
    assert result.query_result.rows == ({
        "serial":"SER1","total":250,"company_id":278,
        "device":"1207 Teachers Work Room BIG -","company":"St. Matthews Catholic School",
    },)
    assert [i.capability_name for i in executor.intents] == [
        "print.meter.usage.search","service.configuration.search","service.company.search"
    ]


def test_post_query_lookup_fails_closed_on_ambiguous_match():
    import pytest
    from orchestrator.open_world_execution import OpenWorldExecutionError
    from orchestrator.open_world_query_planning import OpenWorldLookup, OpenWorldLookupField

    usage = DiscoveredResourceSchema(
        provider_id="kfs", capability_name="usage.search", resource_type="usage",
        operation="search", collection_supported=True, selector_keys=(),
        fields=(DiscoveredField(name="serial", path="serial"),),
    )
    lookup_resource = DiscoveredResourceSchema(
        provider_id="autotask", capability_name="configuration.search", resource_type="configuration",
        operation="search", collection_supported=True, selector_keys=("serial_number","page_size"),
        fields=(DiscoveredField(name="companyID", path="companyID"),),
        query_filter_bindings=(("serialNumber","eq","serial_number"),),
    )
    plan=OpenWorldQueryPlan(
        sources=(OpenWorldQuerySource("u",usage.resource_handle,("serial",)),),
        relational_plan=GovernedQueryPlan(
            sources=("u",), projections=(QueryProjection("serial",QueryField("u","serial")),),
        ), answer_mode="table",
        lookups=(OpenWorldLookup(
            "cfg",lookup_resource.resource_handle,"serial","serialNumber",
            (OpenWorldLookupField("company_id","companyID"),),
        ),),
    )
    class AmbiguousExecutor:
        def execute(self,intent):
            if intent.capability_name == "usage.search":
                return Result("succeeded","kfs",intent.capability_name,"u",{"data":{"records":[{"serial":"S"}]}})
            return Result("succeeded","autotask",intent.capability_name,"a",{"data":{"items":[{"companyID":1},{"companyID":2}]}})
    with pytest.raises(OpenWorldExecutionError, match="multiple governed matches"):
        OpenWorldExecutionCoordinator(OpenWorldEvidenceMaterializer(),DeterministicGovernedQueryEngine()).execute(
            plan=plan,catalog=OpenWorldResourceCatalog(resources=(usage,lookup_resource)),executor=AmbiguousExecutor()
        )


def test_post_query_lookup_deduplicates_identical_inputs():
    from orchestrator.open_world_query_planning import OpenWorldLookup, OpenWorldLookupField
    usage=DiscoveredResourceSchema(
        provider_id="kfs",capability_name="usage.search",resource_type="usage",operation="search",
        collection_supported=True,selector_keys=(),fields=(DiscoveredField("serial","serial"),DiscoveredField("value","value")),
    )
    config=DiscoveredResourceSchema(
        provider_id="autotask",capability_name="configuration.search",resource_type="configuration",operation="search",
        collection_supported=True,selector_keys=("serial_number","page_size"),fields=(DiscoveredField("companyID","companyID"),),
        query_filter_bindings=(("serialNumber","eq","serial_number"),),
    )
    plan=OpenWorldQueryPlan(
        sources=(OpenWorldQuerySource("u",usage.resource_handle,("serial","value")),),
        relational_plan=GovernedQueryPlan(sources=("u",),projections=(
            QueryProjection("serial",QueryField("u","serial")),QueryProjection("value",QueryField("u","value")),
        )),answer_mode="table",
        lookups=(OpenWorldLookup("cfg",config.resource_handle,"serial","serialNumber",(OpenWorldLookupField("company_id","companyID"),)),),
    )
    class CacheExecutor:
        def __init__(self): self.calls=0
        def execute(self,intent):
            if intent.capability_name == "usage.search":
                return Result("succeeded","kfs",intent.capability_name,"u",{"data":{"records":[{"serial":"S","value":1},{"serial":"S","value":2}]}})
            self.calls += 1
            return Result("succeeded","autotask",intent.capability_name,"a",{"data":{"items":[{"companyID":5}]}})
    executor=CacheExecutor()
    result=OpenWorldExecutionCoordinator(OpenWorldEvidenceMaterializer(),DeterministicGovernedQueryEngine()).execute(
        plan=plan,catalog=OpenWorldResourceCatalog(resources=(usage,config)),executor=executor
    )
    assert executor.calls == 1
    assert [row["company_id"] for row in result.query_result.rows] == [5,5]
