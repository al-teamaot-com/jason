"""CAP-001 Professional Ticket Investigation reference implementation."""

from .authority import (
    ContextDecision,
    ContextValidationError,
    ExecutionContextValidator,
    StaticAuthorityResolver,
)
from .persistence import SQLitePilotStore
from .quality import QualityFinding, QualityGateResult, evaluate_reasoning_result
from .service import InvestigationRun, InvestigationService
from .validation import ContractValidationError, validate_document
from .workflow import InvestigationWorkflow, InvalidTransition, Transition, WorkflowState

__all__ = [
    "ContextDecision",
    "ContextValidationError",
    "ContractValidationError",
    "ExecutionContextValidator",
    "InvestigationRun",
    "InvestigationService",
    "InvestigationWorkflow",
    "InvalidTransition",
    "QualityFinding",
    "QualityGateResult",
    "SQLitePilotStore",
    "StaticAuthorityResolver",
    "Transition",
    "WorkflowState",
    "evaluate_reasoning_result",
    "validate_document",
]
