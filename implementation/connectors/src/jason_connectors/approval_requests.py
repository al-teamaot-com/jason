"""Compatibility import for provider-neutral approval contracts.

Canonical ownership moved to :mod:`orchestrator.approval_requests`. Existing
connector/package imports remain temporarily supported while callers migrate.
No provider authority or behavior is implemented here.
"""

from orchestrator.approval_requests import (
    AcceptedApproval,
    ApprovalAuthorityChecker,
    ApprovalDecision,
    ApprovalEvidenceReference,
    ApprovalPresentation,
    ApprovalRequest,
    ApprovalRequestRepository,
    ApprovalRequestService,
    ApprovalRequestStatus,
    ApprovalResponse,
    InMemoryApprovalRequestRepository,
    SQLiteApprovalRequestRepository,
)

__all__ = [
    "AcceptedApproval",
    "ApprovalAuthorityChecker",
    "ApprovalDecision",
    "ApprovalEvidenceReference",
    "ApprovalPresentation",
    "ApprovalRequest",
    "ApprovalRequestRepository",
    "ApprovalRequestService",
    "ApprovalRequestStatus",
    "ApprovalResponse",
    "InMemoryApprovalRequestRepository",
    "SQLiteApprovalRequestRepository",
]
