"""Materialize discovered raw field paths from governed orchestration evidence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .governed_query import (
    VerifiedQueryDataset,
    VerifiedQueryRecord,
)
from .open_world_query_planning import (
    OpenWorldQuerySource,
)
from .open_world_schema import (
    DiscoveredResourceSchema,
)


class OpenWorldEvidenceError(
    RuntimeError
):
    pass


@dataclass(frozen=True, slots=True)
class OpenWorldEvidenceMaterializer:
    max_records: int = 10000

    def materialize(
        self,
        *,
        source: OpenWorldQuerySource,
        resource: DiscoveredResourceSchema,
        results: Sequence[Any],
    ) -> VerifiedQueryDataset:
        records = []
        seen = 0

        for result in results:
            status = str(
                getattr(
                    result,
                    "status",
                    "",
                )
            ).strip().casefold()

            if status not in {
                "succeeded",
                "success",
                "completed",
            }:
                continue

            result_provider = str(
                getattr(
                    result,
                    "provider_id",
                    "",
                )
            ).strip()

            result_capability = str(
                getattr(
                    result,
                    "capability_name",
                    "",
                )
            ).strip()

            if (
                result_provider
                and result_provider
                != resource.provider_id
            ):
                raise OpenWorldEvidenceError(
                    "governed evidence provider "
                    "provenance mismatch"
                )

            if (
                result_capability
                and result_capability
                != resource.capability_name
            ):
                raise OpenWorldEvidenceError(
                    "governed evidence capability "
                    "provenance mismatch"
                )

            output = getattr(
                result,
                "output",
                None,
            )

            if not isinstance(
                output,
                Mapping,
            ):
                continue

            data = output.get(
                "data"
            )

            for index, item in enumerate(
                _records(
                    data
                )
            ):
                if not isinstance(
                    item,
                    Mapping,
                ):
                    continue

                facts = {}

                for path in source.field_paths:
                    found, value = _resolve_path(
                        item,
                        path,
                    )

                    if found:
                        facts[
                            path
                        ] = value

                if not facts:
                    continue

                local_id = _local_identity(
                    item,
                    index=index,
                )

                # Provider-local identifiers are deliberately namespaced.
                # They are NEVER treated as globally canonical identities.
                entity_id = (
                    resource.resource_handle
                    + ":"
                    + local_id
                )

                execution_id = str(
                    getattr(
                        result,
                        "execution_id",
                        "execution",
                    )
                )

                records.append(
                    VerifiedQueryRecord(
                        entity_id=entity_id,
                        resource_type=(
                            resource.resource_type
                        ),
                        facts=facts,
                        evidence_references=tuple(
                            f"{execution_id}:{path}"
                            for path in facts
                        ),
                    )
                )

                seen += 1

                if seen >= self.max_records:
                    break

            if seen >= self.max_records:
                break

        return VerifiedQueryDataset(
            alias=source.alias,
            resource_type=(
                resource.resource_type
            ),
            records=tuple(
                records
            ),
        )


def _records(
    data: Any,
) -> tuple[Any, ...]:
    if isinstance(
        data,
        Mapping,
    ):
        for key in (
            "resource_matches",
            "items",
            "results",
            "records",
        ):
            value = data.get(
                key
            )

            if isinstance(
                value,
                Sequence,
            ) and not isinstance(
                value,
                (
                    str,
                    bytes,
                    bytearray,
                ),
            ):
                return tuple(
                    value
                )

        return (
            data,
        )

    if isinstance(
        data,
        Sequence,
    ) and not isinstance(
        data,
        (
            str,
            bytes,
            bytearray,
        ),
    ):
        return tuple(
            data
        )

    return ()


def _resolve_path(
    value: Any,
    path: str,
) -> tuple[
    bool,
    Any,
]:
    current = value

    for raw in path.split(
        "."
    ):
        segment = raw

        if segment.endswith(
            "[]"
        ):
            segment = segment[
                :-2
            ]

        if not isinstance(
            current,
            Mapping,
        ):
            return (
                False,
                None,
            )

        if segment not in current:
            return (
                False,
                None,
            )

        current = current[
            segment
        ]

    return (
        True,
        current,
    )


def _local_identity(
    item: Mapping[str, Any],
    *,
    index: int,
) -> str:
    # Structural identity hints are local only; no cross-provider equivalence
    # is inferred from them.
    for key in (
        "resolved_resource_id",
        "resource_id",
        "id",
    ):
        value = item.get(
            key
        )

        if value is not None:
            text = str(
                value
            ).strip()

            if text:
                return text

    return (
        "record-"
        + str(
            index
        )
    )
