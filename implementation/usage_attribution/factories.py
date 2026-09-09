"""Safe factories for request-scoped usage attribution.

Factories accept only already-authenticated/bound identity or explicit workload
identity. They do not perform authentication or grant authority.
"""

from __future__ import annotations

from .contracts import ActorType, AttributionContext


def human_attribution(
    *,
    organization_id: str,
    correlation_id: str,
    request_id: str,
    principal_id: str,
    source_channel: str,
    purpose: str,
    capability: str,
    client_id: str | None = None,
    display_name: str | None = None,
    email_address: str | None = None,
    workflow_id: str | None = None,
) -> AttributionContext:
    return AttributionContext(
        organization_id=organization_id,
        correlation_id=correlation_id,
        request_id=request_id,
        actor_type=ActorType.HUMAN,
        actor_id=principal_id,
        source_channel=source_channel,
        purpose=purpose,
        capability=capability,
        client_id=client_id,
        display_name=display_name,
        email_address=email_address,
        workflow_id=workflow_id,
    )


def workload_attribution(
    *,
    organization_id: str,
    correlation_id: str,
    request_id: str,
    workload_id: str,
    workload_name: str,
    source_channel: str,
    purpose: str,
    capability: str,
    actor_type: ActorType = ActorType.SERVICE,
    client_id: str | None = None,
    workflow_id: str | None = None,
) -> AttributionContext:
    if actor_type not in {
        ActorType.SERVICE,
        ActorType.AGENT,
        ActorType.SCHEDULED_PROCESS,
        ActorType.SYSTEM,
    }:
        raise ValueError("workload attribution requires a non-human actor type")
    return AttributionContext(
        organization_id=organization_id,
        correlation_id=correlation_id,
        request_id=request_id,
        actor_type=actor_type,
        actor_id=workload_id,
        source_channel=source_channel,
        purpose=purpose,
        capability=capability,
        client_id=client_id,
        workload_name=workload_name,
        workflow_id=workflow_id,
    )
