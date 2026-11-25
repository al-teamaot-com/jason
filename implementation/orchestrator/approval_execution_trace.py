"""Governed, bounded, tenant-isolated read model for approval execution evidence.

This module only projects existing append-only approval audit records. It does
not initiate approval, dispatch transport or grant authority. Registration in
the active capability registry is a separate reviewed engineering step.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, Callable

from .approval_audit import ApprovalAuditEvent, ApprovalAuditRecorder

CAPABILITY = "approval.execution.trace.read"
MAX_WINDOW = timedelta(days=7)
MAX_RESULTS = 100
_ALLOWED_CHANNELS = frozenset({"microsoft_teams", "teams", "msteams"})
_STATES = {
    "approval.request.created": "request_created",
    "approval.identity.validated": "identity_validated",
    "approval.authorization.validated": "authorization_validated",
    "approval.delivery.queued": "queued",
    "approval.transport.accepted": "transport_accepted",
    "approval.delivery.confirmed": "delivery_confirmed",
    "approval.delivery.recorded": "transport_receipt_recorded",
    "approval.response.authenticated": "response_authenticated",
    "approval.response.accepted": "approved",
    "approval.response.denied": "denied",
    "approval.response.changes_requested": "changes_requested",
    "approval.request.expired": "expired",
    "approval.authorization.rejected": "authorization_rejected",
    "approval.processing.failed": "failed",
}
# This projection deliberately does NOT translate a delivery receipt into
# recipient delivery confirmation.
@dataclass(frozen=True)
class TraceQuery:
    organization_id: str
    start: datetime
    end: datetime
    correlation_id: str | None = None
    approval_id: str | None = None
    limit: int = 50

    def validate(self) -> None:
        if not self.organization_id.strip():
            raise ValueError("organization_id required")
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise ValueError("timezone-aware bounds required")
        if self.end <= self.start or self.end - self.start > MAX_WINDOW:
            raise ValueError("invalid trace window")
        if not 1 <= self.limit <= MAX_RESULTS:
            raise ValueError("invalid trace limit")
        if not (self.correlation_id or self.approval_id):
            raise ValueError("exact correlation_id or approval_id required")
        for selector in (self.correlation_id, self.approval_id):
            if selector is not None and (not selector.strip() or len(selector) > 256 or any(c in selector for c in "*?[]%")):
                raise ValueError("exact bounded selector required")


def read_trace(
    query: TraceQuery,
    events: Iterable[ApprovalAuditEvent],
    *,
    authorized_organization: str,
    audit_access_check: Callable[[str], bool],
) -> dict:
    """Return only allowlisted evidence after independent tenant/access checks.

    The caller must obtain events through a governed tenant-scoped repository.
    No raw metadata, provider payload, tokens, conversation references, user
    content or arbitrary error strings are returned.
    """
    query.validate()
    if query.organization_id != authorized_organization or not audit_access_check(query.organization_id):
        raise PermissionError("approval trace access denied")
    selected: list[ApprovalAuditEvent] = []
    for event in events:
        if event.organization_id != authorized_organization:
            continue
        if not query.start <= event.occurred_at <= query.end:
            continue
        if query.correlation_id and event.correlation_id != query.correlation_id:
            continue
        if query.approval_id and event.approval_id != query.approval_id:
            continue
        selected.append(event)
    selected.sort(key=lambda e: (e.occurred_at, e.event_id))
    # Verify each individual approval hash chain only if the full chain was
    # supplied. A filtered time-window may omit predecessors, so expose hashes
    # without claiming chain verification.
    rows = [
        {
            "event_id": e.event_id,
            "event_hash": e.event_hash,
            "previous_event_hash": e.previous_event_hash,
            "occurred_at": e.occurred_at.astimezone(timezone.utc).isoformat(),
            "approval_id": e.approval_id,
            "request_id": e.request_id,
            "correlation_id": e.correlation_id,
            "organization_id": e.organization_id,
            "state": _STATES.get(str(e.event_type), "unmapped_audit_event"),
            "channel": e.channel if e.channel in _ALLOWED_CHANNELS else None,
            "reason_code": e.reason_code if e.reason_code and e.reason_code.isidentifier() else None,
            "evidence_hashes": [r.content_sha256 for r in e.evidence_references if r.organization_id == authorized_organization],
        }
        for e in selected[: query.limit]
    ]
    return {
        "capability": CAPABILITY,
        "organization_id": authorized_organization,
        "events": rows,
        "truncated": len(selected) > query.limit,
        "delivery_confirmed": any(row["state"] == "delivery_confirmed" for row in rows),
        "historical_coverage": "existing_audit_events_only",
        "read_only": True,
    }
