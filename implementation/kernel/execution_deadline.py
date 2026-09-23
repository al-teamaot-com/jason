from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from time import monotonic
from typing import Iterator


class GovernedExecutionDeadlineExceeded(RuntimeError):
    """The shared governed provider-action deadline has been exhausted."""

    error_code = "PROVIDER_EXECUTION_DEADLINE_EXCEEDED"


_EXECUTION_DEADLINE_MONOTONIC: ContextVar[float | None] = ContextVar(
    "governed_execution_deadline_monotonic",
    default=None,
)


@contextmanager
def governed_execution_deadline(maximum_execution_seconds: float | None) -> Iterator[None]:
    """Apply a deadline that may tighten, but never extend, an existing deadline."""
    if maximum_execution_seconds is None:
        yield
        return
    if maximum_execution_seconds <= 0:
        raise ValueError("maximum_execution_seconds must be positive when provided")
    candidate = monotonic() + maximum_execution_seconds
    with governed_execution_deadline_at(candidate):
        yield


@contextmanager
def governed_execution_deadline_at(deadline_monotonic: float | None) -> Iterator[None]:
    """Apply one absolute deadline, preserving any earlier active deadline."""
    if deadline_monotonic is None:
        yield
        return
    current = _EXECUTION_DEADLINE_MONOTONIC.get()
    effective = min(current, deadline_monotonic) if current is not None else deadline_monotonic
    if effective <= monotonic():
        raise GovernedExecutionDeadlineExceeded(
            "governed provider execution deadline exceeded"
        )
    token = _EXECUTION_DEADLINE_MONOTONIC.set(effective)
    try:
        yield
    finally:
        _EXECUTION_DEADLINE_MONOTONIC.reset(token)


def bounded_execution_timeout(requested_timeout_seconds: float) -> float:
    """Clamp a timeout to the remaining shared governed execution deadline."""
    if requested_timeout_seconds <= 0:
        raise ValueError("requested_timeout_seconds must be positive")
    deadline = _EXECUTION_DEADLINE_MONOTONIC.get()
    if deadline is None:
        return requested_timeout_seconds
    remaining = deadline - monotonic()
    if remaining <= 0:
        raise GovernedExecutionDeadlineExceeded(
            "governed provider execution deadline exceeded"
        )
    return min(requested_timeout_seconds, remaining)
