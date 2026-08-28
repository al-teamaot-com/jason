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


@dataclass(frozen=True, slots=True)
class ModelRuntimeAdapter:
    """Apply backend generation compatibility without changing Jason's contract."""

    client: StructuredReasoner
    schema_adapter: SchemaAdapter

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
        return self.client.complete(
            system=system,
            user=user,
            schema=adapted,
            max_output_tokens=max_output_tokens,
        )


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
