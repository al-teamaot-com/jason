from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable


class WorkflowState(StrEnum):
    RECEIVED = "received"
    CONTEXT_VALIDATED = "context_validated"
    EVIDENCE_COLLECTED = "evidence_collected"
    CASE_NORMALIZED = "case_normalized"
    REASONING_COMPLETE = "reasoning_complete"
    QUALITY_GATED = "quality_gated"
    RESPONSE_READY = "response_ready"
    OUTCOME_PENDING = "outcome_pending"
    COMPLETE = "complete"
    MORE_INFORMATION_REQUIRED = "more_information_required"
    ESCALATION_REQUIRED = "escalation_required"
    REJECTED = "rejected"


_ALLOWED_TRANSITIONS: dict[WorkflowState, set[WorkflowState]] = {
    WorkflowState.RECEIVED: {WorkflowState.CONTEXT_VALIDATED, WorkflowState.REJECTED},
    WorkflowState.CONTEXT_VALIDATED: {
        WorkflowState.EVIDENCE_COLLECTED,
        WorkflowState.MORE_INFORMATION_REQUIRED,
        WorkflowState.REJECTED,
    },
    WorkflowState.EVIDENCE_COLLECTED: {
        WorkflowState.CASE_NORMALIZED,
        WorkflowState.MORE_INFORMATION_REQUIRED,
        WorkflowState.ESCALATION_REQUIRED,
    },
    WorkflowState.CASE_NORMALIZED: {
        WorkflowState.REASONING_COMPLETE,
        WorkflowState.MORE_INFORMATION_REQUIRED,
    },
    WorkflowState.REASONING_COMPLETE: {
        WorkflowState.QUALITY_GATED,
        WorkflowState.ESCALATION_REQUIRED,
    },
    WorkflowState.QUALITY_GATED: {
        WorkflowState.RESPONSE_READY,
        WorkflowState.MORE_INFORMATION_REQUIRED,
        WorkflowState.ESCALATION_REQUIRED,
        WorkflowState.REJECTED,
    },
    WorkflowState.RESPONSE_READY: {WorkflowState.OUTCOME_PENDING},
    WorkflowState.OUTCOME_PENDING: {WorkflowState.COMPLETE},
    WorkflowState.MORE_INFORMATION_REQUIRED: {
        WorkflowState.EVIDENCE_COLLECTED,
        WorkflowState.REJECTED,
    },
    WorkflowState.ESCALATION_REQUIRED: {WorkflowState.COMPLETE},
    WorkflowState.REJECTED: set(),
    WorkflowState.COMPLETE: set(),
}


class InvalidTransition(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Transition:
    from_state: WorkflowState
    to_state: WorkflowState
    reason: str


@dataclass(slots=True)
class InvestigationWorkflow:
    state: WorkflowState = WorkflowState.RECEIVED

    def allowed_transitions(self) -> frozenset[WorkflowState]:
        return frozenset(_ALLOWED_TRANSITIONS[self.state])

    def transition(self, to_state: WorkflowState, reason: str) -> Transition:
        if not reason.strip():
            raise ValueError("A transition reason is required for auditability.")
        if to_state not in _ALLOWED_TRANSITIONS[self.state]:
            raise InvalidTransition(f"Cannot transition from {self.state} to {to_state}.")
        transition = Transition(self.state, to_state, reason.strip())
        self.state = to_state
        return transition

    def replay(self, transitions: Iterable[Transition]) -> WorkflowState:
        for transition in transitions:
            if transition.from_state != self.state:
                raise InvalidTransition("Transition history is not contiguous.")
            self.transition(transition.to_state, transition.reason)
        return self.state
