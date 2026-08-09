"""Governed approval request creation and delivery coordination.

The coordinator records the front half of the approval lifecycle without making a
delivery channel authoritative. Approval requests are created by the provider-neutral
service, audit evidence is persisted, and only then may a channel deliver the request.
Delivery receipts are evidence only and never create approval or execution authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Protocol
from uuid import uuid4

from connectors.src.jason_connectors.approval_requests import ApprovalRequest, ApprovalRequestService

from .approval_audit import ApprovalAuditEvent, ApprovalAuditEventType, ApprovalAuditRecorder


@dataclass(frozen=True, slots=True)
class ApprovalDeliveryReceipt:
    channel: str
    channel_reference_id: str
    delivered_at: datetime

    def validate(self) -> None:
        if not self.channel.strip() or not self.channel_reference_id.strip():
            raise ValueError("approval delivery receipt identifiers must be non-empty")
        if self.delivered_at.tzinfo is None:
            raise ValueError("approval delivery timestamp must be timezone-aware")


class ApprovalDeliveryChannel(Protocol):
    def deliver(self, request: ApprovalRequest) -> ApprovalDeliveryReceipt: ...


@dataclass(frozen=True, slots=True)
class ApprovalRequestDeliveryCoordinator:
    approval_service: ApprovalRequestService
    audit: ApprovalAuditRecorder
    channel: ApprovalDeliveryChannel
    event_id_factory: Callable[[], str] = lambda: str(uuid4())

    def create_and_deliver(
        self,
        request: ApprovalRequest,
        *,
        now: datetime | None = None,
    ) -> ApprovalDeliveryReceipt:
        created = self.approval_service.create(request, now=now)
        self._record(
            event_type=ApprovalAuditEventType.REQUEST_CREATED,
            request=created,
            occurred_at=created.requested_at,
            actor_identity_id=created.requested_by,
            metadata={"requested_mode": created.requested_mode},
        )

        try:
            receipt = self.channel.deliver(created)
            receipt.validate()
            self._record(
                event_type=ApprovalAuditEventType.DELIVERY_RECORDED,
                request=created,
                occurred_at=receipt.delivered_at,
                actor_identity_id=None,
                channel=receipt.channel,
                channel_reference_id=receipt.channel_reference_id,
            )
            return receipt
        except Exception as exc:
            # Delivery failures never weaken the approval requirement. The request
            # remains pending but cannot be acted upon through this coordinator until
            # delivery succeeds through a governed retry path.
            self._record(
                event_type=ApprovalAuditEventType.PROCESSING_FAILED,
                request=created,
                occurred_at=self._now(now),
                actor_identity_id=None,
                reason_code=type(exc).__name__,
                metadata={"stage": "delivery", "error": str(exc)[:240]},
            )
            raise

    def _record(
        self,
        *,
        event_type: ApprovalAuditEventType,
        request: ApprovalRequest,
        occurred_at: datetime,
        actor_identity_id: str | None,
        channel: str | None = None,
        channel_reference_id: str | None = None,
        reason_code: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> None:
        self.audit.record(
            ApprovalAuditEvent(
                event_id=self.event_id_factory(),
                event_type=event_type,
                occurred_at=occurred_at,
                approval_id=request.approval_id,
                request_id=request.request_id,
                correlation_id=request.correlation_id,
                organization_id=request.organization_id,
                client_id=request.client_id,
                actor_identity_id=actor_identity_id,
                capability=request.capability,
                channel=channel,
                channel_reference_id=channel_reference_id,
                evidence_references=request.evidence_references,
                reason_code=reason_code,
                metadata=dict(metadata or {}),
            )
        )

    @staticmethod
    def _now(value: datetime | None) -> datetime:
        current = value or datetime.now(timezone.utc)
        if current.tzinfo is None:
            raise ValueError("approval delivery clock must be timezone-aware")
        return current.astimezone(timezone.utc)
