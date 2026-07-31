"""Normalize provider-specific usage payloads into Jason ledger contracts."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Mapping
from uuid import uuid4

from .contracts import (
    AttemptOutcome,
    CostUsage,
    TokenUsage,
    UsageContext,
    UsageEntry,
    UsageSource,
)


def _integer(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def from_openai_response(
    *,
    context: UsageContext,
    model: str,
    response: Mapping[str, Any],
    outcome: AttemptOutcome = AttemptOutcome.COMPLETED,
    started_at: datetime | None = None,
) -> UsageEntry:
    usage = response.get("usage") or {}
    input_details = usage.get("input_tokens_details") or {}
    output_details = usage.get("output_tokens_details") or {}
    return UsageEntry(
        entry_id=str(uuid4()),
        context=context,
        provider="openai",
        model=model,
        outcome=outcome,
        usage_source=UsageSource.PROVIDER_REPORTED if usage else UsageSource.UNKNOWN,
        tokens=TokenUsage(
            input_tokens=_integer(usage.get("input_tokens")),
            cached_input_tokens=_integer(input_details.get("cached_tokens")),
            output_tokens=_integer(usage.get("output_tokens")),
            reasoning_tokens=_integer(output_details.get("reasoning_tokens")),
            total_tokens=_integer(usage.get("total_tokens")),
        ),
        provider_request_id=response.get("id"),
        finish_reason=response.get("status"),
        started_at=started_at,
        completed_at=datetime.now(timezone.utc),
        confidence=1.0 if usage else 0.0,
    )


def from_openrouter_response(
    *,
    context: UsageContext,
    model: str,
    response: Mapping[str, Any],
    outcome: AttemptOutcome = AttemptOutcome.COMPLETED,
    started_at: datetime | None = None,
) -> UsageEntry:
    usage = response.get("usage") or {}
    prompt_details = usage.get("prompt_tokens_details") or {}
    completion_details = usage.get("completion_tokens_details") or {}
    return UsageEntry(
        entry_id=str(uuid4()),
        context=context,
        provider="openrouter",
        model=model,
        outcome=outcome,
        usage_source=UsageSource.PROVIDER_REPORTED if usage else UsageSource.UNKNOWN,
        tokens=TokenUsage(
            input_tokens=_integer(usage.get("prompt_tokens")),
            cached_input_tokens=_integer(prompt_details.get("cached_tokens")),
            output_tokens=_integer(usage.get("completion_tokens")),
            reasoning_tokens=_integer(
                completion_details.get("reasoning_tokens", usage.get("reasoning_tokens"))
            ),
            total_tokens=_integer(usage.get("total_tokens")),
        ),
        cost=CostUsage(provider_reported_cost=_decimal(usage.get("cost"))),
        provider_request_id=response.get("id"),
        started_at=started_at,
        completed_at=datetime.now(timezone.utc),
        confidence=1.0 if usage else 0.0,
    )


def from_ollama_response(
    *,
    context: UsageContext,
    model: str,
    response: Mapping[str, Any],
    outcome: AttemptOutcome = AttemptOutcome.COMPLETED,
    started_at: datetime | None = None,
) -> UsageEntry:
    input_tokens = _integer(response.get("prompt_eval_count"))
    output_tokens = _integer(response.get("eval_count"))
    total_tokens = None
    if input_tokens is not None and output_tokens is not None:
        total_tokens = input_tokens + output_tokens

    eval_duration_ns = response.get("eval_duration")
    duration_ns = response.get("total_duration")
    has_usage = input_tokens is not None or output_tokens is not None
    return UsageEntry(
        entry_id=str(uuid4()),
        context=context,
        provider="ollama",
        model=model,
        outcome=outcome,
        usage_source=(
            UsageSource.LOCAL_RUNTIME_REPORTED if has_usage else UsageSource.UNKNOWN
        ),
        tokens=TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
        ),
        finish_reason=response.get("done_reason"),
        started_at=started_at,
        completed_at=datetime.now(timezone.utc),
        duration_ms=int(duration_ns / 1_000_000) if duration_ns is not None else None,
        local_eval_duration_ms=(
            int(eval_duration_ns / 1_000_000) if eval_duration_ns is not None else None
        ),
        confidence=1.0 if has_usage else 0.0,
    )
