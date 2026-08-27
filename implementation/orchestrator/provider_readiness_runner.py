"""Generic provider capability readiness runner.

The runner has no provider-specific knowledge and no alert delivery authority.

Responsibilities:
- execute a registered readiness probe;
- classify the resulting observation;
- compare against durable prior state;
- persist current state and transition evidence;
- return any pending alert event created by the transition.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .provider_capability_readiness import (
    ProviderCapabilityObservation,
    ProviderCapabilityReadiness,
    ReadinessTransition,
    classify_readiness,
    evaluate_transition,
)
from .provider_capability_readiness_store import (
    ProviderReadinessAlertEvent,
    SQLiteProviderCapabilityReadinessStore,
)


class ProviderCapabilityReadinessProbe(Protocol):
    def observe(
        self,
        *,
        provider_id: str,
        capability_name: str,
        component_healthy: bool = True,
    ) -> ProviderCapabilityObservation: ...


@dataclass(frozen=True, slots=True)
class ProviderReadinessRunResult:
    current: ProviderCapabilityReadiness
    transition: ReadinessTransition
    alert_event: ProviderReadinessAlertEvent | None


@dataclass(frozen=True, slots=True)
class ProviderCapabilityReadinessRunner:
    store: SQLiteProviderCapabilityReadinessStore

    def run_once(
        self,
        *,
        probe: ProviderCapabilityReadinessProbe,
        provider_id: str,
        capability_name: str,
        component_healthy: bool = True,
    ) -> ProviderReadinessRunResult:
        previous = self.store.get(
            provider_id=provider_id,
            capability_name=capability_name,
        )

        observation = probe.observe(
            provider_id=provider_id,
            capability_name=capability_name,
            component_healthy=component_healthy,
        )

        current = classify_readiness(
            observation
        )

        transition = evaluate_transition(
            previous=previous,
            current=current,
        )

        alert_event = self.store.record(
            transition=transition
        )

        return ProviderReadinessRunResult(
            current=current,
            transition=transition,
            alert_event=alert_event,
        )
