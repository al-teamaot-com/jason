"""Provider-neutral alert projection for readiness transitions.

This module formats an alert payload only.

It does not select a delivery provider and does not send a message.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .provider_capability_readiness_store import (
    ProviderReadinessAlertEvent,
)


@dataclass(frozen=True, slots=True)
class ProviderReadinessAlertProjection:
    event_type: str
    title: str
    summary: str
    details: Mapping[str, str]


def project_readiness_alert(
    *,
    event: ProviderReadinessAlertEvent,
    runtime_state: str,
) -> ProviderReadinessAlertProjection:
    runtime = str(
        runtime_state
    ).strip().upper()

    if not runtime:
        raise ValueError(
            "runtime_state is required"
        )

    if (
        event.event_kind
        == "provider_capability_recovered"
    ):
        title = (
            "Provider capability recovered"
        )

        summary = (
            f"{event.provider_id} recovered for "
            f"{event.capability_name}."
        )

    else:
        title = (
            "Provider capability unavailable"
        )

        summary = (
            f"{event.provider_id} is unavailable for "
            f"{event.capability_name}."
        )

    details = {
        "provider_id":
            event.provider_id,
        "capability_name":
            event.capability_name,
        "jason_runtime_state":
            runtime,
        "provider_readiness_state":
            event.readiness_state.value.upper(),
        "reason":
            event.reason.value,
        "observed_at":
            event.observed_at.isoformat(),
    }

    if event.provider_status_code:
        details = {
            **details,
            "provider_status_code":
                event.provider_status_code,
        }

    return ProviderReadinessAlertProjection(
        event_type=event.event_kind,
        title=title,
        summary=summary,
        details=details,
    )
