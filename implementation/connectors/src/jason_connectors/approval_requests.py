"""Provider-neutral approval request contracts and validation for Project Jason.

Approval channels may deliver requests and return authenticated response metadata,
but they never become the authority. The caller must provide an authority checker
owned by Jason and must persist accepted approvals through the governed authority
repository before execution can continue.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from enum import StrEnum
import json
import os
import sqlite3
from pathlib import Path
from typing import Protocol


class ApprovalRequestStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    CHANGES_REQUESTED = "changes_requested"


class ApprovalDecision(StrEnum):
    APPROVE = "approve"
    DENY = "deny"
    REQUEST_CHANGES = "request_changes"


@dataclass(frozen=True, slots=True)
class ApprovalPresentation:
    title: str
    summary: str
    facts: tuple[tuple[str, str], ...] = ()

    def validate(self) -> None:
        if not self.title.strip() or not self.summary.strip():
            raise ValueError("approval presentation title and summary must be non-empty")
        for label, value in self.facts:
            if not str(label).strip() or not str(value).strip():
                raise ValueError("approval presentation facts must be non-empty")


@dataclass(frozen=True, slots=True)
class ApprovalEvidenceReference:
    artifact_id: str
    organization_id: str
    content_sha256: str

    def validate(self) -> None:
        if not self.artifact_id.strip() or not self.organization_id.strip():
            raise ValueError("approval evidence reference identifiers must be non-empty")
        if len(self.content_sha256) != 64 or any(c not in "0123456789abcdef" for c in self.content_sha256.lower()):
            raise ValueError("approval evidence reference requires a SHA-256 digest")


@dataclass(frozen=True, slots=True)
class ApprovalRequest:
    approval_id: str
    request_id: str
    correlation_id: str
    organization_id: str
    client_id: str | None
    requested_by: str
    capability: str
    requested_mode: str
    requested_at: datetime
    expires_at: datetime
    authorized_approver_ids: tuple[str, ...]
    evidence_references: tuple[ApprovalEvidenceReference, ...] = ()
    presentation: ApprovalPresentation | None = None
    metadata: dict[str, str] = field(default_factory=dict)
    status: ApprovalRequestStatus = ApprovalRequestStatus.PENDING

    def validate(self) -> None:
        required = {
            "approval_id": self.approval_id,
            "request_id": self.request_id,
            "correlation_id": self.correlation_id,
            "organization_id": self.organization_id,
            "requested_by": self.requested_by,
            "capability": self.capability,
            "requested_mode": self.requested_mode,
        }
        missing = [name for name, value in required.items() if not value.strip()]
        if missing:
            raise ValueError(f"missing approval request fields: {', '.join(sorted(missing))}")
        if self.requested_at.tzinfo is None or self.expires_at.tzinfo is None:
            raise ValueError("approval timestamps must be timezone-aware")
        if self.expires_at <= self.requested_at:
            raise ValueError("approval expiration must be after request time")
        if not self.authorized_approver_ids or any(not value.strip() for value in self.authorized_approver_ids):
            raise ValueError("at least one authorized approver identity is required")
        if len(set(self.authorized_approver_ids)) != len(self.authorized_approver_ids):
            raise ValueError("authorized approver identities must be unique")
        for reference in self.evidence_references:
            reference.validate()
            if reference.organization_id != self.organization_id:
                raise ValueError("approval evidence organization must match approval organization")
        if self.presentation is not None:
            self.presentation.validate()
        for key, value in self.metadata.items():
            if not str(key).strip() or not str(value).strip():
                raise ValueError("approval metadata keys and values must be non-empty")


@dataclass(frozen=True, slots=True)
class ApprovalResponse:
    approval_id: str
    organization_id: str
    approver_identity_id: str
    decision: ApprovalDecision
    decided_at: datetime
    channel: str
    channel_response_id: str

    def validate(self) -> None:
        for value in (
            self.approval_id,
            self.organization_id,
            self.approver_identity_id,
            self.channel,
            self.channel_response_id,
        ):
            if not value.strip():
                raise ValueError("approval response identifiers must be non-empty")
        if self.decided_at.tzinfo is None:
            raise ValueError("approval response time must be timezone-aware")


@dataclass(frozen=True, slots=True)
class AcceptedApproval:
    approval_id: str
    request_id: str
    capability: str
    organization_id: str
    client_id: str | None
    requested_by: str
    status: str
    decided_by: str
    decided_at: datetime
    expires_at: datetime
    channel: str
    channel_response_id: str
    evidence_references: tuple[ApprovalEvidenceReference, ...]


class ApprovalAuthorityChecker(Protocol):
    def can_approve(
        self,
        *,
        approver_identity_id: str,
        organization_id: str,
        client_id: str | None,
        capability: str,
        requested_mode: str,
    ) -> bool: ...


class ApprovalRequestRepository(Protocol):
    def get(self, approval_id: str) -> ApprovalRequest | None: ...
    def put(self, request: ApprovalRequest) -> None: ...
    def list_all(self) -> tuple[ApprovalRequest, ...]: ...


@dataclass
class InMemoryApprovalRequestRepository:
    records: dict[str, ApprovalRequest] = field(default_factory=dict)

    def get(self, approval_id: str) -> ApprovalRequest | None:
        return self.records.get(approval_id)

    def put(self, request: ApprovalRequest) -> None:
        self.records[request.approval_id] = request

    def list_all(self) -> tuple[ApprovalRequest, ...]:
        return tuple(self.records[key] for key in sorted(self.records))


class SQLiteApprovalRequestRepository:
    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS approval_requests (
        approval_id TEXT PRIMARY KEY,
        payload TEXT NOT NULL
    );
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(str(self.path), timeout=10.0, isolation_level=None)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA synchronous=FULL")
        self._connection.executescript(self._SCHEMA)
        os.chmod(self.path, 0o600)

    def get(self, approval_id: str) -> ApprovalRequest | None:
        row = self._connection.execute(
            "SELECT payload FROM approval_requests WHERE approval_id=?", (approval_id,)
        ).fetchone()
        return None if row is None else self._decode(str(row["payload"]))

    def put(self, request: ApprovalRequest) -> None:
        request.validate()
        payload = self._encode(request)
        with self._connection:
            row = self._connection.execute(
                "SELECT payload FROM approval_requests WHERE approval_id=?",
                (request.approval_id,),
            ).fetchone()
            if row is not None:
                existing = self._decode(str(row["payload"]))
                if self._immutable_scope(existing) != self._immutable_scope(request):
                    raise ValueError(
                        "approval request id cannot be reused with changed immutable scope"
                    )
                if not self._valid_status_transition(existing.status, request.status):
                    raise ValueError("invalid approval request status transition")
            self._connection.execute(
                "INSERT INTO approval_requests(approval_id,payload) VALUES(?,?) "
                "ON CONFLICT(approval_id) DO UPDATE SET payload=excluded.payload",
                (request.approval_id, payload),
            )

    def list_all(self) -> tuple[ApprovalRequest, ...]:
        rows = self._connection.execute(
            "SELECT payload FROM approval_requests ORDER BY approval_id"
        ).fetchall()
        return tuple(self._decode(str(row["payload"])) for row in rows)

    def close(self) -> None:
        self._connection.close()

    @staticmethod
    def _immutable_scope(request: ApprovalRequest) -> tuple:
        metadata = tuple(
            sorted(
                (str(key), str(value))
                for key, value in request.metadata.items()
                if key != "delivery_message_ids"
            )
        )
        presentation = None
        if request.presentation is not None:
            presentation = (
                request.presentation.title,
                request.presentation.summary,
                tuple(request.presentation.facts),
            )
        evidence = tuple(
            (ref.artifact_id, ref.organization_id, ref.content_sha256)
            for ref in request.evidence_references
        )
        return (
            request.approval_id,
            request.request_id,
            request.correlation_id,
            request.organization_id,
            request.client_id,
            request.requested_by,
            request.capability,
            request.requested_mode,
            request.requested_at,
            request.expires_at,
            tuple(request.authorized_approver_ids),
            evidence,
            presentation,
            metadata,
        )

    @staticmethod
    def _valid_status_transition(
        previous: ApprovalRequestStatus, current: ApprovalRequestStatus
    ) -> bool:
        if previous is current:
            return True
        if previous is ApprovalRequestStatus.PENDING:
            return current in {
                ApprovalRequestStatus.APPROVED,
                ApprovalRequestStatus.DENIED,
                ApprovalRequestStatus.CHANGES_REQUESTED,
                ApprovalRequestStatus.EXPIRED,
                ApprovalRequestStatus.CANCELLED,
            }
        return False

    @staticmethod
    def _encode(request: ApprovalRequest) -> str:
        body = asdict(request)
        body["requested_at"] = request.requested_at.isoformat()
        body["expires_at"] = request.expires_at.isoformat()
        body["status"] = request.status.value
        body["evidence_references"] = [asdict(ref) for ref in request.evidence_references]
        if request.presentation is not None:
            body["presentation"] = {
                "title": request.presentation.title,
                "summary": request.presentation.summary,
                "facts": [list(item) for item in request.presentation.facts],
            }
        return json.dumps(body, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _decode(payload: str) -> ApprovalRequest:
        body = json.loads(payload)
        body["requested_at"] = datetime.fromisoformat(body["requested_at"])
        body["expires_at"] = datetime.fromisoformat(body["expires_at"])
        body["status"] = ApprovalRequestStatus(body["status"])
        body["authorized_approver_ids"] = tuple(body["authorized_approver_ids"])
        body["evidence_references"] = tuple(
            ApprovalEvidenceReference(**item) for item in body.get("evidence_references") or ()
        )
        presentation = body.get("presentation")
        body["presentation"] = (
            ApprovalPresentation(
                title=presentation["title"],
                summary=presentation["summary"],
                facts=tuple((str(a), str(b)) for a, b in presentation.get("facts") or ()),
            )
            if presentation else None
        )
        body["metadata"] = dict(body.get("metadata") or {})
        return ApprovalRequest(**body)


@dataclass
class ApprovalRequestService:
    repository: ApprovalRequestRepository
    authority: ApprovalAuthorityChecker

    def create(self, request: ApprovalRequest, *, now: datetime | None = None) -> ApprovalRequest:
        request.validate()
        current = self._now(now)
        if request.status is not ApprovalRequestStatus.PENDING:
            raise ValueError("new approval requests must start pending")
        if current >= request.expires_at:
            raise ValueError("approval request is already expired")
        if self.repository.get(request.approval_id) is not None:
            raise ValueError("approval_id already exists")
        self.repository.put(request)
        return request

    def accept_response(self, response: ApprovalResponse, *, now: datetime | None = None) -> AcceptedApproval:
        response.validate()
        current = self._now(now)
        request = self.repository.get(response.approval_id)
        if request is None:
            raise ValueError("approval request not found")
        if request.status is not ApprovalRequestStatus.PENDING:
            raise ValueError("approval request is no longer pending")
        if response.organization_id != request.organization_id:
            raise PermissionError("approval response organization mismatch")
        if current >= request.expires_at or response.decided_at >= request.expires_at:
            self.repository.put(replace(request, status=ApprovalRequestStatus.EXPIRED))
            raise PermissionError("approval request expired")
        if response.approver_identity_id not in request.authorized_approver_ids:
            raise PermissionError("responder is not an authorized approver for this request")
        if not self.authority.can_approve(
            approver_identity_id=response.approver_identity_id,
            organization_id=request.organization_id,
            client_id=request.client_id,
            capability=request.capability,
            requested_mode=request.requested_mode,
        ):
            raise PermissionError("Jason authority denied approver authorization")

        if response.decision is ApprovalDecision.APPROVE:
            final_status = ApprovalRequestStatus.APPROVED
        elif response.decision is ApprovalDecision.REQUEST_CHANGES:
            final_status = ApprovalRequestStatus.CHANGES_REQUESTED
        else:
            final_status = ApprovalRequestStatus.DENIED
        self.repository.put(replace(request, status=final_status))
        return AcceptedApproval(
            approval_id=request.approval_id,
            request_id=request.request_id,
            capability=request.capability,
            organization_id=request.organization_id,
            client_id=request.client_id,
            requested_by=request.requested_by,
            status=final_status.value,
            decided_by=response.approver_identity_id,
            decided_at=response.decided_at.astimezone(timezone.utc),
            expires_at=request.expires_at.astimezone(timezone.utc),
            channel=response.channel,
            channel_response_id=response.channel_response_id,
            evidence_references=request.evidence_references,
        )

    @staticmethod
    def _now(value: datetime | None) -> datetime:
        current = value or datetime.now(timezone.utc)
        if current.tzinfo is None:
            raise ValueError("approval service clock must be timezone-aware")
        return current.astimezone(timezone.utc)
