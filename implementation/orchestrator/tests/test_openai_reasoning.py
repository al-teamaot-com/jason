from __future__ import annotations

import json

import pytest

from orchestrator.openai_reasoning import OpenAIStructuredJsonClient


class Transport:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def request(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def response(value):
    return {
        "output": [
            {
                "content": [
                    {
                        "type": "output_text",
                        "text": json.dumps(value),
                    }
                ]
            }
        ]
    }


def test_openai_structured_client_sends_untouched_canonical_schema_with_strict_output_and_no_storage():
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "outcome": {
                "type": "string",
                "enum": ["information", "conversation"],
            },
            "label": {
                "type": ["string", "null"],
            },
        },
        "required": ["outcome", "label"],
    }
    transport = Transport(
        response(
            {
                "outcome": "information",
                "label": None,
            }
        )
    )
    client = OpenAIStructuredJsonClient(
        api_key="super-secret-test-key",
        transport=transport,
        model="quality-model",
        timeout_seconds=45,
    )

    result = client.complete(
        system="bounded system",
        user="bounded user",
        schema=schema,
        max_output_tokens=128,
    )

    assert result == {
        "outcome": "information",
        "label": None,
    }
    assert len(transport.calls) == 1
    call = transport.calls[0]
    assert call["method"] == "POST"
    assert call["url"] == "https://api.openai.com/v1/responses"
    assert call["timeout_seconds"] == 45
    assert call["headers"]["Authorization"] == "Bearer super-secret-test-key"
    assert call["json"]["model"] == "quality-model"
    assert call["json"]["instructions"] == "bounded system"
    assert call["json"]["input"] == "bounded user"
    assert call["json"]["store"] is False
    assert call["json"]["max_output_tokens"] == 128
    format_contract = call["json"]["text"]["format"]
    assert format_contract["type"] == "json_schema"
    assert format_contract["strict"] is True
    assert format_contract["schema"] == schema
    assert format_contract["schema"] is not schema
    assert "tools" not in call["json"]


def test_openai_structured_client_api_key_is_not_exposed_by_repr():
    client = OpenAIStructuredJsonClient(
        api_key="super-secret-test-key",
        transport=Transport(response({"ok": True})),
        model="quality-model",
    )

    rendered = repr(client)

    assert "super-secret-test-key" not in rendered
    assert "api_key=" not in rendered


def test_openai_structured_client_accepts_top_level_output_text():
    client = OpenAIStructuredJsonClient(
        api_key="test-key",
        transport=Transport({"output_text": '{"status":"ok"}'}),
        model="quality-model",
    )

    result = client.complete(
        system="system",
        user="user",
        schema={
            "type": "object",
            "properties": {"status": {"type": "string"}},
            "required": ["status"],
        },
    )

    assert result == {"status": "ok"}


def test_openai_structured_client_rejects_missing_or_malformed_structured_output():
    missing = OpenAIStructuredJsonClient(
        api_key="test-key",
        transport=Transport({"output": []}),
        model="quality-model",
    )
    malformed = OpenAIStructuredJsonClient(
        api_key="test-key",
        transport=Transport({"output_text": "not-json"}),
        model="quality-model",
    )

    schema = {
        "type": "object",
        "properties": {"status": {"type": "string"}},
        "required": ["status"],
    }

    with pytest.raises(ValueError, match="did not contain structured output"):
        missing.complete(system="system", user="user", schema=schema)

    with pytest.raises(ValueError, match="not valid JSON"):
        malformed.complete(system="system", user="user", schema=schema)


def test_openai_structured_client_validates_local_configuration_before_network_use():
    transport = Transport(response({"status": "ok"}))

    with pytest.raises(ValueError, match="API key"):
        OpenAIStructuredJsonClient(
            api_key=" ",
            transport=transport,
            model="quality-model",
        )

    with pytest.raises(ValueError, match="model"):
        OpenAIStructuredJsonClient(
            api_key="key",
            transport=transport,
            model=" ",
        )

    client = OpenAIStructuredJsonClient(
        api_key="key",
        transport=transport,
        model="quality-model",
    )

    with pytest.raises(ValueError, match="output budget"):
        client.complete(
            system="system",
            user="user",
            schema={"type": "object"},
            max_output_tokens=8,
        )

    assert transport.calls == []
