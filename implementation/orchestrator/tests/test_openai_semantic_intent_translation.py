import json

import pytest

from orchestrator.openai_semantic_intent_translation import (
    OpenAISemanticIntentTranslator,
)


CATALOG = {
    "endpoint": (
        "last logged in user",
        "LAN IP address",
        "WAN IP address",
        "operating system",
        "open alerts",
    ),
    "alert": (
        "alerts",
    ),
    "management_site": (
        "sites",
    ),
}


class Transport:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def request(self, **kwargs):
        self.calls.append(kwargs)
        return self.result


def response(value, *, input_tokens=100, output_tokens=20):
    return {
        "output": [
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": json.dumps(value),
                    }
                ],
            }
        ],
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": (
                input_tokens
                + output_tokens
            ),
        },
    }


def translator(value):
    transport = Transport(response(value))
    return (
        OpenAISemanticIntentTranslator(
            api_key="test-secret",
            transport=transport,
            model="test-model",
        ),
        transport,
    )


def test_shorthand_user_request_resolves_to_smallest_fact_set():
    adapter, transport = translator(
        {
            "resolved": True,
            "resource_type": "endpoint",
            "requested_concepts": [
                "last logged in user"
            ],
            "confidence": 0.98,
        }
    )

    outcome = adapter.translate_with_usage(
        text="user on aot-50282?",
        eligible_resources=CATALOG,
        grounded_selectors={
            "endpoint": {
                "hostname": "AOT-50282",
            }
        },
    )

    assert outcome.translation is not None
    assert outcome.translation.resource_type == "endpoint"
    assert (
        outcome.translation.requested_concepts
        == ("last logged in user",)
    )
    assert outcome.translation.resource_selector == {
        "hostname": "AOT-50282",
    }
    assert outcome.usage.total_tokens == 120

    sent = transport.calls[0]
    assert (
        sent["headers"]["Authorization"]
        == "Bearer test-secret"
    )

    schema = (
        sent["json"]["text"]["format"]
    )
    assert schema["type"] == "json_schema"
    assert schema["strict"] is True

    serialized = json.dumps(
        sent["json"],
        sort_keys=True,
    )
    assert "test-secret" not in serialized


def test_generic_ip_can_return_complete_bounded_pair():
    adapter, _ = translator(
        {
            "resolved": True,
            "resource_type": "endpoint",
            "requested_concepts": [
                "LAN IP address",
                "WAN IP address",
            ],
            "confidence": 0.99,
        }
    )

    result = adapter.translate(
        text="what ip does AOT-50282 have?",
        eligible_resources=CATALOG,
        grounded_selectors={
            "endpoint": {
                "hostname": "AOT-50282",
            }
        },
    )

    assert result is not None
    assert result.requested_concepts == (
        "LAN IP address",
        "WAN IP address",
    )


def test_management_wide_alert_read_needs_no_selector():
    adapter, _ = translator(
        {
            "resolved": True,
            "resource_type": "alert",
            "requested_concepts": [
                "alerts",
            ],
            "confidence": 0.96,
        }
    )

    result = adapter.translate(
        text="anything actively alerting right now?",
        eligible_resources=CATALOG,
    )

    assert result is not None
    assert result.resource_type == "alert"
    assert result.resource_selector == {}


def test_unresolved_translation_returns_none():
    adapter, _ = translator(
        {
            "resolved": False,
            "resource_type": "endpoint",
            "requested_concepts": [],
            "confidence": 0.20,
        }
    )

    assert adapter.translate(
        text="something vague",
        eligible_resources=CATALOG,
    ) is None


def test_provider_cannot_return_concept_from_other_resource():
    adapter, _ = translator(
        {
            "resolved": True,
            "resource_type": "alert",
            "requested_concepts": [
                "last logged in user",
            ],
            "confidence": 0.90,
        }
    )

    with pytest.raises(
        PermissionError,
        match="outside governed resource catalog",
    ):
        adapter.translate(
            text="bad provider response",
            eligible_resources=CATALOG,
        )


def test_provider_cannot_invent_resource_type():
    transport = Transport(
        {
            "output_text": json.dumps(
                {
                    "resolved": True,
                    "resource_type": "invented",
                    "requested_concepts": [
                        "alerts"
                    ],
                    "confidence": 0.9,
                }
            )
        }
    )

    adapter = OpenAISemanticIntentTranslator(
        api_key="test-secret",
        transport=transport,
        model="test-model",
    )

    with pytest.raises(
        PermissionError,
        match="resource type outside governed catalog",
    ):
        adapter.translate(
            text="bad provider response",
            eligible_resources=CATALOG,
        )
