"""Hosted structured reasoning client with no execution authority.

This module is intentionally provider-specific only at the model-runtime boundary. Jason's
Conversation Kernel still owns the canonical structured contract and deterministic
validation. The OpenAI client receives no connector handles, provider credentials, tools,
or execution authority; it can only return a candidate JSON object for Jason to validate.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from dataclasses import dataclass, field
from decimal import Decimal
from time import monotonic
from typing import Any, Mapping, Protocol

from usage_ledger.adapters import from_openai_response
from usage_ledger.contracts import (
    AttemptOutcome,
    TokenUsage,
    UsageContext,
    UsageEntry,
    UsageLedger,
    UsageSource,
)
from usage_ledger.runtime_context import new_attempt_context


class JsonHttpTransport(Protocol):
    def request(
        self,
        *,
        method: str,
        url: str,
        headers: Mapping[str, str],
        json: Mapping[str, Any] | None = None,
        timeout_seconds: float = 30.0,
    ) -> Mapping[str, Any]: ...


@dataclass(frozen=True, slots=True)
class OpenAIStructuredJsonClient:
    """Use OpenAI only as a bounded structured reasoning backend.

    Strict Structured Outputs are a generation constraint, not Jason authority. Returned
    content must still pass the caller's canonical deterministic validator and any
    independent quality/evidence review before it can affect a user-facing response.

    ``store`` is explicitly false so Responses API application-state storage is not
    requested. Normal API abuse-monitoring/data-control policy remains an external
    platform concern and must be governed separately before production data egress.
    """

    api_key: str = field(repr=False)
    transport: JsonHttpTransport
    model: str
    endpoint: str = "https://api.openai.com/v1/responses"
    timeout_seconds: float = 60.0
    response_format_name: str = "jason_structured_reasoning"
    usage_ledger: UsageLedger | None = field(default=None, repr=False)
    input_cost_per_million_tokens: Decimal | None = None
    cached_input_cost_per_million_tokens: Decimal | None = None
    output_cost_per_million_tokens: Decimal | None = None

    def __post_init__(self) -> None:
        if not self.api_key.strip():
            raise ValueError("OpenAI API key is required")
        if not self.model.strip():
            raise ValueError("OpenAI model is required")
        if not self.endpoint.strip():
            raise ValueError("OpenAI endpoint is required")
        if self.timeout_seconds < 5 or self.timeout_seconds > 300:
            raise ValueError("OpenAI structured reasoning timeout is invalid")
        name = self.response_format_name.strip()
        if not name or len(name) > 64:
            raise ValueError("OpenAI response format name is invalid")
        if any(not (char.isalnum() or char in {"_", "-"}) for char in name):
            raise ValueError("OpenAI response format name contains invalid characters")

    def complete(
        self,
        *,
        system: str,
        user: str,
        schema: Mapping[str, Any],
        max_output_tokens: int = 160,
    ) -> Mapping[str, Any]:
        if not system.strip() or not user.strip():
            raise ValueError("OpenAI structured reasoning requires system and user text")
        if not isinstance(schema, Mapping) or not schema:
            raise ValueError("OpenAI structured reasoning schema is required")
        if max_output_tokens < 16 or max_output_tokens > 4096:
            raise ValueError("OpenAI structured reasoning output budget is invalid")

        usage_context = new_attempt_context()
        started_at = datetime.now(timezone.utc)
        started_clock = monotonic()
        try:
            response = self.transport.request(
                method="POST",
                url=self.endpoint,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "instructions": system,
                    "input": user,
                    "text": {
                        "format": {
                            "type": "json_schema",
                            "name": self.response_format_name,
                            "strict": True,
                            "schema": dict(schema),
                        }
                    },
                    "max_output_tokens": max_output_tokens,
                    "store": False,
                },
                timeout_seconds=self.timeout_seconds,
            )
        except Exception as error:
            self._record_failed_attempt(
                context=usage_context,
                started_at=started_at,
                duration_ms=int((monotonic() - started_clock) * 1000),
                outcome=(AttemptOutcome.TIMED_OUT if isinstance(error, TimeoutError) else AttemptOutcome.FAILED),
            )
            raise
        if self.usage_ledger is not None and usage_context is not None:
            self.usage_ledger.append(
                from_openai_response(
                    context=usage_context,
                    model=self.model,
                    response=response,
                    started_at=started_at,
                    duration_ms=int((monotonic() - started_clock) * 1000),
                    input_cost_per_million_tokens=self.input_cost_per_million_tokens,
                    cached_input_cost_per_million_tokens=self.cached_input_cost_per_million_tokens,
                    output_cost_per_million_tokens=self.output_cost_per_million_tokens,
                )
            )
        return self._decode_output(response)

    def _record_failed_attempt(
        self,
        *,
        context: UsageContext | None,
        started_at: datetime,
        duration_ms: int,
        outcome: AttemptOutcome,
    ) -> None:
        if self.usage_ledger is None or context is None:
            return
        self.usage_ledger.append(
            UsageEntry(
                entry_id=context.attempt_id,
                context=context,
                provider="openai",
                model=self.model,
                outcome=outcome,
                usage_source=UsageSource.UNKNOWN,
                tokens=TokenUsage(),
                started_at=started_at,
                completed_at=datetime.now(timezone.utc),
                duration_ms=duration_ms,
                confidence=0.0,
            )
        )

    @staticmethod
    def _decode_output(response: Mapping[str, Any]) -> Mapping[str, Any]:
        top_level = response.get("output_text")
        if isinstance(top_level, str) and top_level.strip():
            return OpenAIStructuredJsonClient._decode_json(top_level)

        output = response.get("output")
        if isinstance(output, list):
            for item in output:
                if not isinstance(item, Mapping):
                    continue
                content = item.get("content")
                if not isinstance(content, list):
                    continue
                for part in content:
                    if not isinstance(part, Mapping):
                        continue
                    if part.get("type") != "output_text":
                        continue
                    text = part.get("text")
                    if isinstance(text, str) and text.strip():
                        return OpenAIStructuredJsonClient._decode_json(text)

        raise ValueError("OpenAI response did not contain structured output text")

    @staticmethod
    def _decode_json(raw: str) -> Mapping[str, Any]:
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError as error:
            raise ValueError("OpenAI structured response was not valid JSON") from error
        if not isinstance(decoded, Mapping):
            raise ValueError("OpenAI structured response must be a JSON object")
        return dict(decoded)
