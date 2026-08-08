from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class AuthorityOutcome(str, Enum):
    ALLOWED = "allowed"
    ALLOWED_LIMITED = "allowed_limited"
    APPROVAL_REQUIRED = "approval_required"
    DENIED = "denied"
    INDETERMINATE = "indeterminate"


class PermissionMode(str, Enum):
    OBSERVE = "observe"
    RECOMMEND = "recommend"
    REQUEST_APPROVAL = "request_approval"
    EXECUTE = "execute"
    ADMINISTER = "administer"


_PERMISSION_RANK = {
    PermissionMode.OBSERVE: 0,
    PermissionMode.RECOMMEND: 1,
    PermissionMode.REQUEST_APPROVAL: 2,
    PermissionMode.EXECUTE: 3,
    PermissionMode.ADMINISTER: 4,
}


def permission_rank(mode: PermissionMode) -> int:
    return _PERMISSION_RANK[mode]


@dataclass(frozen=True, slots=True)
class IdentityRecord:
    identity_id: str
    identity_type: str
    organization_id: str
    status: str = "active"

    def __post_init__(self) -> None:
        for name, value in {
            "identity_id": self.identity_id,
            "identity_type": self.identity_type,
            "organization_id": self.organization_id,
            "status": self.status,
        }.items():
            if not value.strip():
                raise ValueError(f"{name} must be non-empty")


@dataclass(frozen=True, slots=True)
class AuthorityGrant:
    grant_id: str
    subject_id: str
    capability: str
    organization_id: str
    client_id: str | None
    permission: PermissionMode
    approval_required: bool = False
    effective_from: datetime | None = None
    effective_until: datetime | None = None
    status: str = "active"

    def __post_init__(self) -> None:
        for name, value in {
            "grant_id": self.grant_id,
            "subject_id": self.subject_id,
            "capability": self.capability,
            "organization_id": self.organization_id,
            "status": self.status,
        }.items():
            if not value.strip():
                raise ValueError(f"{name} must be non-empty")
        if self.effective_from is not None and self.effective_from.tzinfo is None:
            raise ValueError("effective_from must be timezone-aware")
        if self.effective_until is not None and self.effective_until.tzinfo is None:
            raise ValueError("effective_until must be timezone-aware")


@dataclass(frozen=True, slots=True)
class ApprovalRecord:
    approval_id: str
    request_id: str
    capability: str
    organization_id: str
    client_id: str | None
    requested_by: str
    status: str
    decided_by: str | None
    decided_at: datetime | None
    expires_at: datetime | None

    def __post_init__(self) -> None:
        for value in (
            self.approval_id,
            self.request_id,
            self.capability,
            self.organization_id,
            self.requested_by,
            self.status,
        ):
            if not value.strip():
                raise ValueError("approval identifiers/status must be non-empty")
        for value in (self.decided_at, self.expires_at):
            if value is not None and value.tzinfo is None:
                raise ValueError("approval timestamps must be timezone-aware")


@dataclass(frozen=True, slots=True)
class AuthorityRequest:
    request_id: str
    correlation_id: str
    principal_id: str
    organization_id: str
    client_id: str | None
    capability: str
    requested_mode: PermissionMode
    authentication_assurance: str
    approval_id: str | None = None

    def __post_init__(self) -> None:
        for name, value in {
            "request_id": self.request_id,
            "correlation_id": self.correlation_id,
            "principal_id": self.principal_id,
            "organization_id": self.organization_id,
            "capability": self.capability,
            "authentication_assurance": self.authentication_assurance,
        }.items():
            if not value.strip():
                raise ValueError(f"{name} must be non-empty")


@dataclass(frozen=True, slots=True)
class ExecutionContext:
    context_id: str
    correlation_id: str
    principal_id: str
    organization_id: str
    client_id: str | None
    capability: str
    requested_mode: PermissionMode
    maximum_mode: PermissionMode
    outcome: AuthorityOutcome
    approval_required: bool
    matched_grants: tuple[str, ...]
    authentication_assurance: str
    issued_at: datetime
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class AuthorityDecision:
    outcome: AuthorityOutcome
    reason_codes: tuple[str, ...]
    maximum_mode: PermissionMode | None = None
    matched_grants: tuple[str, ...] = ()
    execution_context: ExecutionContext | None = None

    def __post_init__(self) -> None:
        if not self.reason_codes:
            raise ValueError("reason_codes must not be empty")
