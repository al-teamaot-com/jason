from orchestrator.model_runtime_adapter import (
    ollama_grammar_compatible_schema,
)


def test_ollama_generation_schema_omits_max_length_recursively():
    canonical = {
        "type": "object",
        "additionalProperties": False,
        "required": ["plain", "nullable", "items"],
        "properties": {
            "plain": {
                "type": "string",
                "maxLength": 12,
                "enum": ["alpha", "beta"],
            },
            "nullable": {
                "type": ["string", "null"],
                "maxLength": 20,
            },
            "nested": {
                "type": "object",
                "properties": {
                    "label": {
                        "type": "string",
                        "maxLength": 8,
                    },
                },
            },
            "items": {
                "type": "array",
                "maxItems": 4,
                "uniqueItems": True,
                "items": {
                    "type": "string",
                    "maxLength": 6,
                },
            },
        },
    }

    adapted = ollama_grammar_compatible_schema(
        canonical
    )

    assert "maxLength" not in adapted["properties"]["plain"]
    assert "maxLength" not in adapted["properties"]["nullable"]
    assert (
        "maxLength"
        not in adapted["properties"]["nested"]["properties"]["label"]
    )
    assert (
        "maxLength"
        not in adapted["properties"]["items"]["items"]
    )

    assert adapted["properties"]["plain"]["enum"] == [
        "alpha",
        "beta",
    ]
    assert adapted["properties"]["items"]["maxItems"] == 4
    assert adapted["properties"]["items"]["uniqueItems"] is True
    assert adapted["additionalProperties"] is False

    assert adapted["properties"]["nullable"]["anyOf"] == [
        {"type": "string"},
        {"type": "null"},
    ]

    # The canonical Jason contract remains authoritative and must not
    # be mutated merely to satisfy an Ollama generation grammar.
    assert canonical["properties"]["plain"]["maxLength"] == 12
    assert canonical["properties"]["nullable"]["maxLength"] == 20
    assert (
        canonical["properties"]["nested"]
        ["properties"]["label"]["maxLength"]
        == 8
    )
    assert (
        canonical["properties"]["items"]
        ["items"]["maxLength"]
        == 6
    )
