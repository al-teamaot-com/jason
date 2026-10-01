from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
from uuid import UUID

from connectors.core.contracts import ConnectorTransportError, HttpTransport


EXCHANGE_READ_WORKER_URL = "http://jason-exchange-read-worker:8091/v1/read"

_ALLOWED_OPERATIONS = frozenset(
    {
        "message_trace.search",
        "message_trace.detail",
        "mailbox.forwarding.read",
        "mailbox.inbox_rules.read_hidden",
        "mailbox.full_access.read",
        "mailbox.send_as.read",
        "mailbox.send_on_behalf.read",
        "mailbox.transport_rules.read",
        "mailbox.mobile_devices.read",
        "mailbox.retention_audit_config.read",
    }
)

_ALLOWED_ARGUMENTS: dict[str, frozenset[str]] = {
    "message_trace.search": frozenset(
        {"sender", "recipients", "subject", "start", "end", "result_size"}
    ),
    "message_trace.detail": frozenset({"message_trace_id", "recipient"}),
    "mailbox.forwarding.read": frozenset({"mailbox"}),
    "mailbox.inbox_rules.read_hidden": frozenset({"mailbox"}),
    "mailbox.full_access.read": frozenset({"mailbox"}),
    "mailbox.send_as.read": frozenset({"mailbox"}),
    "mailbox.send_on_behalf.read": frozenset({"mailbox"}),
    "mailbox.transport_rules.read": frozenset(),
    "mailbox.mobile_devices.read": frozenset({"mailbox"}),
    "mailbox.retention_audit_config.read": frozenset({"mailbox"}),
}


class ExchangeWorkerProtocolError(RuntimeError):
    error_code = "MICROSOFT_EXCHANGE_WORKER_PROTOCOL_ERROR"


class ExchangeWorkerAuthorizationError(PermissionError):
    error_code = "MICROSOFT_EXCHANGE_WORKER_AUTHORIZATION_DENIED"


def read_worker_token(path: str | Path) -> str:
    token_path = Path(path)
    token = token_path.read_text(encoding="utf-8").strip()
    if not token:
        raise ExchangeWorkerAuthorizationError(
            "Exchange worker authentication token is unavailable."
        )
    return token


@dataclass(frozen=True, slots=True)
class ExchangeReadWorkerClient:
    transport: HttpTransport
    worker_token: str
    timeout_seconds: float = 45.0

    def __post_init__(self) -> None:
        if not self.worker_token.strip():
            raise ExchangeWorkerAuthorizationError(
                "Exchange worker authentication token is unavailable."
            )
        if self.timeout_seconds <= 0 or self.timeout_seconds > 120:
            raise ValueError("Exchange worker timeout must be between 0 and 120 seconds.")

    def execute(
        self,
        *,
        microsoft_tenant_id: str,
        organization: str,
        operation: str,
        arguments: Mapping[str, Any] | None = None,
        correlation_id: str,
    ) -> Mapping[str, Any]:
        tenant_id = self._tenant_id(microsoft_tenant_id)
        primary_domain = self._organization(organization)
        operation_name = operation.strip()
        if operation_name not in _ALLOWED_OPERATIONS:
            raise ExchangeWorkerProtocolError(
                "Exchange worker operation is not allowlisted."
            )

        supplied = dict(arguments or {})
        unsupported = set(supplied) - set(_ALLOWED_ARGUMENTS[operation_name])
        if unsupported:
            raise ExchangeWorkerProtocolError(
                "Exchange worker request contains unsupported arguments."
            )
        if not correlation_id.strip():
            raise ValueError("correlation_id is required")

        payload = {
            "tenant_id": tenant_id,
            "organization": primary_domain,
            "operation": operation_name,
            "arguments": supplied,
            "correlation_id": correlation_id.strip(),
        }
        response = self.transport.request(
            method="POST",
            url=EXCHANGE_READ_WORKER_URL,
            headers={
                "Authorization": f"Bearer {self.worker_token.strip()}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout_seconds=self.timeout_seconds,
        )
        if not isinstance(response, Mapping):
            raise ConnectorTransportError(
                "Exchange read worker returned an unexpected response shape",
                service="microsoft_exchange_online",
            )
        if response.get("ok") is not True:
            code = str(response.get("error_code") or "EXCHANGE_WORKER_FAILURE")
            raise ConnectorTransportError(
                "Exchange read worker operation failed",
                service="microsoft_exchange_online",
                provider_error_code=code,
            )
        data = response.get("data")
        if not isinstance(data, Mapping):
            raise ConnectorTransportError(
                "Exchange read worker returned invalid result data",
                service="microsoft_exchange_online",
            )
        return data

    @staticmethod
    def _tenant_id(value: str) -> str:
        try:
            return str(UUID(value.strip()))
        except (AttributeError, ValueError) as error:
            raise ExchangeWorkerProtocolError(
                "Microsoft tenant identifier is invalid."
            ) from error

    @staticmethod
    def _organization(value: str) -> str:
        organization = value.strip().casefold()
        if (
            not organization.endswith(".onmicrosoft.com")
            or organization.count("@")
            or "/" in organization
            or "\\" in organization
            or len(organization) > 253
        ):
            raise ExchangeWorkerProtocolError(
                "Exchange organization must be the validated primary onmicrosoft.com domain."
            )
        return organization
