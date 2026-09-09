"""Materialize governed orchestration results into verified query datasets.

This module does not infer provider semantics.

Every canonical fact must already have been verified by the existing
GovernedResourceEvidenceInterpreter. This layer only converts verified facts and
durable resource identities into provider-neutral query records.

Equivalent evidence is corroboration. Conflicting values fail closed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .contracts import (
    OrchestrationResult,
    OrchestrationStatus,
)
from .governed_query import (
    VerifiedQueryDataset,
    VerifiedQueryRecord,
)
from .query_source_discovery import (
    QuerySourceBinding,
)
from .resource_evidence import (
    GovernedResourceEvidenceInterpreter,
    VerifiedResourceFact,
)


class QueryEvidenceMaterializationError(
    ValueError
):
    """Governed results could not safely become a canonical query dataset."""


@dataclass(frozen=True, slots=True)
class GovernedQueryEvidenceMaterializer:
    """Convert governed provider evidence into canonical query records."""

    interpreter: GovernedResourceEvidenceInterpreter

    def materialize(
        self,
        *,
        binding: QuerySourceBinding,
        results: Sequence[
            OrchestrationResult
        ],
    ) -> VerifiedQueryDataset:
        records: dict[
            str,
            dict[str, Any],
        ] = {}

        evidence: dict[
            str,
            list[str],
        ] = {}

        for result in results:
            if (
                result.status
                is not
                OrchestrationStatus.SUCCEEDED
            ):
                continue

            if not result.provider_id:
                raise QueryEvidenceMaterializationError(
                    "successful governed query source result "
                    "lacks provider identity"
                )

            if not any(
                contribution.provider_id
                == result.provider_id
                and contribution.capability_name
                == result.capability_name
                for contribution
                in binding.contributions
            ):
                raise QueryEvidenceMaterializationError(
                    "governed result does not match "
                    "the discovered query source binding"
                )

            data = result.output.get(
                "data"
            )

            if not isinstance(
                data,
                Mapping,
            ):
                raise QueryEvidenceMaterializationError(
                    "governed result lacks structured evidence data"
                )

            resource_items = (
                _resource_items(
                    data
                )
            )

            for entity_id, item in (
                resource_items
            ):
                synthetic = _result_for_item(
                    result=result,
                    data=item,
                )

                facts = (
                    self.interpreter.interpret(
                        result=synthetic,
                        requested_facts=(
                            binding.required_facts
                        ),
                    )
                )

                if not facts:
                    continue

                target = records.setdefault(
                    entity_id,
                    {},
                )

                references = (
                    evidence.setdefault(
                        entity_id,
                        [],
                    )
                )

                for fact in facts:
                    _merge_fact(
                        target=target,
                        fact=fact,
                    )

                    references.extend(
                        _fact_references(
                            result=result,
                            fact=fact,
                        )
                    )

        materialized = tuple(
            VerifiedQueryRecord(
                entity_id=entity_id,
                resource_type=(
                    binding.resource_type
                ),
                facts=dict(
                    facts
                ),
                evidence_references=tuple(
                    dict.fromkeys(
                        evidence.get(
                            entity_id,
                            (),
                        )
                    )
                ),
            )
            for entity_id, facts
            in sorted(
                records.items(),
                key=lambda item: (
                    item[0].casefold()
                ),
            )
        )

        return VerifiedQueryDataset(
            alias=binding.source_alias,
            resource_type=(
                binding.resource_type
            ),
            records=materialized,
        )


def _resource_items(
    data: Mapping[str, Any],
) -> tuple[
    tuple[
        str,
        Mapping[str, Any],
    ],
    ...,
]:
    raw_matches = data.get(
        "resource_matches"
    )

    if isinstance(
        raw_matches,
        Sequence,
    ) and not isinstance(
        raw_matches,
        (str, bytes),
    ):
        items = []

        for raw in raw_matches:
            if not isinstance(
                raw,
                Mapping,
            ):
                raise QueryEvidenceMaterializationError(
                    "resource collection contains "
                    "a non-object record"
                )

            entity_id = _entity_id(
                raw
            )

            items.append(
                (
                    entity_id,
                    raw,
                )
            )

        return tuple(items)

    entity_id = _entity_id(
        data
    )

    return (
        (
            entity_id,
            data,
        ),
    )


def _entity_id(
    item: Mapping[str, Any],
) -> str:
    for key in (
        "resource_id",
        "resolved_resource_id",
    ):
        value = str(
            item.get(
                key,
                "",
            )
        ).strip()

        if value:
            return value

    raise QueryEvidenceMaterializationError(
        "verified query record lacks durable resource identity"
    )


def _result_for_item(
    *,
    result: OrchestrationResult,
    data: Mapping[str, Any],
) -> OrchestrationResult:
    return OrchestrationResult(
        execution_id=(
            result.execution_id
        ),
        correlation_id=(
            result.correlation_id
        ),
        capability_name=(
            result.capability_name
        ),
        status=result.status,
        stage=result.stage,
        reason_codes=(
            result.reason_codes
        ),
        resolution=result.resolution,
        output={
            **dict(
                result.output
            ),
            "data": data,
        },
        artifact_references=(
            result.artifact_references
        ),
        attempts=result.attempts,
        provider_id=(
            result.provider_id
        ),
        error_code=(
            result.error_code
        ),
    )


def _merge_fact(
    *,
    target: dict[str, Any],
    fact: VerifiedResourceFact,
) -> None:
    name = fact.canonical_fact

    if name not in target:
        target[
            name
        ] = fact.value
        return

    existing = target[
        name
    ]

    if (
        type(existing)
        is not type(
            fact.value
        )
        or existing
        != fact.value
    ):
        raise QueryEvidenceMaterializationError(
            "conflicting verified canonical values "
            "were observed for one resource fact"
        )


def _fact_references(
    *,
    result: OrchestrationResult,
    fact: VerifiedResourceFact,
) -> tuple[str, ...]:
    pointers = tuple(
        getattr(
            fact,
            "json_pointers",
            (),
        )
        or ()
    )

    if not pointers:
        pointers = (
            fact.json_pointer,
        )

    return tuple(
        f"{result.execution_id}:{pointer}"
        for pointer in pointers
    )
