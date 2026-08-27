"""Provider-neutral operational readiness classification.

This module deliberately contains no provider-specific API knowledge.

Provider/connector adapters produce observations. This module classifies those
observations and determines whether an operational state transition occurred.
It has no execution authority and is not wired into the live request path.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Mapping


class ReadinessState(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    RECOVERING = "recovering"
    UNKNOWN = "unknown"


class ReadinessReason(str, Enum):
    NONE = "none"
    RUNTIME_UNHEALTHY = "runtime_unhealthy"
    DEPENDENCY_UNREACHABLE = "dependency_unreachable"
    AUTHENTICATION_FAILED = "authentication_failed"
    SECRET_UNAVAILABLE = "secret_unavailable"
    PERMISSION_DENIED = "permission_denied"
    QUOTA_EXHAUSTED = "quota_exhausted"
    RATE_LIMITED = "rate_limited"
    PROVIDER_TIMEOUT = "provider_timeout"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    CONTRACT_INCOMPATIBLE = "contract_incompatible"
    CAPABILITY_PROBE_FAILED = "capability_probe_failed"
    UNKNOWN_PROVIDER_FAILURE = "unknown_provider_failure"


@dataclass(frozen=True, slots=True)
class ReadinessDimension:
    checked: bool
    healthy: bool | None
    reason: ReadinessReason = ReadinessReason.NONE

    def __post_init__(self) -> None:
        if not self.checked and self.healthy is not None:
            raise ValueError(
                "unchecked readiness dimension cannot declare health"
            )

        if (
            self.checked
            and self.healthy is True
            and self.reason is not ReadinessReason.NONE
        ):
            raise ValueError(
                "healthy readiness dimension cannot declare a failure reason"
            )


@dataclass(frozen=True, slots=True)
class ProviderCapabilityObservation:
    provider_id: str
    capability_name: str
    observed_at: datetime
    component: ReadinessDimension
    reachability: ReadinessDimension
    authentication: ReadinessDimension
    capability: ReadinessDimension
    evidence_source: str
    probe_version: str
    provider_status_code: str | None = None
    safe_metadata: Mapping[str, str] | None = None

    def __post_init__(self) -> None:
        for name, value in {
            "provider_id": self.provider_id,
            "capability_name": self.capability_name,
            "evidence_source": self.evidence_source,
            "probe_version": self.probe_version,
        }.items():
            if not str(value).strip():
                raise ValueError(
                    f"{name} is required"
                )

        if self.observed_at.tzinfo is None:
            raise ValueError(
                "observed_at must be timezone-aware"
            )


@dataclass(frozen=True, slots=True)
class ProviderCapabilityReadiness:
    provider_id: str
    capability_name: str
    state: ReadinessState
    reason: ReadinessReason
    observed_at: datetime
    evidence_source: str
    provider_status_code: str | None = None


@dataclass(frozen=True, slots=True)
class ReadinessTransition:
    previous: ProviderCapabilityReadiness | None
    current: ProviderCapabilityReadiness
    changed: bool
    should_alert: bool
    recovery: bool


def classify_readiness(
    observation: ProviderCapabilityObservation,
) -> ProviderCapabilityReadiness:
    """Classify one provider-neutral readiness observation.

    Evaluation order is intentional: Jason-local component health precedes
    dependency reachability, which precedes authentication, which precedes
    actual capability execution.
    """

    dimensions = (
        observation.component,
        observation.reachability,
        observation.authentication,
        observation.capability,
    )

    for dimension in dimensions:
        if dimension.checked and dimension.healthy is False:
            reason = (
                dimension.reason
                if dimension.reason is not ReadinessReason.NONE
                else ReadinessReason.UNKNOWN_PROVIDER_FAILURE
            )

            return ProviderCapabilityReadiness(
                provider_id=observation.provider_id,
                capability_name=observation.capability_name,
                state=ReadinessState.UNAVAILABLE,
                reason=reason,
                observed_at=observation.observed_at,
                evidence_source=observation.evidence_source,
                provider_status_code=observation.provider_status_code,
            )

    if not all(
        dimension.checked
        for dimension in dimensions
    ):
        return ProviderCapabilityReadiness(
            provider_id=observation.provider_id,
            capability_name=observation.capability_name,
            state=ReadinessState.UNKNOWN,
            reason=ReadinessReason.NONE,
            observed_at=observation.observed_at,
            evidence_source=observation.evidence_source,
            provider_status_code=observation.provider_status_code,
        )

    return ProviderCapabilityReadiness(
        provider_id=observation.provider_id,
        capability_name=observation.capability_name,
        state=ReadinessState.HEALTHY,
        reason=ReadinessReason.NONE,
        observed_at=observation.observed_at,
        evidence_source=observation.evidence_source,
        provider_status_code=observation.provider_status_code,
    )


def evaluate_transition(
    *,
    previous: ProviderCapabilityReadiness | None,
    current: ProviderCapabilityReadiness,
) -> ReadinessTransition:
    """Determine alert semantics without sending an alert.

    Delivery remains the responsibility of a separately governed capability.
    """

    if previous is not None:
        if previous.provider_id != current.provider_id:
            raise ValueError(
                "provider readiness transition changed provider identity"
            )

        if previous.capability_name != current.capability_name:
            raise ValueError(
                "provider readiness transition changed capability identity"
            )

    changed = (
        previous is None
        or previous.state != current.state
        or previous.reason != current.reason
    )

    recovery = (
        previous is not None
        and previous.state
        in {
            ReadinessState.UNAVAILABLE,
            ReadinessState.DEGRADED,
            ReadinessState.RECOVERING,
            ReadinessState.UNKNOWN,
        }
        and current.state is ReadinessState.HEALTHY
    )

    should_alert = (
        changed
        and (
            current.state
            in {
                ReadinessState.UNAVAILABLE,
                ReadinessState.DEGRADED,
            }
            or recovery
        )
    )

    return ReadinessTransition(
        previous=previous,
        current=current,
        changed=changed,
        should_alert=should_alert,
        recovery=recovery,
    )
