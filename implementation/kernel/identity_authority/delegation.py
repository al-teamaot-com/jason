from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from .contracts import PermissionMode, permission_rank


@dataclass(frozen=True, slots=True)
class DelegationRecord:
    delegation_id: str
    delegator_id: str
    delegate_id: str
    organization_id: str
    client_id: str | None
    capability: str
    maximum_mode: PermissionMode
    effective_from: datetime
    effective_until: datetime
    status: str = "active"

    def __post_init__(self) -> None:
        for name, value in {
            "delegation_id": self.delegation_id,
            "delegator_id": self.delegator_id,
            "delegate_id": self.delegate_id,
            "organization_id": self.organization_id,
            "capability": self.capability,
            "status": self.status,
        }.items():
            if not value.strip():
                raise ValueError(f"{name} must be non-empty")
        if self.effective_from.tzinfo is None or self.effective_until.tzinfo is None:
            raise ValueError("delegation timestamps must be timezone-aware")
        if self.effective_until <= self.effective_from:
            raise ValueError("delegation effective_until must follow effective_from")


@dataclass(frozen=True, slots=True)
class DelegationValidationRequest:
    delegation_id: str
    delegator_id: str
    delegate_id: str
    organization_id: str
    client_id: str | None
    capability: str
    requested_mode: PermissionMode


@dataclass(frozen=True, slots=True)
class DelegationValidationResult:
    valid: bool
    reason_code: str
    record: DelegationRecord | None = None


class DelegationRepository(Protocol):
    def get_delegation(self, delegation_id: str) -> DelegationRecord | None: ...


@dataclass
class DelegationValidator:
    delegations: DelegationRepository
    clock: callable = lambda: datetime.now(timezone.utc)

    def validate(self, request: DelegationValidationRequest) -> DelegationValidationResult:
        record = self.delegations.get_delegation(request.delegation_id)
        if record is None:
            return DelegationValidationResult(False, "DELEGATION_NOT_FOUND")
        if record.status != "active":
            return DelegationValidationResult(False, "DELEGATION_INACTIVE", record)

        now = self.clock()
        if now.tzinfo is None:
            raise ValueError("delegation clock must be timezone-aware")
        now = now.astimezone(timezone.utc)
        if now < record.effective_from or now >= record.effective_until:
            return DelegationValidationResult(False, "DELEGATION_NOT_EFFECTIVE", record)

        exact = (
            record.delegator_id == request.delegator_id
            and record.delegate_id == request.delegate_id
            and record.organization_id == request.organization_id
            and record.client_id == request.client_id
            and record.capability == request.capability
        )
        if not exact:
            return DelegationValidationResult(False, "DELEGATION_SCOPE_MISMATCH", record)
        if permission_rank(request.requested_mode) > permission_rank(record.maximum_mode):
            return DelegationValidationResult(False, "DELEGATION_MODE_EXCEEDED", record)
        return DelegationValidationResult(True, "DELEGATION_VALID", record)
