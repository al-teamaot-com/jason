from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from orchestrator import (
    ExecutionAssessmentReason,
    ExecutionAssessmentStatus,
    ExecutionReconstructionError,
    ExecutionReconstructor,
    InterruptedExecutionAssessor,
    OrchestrationEvent,
    SQLiteOrchestrationEventStore,
)


def _event(
    *,
    event_id: str,
    event_type: str,
    stage: str,
    offset_seconds: int,
) -> OrchestrationEvent:
    return OrchestrationEvent(
        event_id=event_id,
        event_type=event_type,
        execution_id="exec-1",
        correlation_id="corr-1",
        organization_id="aot",
        principal_id="operator-al",
        capability_name="example.capability.read",
        stage=stage,
        occurred_at=(
            datetime(2026, 8, 7, 10, 0, tzinfo=timezone.utc)
            + timedelta(seconds=offset_seconds)
        ),
    )


def _assessor(store: SQLiteOrchestrationEventStore) -> InterruptedExecutionAssessor:
    return InterruptedExecutionAssessor(ExecutionReconstructor(store))


@pytest.mark.parametrize(
    ("event_type", "stage"),
    (
        ("orchestration.request.terminated", "denied"),
        ("orchestration.check_only.validated", "completed"),
        ("orchestration.capability.failed", "failed"),
        ("orchestration.capability.completed", "completed"),
    ),
)
def test_terminal_events_are_terminal(event_type: str, stage: str) -> None:
    store = SQLiteOrchestrationEventStore()
    store.append_event(
        _event(
            event_id="event-1",
            event_type="orchestration.request.received",
            stage="received",
            offset_seconds=0,
        )
    )
    store.append_event(
        _event(
            event_id="event-2",
            event_type=event_type,
            stage=stage,
            offset_seconds=1,
        )
    )

    result = _assessor(store).assess("exec-1")

    assert result.status is ExecutionAssessmentStatus.TERMINAL
    assert result.reason is ExecutionAssessmentReason.TERMINAL_EVENT_RECORDED
    assert result.is_terminal is True
    assert result.is_interrupted is False
    assert result.final_observed_event_type == event_type
    assert result.final_observed_stage == stage


def test_nonterminal_history_is_interrupted_without_guessing_provider_state() -> None:
    store = SQLiteOrchestrationEventStore()
    store.append_event(
        _event(
            event_id="event-1",
            event_type="orchestration.request.received",
            stage="received",
            offset_seconds=0,
        )
    )
    store.append_event(
        _event(
            event_id="event-2",
            event_type="orchestration.capability.invoking",
            stage="invoking",
            offset_seconds=1,
        )
    )

    result = _assessor(store).assess("exec-1")

    assert result.status is ExecutionAssessmentStatus.INTERRUPTED
    assert result.reason is ExecutionAssessmentReason.NO_TERMINAL_EVENT_RECORDED
    assert result.is_terminal is False
    assert result.is_interrupted is True
    assert result.final_observed_event_type == "orchestration.capability.invoking"
    assert result.final_observed_stage == "invoking"


def test_assessment_reuses_reconstruction_failure_contract() -> None:
    store = SQLiteOrchestrationEventStore()

    with pytest.raises(ExecutionReconstructionError, match="No orchestration events exist"):
        _assessor(store).assess("missing")


def test_assessment_is_read_only() -> None:
    store = SQLiteOrchestrationEventStore()
    store.append_event(
        _event(
            event_id="event-1",
            event_type="orchestration.request.received",
            stage="received",
            offset_seconds=0,
        )
    )

    before = store.list_by_execution("exec-1")
    _assessor(store).assess("exec-1")
    after = store.list_by_execution("exec-1")

    assert before == after
