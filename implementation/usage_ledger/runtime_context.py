"""Request-scoped model usage context propagation.

This context carries accounting correlation only. It grants no authority and may
not be used by a model/provider to select scope, capabilities, or execution.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import replace
from typing import Iterator
from uuid import uuid4

from .contracts import UsageContext


_CURRENT: ContextVar[UsageContext | None] = ContextVar(
    "jason_model_usage_context", default=None
)


@contextmanager
def bind_usage_context(context: UsageContext) -> Iterator[None]:
    """Bind one governed human/workflow scope for nested model attempts."""

    token = _CURRENT.set(context)
    try:
        yield
    finally:
        _CURRENT.reset(token)


def _attribution_projection() -> UsageContext | None:
    """Use the generic attribution scope when no legacy model scope is bound.

    The import is intentionally lazy so the usage-ledger package remains usable on
    its own and older runtime paths can continue binding UsageContext directly.
    """

    try:
        from usage_attribution.runtime_context import model_usage_context
    except ImportError:
        return None
    return model_usage_context()


def _unattributed_runtime_context() -> UsageContext:
    """Retain otherwise-unattributed model consumption instead of dropping it.

    This is intentionally low-confidence accounting metadata. It never supplies
    authority or execution scope; it only ensures that a provider call made without
    a bound human/workload context still creates an immutable ledger entry that the
    dashboard can flag as an attribution gap.
    """

    request_id = f"unattributed-{uuid4()}"
    organization_id = os.getenv("JASON_ORGANIZATION_ID", "aot").strip() or "aot"
    return UsageContext(
        workflow_id="unattributed-runtime",
        request_id=request_id,
        attempt_id=str(uuid4()),
        organization_id=organization_id,
        client_id=None,
        capability="unknown",
        routing_profile="unattributed-runtime",
        metadata={
            "actor_type": "unknown",
            "actor_id": "unknown",
            "source_channel": "unknown",
            "purpose": "unattributed model invocation",
            "attribution_quality": "unavailable",
        },
    )


def new_attempt_context(*, parent_attempt_id: str | None = None) -> UsageContext:
    """Return an attributable attempt scope, retaining unknown usage when necessary."""

    current = _CURRENT.get() or _attribution_projection() or _unattributed_runtime_context()
    return replace(
        current,
        attempt_id=str(uuid4()),
        parent_attempt_id=parent_attempt_id,
    )
