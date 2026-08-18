from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from time import monotonic
from typing import Any, Iterator, Mapping, Protocol


class ConnectorError(RuntimeError):
    """Base error safe for internal classification, not direct user display."""


class ConnectorAuthorizationError(ConnectorError):
    pass


class ConnectorConfigurationError(ConnectorError):
    pass


class ConnectorTransportError(ConnectorError):
    pass


class ConnectorExecutionDeadlineExceeded(ConnectorTransportError):
    """Raised when governed connector execution has exhausted its deadline."""

    error_code = "PROVIDER_EXECUTION_DEADLINE_EXCEEDED"


_EXECUTION_DEADLINE_MONOTONIC: ContextVar[float | None] = ContextVar(
    "connector_execution_deadline_monotonic",
    default=None,
)


@contextmanager
def connector_execution_deadline(maximum_execution_seconds: float | None) -> Iterator[None]:
    """Apply one bounded deadline across every transport call in a connector invocation."""
    if maximum_execution_seconds is None:
        yield
        return
    if maximum_execution_seconds <= 0:
        raise ValueError("maximum_execution_seconds must be positive when provided")
    token = _EXECUTION_DEADLINE_MONOTONIC.set(monotonic() + maximum_execution_seconds)
    try:
        yield
    finally:
        _EXECUTION_DEADLINE_MONOTONIC.reset(token)


def bounded_transport_timeout(requested_timeout_seconds: float) -> float:
    """Clamp a transport timeout to the remaining governed connector deadline."""
    if requested_timeout_seconds <= 0:
        raise ValueError("requested_timeout_seconds must be positive")
    deadline = _EXECUTION_DEADLINE_MONOTONIC.get()
    if deadline is None:
        return requested_timeout_seconds
    remaining = deadline - monotonic()
    if remaining <= 0:
        raise ConnectorExecutionDeadlineExceeded(
            "governed provider execution deadline exceeded"
        )
    return min(requested_timeout_seconds, remaining)


@dataclass(frozen=True)
class ConnectorContext:
    correlation_id: str
    principal_id: str
    organization_id: str
    client_id: str | None
    capability: str
    mode: str = "observe"


@dataclass(frozen=True)
class ConnectorRequest:
    context: ConnectorContext
    arguments: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ConnectorResult:
    capability: str
    provider: str
    data: Mapping[str, Any]
    evidence_ids: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


class SecretResolver(Protocol):
    def resolve(self, logical_name: str, context: ConnectorContext) -> Mapping[str, str]: ...


class AuditSink(Protocol):
    def record(self, event_type: str, context: ConnectorContext, details: Mapping[str, Any]) -> None: ...


class HttpTransport(Protocol):
    def request(
        self,
        *,
        method: str,
        url: str,
        headers: Mapping[str, str],
        params: Mapping[str, Any] | None = None,
        json: Mapping[str, Any] | None = None,
        timeout_seconds: float = 30.0,
    ) -> Mapping[str, Any]: ...


class Connector(Protocol):
    provider_name: str
    capabilities: frozenset[str]

    def execute(self, request: ConnectorRequest) -> ConnectorResult: ...


def require_capability(request: ConnectorRequest, allowed: frozenset[str]) -> None:
    if request.context.capability not in allowed:
        raise ConnectorAuthorizationError(
            f"Capability is not registered for this connector: {request.context.capability}"
        )
    if request.context.mode != "observe":
        raise ConnectorAuthorizationError("This connector foundation is read-only.")
