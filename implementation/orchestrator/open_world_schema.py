"""Provider-neutral open-world resource schema discovery.

This layer describes what governed resources currently expose without requiring
Jason developers to predeclare every possible semantic fact.

It does not execute providers directly and does not grant authority.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any, Iterable, Mapping, Sequence


class OpenWorldSchemaError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class DiscoveredField:
    name: str
    path: str
    value_type: str | None = None
    description: str | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError(
                "discovered field name is required"
            )
        if not self.path.strip():
            raise ValueError(
                "discovered field path is required"
            )


@dataclass(frozen=True, slots=True)
class DiscoveredResourceSchema:
    provider_id: str
    capability_name: str
    resource_type: str
    operation: str
    collection_supported: bool
    selector_keys: tuple[str, ...]
    fields: tuple[DiscoveredField, ...]
    selector_source_policy: tuple[
        tuple[str, str],
        ...
    ] = ()

    @property
    def resource_handle(self) -> str:
        raw = "|".join(
            (
                self.provider_id,
                self.capability_name,
                self.resource_type,
                self.operation,
            )
        ).encode("utf-8")

        return (
            "resource_"
            + hashlib.sha256(
                raw
            ).hexdigest()[:20]
        )

    def __post_init__(self) -> None:
        if not self.provider_id.strip():
            raise ValueError(
                "provider_id is required"
            )
        if not self.capability_name.strip():
            raise ValueError(
                "capability_name is required"
            )
        if not self.resource_type.strip():
            raise ValueError(
                "resource_type is required"
            )
        if self.operation not in {
            "read",
            "search",
        }:
            raise ValueError(
                "unsupported discovered operation"
            )


@dataclass(frozen=True, slots=True)
class OpenWorldResourceCatalog:
    resources: tuple[
        DiscoveredResourceSchema,
        ...
    ]

    def model_context(self) -> Mapping[str, Any]:
        return {
            "resources": [
                {
                    "resource_handle": (
                        item.resource_handle
                    ),
                    "resource_type": item.resource_type,
                    "operation": item.operation,
                    "collection_supported": (
                        item.collection_supported
                    ),
                    "selector_keys": list(
                        item.selector_keys
                    ),
                    "selector_source_policy": {
                        key: policy
                        for key, policy
                        in item.selector_source_policy
                    },
                    "fields": [
                        {
                            "name": field.name,
                            "path": field.path,
                            "value_type": (
                                field.value_type
                            ),
                            "description": (
                                field.description
                            ),
                        }
                        for field in item.fields
                    ],
                }
                for item in self.resources
            ]
        }


def flatten_schema_fields(
    value: Any,
    *,
    prefix: str = "",
    max_depth: int = 8,
    max_fields: int = 1000,
) -> tuple[DiscoveredField, ...]:
    """Flatten structural schema/sample data into provider-neutral field paths.

    This is generic structural discovery. It contains no domain field names.
    """

    output: list[
        DiscoveredField
    ] = []

    def add(
        name: str,
        path: str,
        value_type: str | None,
    ) -> None:
        if len(output) >= max_fields:
            return

        output.append(
            DiscoveredField(
                name=name,
                path=path,
                value_type=value_type,
            )
        )

    def walk(
        item: Any,
        path: str,
        depth: int,
    ) -> None:
        if depth > max_depth:
            return

        if isinstance(
            item,
            Mapping,
        ):
            for key, child in item.items():
                key = str(key)
                child_path = (
                    f"{path}.{key}"
                    if path
                    else key
                )

                if isinstance(
                    child,
                    Mapping,
                ):
                    walk(
                        child,
                        child_path,
                        depth + 1,
                    )
                elif isinstance(
                    child,
                    Sequence,
                ) and not isinstance(
                    child,
                    (str, bytes, bytearray),
                ):
                    add(
                        key,
                        child_path,
                        "array",
                    )

                    for sample in child[:1]:
                        walk(
                            sample,
                            child_path + "[]",
                            depth + 1,
                        )
                else:
                    add(
                        key,
                        child_path,
                        infer_value_type(
                            child
                        ),
                    )

            return

        if isinstance(
            item,
            Sequence,
        ) and not isinstance(
            item,
            (str, bytes, bytearray),
        ):
            for sample in item[:1]:
                walk(
                    sample,
                    path + "[]",
                    depth + 1,
                )

    walk(
        value,
        prefix,
        0,
    )

    unique = {}

    for field in output:
        unique.setdefault(
            field.path,
            field,
        )

    return tuple(
        unique.values()
    )


def infer_value_type(
    value: Any,
) -> str | None:
    if value is None:
        return None
    if isinstance(
        value,
        bool,
    ):
        return "boolean"
    if isinstance(
        value,
        int,
    ) and not isinstance(
        value,
        bool,
    ):
        return "integer"
    if isinstance(
        value,
        float,
    ):
        return "number"
    if isinstance(
        value,
        str,
    ):
        return "string"
    if isinstance(
        value,
        Mapping,
    ):
        return "object"
    if isinstance(
        value,
        Sequence,
    ) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        return "array"
    return None
