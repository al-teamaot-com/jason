from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator, Mapping, Protocol

from kernel.execution_deadline import (
    GovernedExecutionDeadlineExceeded,
    bounded_execution_timeout,
    governed_execution_deadline,
)


class ConnectorError(RuntimeError):
    """Base error safe for internal classification, not direct user display."""

    error_code = "CONNECTOR_FAILURE"


class ConnectorAuthorizationError(ConnectorError):
    error_code = "CONNECTOR_AUTHORIZATION_DENIED"


class ConnectorConfigurationError(ConnectorError):
    error_code = "CONNECTOR_CONFIGURATION_ERROR"


class ConnectorCredentialUnavailableError(ConnectorConfigurationError):
    """Local credential bootstrap material is unavailable to this process."""

    error_code = "CONNECTOR_CREDENTIAL_UNAVAILABLE"


class ConnectorTransportError(ConnectorError):
    """Transport failure with bounded, non-secret diagnostic metadata.

    Provider-supplied diagnostic fields are captured only after transport-level
    sanitization. They are suitable for governed troubleshooting and bounded
    operator presentation, but raw HTTP response bodies, headers, credentials,
    and tokens are never retained on the exception.
    """

    error_code = "PROVIDER_TRANSPORT_FAILURE"

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retry_after_seconds: float | None = None,
        service: str | None = None,
        provider_error_type: str | None = None,
        provider_error_code: str | None = None,
        provider_error_param: str | None = None,
        provider_error_message: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retry_after_seconds = retry_after_seconds
        self.service = service
        self.provider_error_type = provider_error_type
        self.provider_error_code = provider_error_code
        self.provider_error_param = provider_error_param
        self.provider_error_message = provider_error_message
        if status_code is not None and type(self) is ConnectorTransportError:
            if 100 <= status_code <= 599:
                self.error_code = f"PROVIDER_HTTP_STATUS_{status_code}"
            else:
                self.error_code = "PROVIDER_HTTP_ERROR"


class ConnectorExecutionDeadlineExceeded(ConnectorTransportError):
    """Raised when governed connector execution has exhausted its deadline."""

    error_code = "PROVIDER_EXECUTION_DEADLINE_EXCEEDED"


@contextmanager
def connector_execution_deadline(maximum_execution_seconds: float | None) -> Iterator[None]:
    """Apply a connector deadline without extending an active governed deadline."""
    with governed_execution_deadline(maximum_execution_seconds):
        yield


def bounded_transport_timeout(requested_timeout_seconds: float) -> float:
    """Clamp a transport timeout to the remaining governed connector deadline."""
    try:
        return bounded_execution_timeout(requested_timeout_seconds)
    except GovernedExecutionDeadlineExceeded as error:
        raise ConnectorExecutionDeadlineExceeded(str(error)) from None


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
    ) -> Any: ...

    def request_bytes(
        self,
        *,
        method: str,
        url: str,
        headers: Mapping[str, str],
        params: Mapping[str, Any] | None = None,
        timeout_seconds: float = 30.0,
        max_bytes: int,
    ) -> bytes: ...


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
