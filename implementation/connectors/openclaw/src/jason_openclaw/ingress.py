from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Protocol

from kernel.identity_authority import (
    DelegationValidationRequest,
    DelegationValidator,
    PermissionMode,
)

from .connector import OpenClawConnector


class TransportAuthenticator(Protocol):
    def authenticate(self, envelope: Mapping[str, Any]) -> str: ...


class IngressAuditSink(Protocol):
    def append(self, event_type: str, payload: Mapping[str, Any]) -> None: ...


@dataclass(frozen=True, slots=True)
class GovernedOpenClawIngress:
    connector: OpenClawConnector
    authenticator: TransportAuthenticator
    audit: IngressAuditSink
    machine_principal_bindings: Mapping[str, str] = field(default_factory=dict)
    require_machine_principal_binding: bool = True
    delegation_validator: DelegationValidator | None = None
    max_clock_skew_seconds: int = 60

    def handle(self, envelope: Mapping[str, Any]) -> dict[str, Any]:
        request_id = str(envelope.get("request_id", "unknown"))
        correlation_id = str(envelope.get("correlation_id", "unknown"))

        try:
            machine_identity = self.authenticator.authenticate(envelope)
        except Exception:
            self.audit.append(
                "openclaw.transport_denied",
                {
                    "request_id": request_id,
                    "correlation_id": correlation_id,
                    "reason": "transport_authentication_failed",
                },
            )
            return {
                "request_id": request_id,
                "correlation_id": correlation_id,
                "status": "rejected",
                "error_code": "transport_authentication_failed",
                "message": "OpenClaw transport authentication failed.",
            }

        freshness_error = self._validate_freshness(envelope)
        if freshness_error is not None:
            return self._deny(request_id, correlation_id, machine_identity, freshness_error,
                              "OpenClaw request freshness validation failed.")

        binding_error, delegation_id = self._validate_machine_principal_binding(
            machine_identity,
            envelope,
        )
        if binding_error is not None:
            return self._deny(request_id, correlation_id, machine_identity, binding_error,
                              "OpenClaw machine identity is not authorized to assert this principal.")

        self.audit.append(
            "openclaw.transport_authenticated",
            {
                "request_id": request_id,
                "correlation_id": correlation_id,
                "machine_identity": machine_identity,
                "delegation_id": delegation_id,
            },
        )
        return self.connector.handle(envelope)

    def _deny(
        self,
        request_id: str,
        correlation_id: str,
        machine_identity: str,
        reason: str,
        message: str,
    ) -> dict[str, Any]:
        self.audit.append(
            "openclaw.transport_denied",
            {
                "request_id": request_id,
                "correlation_id": correlation_id,
                "machine_identity": machine_identity,
                "reason": reason,
            },
        )
        return {
            "request_id": request_id,
            "correlation_id": correlation_id,
            "status": "rejected",
            "error_code": reason,
            "message": message,
        }

    def _validate_machine_principal_binding(
        self,
        machine_identity: str,
        envelope: Mapping[str, Any],
    ) -> tuple[str | None, str | None]:
        if not self.require_machine_principal_binding:
            return None, None
        bound_principal = self.machine_principal_bindings.get(machine_identity)
        if bound_principal is None:
            return "machine_principal_binding_missing", None
        principal = envelope.get("principal")
        if not isinstance(principal, Mapping):
            return "machine_principal_binding_invalid", None
        asserted_principal = str(principal.get("principal_id", "")).strip()
        if asserted_principal == bound_principal:
            return None, None

        delegation_id = str(envelope.get("delegation_id", "")).strip()
        if not delegation_id:
            return "delegation_required", None
        if self.delegation_validator is None:
            return "delegation_validation_unavailable", delegation_id

        try:
            requested_mode = PermissionMode(str(envelope.get("requested_mode", "observe")))
        except ValueError:
            return "delegation_mode_invalid", delegation_id

        result = self.delegation_validator.validate(
            DelegationValidationRequest(
                delegation_id=delegation_id,
                delegator_id=asserted_principal,
                delegate_id=bound_principal,
                organization_id=str(principal.get("organization_id", "")),
                client_id=(
                    str(principal["client_id"])
                    if principal.get("client_id") is not None
                    else None
                ),
                capability=str(envelope.get("capability", "")),
                requested_mode=requested_mode,
            )
        )
        if not result.valid:
            return result.reason_code.lower(), delegation_id
        return None, delegation_id

    def _validate_freshness(self, envelope: Mapping[str, Any]) -> str | None:
        issued_at_raw = envelope.get("issued_at")
        expires_at_raw = envelope.get("expires_at")
        nonce = str(envelope.get("nonce", "")).strip()
        if not issued_at_raw or not expires_at_raw or not nonce:
            return "transport_metadata_missing"

        try:
            issued_at = _parse_utc(str(issued_at_raw))
            expires_at = _parse_utc(str(expires_at_raw))
        except ValueError:
            return "transport_timestamp_invalid"

        now = datetime.now(timezone.utc)
        skew = self.max_clock_skew_seconds
        if issued_at.timestamp() > now.timestamp() + skew:
            return "request_not_yet_valid"
        if expires_at <= issued_at:
            return "request_expiry_invalid"
        if now.timestamp() > expires_at.timestamp() + skew:
            return "request_expired"
        return None


def _parse_utc(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return parsed.astimezone(timezone.utc)
