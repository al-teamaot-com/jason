from __future__ import annotations

import json
from decimal import Decimal

import pytest

from kernel.execution_policy import (
    CostEstimator,
    ExecutionPolicyEngine,
    ExecutionMode,
    InMemoryPricingRegistry,
    PriceConfidence,
    PricingEntry,
)
from orchestrator.governed_hosted_reasoning import (
    GovernedHostedReasoningClient,
    HostedReasoningPolicyDenied,
)
from orchestrator.hosted_reasoning_egress import (
    HostedReasoningEgressClassifier,
)


class RecordingClient:
    model = "gpt-5.4-nano"

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
        return {"ok": True}


def policy():
    pricing = InMemoryPricingRegistry(
        [
            PricingEntry(
                provider_id="openai",
                model_id="gpt-5.4-nano",
                execution_mode=ExecutionMode.HOSTED_AI,
                input_cost_per_million_tokens=Decimal("0.20"),
                output_cost_per_million_tokens=Decimal("1.25"),
                request_cost=Decimal("0"),
                pricing_version="openai-gpt-5.4-nano-2026-08",
                confidence=PriceConfidence.HIGH,
            )
        ]
    )
    return ExecutionPolicyEngine(
        cost_estimator=CostEstimator(pricing)
    )


def payload(message):
    return json.dumps(
        {
            "message": message,
            "context": {
                "conversation_id": "conv-sensitive-test",
                "organization_id": "aot",
                "active_topic": None,
                "active_entity_refs": {},
                "active_entities": [],
                "entities": [],
                "recent_resolutions": [],
            },
        }
    )


def governed(recording):
    return GovernedHostedReasoningClient(
        client=recording,
        policy=policy(),
        provider_id="openai",
        model_id="gpt-5.4-nano",
        classifier=HostedReasoningEgressClassifier(),
    )


def test_normal_question_reaches_provider():
    provider = RecordingClient()

    result = governed(provider).complete(
        system="system",
        user=payload("How much RAM does AOT-50282 have?"),
        schema={"type": "object"},
        max_output_tokens=100,
    )

    assert result == {"ok": True}
    assert len(provider.calls) == 1


def test_sensitive_question_never_reaches_provider():
    provider = RecordingClient()

    with pytest.raises(HostedReasoningPolicyDenied):
        governed(provider).complete(
            system="system",
            user=payload(
                "What is the administrator password for AOT-50282?"
            ),
            schema={"type": "object"},
            max_output_tokens=100,
        )

    assert provider.calls == []


def test_minimum_context_removes_internal_runtime_scope():
    provider = RecordingClient()

    governed(provider).complete(
        system="system",
        user=payload("What CPU does AOT-50282 have?"),
        schema={"type": "object"},
        max_output_tokens=100,
    )

    sent = json.loads(provider.calls[0]["user"])

    assert "conversation_id" not in sent["context"]
    assert "organization_id" not in sent["context"]
    assert sent["message"] == "What CPU does AOT-50282 have?"


def test_missing_organization_fails_closed_before_provider():
    provider = RecordingClient()

    raw = json.dumps(
        {
            "message": "What CPU does NODE-1 have?",
            "context": {},
        }
    )

    with pytest.raises(HostedReasoningPolicyDenied):
        governed(provider).complete(
            system="system",
            user=raw,
            schema={"type": "object"},
            max_output_tokens=100,
        )

    assert provider.calls == []
