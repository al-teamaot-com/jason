from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol


class ConnectorError(RuntimeError):
    """Base error safe for internal classification, not direct user display."""


class ConnectorAuthorizationError(ConnectorError):
    pass


class ConnectorConfigurationError(ConnectorError):
    pass


class ConnectorTransportError(ConnectorError):
    pass


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
