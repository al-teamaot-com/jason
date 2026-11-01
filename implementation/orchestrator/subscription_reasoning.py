from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from connectors.core.contracts import ConnectorTransportError


class JsonHttpTransport(Protocol):
    def request(
        self,
        *,
        method: str,
        url: str,
        headers: Mapping[str, str],
        json: Mapping[str, Any] | None = None,
        timeout_seconds: float = 30.0,
    ) -> Mapping[str, Any]:
        ...


@dataclass(frozen=True, slots=True)
class SubscriptionStructuredJsonClient:
    """Structured reasoning through the isolated ChatGPT-plan sidecar.

    This client carries no OpenAI API key or ChatGPT credential. The sidecar is
    the only component that owns the subscription session and it receives only
    bounded prompt text plus an output schema.
    """

    transport: JsonHttpTransport
    base_url: str = "http://jason-subscription-reasoning:8091"
    timeout_seconds: float = 120.0

    def complete(
        self,
        *,
        system: str,
        user: str,
        schema: Mapping[str, Any],
        max_output_tokens: int,
    ) -> Mapping[str, Any]:
        if not 1 <= int(max_output_tokens) <= 32768:
            raise ValueError("subscription reasoning output budget is invalid")
        response = self.transport.request(
            method="POST",
            url=self.base_url.rstrip("/") + "/v1/structured-complete",
            headers={"Content-Type": "application/json"},
            json={
                "system": str(system),
                "user": str(user),
                "schema": dict(schema),
                "max_output_tokens": int(max_output_tokens),
            },
            timeout_seconds=self.timeout_seconds,
        )
        result = response.get("result") if isinstance(response, Mapping) else None
        if not isinstance(result, Mapping):
            raise ConnectorTransportError(
                "subscription reasoning response omitted structured result",
                service="chatgpt-subscription",
                provider_error_code="subscription_reasoning_invalid_response",
            )
        return dict(result)
