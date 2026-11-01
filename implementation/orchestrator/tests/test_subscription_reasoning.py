from __future__ import annotations

import pytest

from connectors.core.contracts import ConnectorTransportError
from orchestrator.subscription_reasoning import SubscriptionStructuredJsonClient


class Transport:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def request(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def test_subscription_client_posts_bounded_structured_request():
    transport = Transport({"result": {"ok": True}})
    client = SubscriptionStructuredJsonClient(
        transport=transport, base_url="http://reasoning:8091"
    )
    result = client.complete(
        system="system", user="user",
        schema={"type": "object", "properties": {"ok": {"type": "boolean"}}},
        max_output_tokens=128,
    )
    assert result == {"ok": True}
    call = transport.calls[0]
    assert call["url"] == "http://reasoning:8091/v1/structured-complete"
    assert call["json"]["system"] == "system"
    assert call["json"]["max_output_tokens"] == 128


def test_subscription_client_rejects_invalid_sidecar_response():
    client = SubscriptionStructuredJsonClient(transport=Transport({"result": "bad"}))
    with pytest.raises(ConnectorTransportError) as exc:
        client.complete(
            system="s", user="u", schema={"type": "object"},
            max_output_tokens=16,
        )
    assert exc.value.provider_error_code == "subscription_reasoning_invalid_response"


def test_subscription_client_rejects_unbounded_output_budget():
    client = SubscriptionStructuredJsonClient(transport=Transport({"result": {}}))
    with pytest.raises(ValueError):
        client.complete(
            system="s", user="u", schema={"type": "object"},
            max_output_tokens=50000,
        )



def test_explicit_api_fallback_does_not_hide_local_validation_errors():
    class Primary:
        def complete(self, **kwargs):
            raise ValueError("invalid governed request")

    class Fallback:
        def __init__(self):
            self.calls = 0

        def complete(self, **kwargs):
            self.calls += 1
            return {"ok": True}

    from orchestrator.subscription_reasoning import ExplicitFallbackStructuredJsonClient

    fallback = Fallback()
    client = ExplicitFallbackStructuredJsonClient(primary=Primary(), fallback=fallback)
    with pytest.raises(ValueError, match="invalid governed request"):
        client.complete(
            system="s",
            user="u",
            schema={"type": "object"},
            max_output_tokens=16,
        )
    assert fallback.calls == 0
