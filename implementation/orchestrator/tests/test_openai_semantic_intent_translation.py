import json

import pytest

from orchestrator.openai_semantic_intent_translation import (
    OpenAISemanticIntentTranslator,
)


CONCEPTS = (
    "last logged in user",
    "LAN IP address",
    "WAN IP address",
    "processor model",
    "logical processor count",
    "total memory",
    "open alerts",
    "sites",
)


class Transport:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def request(self, **kwargs):
        self.calls.append(kwargs)
        return self.result


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
        ],
        "usage": {
            "input_tokens": 100,
            "output_tokens": 20,
            "total_tokens": 120,
        },
    }


def adapter(value):
    transport = Transport(
        response(value)
    )

    return (
        OpenAISemanticIntentTranslator(
            api_key="test-secret",
            transport=transport,
            model="test-model",
        ),
        transport,
    )


def test_user_shorthand_returns_one_concept():
    translator, _ = adapter(
        {
            "resolved": True,
            "requested_concepts": [
                "last logged in user"
            ],
            "confidence": 0.99,
        }
    )

    outcome = (
        translator.translate_with_usage(
            text="user on aot-50282?",
            eligible_concepts=CONCEPTS,
            grounded_selector={
                "hostname": "AOT-50282",
            },
        )
    )

    assert outcome.translation is not None
    assert (
        outcome.translation.requested_concepts
        == ("last logged in user",)
    )
    assert outcome.usage.total_tokens == 120


def test_generic_ip_can_require_bounded_pair():
    translator, _ = adapter(
        {
            "resolved": True,
            "requested_concepts": [
                "LAN IP address",
                "WAN IP address",
            ],
            "confidence": 0.99,
        }
    )

    result = translator.translate(
        text="what ip does AOT-50282 have?",
        eligible_concepts=CONCEPTS,
        grounded_selector={
            "hostname": "AOT-50282",
        },
    )

    assert result is not None
    assert result.requested_concepts == (
        "LAN IP address",
        "WAN IP address",
    )


def test_alert_meaning_is_same_with_or_without_grounded_target():
    targeted, _ = adapter(
        {
            "resolved": True,
            "requested_concepts": [
                "open alerts"
            ],
            "confidence": 0.97,
        }
    )

    management, _ = adapter(
        {
            "resolved": True,
            "requested_concepts": [
                "open alerts"
            ],
            "confidence": 0.97,
        }
    )

    targeted_result = targeted.translate(
        text="alerts on AOT-50282?",
        eligible_concepts=CONCEPTS,
        grounded_selector={
            "hostname": "AOT-50282",
        },
    )

    management_result = management.translate(
        text="anything actively alerting?",
        eligible_concepts=CONCEPTS,
    )

    assert targeted_result is not None
    assert management_result is not None

    assert (
        targeted_result.requested_concepts
        == management_result.requested_concepts
        == ("open alerts",)
    )


def test_transport_payload_contains_no_implementation_topology():
    translator, transport = adapter(
        {
            "resolved": True,
            "requested_concepts": [
                "open alerts"
            ],
            "confidence": 0.95,
        }
    )

    translator.translate(
        text="show alerts",
        eligible_concepts=CONCEPTS,
    )

    serialized = json.dumps(
        transport.calls[0]["json"],
        sort_keys=True,
    )

    assert "endpoint.alert.search" not in serialized
    assert "management.alert.search" not in serialized
    assert "datto_rmm" not in serialized
    assert "resource_type" not in serialized
    assert '"scope"' not in serialized
    assert "hostname" not in serialized


def test_provider_cannot_invent_concept():
    translator, _ = adapter(
        {
            "resolved": True,
            "requested_concepts": [
                "invented fact"
            ],
            "confidence": 0.90,
        }
    )

    with pytest.raises(
        PermissionError,
        match="outside governed catalog",
    ):
        translator.translate(
            text="bad response",
            eligible_concepts=CONCEPTS,
        )


def test_unresolved_returns_none():
    translator, _ = adapter(
        {
            "resolved": False,
            "requested_concepts": [],
            "confidence": 0.1,
        }
    )

    assert translator.translate(
        text="something unknown",
        eligible_concepts=CONCEPTS,
    ) is None
