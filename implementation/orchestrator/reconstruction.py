from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from .event_store import OrchestrationEvent


class OrchestrationEventReader(Protocol):
    def list_by_execution(self, execution_id: str) -> tuple[OrchestrationEvent, ...]: ...


class ExecutionReconstructionError(ValueError):
    """Raised when durable events cannot be reconstructed safely."""


@dataclass(frozen=True, slots=True)
class ExecutionTimelineEntry:
    event_id: str
    event_type: str
    stage: str
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class ReconstructedExecution:
    execution_id: str
    correlation_id: str
    organization_id: str
    principal_id: str
    capability_name: str
    final_event_type: str
    final_stage: str
    event_count: int
    started_at: datetime
    last_observed_at: datetime
    timeline: tuple[ExecutionTimelineEntry, ...]


class ExecutionReconstructor:
    """Build a read-only observed execution view from durable events."""

    def __init__(self, event_reader: OrchestrationEventReader) -> None:
        self._event_reader = event_reader

    def reconstruct(self, execution_id: str) -> ReconstructedExecution:
        canonical_execution_id = execution_id.strip()
        if not canonical_execution_id:
            raise ValueError("execution_id must be non-empty.")

        events = self._event_reader.list_by_execution(canonical_execution_id)
        if not events:
            raise LookupError(
                f"No orchestration events exist for execution: {canonical_execution_id}"
            )

        first = events[0]
        expected = {
            "execution_id": first.execution_id,
            "correlation_id": first.correlation_id,
            "organization_id": first.organization_id,
            "principal_id": first.principal_id,
            "capability_name": first.capability_name,
        }

        for event in events:
            actual = {
                "execution_id": event.execution_id,
                "correlation_id": event.correlation_id,
                "organization_id": event.organization_id,
                "principal_id": event.principal_id,
                "capability_name": event.capability_name,
            }
            mismatched = sorted(
                key for key, value in actual.items() if value != expected[key]
            )
            if mismatched:
                raise ExecutionReconstructionError(
                    "Execution history contains inconsistent identity context: "
                    + ", ".join(mismatched)
                )

        timeline = tuple(
            ExecutionTimelineEntry(
                event_id=event.event_id,
                event_type=event.event_type,
                stage=event.stage,
                occurred_at=event.occurred_at,
            )
            for event in events
        )
        final = events[-1]

        return ReconstructedExecution(
            execution_id=first.execution_id,
            correlation_id=first.correlation_id,
            organization_id=first.organization_id,
            principal_id=first.principal_id,
            capability_name=first.capability_name,
            final_event_type=final.event_type,
            final_stage=final.stage,
            event_count=len(events),
            started_at=events[0].occurred_at,
            last_observed_at=final.occurred_at,
            timeline=timeline,
        )
