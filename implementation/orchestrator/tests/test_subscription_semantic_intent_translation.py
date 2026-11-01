from __future__ import annotations

import pytest

from orchestrator.subscription_semantic_intent_translation import (
    SubscriptionSemanticIntentTranslator,
)


class Client:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def complete(self, **kwargs):
        self.calls.append(kwargs)
        return self.result


def test_subscription_semantic_translation_uses_governed_catalog():
    client = Client({
        "resolved": True,
        "requested_concepts": ["lan_ip", "wan_ip"],
        "confidence": 0.92,
    })
    translator = SubscriptionSemanticIntentTranslator(client)
    result = translator.translate(
        text="what is its ip",
        eligible_concepts=("lan_ip", "wan_ip"),
        grounded_selector={"resource_id": "123"},
    )
    assert result is not None
    assert result.requested_concepts == ("lan_ip", "wan_ip")
    assert result.operation == "read"
    assert client.calls[0]["max_output_tokens"] == 256


def test_subscription_semantic_translation_rejects_out_of_catalog_concept():
    translator = SubscriptionSemanticIntentTranslator(Client({
        "resolved": True,
        "requested_concepts": ["unauthorized"],
        "confidence": 1.0,
    }))
    with pytest.raises(PermissionError):
        translator.translate(
            text="x", eligible_concepts=("allowed",), grounded_selector=None
        )


def test_subscription_semantic_translation_allows_unresolved():
    translator = SubscriptionSemanticIntentTranslator(Client({
        "resolved": False,
        "requested_concepts": [],
        "confidence": 0.0,
    }))
    assert translator.translate(
        text="x", eligible_concepts=("allowed",), grounded_selector=None
    ) is None
