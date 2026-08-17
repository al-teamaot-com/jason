"""Model-runtime compatibility adapters for bounded structured reasoning.

Jason owns canonical structured contracts. Individual model runtimes may support only a
subset or dialect of JSON Schema for constrained generation. Runtime-specific grammar
quirks belong here, below the Conversation Kernel and outside governance semantics.

Adapters may change only the representation sent to a model runtime. The caller still
validates the returned proposal against Jason's canonical deterministic contract, so a
compatibility transform cannot grant authority or make unsupported output valid.
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
    """Apply backend compatibility without changing Jason's canonical contract."""

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
    """Return an Ollama-grammar-compatible representation of a JSON Schema.

    Ollama grammar generation may reject complex schemas that use a JSON Schema type
    union such as ``{"type": ["string", "null"]}`` even though simple unions work.
    ``anyOf`` with one typed branch per union member is semantically equivalent for the
    bounded schemas Jason supplies and is accepted by the runtime grammar.

    The transform is recursive, non-mutating, and deliberately semantic-free. It does
    not inspect human text, resource kinds, providers, capabilities, facts, or values.
    Existing schema constraints remain siblings of the converted union and therefore
    continue to apply according to JSON Schema semantics.
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
                adapted["anyOf"] = [{"type": item} for item in members]
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
