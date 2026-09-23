"""Request-scoped resource attribution context.

This module carries accounting/audit correlation only. It grants no authority and
must never be used to select capabilities, providers, organization/client scope, or
permission mode.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import replace
from typing import Iterator
from uuid import uuid4

from usage_ledger.contracts import UsageContext

from .contracts import AttributionContext


_CURRENT: ContextVar[AttributionContext | None] = ContextVar(
    "jason_usage_attribution_context",
    default=None,
)


@contextmanager
def bind_attribution_context(context: AttributionContext) -> Iterator[None]:
    """Bind one authenticated human/workload attribution scope for nested usage."""

    token = _CURRENT.set(context)
    try:
        yield
    finally:
        _CURRENT.reset(token)


def current_attribution_context() -> AttributionContext | None:
    return _CURRENT.get()


def child_attribution_context(
    *,
    capability: str | None = None,
    purpose: str | None = None,
    provider_request_id: str | None = None,
) -> AttributionContext | None:
    """Return a narrowed accounting scope while retaining the originating actor."""

    current = _CURRENT.get()
    if current is None:
        return None

    metadata = dict(current.metadata)
    if provider_request_id:
        metadata["provider_request_id"] = provider_request_id

    return replace(
        current,
        capability=(capability or current.capability).strip(),
        purpose=(purpose or current.purpose).strip(),
        metadata=metadata,
    )


def model_usage_context(
    *,
    capability: str | None = None,
    purpose: str | None = None,
    agent_name: str | None = None,
) -> UsageContext | None:
    """Project the bound actor scope into the existing model usage ledger contract."""

    current = child_attribution_context(capability=capability, purpose=purpose)
    if current is None:
        return None

    metadata = dict(current.metadata)
    metadata.update(
        {
            "correlation_id": current.correlation_id,
            "actor_type": current.actor_type.value,
            "actor_id": current.actor_id,
            "source_channel": current.source_channel,
            "purpose": current.purpose,
        }
    )
    if current.display_name:
        metadata["display_name"] = current.display_name
    if current.email_address:
        metadata["email_address"] = current.email_address
    if current.workload_name:
        metadata["workload_name"] = current.workload_name

    return UsageContext(
        workflow_id=(current.workflow_id or current.correlation_id),
        request_id=current.request_id,
        attempt_id=str(uuid4()),
        organization_id=current.organization_id,
        client_id=current.client_id,
        capability=current.capability,
        agent_name=agent_name or current.workload_name,
        routing_profile=current.source_channel,
        metadata=metadata,
    )
