"""Request-scoped model usage context propagation.

This context carries accounting correlation only. It grants no authority and may
not be used by a model/provider to select scope, capabilities, or execution.
"""

from __future__ import annotations

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


def new_attempt_context(*, parent_attempt_id: str | None = None) -> UsageContext | None:
    """Return the bound scope with a fresh idempotent provider-attempt identity."""

    current = _CURRENT.get()
    if current is None:
        return None
    return replace(
        current,
        attempt_id=str(uuid4()),
        parent_attempt_id=parent_attempt_id,
    )
