from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from orchestrator import (
    ExecutionReconstructionError,
    ExecutionReconstructor,
    OrchestrationEvent,
    SQLiteOrchestrationEventStore,
)


def _event(
    *,
    event_id: str,
    event_type: str,
    stage: str,
    offset_seconds: int,
    correlation_id: str = "corr-1",
    organization_id: str = "aot",
    principal_id: str = "operator-al",
    capability_name: str = "example.capability.read",
) -> OrchestrationEvent:
    return OrchestrationEvent(
        event_id=event_id,
        event_type=event_type,
        execution_id="exec-1",
        correlation_id=correlation_id,
        organization_id=organization_id,
        principal_id=principal_id,
        capability_name=capability_name,
        stage=stage,
        occurred_at=datetime(2026, 8, 7, 9, 0, tzinfo=timezone.utc)
        + timedelta(seconds=offset_seconds),
    )


def test_reconstructs_ordered_observed_execution() -> None:
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
            event_type="orchestration.capability.resolved",
            stage="policy_decided",
            offset_seconds=1,
        )
    )
    store.append_event(
        _event(
            event_id="event-3",
            event_type="orchestration.capability.completed",
            stage="completed",
            offset_seconds=2,
        )
    )

    reconstructed = ExecutionReconstructor(store).reconstruct("exec-1")

    assert reconstructed.execution_id == "exec-1"
    assert reconstructed.correlation_id == "corr-1"
    assert reconstructed.organization_id == "aot"
    assert reconstructed.principal_id == "operator-al"
    assert reconstructed.capability_name == "example.capability.read"
    assert reconstructed.final_event_type == "orchestration.capability.completed"
    assert reconstructed.final_stage == "completed"
    assert reconstructed.event_count == 3
    assert tuple(entry.event_id for entry in reconstructed.timeline) == (
        "event-1",
        "event-2",
        "event-3",
    )


def test_missing_execution_fails_closed() -> None:
    store = SQLiteOrchestrationEventStore()

    with pytest.raises(LookupError, match="No orchestration events exist"):
        ExecutionReconstructor(store).reconstruct("missing")


def test_empty_execution_id_is_denied() -> None:
    store = SQLiteOrchestrationEventStore()

    with pytest.raises(ValueError, match="execution_id must be non-empty"):
        ExecutionReconstructor(store).reconstruct("   ")


def test_inconsistent_identity_context_fails_closed() -> None:
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
            event_type="orchestration.capability.completed",
            stage="completed",
            offset_seconds=1,
            organization_id="other-org",
        )
    )

    with pytest.raises(
        ExecutionReconstructionError,
        match="inconsistent identity context: organization_id",
    ):
        ExecutionReconstructor(store).reconstruct("exec-1")


def test_reconstruction_is_read_only() -> None:
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
    ExecutionReconstructor(store).reconstruct("exec-1")
    after = store.list_by_execution("exec-1")

    assert before == after
