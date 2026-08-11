from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Protocol

from orchestrator.teams_conversation_flow import (
    TeamsConversationFlowResult,
    TeamsConversationPrincipalEvidence,
    TeamsConversationRequest,
)


class ConversationTransportAuthenticator(Protocol):
    def authenticate(self, envelope: Mapping[str, Any]) -> str: ...


class ConversationReplayStore(Protocol):
    def claim(self, request_id: str) -> bool: ...


class ConversationAuditSink(Protocol):
    def append(self, event_type: str, payload: Mapping[str, Any]) -> None: ...


class GovernedConversationFlow(Protocol):
    def handle(self, request: TeamsConversationRequest) -> TeamsConversationFlowResult: ...


@dataclass(frozen=True, slots=True)
class OpenClawTeamsConversationEnvelope:
    request_id: str
    correlation_id: str
    issued_at: datetime
    expires_at: datetime
    nonce: str
    text: str
    microsoft_tenant_id: str
    microsoft_object_id: str
    authentication_assurance: str
    conversation_id: str
    message_id: str

    @classmethod
    def from_mapping(cls, envelope: Mapping[str, Any]) -> "OpenClawTeamsConversationEnvelope":
        if str(envelope.get("kind", "")).strip() != "conversation.turn":
            raise ValueError("conversation envelope kind is invalid")
        if str(envelope.get("channel", "")).strip() != "msteams":
            raise ValueError("conversation envelope channel is not supported")

        forbidden = {
            "principal",
            "principal_id",
            "organization_id",
            "client_id",
            "capability",
            "capability_name",
            "provider",
            "provider_id",
            "connector",
            "connector_id",
            "arguments",
            "shell",
            "shell_command",
            "target_agent",
            "agent_endpoint",
            "invoke_agent",
        }
        present = sorted(forbidden.intersection(envelope))
        if present:
            raise PermissionError(
                "conversation transport cannot assert Jason authority or execution routing: "
                + ", ".join(present)
            )

        transport_identity = envelope.get("transport_identity")
        if not isinstance(transport_identity, Mapping):
            raise ValueError("conversation transport_identity object is required")
        identity_forbidden = {
            "principal_id",
            "organization_id",
            "client_id",
            "capability",
            "provider",
            "connector",
            "target_agent",
        }
        identity_present = sorted(identity_forbidden.intersection(transport_identity))
        if identity_present:
            raise PermissionError(
                "transport identity cannot assert Jason scope or routing: "
                + ", ".join(identity_present)
            )

        values = {
            "request_id": str(envelope.get("request_id", "")).strip(),
            "correlation_id": str(envelope.get("correlation_id", "")).strip(),
            "nonce": str(envelope.get("nonce", "")).strip(),
            "text": str(envelope.get("text", "")).strip(),
            "microsoft_tenant_id": str(
                transport_identity.get("microsoft_tenant_id", "")
            ).strip(),
            "microsoft_object_id": str(
                transport_identity.get("microsoft_object_id", "")
            ).strip(),
            "authentication_assurance": str(
                transport_identity.get("authentication_assurance", "")
            ).strip(),
            "conversation_id": str(envelope.get("conversation_id", "")).strip(),
            "message_id": str(envelope.get("message_id", "")).strip(),
        }
        missing = sorted(name for name, value in values.items() if not value)
        if missing:
            raise ValueError(
                "conversation envelope fields are empty: " + ", ".join(missing)
            )
        if values["authentication_assurance"] != "botframework-authenticated":
            raise PermissionError(
                "Teams conversation requires Bot Framework authenticated identity evidence"
            )

        issued_at = _parse_utc(str(envelope.get("issued_at", "")))
        expires_at = _parse_utc(str(envelope.get("expires_at", "")))
        return cls(
            request_id=values["request_id"],
            correlation_id=values["correlation_id"],
            issued_at=issued_at,
            expires_at=expires_at,
            nonce=values["nonce"],
            text=values["text"],
            microsoft_tenant_id=values["microsoft_tenant_id"],
            microsoft_object_id=values["microsoft_object_id"],
            authentication_assurance=values["authentication_assurance"],
            conversation_id=values["conversation_id"],
            message_id=values["message_id"],
        )


@dataclass(frozen=True, slots=True)
class GovernedOpenClawTeamsConversationIngress:
    """Authenticate an OpenClaw Teams turn and hand only identity evidence/text to Jason.

    OpenClaw may attest the Microsoft transport identity only after Bot Framework
    authentication. It may not assert a Jason principal, organization, client,
    capability, provider, shell command, or agent route. Jason derives those through
    its own identity, planning, authority, policy, and orchestration boundaries.
    """

    authenticator: ConversationTransportAuthenticator
    replay: ConversationReplayStore
    audit: ConversationAuditSink
    flow: GovernedConversationFlow
    allowed_machine_identities: frozenset[str]
    max_clock_skew_seconds: int = 60

    def handle(self, envelope: Mapping[str, Any]) -> dict[str, Any]:
        request_id = str(envelope.get("request_id", "unknown"))
        correlation_id = str(envelope.get("correlation_id", "unknown"))

        try:
            machine_identity = self.authenticator.authenticate(envelope)
        except Exception:
            return self._reject(
                request_id=request_id,
                correlation_id=correlation_id,
                reason="transport_authentication_failed",
            )
        if machine_identity not in self.allowed_machine_identities:
            return self._reject(
                request_id=request_id,
                correlation_id=correlation_id,
                reason="machine_identity_not_allowed",
                machine_identity=machine_identity,
            )

        try:
            parsed = OpenClawTeamsConversationEnvelope.from_mapping(envelope)
        except PermissionError:
            return self._reject(
                request_id=request_id,
                correlation_id=correlation_id,
                reason="transport_authority_assertion_forbidden",
                machine_identity=machine_identity,
            )
        except (TypeError, ValueError):
            return self._reject(
                request_id=request_id,
                correlation_id=correlation_id,
                reason="invalid_conversation_contract",
                machine_identity=machine_identity,
            )

        freshness_error = self._freshness_error(parsed)
        if freshness_error is not None:
            return self._reject(
                request_id=parsed.request_id,
                correlation_id=parsed.correlation_id,
                reason=freshness_error,
                machine_identity=machine_identity,
            )
        if not self.replay.claim(parsed.request_id):
            return self._reject(
                request_id=parsed.request_id,
                correlation_id=parsed.correlation_id,
                reason="replay_detected",
                machine_identity=machine_identity,
            )

        self.audit.append(
            "openclaw.teams_conversation_authenticated",
            {
                "request_id": parsed.request_id,
                "correlation_id": parsed.correlation_id,
                "machine_identity": machine_identity,
                "microsoft_tenant_id": parsed.microsoft_tenant_id,
                "microsoft_object_id": parsed.microsoft_object_id,
                "conversation_id": parsed.conversation_id,
                "message_id": parsed.message_id,
            },
        )

        request = TeamsConversationRequest(
            text=parsed.text,
            identity=TeamsConversationPrincipalEvidence(
                microsoft_tenant_id=parsed.microsoft_tenant_id,
                microsoft_object_id=parsed.microsoft_object_id,
                authentication_assurance=parsed.authentication_assurance,
                conversation_id=parsed.conversation_id,
                message_id=parsed.message_id,
            ),
        )
        try:
            result = self.flow.handle(request)
        except PermissionError as error:
            if getattr(error, "code", None) == "APPROVAL_REQUIRED":
                self.audit.append(
                    "openclaw.teams_conversation_approval_required",
                    {
                        "request_id": parsed.request_id,
                        "correlation_id": parsed.correlation_id,
                        "machine_identity": machine_identity,
                    },
                )
                return {
                    "request_id": parsed.request_id,
                    "correlation_id": parsed.correlation_id,
                    "status": "approval_required",
                    "error_code": "approval_required",
                }
            return self._deny(
                parsed=parsed,
                machine_identity=machine_identity,
                reason="conversation_denied",
            )
        except LookupError:
            return self._reject(
                request_id=parsed.request_id,
                correlation_id=parsed.correlation_id,
                reason="conversation_unresolved",
                machine_identity=machine_identity,
            )
        except Exception:
            self.audit.append(
                "openclaw.teams_conversation_failed",
                {
                    "request_id": parsed.request_id,
                    "correlation_id": parsed.correlation_id,
                    "machine_identity": machine_identity,
                },
            )
            return {
                "request_id": parsed.request_id,
                "correlation_id": parsed.correlation_id,
                "status": "failed",
                "error_code": "conversation_failed",
            }

        self.audit.append(
            "openclaw.teams_conversation_completed",
            {
                "request_id": parsed.request_id,
                "correlation_id": parsed.correlation_id,
                "machine_identity": machine_identity,
                "transport_message_id": result.transport_message_id,
                "orchestration_status": result.orchestration.status.value,
            },
        )
        return {
            "request_id": parsed.request_id,
            "correlation_id": parsed.correlation_id,
            "status": "completed",
            "transport_message_id": result.transport_message_id,
            "orchestration_status": result.orchestration.status.value,
        }

    def _freshness_error(
        self,
        parsed: OpenClawTeamsConversationEnvelope,
    ) -> str | None:
        now = datetime.now(timezone.utc)
        skew = self.max_clock_skew_seconds
        if parsed.issued_at.timestamp() > now.timestamp() + skew:
            return "request_not_yet_valid"
        if parsed.expires_at <= parsed.issued_at:
            return "request_expiry_invalid"
        if now.timestamp() > parsed.expires_at.timestamp() + skew:
            return "request_expired"
        return None

    def _reject(
        self,
        *,
        request_id: str,
        correlation_id: str,
        reason: str,
        machine_identity: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "request_id": request_id,
            "correlation_id": correlation_id,
            "reason": reason,
        }
        if machine_identity is not None:
            payload["machine_identity"] = machine_identity
        self.audit.append("openclaw.teams_conversation_rejected", payload)
        return {
            "request_id": request_id,
            "correlation_id": correlation_id,
            "status": "rejected",
            "error_code": reason,
        }

    def _deny(
        self,
        *,
        parsed: OpenClawTeamsConversationEnvelope,
        machine_identity: str,
        reason: str,
    ) -> dict[str, Any]:
        self.audit.append(
            "openclaw.teams_conversation_denied",
            {
                "request_id": parsed.request_id,
                "correlation_id": parsed.correlation_id,
                "machine_identity": machine_identity,
                "reason": reason,
            },
        )
        return {
            "request_id": parsed.request_id,
            "correlation_id": parsed.correlation_id,
            "status": "denied",
            "error_code": reason,
        }


def _parse_utc(value: str) -> datetime:
    if not value.strip():
        raise ValueError("timestamp is required")
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return parsed.astimezone(timezone.utc)
