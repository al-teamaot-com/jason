from __future__ import annotations

from copy import deepcopy

import pytest

from orchestrator.conversation_kernel import _decision_schema
from orchestrator.model_runtime_adapter import (
    openai_structured_output_compatible_schema,
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


def test_ollama_adapter_recursively_rewrites_type_unions_without_mutating_canonical_schema():
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
        "maxLength": 80,
        "anyOf": [
            {"type": "string"},
            {"type": "null"},
        ],
    }
    assert adapted["properties"]["items"]["items"]["properties"]["count"] == {
        "minimum": 0,
        "anyOf": [
            {"type": "integer"},
            {"type": "null"},
        ],
    }


def test_ollama_generation_schema_preserves_constraints_as_hints_without_claiming_enforcement():
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
                "maxLength": 80,
            },
        },
    }

    adapted = ollama_grammar_compatible_schema(canonical)

    assert adapted["required"] == ["mode", "target"]
    assert adapted["properties"]["mode"] == canonical["properties"]["mode"]
    assert adapted["properties"]["target"] == {
        "enum": ["resource-a", "resource-b", None],
        "maxLength": 80,
        "anyOf": [
            {"type": "string"},
            {"type": "null"},
        ],
    }


def test_ollama_adapter_fails_closed_when_union_rewrite_would_collide_with_existing_anyof():
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


def test_ollama_adapter_rejects_empty_and_duplicate_type_unions():
    with pytest.raises(ValueError, match="non-empty types"):
        ollama_grammar_compatible_schema({"type": []})

    with pytest.raises(ValueError, match="duplicate types"):
        ollama_grammar_compatible_schema({"type": ["string", "string"]})


def test_model_runtime_adapter_changes_only_generation_schema_sent_to_backend():
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


def test_conversation_contract_remains_canonical_while_runtime_view_removes_type_unions():
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
    assert adapted_clarification == {
        "maxLength": 2400,
        "anyOf": [
            {"type": "string"},
            {"type": "null"},
        ],
    }
    assert adapted_entity_ref == {
        "enum": ["verified-resource-1", None],
        "anyOf": [
            {"type": "string"},
            {"type": "null"},
        ],
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


def test_no_verified_context_keeps_null_only_entity_ref_in_canonical_contract():
    canonical = _decision_schema(())
    adapted = ollama_grammar_compatible_schema(canonical)

    canonical_entity_ref = canonical["properties"]["information_needs"]["items"][
        "properties"
    ]["target_entity_ref"]
    adapted_entity_ref = adapted["properties"]["information_needs"]["items"][
        "properties"
    ]["target_entity_ref"]

    assert canonical_entity_ref == {
        "type": ["string", "null"],
        "enum": [None],
    }
    assert adapted_entity_ref == {
        "enum": [None],
        "anyOf": [
            {"type": "string"},
            {"type": "null"},
        ],
    }


def test_openai_adapter_removes_unique_items_recursively_without_mutating_canonical():
    from orchestrator.model_runtime_adapter import (
        openai_structured_output_compatible_schema,
    )

    canonical = {
        "type": "object",
        "properties": {
            "requirements": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "entity_refs": {
                            "type": "array",
                            "items": {"type": "string"},
                            "uniqueItems": True,
                            "maxItems": 8,
                        }
                    },
                    "required": ["entity_refs"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["requirements"],
        "additionalProperties": False,
    }

    adapted = openai_structured_output_compatible_schema(canonical)

    entity_refs = (
        adapted["properties"]["requirements"]["items"]["properties"]["entity_refs"]
    )

    assert "uniqueItems" not in entity_refs
    assert entity_refs["maxItems"] == 8

    canonical_entity_refs = (
        canonical["properties"]["requirements"]["items"]["properties"]["entity_refs"]
    )
    assert canonical_entity_refs["uniqueItems"] is True


def test_openai_adapter_preserves_unrelated_schema_structure():
    from orchestrator.model_runtime_adapter import (
        openai_structured_output_compatible_schema,
    )

    canonical = {
        "type": "object",
        "properties": {
            "status": {
                "type": ["string", "null"],
                "enum": ["ok", None],
            },
            "items": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 5,
            },
        },
        "required": ["status", "items"],
        "additionalProperties": False,
    }

    adapted = openai_structured_output_compatible_schema(canonical)

    assert adapted == canonical
    assert adapted is not canonical


def test_openai_adapter_requires_every_closed_object_property_recursively():
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "resource_selector": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "hostname": {"type": "string"},
                    "resource_id": {"type": "string"},
                },
            },
            "resolved": {"type": "boolean"},
        },
    }

    adapted = openai_structured_output_compatible_schema(schema)

    assert adapted["required"] == ["resource_selector", "resolved"]
    resource_selector_schema = adapted["properties"]["resource_selector"]
    assert {"type": "null"} in resource_selector_schema["anyOf"]
    resource_selector_object = next(
        branch
        for branch in resource_selector_schema["anyOf"]
        if branch.get("type") == "object"
    )
    assert resource_selector_object["required"] == [
        "hostname",
        "resource_id",
    ]


def test_openai_optional_closed_properties_are_nullable_then_restored():
    from orchestrator.model_runtime_adapter import (
        ModelRuntimeAdapter,
        openai_structured_output_compatible_schema,
        openai_structured_output_restore_optional_values,
    )

    canonical = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "resource_selector": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "hostname": {"type": "string", "minLength": 1},
                    "resource_id": {"type": "string", "minLength": 1},
                },
            },
            "resolved": {"type": "boolean"},
        },
        "required": ["resource_selector", "resolved"],
    }

    class Client:
        def __init__(self):
            self.schema = None

        def complete(self, **kwargs):
            self.schema = kwargs["schema"]
            return {
                "resource_selector": {
                    "hostname": "DEVICE-12",
                    "resource_id": None,
                },
                "resolved": True,
            }

    client = Client()
    adapter = ModelRuntimeAdapter(
        client=client,
        schema_adapter=openai_structured_output_compatible_schema,
        result_adapter=openai_structured_output_restore_optional_values,
    )

    result = adapter.complete(
        system="system",
        user="user",
        schema=canonical,
    )

    generated_selector = client.schema["properties"]["resource_selector"]
    assert generated_selector["required"] == ["hostname", "resource_id"]
    assert {"type": "null"} in generated_selector["properties"]["resource_id"]["anyOf"]

    assert result == {
        "resource_selector": {"hostname": "DEVICE-12"},
        "resolved": True,
    }
