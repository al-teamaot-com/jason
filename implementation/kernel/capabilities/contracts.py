from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Mapping


CAPABILITY_NAME_PATTERN = re.compile(
    r"^[a-z0-9]+(?:\.[a-z0-9]+){2,}$"
)

CAPABILITY_VERSION_PATTERN = re.compile(
    r"^[0-9]+(?:\.[0-9]+)+$"
)

ARCHITECTURAL_CAPABILITY_ID_PATTERN = re.compile(
    r"^JAC-[0-9]{3}$"
)


class CapabilityLifecycle(str, Enum):
    PROPOSED = "proposed"
    BUILDING = "building"
    PILOT = "pilot"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    SUSPENDED = "suspended"
    RETIRED = "retired"


class CapabilityRisk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IdempotencyBehavior(str, Enum):
    IDEMPOTENT = "idempotent"
    CONDITIONALLY_IDEMPOTENT = "conditionally_idempotent"
    NON_IDEMPOTENT = "non_idempotent"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class CapabilityApproval:
    required: bool = False
    approver_classes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.required and not self.approver_classes:
            raise ValueError(
                "Approval-required capabilities need approver classes."
            )


@dataclass(frozen=True, slots=True)
class CapabilityEvidence:
    required: bool = False
    requirements: tuple[str, ...] = ()
    verification_requirements: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.required and not self.requirements:
            raise ValueError(
                "Evidence-required capabilities need evidence requirements."
            )


@dataclass(frozen=True, slots=True)
class CapabilityStewardship:
    steward: str
    business_justification: str
    review_interval_days: int
    retirement_criteria: tuple[str, ...]
    last_reviewed_at: datetime | None = None
    operational_owner: str | None = None
    approval_owner: str | None = None
    authoritative_change_sources: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.steward.strip():
            raise ValueError("steward must be non-empty.")
        if not self.business_justification.strip():
            raise ValueError(
                "business_justification must be non-empty."
            )
        if self.review_interval_days < 1:
            raise ValueError(
                "review_interval_days must be at least one."
            )
        if not self.retirement_criteria:
            raise ValueError(
                "retirement_criteria must not be empty."
            )


@dataclass(frozen=True, slots=True)
class CapabilityDefinition:
    capability_name: str
    version: str
    display_name: str
    lifecycle_status: CapabilityLifecycle
    business_purpose: str
    owner_service: str
    architectural_capability_ids: frozenset[str]
    risk_level: CapabilityRisk
    data_classifications: frozenset[str]
    permitted_execution_modes: frozenset[str]
    input_schema_reference: str
    output_schema_reference: str
    invoking_roles: frozenset[str]
    approval: CapabilityApproval
    evidence: CapabilityEvidence
    dependencies: frozenset[str]
    idempotency_behavior: IdempotencyBehavior
    idempotency_key_required: bool
    timeout_seconds: int
    maximum_attempts: int
    failure_behavior: str
    tenant_isolation_required: bool
    client_isolation_required: bool
    stewardship: CapabilityStewardship
    created_at: datetime
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not CAPABILITY_NAME_PATTERN.fullmatch(
            self.capability_name
        ):
            raise ValueError(
                f"Invalid capability name: {self.capability_name}"
            )

        if not CAPABILITY_VERSION_PATTERN.fullmatch(self.version):
            raise ValueError(
                f"Invalid capability version: {self.version}"
            )

        if not self.display_name.strip():
            raise ValueError("display_name must be non-empty.")

        for architectural_id in self.architectural_capability_ids:
            if not ARCHITECTURAL_CAPABILITY_ID_PATTERN.fullmatch(
                architectural_id
            ):
                raise ValueError(
                    "Invalid architectural capability ID: "
                    f"{architectural_id}"
                )

        if self.capability_name in self.dependencies:
            raise ValueError(
                "A capability cannot depend on itself."
            )

        for dependency in self.dependencies:
            if not CAPABILITY_NAME_PATTERN.fullmatch(dependency):
                raise ValueError(
                    f"Invalid dependency capability name: {dependency}"
                )

        if self.timeout_seconds < 1:
            raise ValueError(
                "timeout_seconds must be at least one."
            )

        if self.maximum_attempts < 1:
            raise ValueError(
                "maximum_attempts must be at least one."
            )


@dataclass(frozen=True, slots=True)
class CapabilityQuery:
    lifecycle_status: CapabilityLifecycle | None = None
    architectural_capability_id: str | None = None
    execution_mode: str | None = None
    risk_level: CapabilityRisk | None = None

    def __post_init__(self) -> None:
        if (
            self.architectural_capability_id is not None
            and not ARCHITECTURAL_CAPABILITY_ID_PATTERN.fullmatch(
                self.architectural_capability_id
            )
        ):
            raise ValueError(
                "Invalid architectural capability ID: "
                f"{self.architectural_capability_id}"
            )

        if (
            self.execution_mode is not None
            and not self.execution_mode.strip()
        ):
            raise ValueError(
                "execution_mode must be non-empty when provided."
            )
