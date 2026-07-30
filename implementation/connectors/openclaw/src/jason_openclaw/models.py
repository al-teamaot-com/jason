from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping


class ConnectorContractError(ValueError):
    """Raised when an OpenClaw request violates the connector contract."""


@dataclass(frozen=True, slots=True)
class OpenClawPrincipal:
    principal_id: str
    channel: str
    external_user_id: str
    organization_id: str
    client_id: str | None = None
    authentication_assurance: str = "external_authenticated"


@dataclass(frozen=True, slots=True)
class CapabilityRequest:
    request_id: str
    correlation_id: str
    capability: str
    arguments: Mapping[str, Any]
    principal: OpenClawPrincipal
    requested_mode: str = "observe"
    requested_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "CapabilityRequest":
        required = {"request_id", "correlation_id", "capability", "arguments", "principal"}
        missing = sorted(required - payload.keys())
        if missing:
            raise ConnectorContractError(f"Missing required fields: {', '.join(missing)}")

        capability = str(payload["capability"]).strip()
        if not capability or capability.startswith("http") or "/" in capability:
            raise ConnectorContractError("A registered logical capability name is required.")

        arguments = payload["arguments"]
        if not isinstance(arguments, Mapping):
            raise ConnectorContractError("arguments must be an object.")

        principal_payload = payload["principal"]
        if not isinstance(principal_payload, Mapping):
            raise ConnectorContractError("principal must be an object.")

        principal_required = {"principal_id", "channel", "external_user_id", "organization_id"}
        principal_missing = sorted(principal_required - principal_payload.keys())
        if principal_missing:
            raise ConnectorContractError(
                f"Missing principal fields: {', '.join(principal_missing)}"
            )

        requested_mode = str(payload.get("requested_mode", "observe"))
        if requested_mode not in {"observe", "recommend", "request_approval", "execute"}:
            raise ConnectorContractError("Unsupported requested_mode.")

        principal = OpenClawPrincipal(
            principal_id=str(principal_payload["principal_id"]),
            channel=str(principal_payload["channel"]),
            external_user_id=str(principal_payload["external_user_id"]),
            organization_id=str(principal_payload["organization_id"]),
            client_id=(
                str(principal_payload["client_id"])
                if principal_payload.get("client_id") is not None
                else None
            ),
            authentication_assurance=str(
                principal_payload.get("authentication_assurance", "external_authenticated")
            ),
        )

        return cls(
            request_id=str(payload["request_id"]),
            correlation_id=str(payload["correlation_id"]),
            capability=capability,
            arguments=dict(arguments),
            principal=principal,
            requested_mode=requested_mode,
        )


@dataclass(frozen=True, slots=True)
class CapabilityResponse:
    request_id: str
    correlation_id: str
    status: str
    capability: str
    result: Mapping[str, Any] | None = None
    error_code: str | None = None
    message: str | None = None
    approval_id: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "correlation_id": self.correlation_id,
            "status": self.status,
            "capability": self.capability,
            "result": dict(self.result) if self.result is not None else None,
            "error_code": self.error_code,
            "message": self.message,
            "approval_id": self.approval_id,
        }
