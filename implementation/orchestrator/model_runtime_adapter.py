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


_STRING_KEYWORDS = {
    "minLength",
    "maxLength",
    "pattern",
    "format",
    "contentEncoding",
    "contentMediaType",
    "contentSchema",
}
_NUMERIC_KEYWORDS = {
    "multipleOf",
    "maximum",
    "exclusiveMaximum",
    "minimum",
    "exclusiveMinimum",
}
_ARRAY_KEYWORDS = {
    "prefixItems",
    "items",
    "contains",
    "minContains",
    "maxContains",
    "minItems",
    "maxItems",
    "uniqueItems",
    "unevaluatedItems",
}
_OBJECT_KEYWORDS = {
    "properties",
    "patternProperties",
    "additionalProperties",
    "propertyNames",
    "required",
    "dependentRequired",
    "dependentSchemas",
    "minProperties",
    "maxProperties",
    "unevaluatedProperties",
}
_COMMON_KEYWORDS = {
    "title",
    "description",
    "default",
    "examples",
    "deprecated",
    "readOnly",
    "writeOnly",
}
_UNSUPPORTED_UNION_SIBLINGS = {
    "$ref",
    "$dynamicRef",
    "allOf",
    "anyOf",
    "oneOf",
    "not",
    "if",
    "then",
    "else",
}


def ollama_grammar_compatible_schema(schema: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return an Ollama-grammar-compatible representation of a JSON Schema.

    Ollama grammar generation may reject complex schemas that use a JSON Schema type
    union such as ``{"type": ["string", "null"]}``. The runtime also does not reliably
    enforce sibling constraints placed beside a generated ``anyOf``. Jason therefore
    expands each union member into a self-contained branch and moves only constraints
    applicable to that JSON type into that branch.

    For value constraints such as ``enum`` and ``const``, impossible branches are
    removed rather than broadening the canonical contract. For example,
    ``{"type": ["string", "null"], "enum": [null]}`` becomes a single null branch,
    while an enum containing a verified string reference and null becomes one bounded
    string branch plus one bounded null branch.

    The transform is recursive, non-mutating, and deliberately semantic-free. It does
    not inspect human text, resource kinds, providers, capabilities, facts, or values.
    Jason still validates the returned proposal against the untouched canonical schema.
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
            if any(key in value for key in _UNSUPPORTED_UNION_SIBLINGS):
                raise ValueError(
                    "model schema cannot safely adapt type union with composition/reference sibling"
                )

            branches = [
                branch
                for member in members
                if (branch := _union_branch(value, member)) is not None
            ]
            if not branches:
                raise ValueError("model schema type union has no satisfiable branch")
            if len(branches) == 1:
                return branches[0]
            return {"anyOf": branches}

        return {
            str(key): _adapt_schema_value(item)
            for key, item in value.items()
        }

    if isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        return [_adapt_schema_value(item) for item in value]

    return value


def _union_branch(schema: Mapping[str, Any], member: str) -> dict[str, Any] | None:
    if member not in {"null", "boolean", "object", "array", "number", "integer", "string"}:
        raise ValueError(f"model schema union contains unsupported JSON type: {member}")

    enum_values = schema.get("enum")
    if enum_values is not None:
        if not isinstance(enum_values, Sequence) or isinstance(
            enum_values, (str, bytes, bytearray)
        ):
            raise ValueError("model schema enum must be an array")
        compatible_enum = [
            item
            for item in enum_values
            if _json_value_matches_type(item, member)
        ]
        if not compatible_enum:
            return None
    else:
        compatible_enum = None

    has_const = "const" in schema
    const_value = schema.get("const")
    if has_const and not _json_value_matches_type(const_value, member):
        return None

    branch: dict[str, Any] = {"type": member}
    if compatible_enum is not None:
        branch["enum"] = _adapt_schema_value(compatible_enum)
    if has_const:
        branch["const"] = _adapt_schema_value(const_value)

    for key, item in schema.items():
        if key in {"type", "enum", "const"}:
            continue
        if key in _UNSUPPORTED_UNION_SIBLINGS:
            raise ValueError(
                "model schema cannot safely adapt type union with composition/reference sibling"
            )
        if key in _COMMON_KEYWORDS or _keyword_applies_to_type(key, member):
            branch[str(key)] = _adapt_schema_value(item)
            continue
        if _is_known_type_specific_keyword(key):
            continue
        raise ValueError(f"model schema union contains unsupported sibling keyword: {key}")

    return branch


def _keyword_applies_to_type(key: str, member: str) -> bool:
    if key in _STRING_KEYWORDS:
        return member == "string"
    if key in _NUMERIC_KEYWORDS:
        return member in {"number", "integer"}
    if key in _ARRAY_KEYWORDS:
        return member == "array"
    if key in _OBJECT_KEYWORDS:
        return member == "object"
    return False


def _is_known_type_specific_keyword(key: str) -> bool:
    return key in (
        _STRING_KEYWORDS
        | _NUMERIC_KEYWORDS
        | _ARRAY_KEYWORDS
        | _OBJECT_KEYWORDS
    )


def _json_value_matches_type(value: Any, member: str) -> bool:
    if member == "null":
        return value is None
    if member == "boolean":
        return isinstance(value, bool)
    if member == "object":
        return isinstance(value, Mapping)
    if member == "array":
        return isinstance(value, Sequence) and not isinstance(
            value, (str, bytes, bytearray)
        )
    if member == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if member == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if member == "string":
        return isinstance(value, str)
    return False
