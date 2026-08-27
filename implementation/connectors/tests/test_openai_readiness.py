from __future__ import annotations

import urllib.error

import pytest

from connectors.openai.readiness import (
    OpenAIProviderFailure,
    OpenAIResponsesReadinessProbe,
    normalize_openai_failure,
)
from orchestrator.provider_capability_readiness import (
    ReadinessReason,
    ReadinessState,
    classify_readiness,
)


def probe():
    return OpenAIResponsesReadinessProbe(
        api_key="test-key",
        model="test-model",
    )


@pytest.mark.parametrize(
    (
        "status",
        "error_type",
        "error_code",
        "expected",
    ),
    [
        (
            429,
            "insufficient_quota",
            "credit_balance_exhausted",
            ReadinessReason.QUOTA_EXHAUSTED,
        ),
        (
            429,
            None,
            "credit_balance_exhausted",
            ReadinessReason.QUOTA_EXHAUSTED,
        ),
        (
            401,
            "invalid_request_error",
            "invalid_api_key",
            ReadinessReason.AUTHENTICATION_FAILED,
        ),
        (
            403,
            None,
            None,
            ReadinessReason.PERMISSION_DENIED,
        ),
        (
            429,
            "rate_limit_error",
            "rate_limit_exceeded",
            ReadinessReason.RATE_LIMITED,
        ),
        (
            400,
            "invalid_request_error",
            None,
            ReadinessReason.CONTRACT_INCOMPATIBLE,
        ),
        (
            500,
            "server_error",
            None,
            ReadinessReason.PROVIDER_UNAVAILABLE,
        ),
        (
            503,
            "server_error",
            None,
            ReadinessReason.PROVIDER_UNAVAILABLE,
        ),
        (
            504,
            None,
            None,
            ReadinessReason.PROVIDER_TIMEOUT,
        ),
    ],
)
def test_openai_failure_normalization(
    status,
    error_type,
    error_code,
    expected,
):
    assert normalize_openai_failure(
        status_code=status,
        error_type=error_type,
        error_code=error_code,
    ) is expected


def test_successful_capability_probe_is_healthy(
    monkeypatch,
):
    instance = probe()

    monkeypatch.setattr(
        OpenAIResponsesReadinessProbe,
        "_resolve_endpoint",
        lambda self: None,
    )

    monkeypatch.setattr(
        OpenAIResponsesReadinessProbe,
        "_request",
        lambda self: {
            "status": "completed",
        },
    )

    observation = instance.observe(
        provider_id="provider.openai",
        capability_name="conversation.intent.interpret",
    )

    result = classify_readiness(
        observation
    )

    assert result.state is ReadinessState.HEALTHY
    assert result.reason is ReadinessReason.NONE
    assert result.provider_status_code == "200"


def test_credit_exhaustion_is_capability_failure_not_runtime_failure(
    monkeypatch,
):
    instance = probe()

    monkeypatch.setattr(
        OpenAIResponsesReadinessProbe,
        "_resolve_endpoint",
        lambda self: None,
    )

    monkeypatch.setattr(
        OpenAIResponsesReadinessProbe,
        "_request",
        lambda self: OpenAIProviderFailure(
            status_code=429,
            error_type="insufficient_quota",
            error_code="credit_balance_exhausted",
        ),
    )

    observation = instance.observe(
        provider_id="provider.openai-conversation-kernel",
        capability_name="conversation.intent.interpret",
    )

    assert observation.component.healthy is True
    assert observation.reachability.healthy is True
    assert observation.authentication.healthy is True
    assert observation.capability.healthy is False

    result = classify_readiness(
        observation
    )

    assert result.state is ReadinessState.UNAVAILABLE
    assert result.reason is ReadinessReason.QUOTA_EXHAUSTED
    assert result.provider_status_code == "429"


def test_invalid_api_key_is_authentication_failure(
    monkeypatch,
):
    instance = probe()

    monkeypatch.setattr(
        OpenAIResponsesReadinessProbe,
        "_resolve_endpoint",
        lambda self: None,
    )

    monkeypatch.setattr(
        OpenAIResponsesReadinessProbe,
        "_request",
        lambda self: OpenAIProviderFailure(
            status_code=401,
            error_type="invalid_request_error",
            error_code="invalid_api_key",
        ),
    )

    observation = instance.observe(
        provider_id="provider.openai",
        capability_name="conversation.intent.interpret",
    )

    assert observation.authentication.healthy is False
    assert observation.capability.checked is False

    result = classify_readiness(
        observation
    )

    assert result.reason is (
        ReadinessReason.AUTHENTICATION_FAILED
    )


def test_provider_unreachable_does_not_claim_authentication_was_tested(
    monkeypatch,
):
    instance = probe()

    def fail_resolution():
        raise OSError(
            "DNS unavailable"
        )

    monkeypatch.setattr(
        OpenAIResponsesReadinessProbe,
        "_resolve_endpoint",
        lambda self: fail_resolution(),
    )

    observation = instance.observe(
        provider_id="provider.openai",
        capability_name="conversation.intent.interpret",
    )

    assert observation.reachability.healthy is False
    assert observation.authentication.checked is False
    assert observation.capability.checked is False

    result = classify_readiness(
        observation
    )

    assert result.reason is (
        ReadinessReason.DEPENDENCY_UNREACHABLE
    )


def test_runtime_failure_prevents_external_probe(
    monkeypatch,
):
    instance = probe()

    called = {
        "resolve": False,
    }

    def resolution():
        called["resolve"] = True

    monkeypatch.setattr(
        OpenAIResponsesReadinessProbe,
        "_resolve_endpoint",
        lambda self: resolution(),
    )

    observation = instance.observe(
        provider_id="provider.openai",
        capability_name="conversation.intent.interpret",
        component_healthy=False,
    )

    assert called["resolve"] is False

    result = classify_readiness(
        observation
    )

    assert result.reason is (
        ReadinessReason.RUNTIME_UNHEALTHY
    )


def test_probe_configuration_does_not_expose_api_key_in_repr():
    instance = OpenAIResponsesReadinessProbe(
        api_key="super-secret-value",
        model="test-model",
    )

    rendered = repr(
        instance
    )

    assert "super-secret-value" not in rendered
    assert "api_key=" not in rendered
