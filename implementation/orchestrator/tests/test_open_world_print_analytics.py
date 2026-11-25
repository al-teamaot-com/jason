from dataclasses import dataclass

from orchestrator.governed_query import (
    DeterministicGovernedQueryEngine, GovernedQueryPlan, QueryAggregate,
    QueryArithmetic, QueryField, QueryJoin, QueryLiteral, QueryOrder, QueryOutput,
    QueryPredicate, QueryProjection,
)
from orchestrator.open_world_evidence_materialization import OpenWorldEvidenceMaterializer
from orchestrator.open_world_execution import OpenWorldExecutionCoordinator
from orchestrator.open_world_query_planning import OpenWorldQueryPlan, OpenWorldQuerySource
from orchestrator.open_world_schema import DiscoveredField, DiscoveredResourceSchema, OpenWorldResourceCatalog


ROWS = [
    {"device_id":"a","customer_name":"Alpha","total_impressions":100,"color_impressions":20,"copier_impressions":30,"printer_impressions":70,"usage_status":"verified"},
    {"device_id":"b","customer_name":"Beta","total_impressions":240,"color_impressions":10,"copier_impressions":200,"printer_impressions":40,"usage_status":"verified"},
    {"device_id":"c","customer_name":"Alpha","total_impressions":180,"color_impressions":80,"copier_impressions":60,"printer_impressions":120,"usage_status":"verified"},
    {"device_id":"d","customer_name":"Gamma","total_impressions":None,"color_impressions":None,"copier_impressions":None,"printer_impressions":None,"usage_status":"exception"},
]


@dataclass
class Result:
    status: str = "succeeded"
    provider_id: str = "kyocera_kfs"
    capability_name: str = "print.meter.usage.search"
    execution_id: str = "exec-usage"
    output: dict = None


class Executor:
    def __init__(self): self.intents=[]
    def execute(self, intent):
        self.intents.append(intent)
        return Result(output={"data":{"records":ROWS}})


def resource():
    names=("device_id","customer_name","total_impressions","color_impressions","copier_impressions","printer_impressions","usage_status")
    return DiscoveredResourceSchema(
        provider_id="kyocera_kfs", capability_name="print.meter.usage.search",
        resource_type="print_usage", operation="search", collection_supported=True,
        selector_keys=(), fields=tuple(DiscoveredField(name=n,path=n) for n in names),
    )


def execute(relational, field_paths):
    r=resource(); source=OpenWorldQuerySource(alias="u",resource_handle=r.resource_handle,field_paths=field_paths)
    return OpenWorldExecutionCoordinator(
        materializer=OpenWorldEvidenceMaterializer(), query_engine=DeterministicGovernedQueryEngine(),
    ).execute(
        plan=OpenWorldQueryPlan(sources=(source,),relational_plan=relational,answer_mode="table"),
        catalog=OpenWorldResourceCatalog(resources=(r,)), executor=Executor(),
    ).query_result


def verified_filter():
    return QueryPredicate(
        left=QueryField(source="u",fact="usage_status"), operator="eq", right=QueryLiteral("verified")
    )


def test_same_generic_usage_resource_answers_top_n_without_report_capability():
    result=execute(
        GovernedQueryPlan(
            sources=("u",), filters=(verified_filter(),),
            projections=(
                QueryProjection(name="company",expression=QueryField(source="u",fact="customer_name")),
                QueryProjection(name="device",expression=QueryField(source="u",fact="device_id")),
                QueryProjection(name="total",expression=QueryField(source="u",fact="total_impressions")),
            ),
            order_by=(QueryOrder(expression=QueryOutput(name="total"),direction="desc"),),
            limit=2,
        ),
        ("customer_name","device_id","total_impressions","usage_status"),
    )
    assert result.rows == (
        {"company":"Beta","device":"b","total":240},
        {"company":"Alpha","device":"c","total":180},
    )


def test_same_generic_usage_resource_answers_unseen_customer_color_aggregation():
    result=execute(
        GovernedQueryPlan(
            sources=("u",), filters=(verified_filter(),),
            group_by=(QueryProjection(name="company",expression=QueryField(source="u",fact="customer_name")),),
            aggregates=(QueryAggregate(name="color_total",operation="sum",expression=QueryField(source="u",fact="color_impressions")),),
            order_by=(QueryOrder(expression=QueryOutput(name="color_total"),direction="desc"),),
        ),
        ("customer_name","color_impressions","usage_status"),
    )
    assert result.rows == (
        {"company":"Alpha","color_total":100},
        {"company":"Beta","color_total":10},
    )



def test_same_generic_usage_resource_answers_cross_period_increase_question():
    r = resource()
    current = OpenWorldQuerySource(
        alias="current", resource_handle=r.resource_handle,
        field_paths=("device_id", "customer_name", "total_impressions", "usage_status"),
    )
    previous = OpenWorldQuerySource(
        alias="previous", resource_handle=r.resource_handle,
        field_paths=("device_id", "total_impressions", "usage_status"),
    )

    class PeriodExecutor:
        def __init__(self): self.calls = 0
        def execute(self, intent):
            self.calls += 1
            rows = (
                [
                    {"device_id":"a","customer_name":"Alpha","total_impressions":160,"usage_status":"verified"},
                    {"device_id":"b","customer_name":"Beta","total_impressions":260,"usage_status":"verified"},
                    {"device_id":"c","customer_name":"Alpha","total_impressions":250,"usage_status":"verified"},
                ]
                if self.calls == 1 else
                [
                    {"device_id":"a","total_impressions":100,"usage_status":"verified"},
                    {"device_id":"b","total_impressions":240,"usage_status":"verified"},
                    {"device_id":"c","total_impressions":180,"usage_status":"verified"},
                ]
            )
            return Result(output={"data":{"records":rows}})

    increase = QueryArithmetic(
        left=QueryField(source="current", fact="total_impressions"),
        operator="subtract",
        right=QueryField(source="previous", fact="total_impressions"),
    )
    plan = OpenWorldQueryPlan(
        sources=(current, previous),
        relational_plan=GovernedQueryPlan(
            sources=("current", "previous"),
            joins=(QueryJoin(
                left=QueryField(source="current", fact="device_id"),
                right=QueryField(source="previous", fact="device_id"),
                join_type="inner",
            ),),
            filters=(
                QueryPredicate(QueryField("current","usage_status"),"eq",QueryLiteral("verified")),
                QueryPredicate(QueryField("previous","usage_status"),"eq",QueryLiteral("verified")),
            ),
            projections=(
                QueryProjection("company", QueryField("current","customer_name")),
                QueryProjection("device", QueryField("current","device_id")),
                QueryProjection("increase", increase),
            ),
            order_by=(QueryOrder(QueryOutput("increase"), "desc"),),
        ),
        answer_mode="table",
    )
    result = OpenWorldExecutionCoordinator(
        materializer=OpenWorldEvidenceMaterializer(),
        query_engine=DeterministicGovernedQueryEngine(),
    ).execute(
        plan=plan,
        catalog=OpenWorldResourceCatalog(resources=(r,)),
        executor=PeriodExecutor(),
    ).query_result
    assert result.rows == (
        {"company":"Alpha","device":"c","increase":70},
        {"company":"Alpha","device":"a","increase":60},
        {"company":"Beta","device":"b","increase":20},
    )
