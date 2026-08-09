"""Immutable approval lifecycle audit events for Project Jason.

Events are small, append-only governance records. Large evidence remains in INF-013
artifact storage and is referenced by immutable identifiers/hashes rather than copied
into the audit stream.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from hashlib import sha256
import json
from typing import Mapping, Protocol, Sequence

from connectors.src.jason_connectors.approval_requests import ApprovalEvidenceReference


class ApprovalAuditEventType(StrEnum):
    REQUEST_CREATED = "approval.request.created"
    DELIVERY_RECORDED = "approval.delivery.recorded"
    RESPONSE_AUTHENTICATED = "approval.response.authenticated"
    RESPONSE_ACCEPTED = "approval.response.accepted"
    RESPONSE_DENIED = "approval.response.denied"
    REQUEST_EXPIRED = "approval.request.expired"
    AUTHORIZATION_REJECTED = "approval.authorization.rejected"
    JKD_REAUTHORIZED = "approval.jkd.reauthorized"
    ORCHESTRATOR_RESUMED = "approval.orchestrator.resumed"
    PROCESSING_FAILED = "approval.processing.failed"


@dataclass(frozen=True, slots=True)
class ApprovalAuditEvent:
    event_id: str
    event_type: ApprovalAuditEventType
    occurred_at: datetime
    approval_id: str
    request_id: str
    correlation_id: str
    organization_id: str
    client_id: str | None
    actor_identity_id: str | None
    capability: str
    channel: str | None = None
    channel_reference_id: str | None = None
    authority_context_id: str | None = None
    reason_code: str | None = None
    evidence_references: tuple[ApprovalEvidenceReference, ...] = ()
    previous_event_hash: str | None = None
    event_hash: str = ""
    metadata: Mapping[str, str] = field(default_factory=dict)

    def validate(self) -> None:
        required = {
            "event_id": self.event_id,
            "approval_id": self.approval_id,
            "request_id": self.request_id,
            "correlation_id": self.correlation_id,
            "organization_id": self.organization_id,
            "capability": self.capability,
        }
        missing = [name for name, value in required.items() if not value.strip()]
        if missing:
            raise ValueError(f"missing approval audit fields: {', '.join(sorted(missing))}")
        if self.occurred_at.tzinfo is None:
            raise ValueError("approval audit timestamp must be timezone-aware")
        for reference in self.evidence_references:
            reference.validate()
            if reference.organization_id != self.organization_id:
                raise ValueError("audit evidence organization must match event organization")
        if self.previous_event_hash is not None and len(self.previous_event_hash) != 64:
            raise ValueError("previous_event_hash must be a SHA-256 digest")
        if self.event_hash and len(self.event_hash) != 64:
            raise ValueError("event_hash must be a SHA-256 digest")

    def canonical_payload(self) -> bytes:
        body = {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "occurred_at": self.occurred_at.astimezone(timezone.utc).isoformat(),
            "approval_id": self.approval_id,
            "request_id": self.request_id,
            "correlation_id": self.correlation_id,
            "organization_id": self.organization_id,
            "client_id": self.client_id,
            "actor_identity_id": self.actor_identity_id,
            "capability": self.capability,
            "channel": self.channel,
            "channel_reference_id": self.channel_reference_id,
            "authority_context_id": self.authority_context_id,
            "reason_code": self.reason_code,
            "evidence_references": [
                {
                    "artifact_id": ref.artifact_id,
                    "organization_id": ref.organization_id,
                    "content_sha256": ref.content_sha256,
                }
                for ref in self.evidence_references
            ],
            "previous_event_hash": self.previous_event_hash,
            "metadata": dict(sorted(self.metadata.items())),
        }
        return json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def calculated_hash(self) -> str:
        return sha256(self.canonical_payload()).hexdigest()


class ApprovalAuditSink(Protocol):
    def last_for_approval(self, approval_id: str) -> ApprovalAuditEvent | None: ...
    def append(self, event: ApprovalAuditEvent) -> None: ...


@dataclass
class InMemoryApprovalAuditSink:
    events: list[ApprovalAuditEvent] = field(default_factory=list)

    def last_for_approval(self, approval_id: str) -> ApprovalAuditEvent | None:
        for event in reversed(self.events):
            if event.approval_id == approval_id:
                return event
        return None

    def append(self, event: ApprovalAuditEvent) -> None:
        if any(existing.event_id == event.event_id for existing in self.events):
            raise ValueError("approval audit event_id already exists")
        self.events.append(event)


@dataclass
class ApprovalAuditRecorder:
    sink: ApprovalAuditSink

    def record(self, event: ApprovalAuditEvent) -> ApprovalAuditEvent:
        event.validate()
        previous = self.sink.last_for_approval(event.approval_id)
        previous_hash = previous.event_hash if previous is not None else None
        if event.previous_event_hash not in (None, previous_hash):
            raise ValueError("approval audit chain mismatch")
        chained = ApprovalAuditEvent(
            event_id=event.event_id,
            event_type=event.event_type,
            occurred_at=event.occurred_at,
            approval_id=event.approval_id,
            request_id=event.request_id,
            correlation_id=event.correlation_id,
            organization_id=event.organization_id,
            client_id=event.client_id,
            actor_identity_id=event.actor_identity_id,
            capability=event.capability,
            channel=event.channel,
            channel_reference_id=event.channel_reference_id,
            authority_context_id=event.authority_context_id,
            reason_code=event.reason_code,
            evidence_references=event.evidence_references,
            previous_event_hash=previous_hash,
            metadata=dict(event.metadata),
        )
        final = ApprovalAuditEvent(
            **{name: getattr(chained, name) for name in chained.__dataclass_fields__ if name != "event_hash"},
            event_hash=chained.calculated_hash(),
        )
        final.validate()
        self.sink.append(final)
        return final

    @staticmethod
    def verify_chain(events: Sequence[ApprovalAuditEvent]) -> bool:
        previous_hash: str | None = None
        approval_id: str | None = None
        for event in events:
            event.validate()
            if approval_id is None:
                approval_id = event.approval_id
            if event.approval_id != approval_id:
                return False
            if event.previous_event_hash != previous_hash:
                return False
            if event.event_hash != event.calculated_hash():
                return False
            previous_hash = event.event_hash
        return True
