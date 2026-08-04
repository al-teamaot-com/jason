from __future__ import annotations

from dataclasses import dataclass, field, fields
from datetime import datetime
from enum import Enum
from typing import Mapping


class ProviderType(str, Enum):
    HOSTED_AI = "hosted_ai"
    LOCAL_AI = "local_ai"
    DETERMINISTIC = "deterministic"
    WORKFLOW = "workflow"
    HUMAN = "human"
    EXTERNAL_CONNECTOR = "external_connector"


class ProviderLifecycle(str, Enum):
    PLANNED = "planned"
    AVAILABLE = "available"
    DEPRECATED = "deprecated"
    RETIRED = "retired"


class ProviderHealth(str, Enum):
    HEALTHY = "healthy"
    WARNING = "warning"
    UNAVAILABLE = "unavailable"
    MAINTENANCE = "maintenance"
    UNKNOWN = "unknown"


class ProviderApproval(str, Enum):
    APPROVED = "approved"
    PILOT = "pilot"
    BLOCKED = "blocked"
    RETIRED = "retired"


@dataclass(frozen=True, slots=True)
class ProviderLimits:
    maximum_context_tokens: int | None = None
    maximum_input_tokens: int | None = None
    maximum_output_tokens: int | None = None
    maximum_concurrent_executions: int | None = None
    maximum_requests_per_minute: int | None = None
    maximum_execution_seconds: int | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "maximum_context_tokens",
            "maximum_input_tokens",
            "maximum_output_tokens",
            "maximum_concurrent_executions",
            "maximum_requests_per_minute",
            "maximum_execution_seconds",
        ):
            value = getattr(self, field_name)
            if value is not None and value < 1:
                raise ValueError(
                    f"{field_name} must be positive when provided."
                )


@dataclass(frozen=True, slots=True)
class ProviderFeatures:
    tools: bool = False
    vision: bool = False
    audio: bool = False
    streaming: bool = False
    structured_output: bool = False
    function_calling: bool = False
    batch_execution: bool = False
    stateful_sessions: bool = False


@dataclass(frozen=True, slots=True)
class ProviderStewardship:
    technology_steward: str
    business_justification: str
    review_interval_days: int
    last_reviewed_at: datetime
    retirement_criteria: tuple[str, ...]
    vendor_change_sources: tuple[str, ...] = ()
    operational_owner: str | None = None
    approval_owner: str | None = None

    def __post_init__(self) -> None:
        if not self.technology_steward.strip():
            raise ValueError("technology_steward must be non-empty.")
        if not self.business_justification.strip():
            raise ValueError("business_justification must be non-empty.")
        if self.review_interval_days < 1:
            raise ValueError("review_interval_days must be at least one.")
        if not self.retirement_criteria:
            raise ValueError("retirement_criteria must not be empty.")


@dataclass(frozen=True, slots=True)
class ExecutionProvider:
    provider_id: str
    display_name: str
    provider_type: ProviderType
    lifecycle_status: ProviderLifecycle
    health_status: ProviderHealth
    approval_status: ProviderApproval
    execution_modes: frozenset[str]
    capabilities: frozenset[str]
    supported_classifications: frozenset[str]
    regions: frozenset[str]
    limits: ProviderLimits
    features: ProviderFeatures
    pricing_profile_id: str | None
    stewardship: ProviderStewardship
    created_at: datetime
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.provider_id.strip():
            raise ValueError("provider_id must be non-empty.")
        if not self.display_name.strip():
            raise ValueError("display_name must be non-empty.")
        if not self.execution_modes:
            raise ValueError("execution_modes must not be empty.")
        if not self.capabilities:
            raise ValueError("capabilities must not be empty.")
        if not self.supported_classifications:
            raise ValueError("supported_classifications must not be empty.")


@dataclass(frozen=True, slots=True)
class ProviderCandidateQuery:
    capability: str
    execution_mode: str | None = None
    classification: str | None = None
    region: str | None = None
    include_warning: bool = False
    include_deprecated: bool = False
    allow_pilot: bool = False

    def __post_init__(self) -> None:
        if not self.capability.strip():
            raise ValueError("capability must be non-empty.")
