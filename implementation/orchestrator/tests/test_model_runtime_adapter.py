from __future__ import annotations

from copy import deepcopy

import pytest

from orchestrator.conversation_kernel import _decision_schema
from orchestrator.model_runtime_adapter import (
    ModelRuntimeAdapter,
    ollama_grammar_compatible_schema,
)


class FakeStructuredClient:
    model = "fake-model"
    base_url = "http://fake-runtime"
    timeout_seconds = 33.0

    def __init__(self):
        self.calls = []

    def complete(self, *, system, user, schema, max_output_tokens=160):
        self.calls.append(
            {
                "system": system,
                "user": user,
                "schema": schema,
                "max_output_tokens": max_output_tokens,
            }
        )
        return {"status": "ok"}


def test_ollama_adapter_recursively_converts_type_unions_without_mutating_canonical_schema():
    canonical = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "label": {
                "type": ["string", "null"],
                "maxLength": 80,
            },
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "count": {
                            "type": ["integer", "null"],
                            "minimum": 0,
                        }
                    },
                },
            },
        },
    }
    original = deepcopy(canonical)

    adapted = ollama_grammar_compatible_schema(canonical)

    assert canonical == original
    assert adapted["properties"]["label"] == {
        "anyOf": [
            {"type": "string", "maxLength": 80},
            {"type": "null"},
        ],
    }
    assert adapted["properties"]["items"]["items"]["properties"]["count"] == {
        "anyOf": [
            {"type": "integer", "minimum": 0},
            {"type": "null"},
        ],
    }


def test_ollama_adapter_moves_closed_enum_values_into_compatible_union_branches():
    canonical = {
        "type": "object",
        "required": ["mode", "target"],
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["read", "review"],
            },
            "target": {
                "type": ["string", "null"],
                "enum": ["resource-a", "resource-b", None],
            },
        },
    }

    adapted = ollama_grammar_compatible_schema(canonical)

    assert adapted["required"] == ["mode", "target"]
    assert adapted["properties"]["mode"] == canonical["properties"]["mode"]
    assert adapted["properties"]["target"] == {
        "anyOf": [
            {
                "type": "string",
                "enum": ["resource-a", "resource-b"],
            },
            {
                "type": "null",
                "enum": [None],
            },
        ]
    }


def test_ollama_adapter_removes_union_branches_that_cannot_satisfy_enum():
    canonical = {
        "type": ["string", "null"],
        "enum": [None],
        "maxLength": 80,
    }

    adapted = ollama_grammar_compatible_schema(canonical)

    assert adapted == {
        "type": "null",
        "enum": [None],
    }


def test_ollama_adapter_moves_type_specific_constraints_only_to_applicable_branch():
    canonical = {
        "type": ["string", "null"],
        "minLength": 1,
        "maxLength": 3,
        "pattern": "^[A-Z]+$",
    }

    adapted = ollama_grammar_compatible_schema(canonical)

    assert adapted == {
        "anyOf": [
            {
                "type": "string",
                "minLength": 1,
                "maxLength": 3,
                "pattern": "^[A-Z]+$",
            },
            {
                "type": "null",
            },
        ]
    }


def test_ollama_adapter_fails_closed_when_union_rewrite_would_collide_with_composition():
    with pytest.raises(ValueError, match="cannot safely adapt"):
        ollama_grammar_compatible_schema(
            {
                "type": ["string", "null"],
                "anyOf": [
                    {"const": "alpha"},
                    {"const": None},
                ],
            }
        )


def test_ollama_adapter_fails_closed_for_unknown_union_sibling_keyword():
    with pytest.raises(ValueError, match="unsupported sibling keyword"):
        ollama_grammar_compatible_schema(
            {
                "type": ["string", "null"],
                "vendorExtension": "unsafe-to-assume",
            }
        )


def test_model_runtime_adapter_changes_only_schema_representation_sent_to_backend():
    inner = FakeStructuredClient()
    runtime = ModelRuntimeAdapter(
        client=inner,
        schema_adapter=ollama_grammar_compatible_schema,
    )
    canonical = {
        "type": "object",
        "properties": {
            "value": {"type": ["string", "null"]},
        },
    }

    result = runtime.complete(
        system="bounded system",
        user="bounded user",
        schema=canonical,
        max_output_tokens=72,
    )

    assert result == {"status": "ok"}
    assert runtime.model == "fake-model"
    assert runtime.base_url == "http://fake-runtime"
    assert runtime.timeout_seconds == 33.0
    assert inner.calls[0]["system"] == "bounded system"
    assert inner.calls[0]["user"] == "bounded user"
    assert inner.calls[0]["max_output_tokens"] == 72
    assert inner.calls[0]["schema"]["properties"]["value"] == {
        "anyOf": [
            {"type": "string"},
            {"type": "null"},
        ]
    }
    assert canonical["properties"]["value"]["type"] == ["string", "null"]


def test_conversation_contract_remains_canonical_while_runtime_view_bounds_known_entity_refs():
    canonical = _decision_schema(("verified-resource-1",))
    adapted = ollama_grammar_compatible_schema(canonical)

    canonical_clarification = canonical["properties"]["clarification_question"]
    adapted_clarification = adapted["properties"]["clarification_question"]
    canonical_entity_ref = canonical["properties"]["information_needs"]["items"][
        "properties"
    ]["target_entity_ref"]
    adapted_entity_ref = adapted["properties"]["information_needs"]["items"][
        "properties"
    ]["target_entity_ref"]

    assert canonical_clarification["type"] == ["string", "null"]
    assert canonical_entity_ref["type"] == ["string", "null"]
    assert adapted_clarification["anyOf"] == [
        {
            "type": "string",
            "maxLength": 2400,
        },
        {"type": "null"},
    ]
    assert adapted_entity_ref == {
        "anyOf": [
            {
                "type": "string",
                "enum": ["verified-resource-1"],
            },
            {
                "type": "null",
                "enum": [None],
            },
        ]
    }

    def type_union_count(value):
        if isinstance(value, dict):
            count = int(
                isinstance(value.get("type"), list)
                and len(value["type"]) > 1
            )
            return count + sum(type_union_count(item) for item in value.values())
        if isinstance(value, list):
            return sum(type_union_count(item) for item in value)
        return 0

    assert type_union_count(canonical) > 0
    assert type_union_count(adapted) == 0


def test_conversation_contract_runtime_view_allows_only_null_entity_ref_without_verified_context():
    canonical = _decision_schema(())
    adapted = ollama_grammar_compatible_schema(canonical)

    adapted_entity_ref = adapted["properties"]["information_needs"]["items"][
        "properties"
    ]["target_entity_ref"]

    assert adapted_entity_ref == {
        "type": "null",
        "enum": [None],
    }
