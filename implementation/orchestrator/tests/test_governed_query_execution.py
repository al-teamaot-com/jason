from dataclasses import dataclass

from orchestrator.governed_query import (
    GovernedQueryPlan,
    GovernedQueryResult,
    VerifiedQueryDataset,
    VerifiedQueryRecord,
)
from orchestrator.governed_query_execution import (
    GovernedQueryExecutionCoordinator,
)
from orchestrator.query_source_discovery import (
    QuerySourceBinding,
    QuerySourceContribution,
)
from orchestrator.semantic_query_planning import (
    SemanticQueryPlan,
    SemanticQuerySource,
)
from orchestrator.teams_conversation_flow import (
    ConversationIntent,
)


class FakeDiscovery:
    def __init__(self, bindings):
        self.bindings = tuple(bindings)
        self.calls = []

    def discover_all(self, sources):
        self.calls.append(tuple(sources))
        return self.bindings


class FakeIntentBuilder:
    def __init__(self):
        self.calls = []

    def build(
        self,
        *,
        human_text,
        planned,
    ):
        self.calls.append(
            (
                human_text,
                tuple(planned),
            )
        )

        item = tuple(planned)[0]

        return ConversationIntent(
            capability_name=(
                item.capability.capability_name
            ),
            arguments={
                "selector": (
                    item.need.target.reference
                ),
                "requested_facts": [
                    item.need.need
                ],
            },
            permission_mode="observe",
            risk=item.capability.risk,
        )


class FakeExecutor:
    def __init__(self):
        self.intents = []

    def execute(self, intent):
        self.intents.append(intent)
        return {
            "capability_name": (
                intent.capability_name
            ),
            "arguments": dict(
                intent.arguments
            ),
        }


class FakeMaterializer:
    def __init__(self):
        self.calls = []

    def materialize(
        self,
        *,
        binding,
        results,
    ):
        self.calls.append(
            (
                binding,
                tuple(results),
            )
        )

        return VerifiedQueryDataset(
            alias=binding.source_alias,
            resource_type=(
                binding.resource_type
            ),
            records=(
                VerifiedQueryRecord(
                    entity_id=(
                        binding.source_alias
                        + "-1"
                    ),
                    resource_type=(
                        binding.resource_type
                    ),
                    facts={
                        fact: 1
                        for fact
                        in binding.required_facts
                    },
                    evidence_references=(
                        "evidence:test",
                    ),
                ),
            ),
        )


class FakeEngine:
    def __init__(self):
        self.calls = []

    def execute(
        self,
        *,
        plan,
        datasets,
        now=None,
    ):
        del now

        self.calls.append(
            (
                plan,
                tuple(datasets),
            )
        )

        return GovernedQueryResult(
            columns=("result",),
            rows=(
                {
                    "result": 1,
                },
            ),
            source_aliases=(
                plan.sources
            ),
            evidence_references=(
                "evidence:test",
            ),
        )


def contribution(
    name,
    facts,
    *,
    selector_required=False,
    collection_scope="authorized",
):
    return QuerySourceContribution(
        provider_id=(
            "synthetic-provider-"
            + name
        ),
        capability_name=name,
        resource_type="object",
        canonical_facts=tuple(facts),
        operation="search",
        selector_keys=(
            "name",
        ),
        selector_required=(
            selector_required
        ),
        collection_scope=(
            collection_scope
        ),
        permission_mode="observe",
        risk="low",
        description="Synthetic resource read",
    )


def test_collection_query_executes_discovered_contributions_through_executor():
    source = SemanticQuerySource(
        alias="objects",
        resource_type="object",
        scope="collection",
        required_facts=(
            "fact_a",
            "fact_b",
        ),
    )

    binding = QuerySourceBinding(
        source_alias="objects",
        resource_type="object",
        required_facts=(
            "fact_a",
            "fact_b",
        ),
        contributions=(
            contribution(
                "capability-a",
                ("fact_a",),
            ),
            contribution(
                "capability-b",
                ("fact_b",),
            ),
        ),
    )

    executor = FakeExecutor()
    materializer = FakeMaterializer()
    engine = FakeEngine()

    coordinator = (
        GovernedQueryExecutionCoordinator(
            discovery=FakeDiscovery(
                (binding,)
            ),
            intent_builder=(
                FakeIntentBuilder()
            ),
            materializer=materializer,
            query_engine=engine,
        )
    )

    plan = SemanticQueryPlan(
        sources=(source,),
        relational_plan=GovernedQueryPlan(
            sources=("objects",),
        ),
    )

    result = coordinator.execute(
        human_text="synthetic request",
        plan=plan,
        executor=executor,
    )

    assert len(
        executor.intents
    ) == 2

    assert {
        item.capability_name
        for item in executor.intents
    } == {
        "capability-a",
        "capability-b",
    }

    assert executor.intents[
        0
    ].permission_mode == "observe"

    assert len(
        materializer.calls
    ) == 1

    assert len(
        result.orchestrations
    ) == 2

    assert result.query_result.rows == (
        {
            "result": 1,
        },
    )


def test_single_resource_query_reuses_existing_selector_grounding_builder():
    source = SemanticQuerySource(
        alias="objects",
        resource_type="object",
        scope="single",
        required_facts=(
            "fact_a",
        ),
        selector_reference="literal-reference",
    )

    binding = QuerySourceBinding(
        source_alias="objects",
        resource_type="object",
        required_facts=(
            "fact_a",
        ),
        contributions=(
            contribution(
                "capability-a",
                ("fact_a",),
                selector_required=True,
                collection_scope=None,
            ),
        ),
    )

    builder = FakeIntentBuilder()
    executor = FakeExecutor()

    coordinator = (
        GovernedQueryExecutionCoordinator(
            discovery=FakeDiscovery(
                (binding,)
            ),
            intent_builder=builder,
            materializer=(
                FakeMaterializer()
            ),
            query_engine=FakeEngine(),
        )
    )

    coordinator.execute(
        human_text="synthetic request",
        plan=SemanticQueryPlan(
            sources=(source,),
            relational_plan=GovernedQueryPlan(
                sources=("objects",),
            ),
        ),
        executor=executor,
    )

    assert len(
        builder.calls
    ) == 1

    intent = executor.intents[0]

    assert (
        intent.arguments["selector"]
        == "literal-reference"
    )


def test_multiple_semantic_sources_are_materialized_independently_before_query():
    first = SemanticQuerySource(
        alias="left",
        resource_type="object",
        scope="collection",
        required_facts=(
            "fact_a",
        ),
    )

    second = SemanticQuerySource(
        alias="right",
        resource_type="object",
        scope="collection",
        required_facts=(
            "fact_b",
        ),
    )

    bindings = (
        QuerySourceBinding(
            source_alias="left",
            resource_type="object",
            required_facts=(
                "fact_a",
            ),
            contributions=(
                contribution(
                    "capability-left",
                    ("fact_a",),
                ),
            ),
        ),
        QuerySourceBinding(
            source_alias="right",
            resource_type="object",
            required_facts=(
                "fact_b",
            ),
            contributions=(
                contribution(
                    "capability-right",
                    ("fact_b",),
                ),
            ),
        ),
    )

    materializer = FakeMaterializer()
    engine = FakeEngine()

    coordinator = (
        GovernedQueryExecutionCoordinator(
            discovery=FakeDiscovery(
                bindings
            ),
            intent_builder=(
                FakeIntentBuilder()
            ),
            materializer=materializer,
            query_engine=engine,
        )
    )

    relational = GovernedQueryPlan(
        sources=(
            "left",
            "right",
        ),
        joins=(),
    )

    try:
        coordinator.execute(
            human_text="synthetic request",
            plan=SemanticQueryPlan(
                sources=(
                    first,
                    second,
                ),
                relational_plan=relational,
            ),
            executor=FakeExecutor(),
        )
    except Exception:
        # FakeEngine deliberately ignores relational validity; this test only
        # establishes that each semantic source reaches independent materialization.
        pass

    assert {
        call[0].source_alias
        for call in materializer.calls
    } == {
        "left",
        "right",
    }


def test_collection_query_never_uses_selector_grounding_model():
    source = SemanticQuerySource(
        alias="objects",
        resource_type="object",
        scope="collection",
        required_facts=(
            "fact_a",
        ),
    )

    binding = QuerySourceBinding(
        source_alias="objects",
        resource_type="object",
        required_facts=(
            "fact_a",
        ),
        contributions=(
            contribution(
                "capability-a",
                ("fact_a",),
            ),
        ),
    )

    builder = FakeIntentBuilder()

    coordinator = (
        GovernedQueryExecutionCoordinator(
            discovery=FakeDiscovery(
                (binding,)
            ),
            intent_builder=builder,
            materializer=(
                FakeMaterializer()
            ),
            query_engine=FakeEngine(),
        )
    )

    coordinator.execute(
        human_text="synthetic request",
        plan=SemanticQueryPlan(
            sources=(source,),
            relational_plan=GovernedQueryPlan(
                sources=("objects",),
            ),
        ),
        executor=FakeExecutor(),
    )

    assert builder.calls == []
