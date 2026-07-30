"""Adapter contracts for the governed remediation workflow.

Concrete adapters belong in connector packages and must be invoked by the
central orchestrator. This file intentionally contains no vendor credentials,
HTTP clients, or direct agent-to-agent communication.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol


@dataclass(frozen=True)
class CapabilityRequest:
    capability: str
    correlation_id: str
    organization_id: str
    client_id: str
    payload: Mapping[str, Any]


@dataclass(frozen=True)
class CapabilityResponse:
    capability: str
    success: bool
    result: Mapping[str, Any]
    evidence_references: tuple[str, ...] = ()
    error_code: str | None = None
    error_message: str | None = None


class CapabilityRouter(Protocol):
    def invoke(self, request: CapabilityRequest) -> CapabilityResponse:
        """Invoke one named capability after routing, authorization, and audit."""


REQUIRED_CAPABILITIES = (
    "autotask.ticket.get",
    "triage.ticket.assess",
    "remediation.policy.evaluate",
    "approval.request",
    "approval.get",
    "drmm.component.run",
    "drmm.job.status",
    "remediation.verify",
    "autotask.ticket.note.add",
    "communication.follow_up.request",
    "remediation.outcome.record",
    "audit.event.record",
)


class RoutedAutotaskAdapter:
    def __init__(self, router: CapabilityRouter) -> None:
        self.router = router

    def get_ticket(self, *, ticket_id: str, organization_id: str, client_id: str, correlation_id: str) -> CapabilityResponse:
        return self.router.invoke(CapabilityRequest("autotask.ticket.get", correlation_id, organization_id, client_id, {"ticket_id": ticket_id}))

    def add_note(self, *, ticket_id: str, body: str, organization_id: str, client_id: str, correlation_id: str) -> CapabilityResponse:
        return self.router.invoke(CapabilityRequest("autotask.ticket.note.add", correlation_id, organization_id, client_id, {"ticket_id": ticket_id, "body": body, "publish": "internal"}))


class RoutedDrmmAdapter:
    def __init__(self, router: CapabilityRouter) -> None:
        self.router = router

    def run_component(self, *, device_id: str, component_id: str, variables: Mapping[str, Any], idempotency_key: str, organization_id: str, client_id: str, correlation_id: str) -> CapabilityResponse:
        return self.router.invoke(
            CapabilityRequest(
                "drmm.component.run",
                correlation_id,
                organization_id,
                client_id,
                {
                    "device_id": device_id,
                    "component_id": component_id,
                    "variables": dict(variables),
                    "idempotency_key": idempotency_key,
                },
            )
        )


class RoutedCommunicationAdapter:
    def __init__(self, router: CapabilityRouter) -> None:
        self.router = router

    def request_follow_up(self, *, ticket_id: str, contact_ref: str, message: str, preferred_channels: tuple[str, ...], organization_id: str, client_id: str, correlation_id: str) -> CapabilityResponse:
        return self.router.invoke(
            CapabilityRequest(
                "communication.follow_up.request",
                correlation_id,
                organization_id,
                client_id,
                {
                    "ticket_id": ticket_id,
                    "contact_ref": contact_ref,
                    "message": message,
                    "preferred_channels": list(preferred_channels),
                    "call_mode": "notification_and_confirmation",
                },
            )
        )
