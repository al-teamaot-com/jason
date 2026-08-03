from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Mapping

from connectors.core.contracts import (
    AuditSink,
    ConnectorRequest,
    ConnectorResult,
    HttpTransport,
    SecretResolver,
    require_capability,
)


@dataclass(frozen=True)
class PreparedRequest:
    method: str
    url: str
    headers: Mapping[str, str]
    params: Mapping[str, Any] | None = None
    json: Mapping[str, Any] | None = None
    timeout_seconds: float = 30.0
    audit_operation: str | None = None


class ConnectorBase(ABC):
    provider_name: str
    capabilities: frozenset[str]
    logical_secret: str

    def __init__(
        self,
        secrets: SecretResolver,
        transport: HttpTransport,
        audit: AuditSink,
    ) -> None:
        self._secrets = secrets
        self._transport = transport
        self._audit = audit

    def execute(self, request: ConnectorRequest) -> ConnectorResult:
        require_capability(request, self.capabilities)

        credentials = self._secrets.resolve(
            self.logical_secret,
            request.context,
        )

        prepared = self.prepare_request(
            request,
            credentials,
        )

        operation = prepared.audit_operation or prepared.url

        self._audit.record(
            "connector.requested",
            request.context,
            {
                "provider": self.provider_name,
                "operation": operation,
            },
        )

        payload = self._transport.request(
            method=prepared.method,
            url=prepared.url,
            headers=prepared.headers,
            params=prepared.params,
            json=prepared.json,
            timeout_seconds=prepared.timeout_seconds,
        )

        self._audit.record(
            "connector.completed",
            request.context,
            {
                "provider": self.provider_name,
            },
        )

        return ConnectorResult(
            capability=request.context.capability,
            provider=self.provider_name,
            data=payload,
        )

    @abstractmethod
    def prepare_request(
        self,
        request: ConnectorRequest,
        credentials: Mapping[str, str],
    ) -> PreparedRequest:
        """Translate an authorized capability into a provider request."""
