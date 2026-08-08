from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from .models import CapabilityRequest, CapabilityResponse, ConnectorContractError


class CapabilityDispatcher(Protocol):
    def dispatch(self, request: CapabilityRequest) -> Mapping[str, Any]: ...


class AuthorityEvaluator(Protocol):
    def evaluate(self, request: CapabilityRequest) -> str: ...


class PolicyEvaluator(Protocol):
    def evaluate(self, request: CapabilityRequest) -> str: ...


class AuditSink(Protocol):
    def append(self, event_type: str, payload: Mapping[str, Any]) -> None: ...


class ReplayStore(Protocol):
    def claim(self, request_id: str) -> bool: ...


@dataclass(frozen=True, slots=True)
class OpenClawConnector:
    dispatcher: CapabilityDispatcher
    authority: AuthorityEvaluator
    audit: AuditSink
    replay: ReplayStore
    policy: PolicyEvaluator | None = None

    def handle(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        try:
            request = CapabilityRequest.from_payload(payload)
        except ConnectorContractError as exc:
            return CapabilityResponse(
                request_id=str(payload.get("request_id", "unknown")),
                correlation_id=str(payload.get("correlation_id", "unknown")),
                status="rejected",
                capability=str(payload.get("capability", "unknown")),
                error_code="invalid_contract",
                message=str(exc),
            ).to_payload()

        if not self.replay.claim(request.request_id):
            self.audit.append("openclaw.request_replayed", {
                "request_id": request.request_id,
                "correlation_id": request.correlation_id,
                "capability": request.capability,
            })
            return CapabilityResponse(
                request_id=request.request_id,
                correlation_id=request.correlation_id,
                status="rejected",
                capability=request.capability,
                error_code="replay_detected",
                message="The request ID has already been processed.",
            ).to_payload()

        decision = self.authority.evaluate(request)
        self.audit.append("openclaw.request_received", {
            "request_id": request.request_id,
            "correlation_id": request.correlation_id,
            "capability": request.capability,
            "principal_id": request.principal.principal_id,
            "organization_id": request.principal.organization_id,
            "client_id": request.principal.client_id,
            "requested_mode": request.requested_mode,
            "authority_decision": decision,
        })

        if decision == "approval_required":
            return self._approval_required(request, "authority_approval_required")
        if decision != "allowed":
            self.audit.append("openclaw.request_denied", {
                "request_id": request.request_id,
                "correlation_id": request.correlation_id,
                "capability": request.capability,
                "decision": decision,
            })
            return CapabilityResponse(
                request_id=request.request_id,
                correlation_id=request.correlation_id,
                status="denied",
                capability=request.capability,
                error_code="authority_denied",
                message="The requester is not authorized for this capability and client scope.",
            ).to_payload()

        if self.policy is not None:
            policy_decision = self.policy.evaluate(request)
            self.audit.append("openclaw.policy_evaluated", {
                "request_id": request.request_id,
                "correlation_id": request.correlation_id,
                "capability": request.capability,
                "decision": policy_decision,
            })
            if policy_decision == "approval_required":
                return self._approval_required(request, "policy_approval_required")
            if policy_decision != "allowed":
                return CapabilityResponse(
                    request_id=request.request_id,
                    correlation_id=request.correlation_id,
                    status="denied",
                    capability=request.capability,
                    error_code="policy_denied",
                    message="A governance policy gate denied the request.",
                ).to_payload()

        try:
            result = self.dispatcher.dispatch(request)
        except KeyError:
            self.audit.append("openclaw.capability_unknown", {
                "request_id": request.request_id,
                "correlation_id": request.correlation_id,
                "capability": request.capability,
            })
            return CapabilityResponse(
                request_id=request.request_id,
                correlation_id=request.correlation_id,
                status="rejected",
                capability=request.capability,
                error_code="capability_not_registered",
                message="The requested capability is not registered.",
            ).to_payload()
        except Exception:
            self.audit.append("openclaw.capability_failed", {
                "request_id": request.request_id,
                "correlation_id": request.correlation_id,
                "capability": request.capability,
            })
            return CapabilityResponse(
                request_id=request.request_id,
                correlation_id=request.correlation_id,
                status="failed",
                capability=request.capability,
                error_code="capability_failed",
                message="The capability failed. Consult the correlated audit record.",
            ).to_payload()

        self.audit.append("openclaw.capability_completed", {
            "request_id": request.request_id,
            "correlation_id": request.correlation_id,
            "capability": request.capability,
        })
        return CapabilityResponse(
            request_id=request.request_id,
            correlation_id=request.correlation_id,
            status="completed",
            capability=request.capability,
            result=result,
        ).to_payload()

    @staticmethod
    def _approval_required(request: CapabilityRequest, code: str) -> dict[str, Any]:
        return CapabilityResponse(
            request_id=request.request_id,
            correlation_id=request.correlation_id,
            status="approval_required",
            capability=request.capability,
            error_code=code,
            message="A recorded human approval is required before execution.",
        ).to_payload()
