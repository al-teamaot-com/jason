"""Model-assisted semantic mapping over dynamically discovered governed schemas."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from .open_world_schema import (
    OpenWorldResourceCatalog,
)


class StructuredOpenWorldClient(
    Protocol
):
    def complete(
        self,
        *,
        system: str,
        user: str,
        schema: Mapping[str, Any],
        max_output_tokens: int,
    ):
        ...


@dataclass(frozen=True, slots=True)
class SemanticFieldBinding:
    resource_handle: str
    field_path: str
    semantic_role: str


@dataclass(frozen=True, slots=True)
class OpenWorldSemanticResolution:
    information_request: bool
    bindings: tuple[
        SemanticFieldBinding,
        ...
    ]


@dataclass(frozen=True, slots=True)
class OpenWorldSemanticMapper:
    client: StructuredOpenWorldClient

    def map(
        self,
        *,
        human_text: str,
        catalog: OpenWorldResourceCatalog,
    ) -> OpenWorldSemanticResolution:
        import json

        result = self.client.complete(
            system=_SYSTEM,
            user=json.dumps(
                {
                    "question": human_text,
                    "resources": (
                        catalog.model_context()
                    ),
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            schema=_SCHEMA,
            max_output_tokens=1600,
        )

        if not isinstance(
            result,
            Mapping,
        ):
            raise ValueError(
                "open-world semantic response "
                "must be an object"
            )

        information_request = bool(
            result.get(
                "information_request"
            )
        )

        raw_bindings = result.get(
            "bindings",
            []
        )

        bindings = tuple(
            SemanticFieldBinding(
                resource_handle=str(
                    item["resource_handle"]
                ),
                field_path=str(
                    item["field_path"]
                ),
                semantic_role=str(
                    item["semantic_role"]
                ),
            )
            for item in raw_bindings
        )

        allowed = {
            (
                resource.resource_handle,
                field.path,
            )
            for resource in catalog.resources
            for field in resource.fields
        }

        bindings = tuple(
            binding
            for binding in bindings
            if (
                binding.resource_handle,
                binding.field_path,
            ) in allowed
        )

        if (
            not information_request
            and bindings
        ):
            raise ValueError(
                "non-information resolution cannot "
                "contain field bindings"
            )

        return OpenWorldSemanticResolution(
            information_request=(
                information_request
            ),
            bindings=bindings,
        )


_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "information_request",
        "bindings",
    ],
    "properties": {
        "information_request": {
            "type": "boolean",
        },
        "bindings": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "resource_handle",
                    "field_path",
                    "semantic_role",
                ],
                "properties": {
                    "resource_handle": {
                        "type": "string",
                    },
                    "field_path": {
                        "type": "string",
                    },
                    "semantic_role": {
                        "type": "string",
                    },
                },
            },
        },
    },
}


_SYSTEM = """
You are Jason's open-world semantic schema mapper.

Determine whether the human is requesting operational information.

IMPORTANT:
- Classify the request independently of whether the currently supplied schemas
  already expose a matching field.
- If the human asks for facts, state, inventory, measurements, configuration,
  status, history, relationships, counts, rankings, comparisons, or other
  operational data about managed resources, information_request must be true.
- An empty or incomplete field match does NOT make an operational information
  request into ordinary conversation.
- bindings may be empty when the current catalog does not yet expose a usable
  field; later governed structural discovery may expand the catalog.

For operational information:
- inspect the supplied live resource schemas;
- map concepts in the question to fields actually exposed by those schemas;
- identify resources only by their opaque resource_handle;
- do not infer or name providers, vendors, connectors, APIs, or capabilities;
- do not answer the question;
- do not invent values, fields, resources, or relationships.

Known semantic hints may help but are never required for a discovered field to
be usable.

For ordinary non-operational conversation:
- information_request must be false;
- bindings must be empty.

Return only the structured object required by the schema.
""".strip()
