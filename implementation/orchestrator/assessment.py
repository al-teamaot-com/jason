from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .reconstruction import ExecutionReconstructor, ReconstructedExecution


class ExecutionAssessmentStatus(str, Enum):
    TERMINAL = "terminal"
    INTERRUPTED = "interrupted"


class ExecutionAssessmentReason(str, Enum):
    TERMINAL_EVENT_RECORDED = "terminal_event_recorded"
    NO_TERMINAL_EVENT_RECORDED = "no_terminal_event_recorded"


_TERMINAL_EVENT_TYPES = frozenset(
    {
        "orchestration.request.terminated",
        "orchestration.check_only.validated",
        "orchestration.capability.failed",
        "orchestration.capability.completed",
    }
)


@dataclass(frozen=True, slots=True)
class ExecutionAssessment:
    execution_id: str
    correlation_id: str
    organization_id: str
    principal_id: str
    capability_name: str
    status: ExecutionAssessmentStatus
    reason: ExecutionAssessmentReason
    final_observed_event_type: str
    final_observed_stage: str
    event_count: int

    @property
    def is_terminal(self) -> bool:
        return self.status is ExecutionAssessmentStatus.TERMINAL

    @property
    def is_interrupted(self) -> bool:
        return self.status is ExecutionAssessmentStatus.INTERRUPTED


class InterruptedExecutionAssessor:
    """Classify reconstructed history without executing or contacting providers."""

    def __init__(self, reconstructor: ExecutionReconstructor) -> None:
        self._reconstructor = reconstructor

    def assess(self, execution_id: str) -> ExecutionAssessment:
        reconstructed = self._reconstructor.reconstruct(execution_id)
        return self.assess_reconstructed(reconstructed)

    @staticmethod
    def assess_reconstructed(
        reconstructed: ReconstructedExecution,
    ) -> ExecutionAssessment:
        terminal = reconstructed.final_event_type in _TERMINAL_EVENT_TYPES
        return ExecutionAssessment(
            execution_id=reconstructed.execution_id,
            correlation_id=reconstructed.correlation_id,
            organization_id=reconstructed.organization_id,
            principal_id=reconstructed.principal_id,
            capability_name=reconstructed.capability_name,
            status=(
                ExecutionAssessmentStatus.TERMINAL
                if terminal
                else ExecutionAssessmentStatus.INTERRUPTED
            ),
            reason=(
                ExecutionAssessmentReason.TERMINAL_EVENT_RECORDED
                if terminal
                else ExecutionAssessmentReason.NO_TERMINAL_EVENT_RECORDED
            ),
            final_observed_event_type=reconstructed.final_event_type,
            final_observed_stage=reconstructed.final_stage,
            event_count=reconstructed.event_count,
        )
