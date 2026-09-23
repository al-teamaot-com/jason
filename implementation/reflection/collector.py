from __future__ import annotations

from collections.abc import Sequence
from uuid import uuid4

from orchestrator.event_store import OrchestrationEvent

from .contracts import ReflectionRecord


_TERMINAL_EVENT_TYPES = {
    "orchestration.capability.completed",
    "orchestration.capability.failed",
    "orchestration.request.terminated",
    "orchestration.authority_context.denied",
    "orchestration.execution_plan.denied",
}


def reflection_record_from_events(
    events: Sequence[OrchestrationEvent],
    *,
    record_id: str | None = None,
    user_correction_category: str | None = None,
) -> ReflectionRecord:
    """Build one bounded reflection record from one execution timeline.

    Raw request arguments and provider response bodies are intentionally excluded.
    Only canonical event context and explicitly bounded reflection telemetry are used.
    """

    if not events:
        raise ValueError("at least one orchestration event is required")

    execution_ids = {event.execution_id for event in events}
    correlations = {event.correlation_id for event in events}
    organizations = {event.organization_id for event in events}
    capabilities = {event.capability_name for event in events}
    if len(execution_ids) != 1 or len(correlations) != 1:
        raise ValueError("reflection events must belong to one execution/correlation")
    if len(organizations) != 1 or len(capabilities) != 1:
        raise ValueError("reflection events must preserve organization/capability identity")

    terminal = next(
        (event for event in reversed(events) if event.event_type in _TERMINAL_EVENT_TYPES),
        None,
    )
    if terminal is None:
        raise ValueError("reflection requires a terminal orchestration event")

    payload = terminal.payload
    record = ReflectionRecord(
        record_id=record_id or str(uuid4()),
        execution_id=terminal.execution_id,
        correlation_id=terminal.correlation_id,
        organization_id=terminal.organization_id,
        client_id=_optional_text(payload.get("client_id")),
        capability_name=terminal.capability_name,
        provider_id=_optional_text(payload.get("provider_id")),
        outcome=str(payload.get("status") or terminal.stage).strip(),
        normalized_intent=str(payload.get("reflection_normalized_intent") or "").strip(),
        selector_strategy=str(payload.get("reflection_selector_strategy") or "").strip(),
        requested_result_scope=str(
            payload.get("reflection_requested_result_scope") or "unknown"
        ).strip(),
        result_count=_optional_int(payload.get("reflection_result_count")),
        candidate_count=_optional_int(payload.get("reflection_candidate_count")),
        provider_call_count=_int_default(payload.get("reflection_provider_call_count"), 0),
        pagination_count=_int_default(payload.get("reflection_pagination_count"), 0),
        fallback_count=_int_default(payload.get("reflection_fallback_count"), 0),
        evidence_item_count=_int_default(
            payload.get("reflection_evidence_item_count"), 0
        ),
        duration_ms=_optional_float(payload.get("duration_ms")),
        search_strategies=tuple(
            str(value).strip()
            for value in payload.get("reflection_search_strategies", ())
            if str(value).strip()
        ),
        search_result_counts=tuple(
            int(value) for value in payload.get("reflection_search_result_counts", ())
        ),
        warning_codes=tuple(
            str(value).strip()
            for value in payload.get("reflection_warning_codes", ())
            if str(value).strip()
        ),
        user_correction_category=(
            str(user_correction_category).strip()
            if user_correction_category is not None
            else None
        ),
        observed_at=terminal.occurred_at,
    )
    record.validate()
    return record


def _optional_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("boolean is not a valid reflection count")
    return int(value)


def _int_default(value: object, default: int) -> int:
    return default if value is None else int(value)


def _optional_float(value: object) -> float | None:
    return None if value is None else float(value)
