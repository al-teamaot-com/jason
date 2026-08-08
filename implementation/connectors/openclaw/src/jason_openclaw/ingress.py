from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Protocol

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
            self.audit.append(
                "openclaw.transport_denied",
                {
                    "request_id": request_id,
                    "correlation_id": correlation_id,
                    "machine_identity": machine_identity,
                    "reason": freshness_error,
                },
            )
            return {
                "request_id": request_id,
                "correlation_id": correlation_id,
                "status": "rejected",
                "error_code": freshness_error,
                "message": "OpenClaw request freshness validation failed.",
            }

        self.audit.append(
            "openclaw.transport_authenticated",
            {
                "request_id": request_id,
                "correlation_id": correlation_id,
                "machine_identity": machine_identity,
            },
        )
        return self.connector.handle(envelope)

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
