"""Governed structural introspection for open-world provider resources.

A schema probe:
- executes through the normal governed ConversationIntent boundary;
- never invokes a connector directly;
- requires observe-only read/search authority;
- examines structure, not operational values;
- returns field paths/types only.

The resulting schema is suitable for semantic planning without requiring every
possible fact to have been predeclared by Jason developers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence

from .open_world_schema import (
    DiscoveredField,
    flatten_schema_fields,
)
from .query_source_discovery import (
    QuerySourceContribution,
)
from .teams_conversation_flow import (
    ConversationIntent,
)


class GovernedSchemaProbeError(
    RuntimeError
):
    pass


class GovernedSchemaProbeExecutor(
    Protocol
):
    def execute(
        self,
        intent: ConversationIntent,
    ):
        ...


@dataclass(frozen=True, slots=True)
class GovernedSchemaProbeResult:
    provider_id: str
    capability_name: str
    resource_type: str
    fields: tuple[
        DiscoveredField,
        ...
    ]


@dataclass(frozen=True, slots=True)
class GovernedSchemaProbe:
    max_records: int = 3
    max_fields: int = 1000
    max_depth: int = 8

    def probe(
        self,
        *,
        contribution: QuerySourceContribution,
        executor: GovernedSchemaProbeExecutor,
        selector_reference: str | None = None,
    ) -> GovernedSchemaProbeResult:
        if (
            contribution.permission_mode
            != "observe"
        ):
            raise GovernedSchemaProbeError(
                "schema probing requires observe-only authority"
            )

        if contribution.operation not in {
            "read",
            "search",
        }:
            raise GovernedSchemaProbeError(
                "schema probing requires read/search capability"
            )

        # Structural discovery uses the provider's ordinary governed
        # read/search contract. Providers do not need to implement a special
        # Jason-specific schema-probe argument or workflow.
        arguments: dict[
            str,
            Any,
        ] = {}

        selector = (
            selector_reference
            or ""
        ).strip()

        if contribution.selector_required:
            if not selector:
                raise GovernedSchemaProbeError(
                    "selector-required schema probe "
                    "requires a grounded reference"
                )

            arguments[
                "selector"
            ] = selector

        elif selector:
            arguments[
                "selector"
            ] = selector

        intent = ConversationIntent(
            capability_name=(
                contribution.capability_name
            ),
            arguments=arguments,
            execution_mode="deterministic",
            permission_mode="observe",
            risk=contribution.risk,
        )

        result = executor.execute(
            intent
        )

        data = self._successful_data(
            result=result,
            contribution=contribution,
        )

        samples = self._samples(
            data
        )

        fields: dict[
            str,
            DiscoveredField,
        ] = {}

        for sample in samples:
            for field in flatten_schema_fields(
                sample,
                max_depth=self.max_depth,
                max_fields=self.max_fields,
            ):
                fields.setdefault(
                    field.path,
                    field,
                )

                if (
                    len(fields)
                    >= self.max_fields
                ):
                    break

            if (
                len(fields)
                >= self.max_fields
            ):
                break

        if not fields:
            raise GovernedSchemaProbeError(
                "governed schema probe returned no discoverable fields"
            )

        return GovernedSchemaProbeResult(
            provider_id=(
                contribution.provider_id
            ),
            capability_name=(
                contribution.capability_name
            ),
            resource_type=(
                contribution.resource_type
            ),
            fields=tuple(
                fields.values()
            ),
        )

    def _successful_data(
        self,
        *,
        result,
        contribution: QuerySourceContribution,
    ) -> Any:
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
            raise GovernedSchemaProbeError(
                "schema probe orchestration did not succeed"
            )

        provider_id = str(
            getattr(
                result,
                "provider_id",
                "",
            )
        ).strip()

        capability_name = str(
            getattr(
                result,
                "capability_name",
                "",
            )
        ).strip()

        if (
            provider_id
            and provider_id
            != contribution.provider_id
        ):
            raise GovernedSchemaProbeError(
                "schema probe provider provenance mismatch"
            )

        if (
            capability_name
            and capability_name
            != contribution.capability_name
        ):
            raise GovernedSchemaProbeError(
                "schema probe capability provenance mismatch"
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
            raise GovernedSchemaProbeError(
                "schema probe result lacks structured output"
            )

        if "data" not in output:
            raise GovernedSchemaProbeError(
                "schema probe result lacks data"
            )

        return output[
            "data"
        ]

    def _samples(
        self,
        data: Any,
    ) -> tuple[
        Any,
        ...
    ]:
        if isinstance(
            data,
            Mapping,
        ):
            matches = data.get(
                "resource_matches"
            )

            if isinstance(
                matches,
                Sequence,
            ) and not isinstance(
                matches,
                (
                    str,
                    bytes,
                    bytearray,
                ),
            ):
                return tuple(
                    matches[
                        : self.max_records
                    ]
                )

            items = data.get(
                "items"
            )

            if isinstance(
                items,
                Sequence,
            ) and not isinstance(
                items,
                (
                    str,
                    bytes,
                    bytearray,
                ),
            ):
                return tuple(
                    items[
                        : self.max_records
                    ]
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
                data[
                    : self.max_records
                ]
            )

        raise GovernedSchemaProbeError(
            "schema probe data is not structurally inspectable"
        )
