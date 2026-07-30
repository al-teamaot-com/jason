import pytest

from jason_cap_001 import InvestigationWorkflow, InvalidTransition, WorkflowState


def test_happy_path_reaches_outcome_pending() -> None:
    workflow = InvestigationWorkflow()
    states = [
        WorkflowState.CONTEXT_VALIDATED,
        WorkflowState.EVIDENCE_COLLECTED,
        WorkflowState.CASE_NORMALIZED,
        WorkflowState.REASONING_COMPLETE,
        WorkflowState.QUALITY_GATED,
        WorkflowState.RESPONSE_READY,
        WorkflowState.OUTCOME_PENDING,
    ]

    for state in states:
        workflow.transition(state, f"advance to {state}")

    assert workflow.state is WorkflowState.OUTCOME_PENDING


def test_invalid_transition_fails_closed() -> None:
    workflow = InvestigationWorkflow()

    with pytest.raises(InvalidTransition):
        workflow.transition(WorkflowState.REASONING_COMPLETE, "skip required controls")

    assert workflow.state is WorkflowState.RECEIVED


def test_transition_requires_audit_reason() -> None:
    workflow = InvestigationWorkflow()

    with pytest.raises(ValueError):
        workflow.transition(WorkflowState.CONTEXT_VALIDATED, "   ")


def test_missing_information_can_resume_collection() -> None:
    workflow = InvestigationWorkflow()
    workflow.transition(WorkflowState.CONTEXT_VALIDATED, "context authorized")
    workflow.transition(WorkflowState.MORE_INFORMATION_REQUIRED, "asset identity is missing")
    workflow.transition(WorkflowState.EVIDENCE_COLLECTED, "asset identity supplied")

    assert workflow.state is WorkflowState.EVIDENCE_COLLECTED


def test_rejected_state_is_terminal() -> None:
    workflow = InvestigationWorkflow()
    workflow.transition(WorkflowState.REJECTED, "client boundary mismatch")

    with pytest.raises(InvalidTransition):
        workflow.transition(WorkflowState.CONTEXT_VALIDATED, "attempt to continue")
