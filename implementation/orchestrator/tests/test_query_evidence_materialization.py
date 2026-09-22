from dataclasses import dataclass

import pytest

from orchestrator.contracts import (
    ExecutionStage,
    OrchestrationResult,
    OrchestrationStatus,
)
from orchestrator.query_evidence_materialization import (
    GovernedQueryEvidenceMaterializer,
    QueryEvidenceMaterializationError,
)
from orchestrator.query_source_discovery import (
    QuerySourceBinding,
    QuerySourceContribution,
)


@dataclass(frozen=True)
class FakeFact:
    canonical_fact: str
    value: object
    json_pointer: str
    json_pointers: tuple[str, ...] = ()


class FakeInterpreter:
    def interpret(
        self,
        *,
        result,
        requested_facts,
        evidence_contexts=None,
    ):
        del evidence_contexts

        data = result.output["data"]

        facts = []

        for name in requested_facts:
            if name not in data:
                continue

            facts.append(
                FakeFact(
                    canonical_fact=name,
                    value=data[name],
                    json_pointer=f"/{name}",
                )
            )

        return tuple(facts)


def result(
    *,
    provider,
    capability,
    data,
    execution_id,
):
    return OrchestrationResult(
        execution_id=execution_id,
        correlation_id="corr",
        capability_name=capability,
        status=(
            OrchestrationStatus.SUCCEEDED
        ),
        stage=ExecutionStage.COMPLETED,
        reason_codes=("ok",),
        resolution=None,
        output={
            "provider": provider,
            "data": data,
        },
        attempts=1,
        provider_id=provider,
    )


def binding():
    return QuerySourceBinding(
        source_alias="objects",
        resource_type="object",
        required_facts=(
            "fact_one",
            "fact_two",
        ),
        contributions=(
            QuerySourceContribution(
                provider_id="source-a",
                capability_name="read-a",
                resource_type="object",
                canonical_facts=(
                    "fact_one",
                ),
                operation="search",
                selector_keys=(),
                selector_required=False,
                collection_scope="authorized",
            ),
            QuerySourceContribution(
                provider_id="source-b",
                capability_name="read-b",
                resource_type="object",
                canonical_facts=(
                    "fact_two",
                ),
                operation="search",
                selector_keys=(),
                selector_required=False,
                collection_scope="authorized",
            ),
        ),
    )


def test_materializes_cross_provider_facts_into_one_canonical_record():
    materializer = (
        GovernedQueryEvidenceMaterializer(
            interpreter=FakeInterpreter()
        )
    )

    dataset = materializer.materialize(
        binding=binding(),
        results=(
            result(
                provider="source-a",
                capability="read-a",
                execution_id="exec-a",
                data={
                    "resource_matches": [
                        {
                            "resource_id": "r-1",
                            "fact_one": 7,
                        }
                    ]
                },
            ),
            result(
                provider="source-b",
                capability="read-b",
                execution_id="exec-b",
                data={
                    "resource_matches": [
                        {
                            "resource_id": "r-1",
                            "fact_two": "x",
                        }
                    ]
                },
            ),
        ),
    )

    assert len(dataset.records) == 1

    record = dataset.records[0]

    assert record.entity_id == "r-1"
    assert record.facts == {
        "fact_one": 7,
        "fact_two": "x",
    }

    assert set(
        record.evidence_references
    ) == {
        "exec-a:/fact_one",
        "exec-b:/fact_two",
    }


def test_conflicting_verified_values_fail_closed():
    materializer = (
        GovernedQueryEvidenceMaterializer(
            interpreter=FakeInterpreter()
        )
    )

    local_binding = (
        QuerySourceBinding(
            source_alias="objects",
            resource_type="object",
            required_facts=(
                "fact_one",
            ),
            contributions=(
                QuerySourceContribution(
                    provider_id="source-a",
                    capability_name="read-a",
                    resource_type="object",
                    canonical_facts=(
                        "fact_one",
                    ),
                    operation="search",
                    selector_keys=(),
                    selector_required=False,
                    collection_scope="authorized",
                ),
                QuerySourceContribution(
                    provider_id="source-b",
                    capability_name="read-b",
                    resource_type="object",
                    canonical_facts=(
                        "fact_one",
                    ),
                    operation="search",
                    selector_keys=(),
                    selector_required=False,
                    collection_scope="authorized",
                ),
            ),
        )
    )

    with pytest.raises(
        QueryEvidenceMaterializationError,
        match="conflicting verified canonical values",
    ):
        materializer.materialize(
            binding=local_binding,
            results=(
                result(
                    provider="source-a",
                    capability="read-a",
                    execution_id="exec-a",
                    data={
                        "resource_id": "r-1",
                        "fact_one": 7,
                    },
                ),
                result(
                    provider="source-b",
                    capability="read-b",
                    execution_id="exec-b",
                    data={
                        "resource_id": "r-1",
                        "fact_one": 8,
                    },
                ),
            ),
        )


def test_result_outside_discovered_binding_fails_closed():
    materializer = (
        GovernedQueryEvidenceMaterializer(
            interpreter=FakeInterpreter()
        )
    )

    with pytest.raises(
        QueryEvidenceMaterializationError,
        match="does not match",
    ):
        materializer.materialize(
            binding=binding(),
            results=(
                result(
                    provider="unknown-source",
                    capability="unknown-read",
                    execution_id="exec-x",
                    data={
                        "resource_id": "r-1",
                        "fact_one": 7,
                    },
                ),
            ),
        )


def test_collection_record_without_durable_identity_fails_closed():
    materializer = (
        GovernedQueryEvidenceMaterializer(
            interpreter=FakeInterpreter()
        )
    )

    with pytest.raises(
        QueryEvidenceMaterializationError,
        match="durable resource identity",
    ):
        materializer.materialize(
            binding=binding(),
            results=(
                result(
                    provider="source-a",
                    capability="read-a",
                    execution_id="exec-a",
                    data={
                        "resource_matches": [
                            {
                                "fact_one": 7,
                            }
                        ]
                    },
                ),
            ),
        )
