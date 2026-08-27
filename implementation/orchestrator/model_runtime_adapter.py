"""Model-runtime compatibility adapters for bounded structured reasoning.

Jason owns canonical structured contracts. Individual model runtimes may support only a
subset or dialect of JSON Schema for constrained generation. Runtime-specific grammar
quirks belong here, below the Conversation Kernel and outside governance semantics.

The runtime schema is a generation aid, never an authorization or validation boundary.
Adapters may make a canonical schema easier for a backend grammar to consume, but Jason
always validates returned model output against the untouched canonical contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol, Sequence


class StructuredReasoner(Protocol):
    def complete(
        self,
        *,
        system: str,
        user: str,
        schema: Mapping[str, Any],
        max_output_tokens: int = 160,
    ) -> Mapping[str, Any]: ...


SchemaAdapter = Callable[[Mapping[str, Any]], Mapping[str, Any]]
ResultAdapter = Callable[
    [Mapping[str, Any], Mapping[str, Any]],
    Mapping[str, Any],
]


@dataclass(frozen=True, slots=True)
class ModelRuntimeAdapter:
    """Apply backend generation compatibility without changing Jason's contract."""

    client: StructuredReasoner
    schema_adapter: SchemaAdapter
    result_adapter: ResultAdapter | None = None

    @property
    def model(self) -> str:
        return str(getattr(self.client, "model", ""))

    @property
    def base_url(self) -> str:
        return str(getattr(self.client, "base_url", ""))

    @property
    def timeout_seconds(self) -> float:
        return float(getattr(self.client, "timeout_seconds", 0.0))

    def complete(
        self,
        *,
        system: str,
        user: str,
        schema: Mapping[str, Any],
        max_output_tokens: int = 160,
    ) -> Mapping[str, Any]:
        adapted = self.schema_adapter(schema)
        result = self.client.complete(
            system=system,
            user=user,
            schema=adapted,
            max_output_tokens=max_output_tokens,
        )
        if self.result_adapter is None:
            return result
        return self.result_adapter(result, schema)



def openai_structured_output_compatible_schema(
    schema: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Return an OpenAI Structured Outputs generation view of Jason's schema.

    Jason's canonical JSON Schema remains unchanged and continues to be the
    deterministic validation authority. This adapter removes only generation-time
    constraints known to be unsupported by OpenAI's Structured Outputs schema
    compiler.

    ``uniqueItems`` is intentionally omitted from the generation view. Jason's
    canonical validator still enforces uniqueness after model output is returned.

    The transformation is recursive, non-mutating, and provider-compatibility-only.
    It does not inspect or change human text, entity identifiers, capabilities,
    providers, facts, permissions, or execution semantics.
    """

    adapted = _adapt_openai_schema_value(schema)
    if not isinstance(adapted, Mapping):
        raise ValueError("adapted OpenAI schema must remain an object")
    return dict(adapted)


def _adapt_openai_schema_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        adapted = {
            str(key): _adapt_openai_schema_value(item)
            for key, item in value.items()
            if key != "uniqueItems"
        }

        properties = adapted.get("properties")
        canonical_properties = value.get("properties")
        if (
            adapted.get("type") == "object"
            and adapted.get("additionalProperties") is False
            and isinstance(properties, Mapping)
            and isinstance(canonical_properties, Mapping)
        ):
            raw_required = value.get("required", ())
            canonical_required = {
                str(item)
                for item in raw_required
                if isinstance(item, str)
            } if isinstance(raw_required, Sequence) and not isinstance(
                raw_required, (str, bytes, bytearray)
            ) else set()

            mutable_properties = dict(properties)
            for key, property_schema in tuple(mutable_properties.items()):
                canonical_property = canonical_properties.get(key)
                if (
                    key not in canonical_required
                    and isinstance(canonical_property, Mapping)
                    and not _schema_allows_null(canonical_property)
                ):
                    mutable_properties[key] = {
                        "anyOf": [
                            property_schema,
                            {"type": "null"},
                        ]
                    }

            adapted["properties"] = mutable_properties
            adapted["required"] = [str(key) for key in mutable_properties]

        return adapted

    if isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        return [_adapt_openai_schema_value(item) for item in value]

    return value


def _schema_allows_null(schema: Mapping[str, Any]) -> bool:
    raw_type = schema.get("type")
    if raw_type == "null":
        return True
    if isinstance(raw_type, Sequence) and not isinstance(
        raw_type, (str, bytes, bytearray)
    ):
        return "null" in raw_type

    raw_enum = schema.get("enum")
    if isinstance(raw_enum, Sequence) and not isinstance(
        raw_enum, (str, bytes, bytearray)
    ) and None in raw_enum:
        return True

    if "const" in schema and schema.get("const") is None:
        return True

    for keyword in ("anyOf", "oneOf"):
        branches = schema.get(keyword)
        if isinstance(branches, Sequence) and not isinstance(
            branches, (str, bytes, bytearray)
        ):
            if any(
                isinstance(branch, Mapping) and _schema_allows_null(branch)
                for branch in branches
            ):
                return True

    # A schema with no explicit type/value constraint already permits null.
    return raw_type is None and not any(
        keyword in schema for keyword in ("enum", "const", "anyOf", "oneOf")
    )


def openai_structured_output_restore_optional_values(
    result: Mapping[str, Any],
    canonical_schema: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Remove only null values introduced for OpenAI optional-field compatibility."""

    restored = _restore_openai_optional_values(result, canonical_schema)
    if not isinstance(restored, Mapping):
        raise ValueError("restored OpenAI structured output must remain an object")
    return dict(restored)


def _restore_openai_optional_values(value: Any, schema: Any) -> Any:
    if isinstance(value, Mapping) and isinstance(schema, Mapping):
        properties = schema.get("properties")
        raw_required = schema.get("required", ())
        required = {
            str(item)
            for item in raw_required
            if isinstance(item, str)
        } if isinstance(raw_required, Sequence) and not isinstance(
            raw_required, (str, bytes, bytearray)
        ) else set()

        restored: dict[str, Any] = {}
        for raw_key, item in value.items():
            key = str(raw_key)
            property_schema = (
                properties.get(key)
                if isinstance(properties, Mapping)
                else None
            )

            if isinstance(property_schema, Mapping):
                if (
                    item is None
                    and key not in required
                    and not _schema_allows_null(property_schema)
                ):
                    continue
                restored[key] = _restore_openai_optional_values(
                    item,
                    property_schema,
                )
            else:
                # Preserve unknown output so Jason's canonical validation can reject it.
                restored[key] = item

        return restored

    if (
        isinstance(value, Sequence)
        and not isinstance(value, (str, bytes, bytearray))
        and isinstance(schema, Mapping)
    ):
        item_schema = schema.get("items")
        if isinstance(item_schema, Mapping):
            return [
                _restore_openai_optional_values(item, item_schema)
                for item in value
            ]

    return value


def ollama_grammar_compatible_schema(schema: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return a conservative Ollama generation view of a canonical JSON Schema.

    Ollama 0.32.x can reject complex schemas that use a JSON Schema type union such as
    ``{"type": ["string", "null"]}``, while accepting the equivalent structural
    ``anyOf`` form. At the same time, its grammar generator does not consistently apply
    sibling constraints such as ``enum`` or ``maxLength`` when they sit beside a generated
    ``anyOf``, and moving those constraints into every branch can make the full schema
    grammar fail to compile.

    Jason therefore does not attempt to transpile every JSON Schema validation semantic
    into an Ollama grammar. This adapter performs only the minimum representation rewrite
    needed for bounded structured generation: type arrays become type-only ``anyOf``
    branches while the original sibling constraints remain present as non-authoritative
    generation hints. The deterministic Jason validator remains the sole authority for
    exact enums, grounding, lengths, relationships, permissions, and outcome invariants.

    This is intentionally recursive, non-mutating, and semantic-free. It never inspects
    human text, resource kinds, providers, capabilities, facts, or values.
    """

    adapted = _adapt_schema_value(schema)
    if not isinstance(adapted, Mapping):
        raise ValueError("adapted model schema must remain an object")
    return dict(adapted)


def _adapt_schema_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        raw_type = value.get("type")
        is_type_sequence = isinstance(raw_type, Sequence) and not isinstance(
            raw_type, (str, bytes, bytearray)
        )

        if is_type_sequence:
            members = tuple(str(item).strip() for item in raw_type)
            if not members or any(not item for item in members):
                raise ValueError("model schema type union must contain non-empty types")
            if len(set(members)) != len(members):
                raise ValueError("model schema type union contains duplicate types")
            if "anyOf" in value:
                raise ValueError(
                    "model schema cannot safely adapt both type union and existing anyOf"
                )

            adapted = {
                str(key): _adapt_schema_value(item)
                for key, item in value.items()
                if key != "type"
            }

            if len(members) == 1:
                adapted["type"] = members[0]
            else:
                adapted["anyOf"] = [{"type": member} for member in members]
            return adapted

        return {
            str(key): _adapt_schema_value(item)
            for key, item in value.items()
        }

    if isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        return [_adapt_schema_value(item) for item in value]

    return value
