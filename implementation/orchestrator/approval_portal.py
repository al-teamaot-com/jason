"""Deterministic Teams notification + authenticated Jason approval portal flow.

Teams is notification transport only. The approval decision is accepted only through
an authenticated Jason surface, checked against the provider-neutral ApprovalRequest,
persisted into JKD-001, re-authorized, replay-guarded, and resumed through the
Central Orchestrator.
"""
from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import quote
from urllib.request import Request, urlopen
from uuid import uuid4

from connectors.src.jason_connectors.approval_requests import (
    AcceptedApproval,
    ApprovalDecision,
    ApprovalEvidenceReference,
    ApprovalRequest,
    ApprovalRequestService,
    ApprovalRequestStatus,
    ApprovalResponse,
)
from kernel.execution_policy import DataHandlingPolicy, ExecutionBudget

from .approval_audit import (
    ApprovalAuditEvent,
    ApprovalAuditEventType,
    ApprovalAuditRecorder,
)
from .approval_continuation import ApprovalExecutionContinuation
from .approval_delivery import ApprovalDeliveryReceipt
from .approvals import ApprovalResumeBridge
from .contracts import ArtifactReference, OrchestrationMode, OrchestrationRequest


_SCHEMA = """
CREATE TABLE IF NOT EXISTS portal_approval_requests (
    approval_id TEXT PRIMARY KEY,
    request_json TEXT NOT NULL,
    orchestration_json TEXT,
    portal_url TEXT
);
CREATE INDEX IF NOT EXISTS ix_portal_approval_status
ON portal_approval_requests(approval_id);
"""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _request_to_json(value: ApprovalRequest) -> str:
    payload = {
        "approval_id": value.approval_id,
        "request_id": value.request_id,
        "correlation_id": value.correlation_id,
        "organization_id": value.organization_id,
        "client_id": value.client_id,
        "requested_by": value.requested_by,
        "capability": value.capability,
        "requested_mode": value.requested_mode,
        "requested_at": value.requested_at.astimezone(timezone.utc).isoformat(),
        "expires_at": value.expires_at.astimezone(timezone.utc).isoformat(),
        "authorized_approver_ids": list(value.authorized_approver_ids),
        "evidence_references": [
            {
                "artifact_id": ref.artifact_id,
                "organization_id": ref.organization_id,
                "content_sha256": ref.content_sha256,
            }
            for ref in value.evidence_references
        ],
        "status": value.status.value,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _request_from_json(raw: str) -> ApprovalRequest:
    payload = json.loads(raw)
    return ApprovalRequest(
        approval_id=str(payload["approval_id"]),
        request_id=str(payload["request_id"]),
        correlation_id=str(payload["correlation_id"]),
        organization_id=str(payload["organization_id"]),
        client_id=payload.get("client_id"),
        requested_by=str(payload["requested_by"]),
        capability=str(payload["capability"]),
        requested_mode=str(payload["requested_mode"]),
        requested_at=datetime.fromisoformat(str(payload["requested_at"])),
        expires_at=datetime.fromisoformat(str(payload["expires_at"])),
        authorized_approver_ids=tuple(
            str(item) for item in payload.get("authorized_approver_ids", ())
        ),
        evidence_references=tuple(
            ApprovalEvidenceReference(
                artifact_id=str(item["artifact_id"]),
                organization_id=str(item["organization_id"]),
                content_sha256=str(item["content_sha256"]),
            )
            for item in payload.get("evidence_references", ())
        ),
        status=ApprovalRequestStatus(str(payload["status"])),
    )


def _orchestration_to_json(value: OrchestrationRequest) -> str:
    payload = {
        "execution_id": value.execution_id,
        "correlation_id": value.correlation_id,
        "principal_id": value.principal_id,
        "organization_id": value.organization_id,
        "client_id": value.client_id,
        "capability_name": value.capability_name,
        "capability_version": value.capability_version,
        "requested_mode": value.requested_mode,
        "permission_mode": value.permission_mode,
        "orchestration_mode": value.orchestration_mode.value,
        "authority_allowed": value.authority_allowed,
        "approval_present": value.approval_present,
        "risk": value.risk,
        "data_handling": {
            "classification": value.data_handling.classification,
            "hosted_processing_allowed": value.data_handling.hosted_processing_allowed,
            "redaction_profile": value.data_handling.redaction_profile,
            "retention_allowed": value.data_handling.retention_allowed,
        },
        "budget": {
            "maximum_estimated_cost": str(value.budget.maximum_estimated_cost),
            "currency": value.budget.currency,
            "maximum_input_tokens": value.budget.maximum_input_tokens,
            "maximum_output_tokens": value.budget.maximum_output_tokens,
            "maximum_attempts": value.budget.maximum_attempts,
        },
        "arguments": dict(value.arguments),
        "region": value.region,
        "policy_ids": list(value.policy_ids),
        "artifact_references": [
            {
                "reference": item.reference,
                "media_type": item.media_type,
                "sha256": item.sha256,
            }
            for item in value.artifact_references
        ],
        "requester_kind": value.requester_kind,
        "principal_attributes": dict(value.principal_attributes),
        "allow_pilot_capability": value.allow_pilot_capability,
        "allow_pilot_provider": value.allow_pilot_provider,
        "authority_context_id": value.authority_context_id,
        "idempotency_key": value.idempotency_key,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _orchestration_from_json(raw: str) -> OrchestrationRequest:
    payload = json.loads(raw)
    handling = payload["data_handling"]
    budget = payload["budget"]
    return OrchestrationRequest(
        execution_id=str(payload["execution_id"]),
        correlation_id=str(payload["correlation_id"]),
        principal_id=str(payload["principal_id"]),
        organization_id=str(payload["organization_id"]),
        client_id=payload.get("client_id"),
        capability_name=str(payload["capability_name"]),
        capability_version=payload.get("capability_version"),
        requested_mode=str(payload["requested_mode"]),
        permission_mode=str(payload.get("permission_mode") or "observe"),
        orchestration_mode=OrchestrationMode(str(payload["orchestration_mode"])),
        authority_allowed=bool(payload["authority_allowed"]),
        approval_present=bool(payload["approval_present"]),
        risk=str(payload["risk"]),
        data_handling=DataHandlingPolicy(
            classification=str(handling["classification"]),
            hosted_processing_allowed=bool(handling["hosted_processing_allowed"]),
            redaction_profile=handling.get("redaction_profile"),
            retention_allowed=bool(handling.get("retention_allowed", False)),
        ),
        budget=ExecutionBudget(
            maximum_estimated_cost=Decimal(str(budget["maximum_estimated_cost"])),
            currency=str(budget.get("currency") or "USD"),
            maximum_input_tokens=int(budget.get("maximum_input_tokens", 0)),
            maximum_output_tokens=int(budget.get("maximum_output_tokens", 0)),
            maximum_attempts=int(budget.get("maximum_attempts", 1)),
        ),
        arguments=dict(payload.get("arguments") or {}),
        region=payload.get("region"),
        policy_ids=tuple(str(item) for item in payload.get("policy_ids", ())),
        artifact_references=tuple(
            ArtifactReference(
                reference=str(item["reference"]),
                media_type=item.get("media_type"),
                sha256=item.get("sha256"),
            )
            for item in payload.get("artifact_references", ())
        ),
        requester_kind=str(payload.get("requester_kind") or "human"),
        principal_attributes=dict(payload.get("principal_attributes") or {}),
        allow_pilot_capability=bool(payload.get("allow_pilot_capability", False)),
        allow_pilot_provider=bool(payload.get("allow_pilot_provider", False)),
        authority_context_id=payload.get("authority_context_id"),
        idempotency_key=payload.get("idempotency_key"),
    )


@dataclass(frozen=True, slots=True)
class SQLitePortalApprovalStore:
    database_path: str

    def initialize(self) -> None:
        path = Path(self.database_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(_SCHEMA)
        os.chmod(path, 0o600)

    def get(self, approval_id: str) -> ApprovalRequest | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT request_json FROM portal_approval_requests WHERE approval_id=?",
                (approval_id,),
            ).fetchone()
        return None if row is None else _request_from_json(row["request_json"])

    def put(self, request: ApprovalRequest) -> None:
        request.validate()
        encoded = _request_to_json(request)
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT request_json FROM portal_approval_requests WHERE approval_id=?",
                (request.approval_id,),
            ).fetchone()
            if existing is None:
                connection.execute(
                    "INSERT INTO portal_approval_requests(approval_id,request_json) VALUES (?,?)",
                    (request.approval_id, encoded),
                )
            else:
                previous = _request_from_json(existing["request_json"])
                immutable_previous = (
                    previous.request_id,
                    previous.correlation_id,
                    previous.organization_id,
                    previous.client_id,
                    previous.requested_by,
                    previous.capability,
                    previous.requested_mode,
                    previous.authorized_approver_ids,
                )
                immutable_new = (
                    request.request_id,
                    request.correlation_id,
                    request.organization_id,
                    request.client_id,
                    request.requested_by,
                    request.capability,
                    request.requested_mode,
                    request.authorized_approver_ids,
                )
                if immutable_previous != immutable_new:
                    raise ValueError("conflicting portal approval request reuse")
                connection.execute(
                    "UPDATE portal_approval_requests SET request_json=? WHERE approval_id=?",
                    (encoded, request.approval_id),
                )

    def bind_orchestration(
        self,
        *,
        approval_id: str,
        request: OrchestrationRequest,
        portal_url: str,
    ) -> None:
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT orchestration_json FROM portal_approval_requests WHERE approval_id=?",
                (approval_id,),
            ).fetchone()
            if existing is None:
                raise ValueError("approval request not found")
            encoded = _orchestration_to_json(request)
            if existing["orchestration_json"] not in (None, encoded):
                raise ValueError("conflicting orchestration binding for approval")
            connection.execute(
                "UPDATE portal_approval_requests SET orchestration_json=?, portal_url=? WHERE approval_id=?",
                (encoded, portal_url, approval_id),
            )

    def get_orchestration(self, approval_id: str) -> OrchestrationRequest | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT orchestration_json FROM portal_approval_requests WHERE approval_id=?",
                (approval_id,),
            ).fetchone()
        if row is None or row["orchestration_json"] is None:
            return None
        return _orchestration_from_json(row["orchestration_json"])

    def portal_url(self, approval_id: str) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT portal_url FROM portal_approval_requests WHERE approval_id=?",
                (approval_id,),
            ).fetchone()
        if row is None:
            return None
        return None if row["portal_url"] is None else str(row["portal_url"])

    def list_pending_for_approver(
        self,
        *,
        approver_identity_id: str,
        organization_id: str,
        now: datetime | None = None,
    ) -> tuple[ApprovalRequest, ...]:
        current = (now or _utc_now()).astimezone(timezone.utc)
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT request_json FROM portal_approval_requests ORDER BY approval_id"
            ).fetchall()
        result = []
        for row in rows:
            item = _request_from_json(row["request_json"])
            if (
                item.organization_id == organization_id
                and item.status is ApprovalRequestStatus.PENDING
                and current < item.expires_at
                and approver_identity_id in item.authorized_approver_ids
            ):
                result.append(item)
        return tuple(result)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        return connection


@dataclass(frozen=True, slots=True)
class PortalTeamsApprovalNotificationChannel:
    bindings: Any
    gateway_url: str
    proactive_token_file: str
    portal_url_template: str

    def portal_url(self, approval_id: str) -> str:
        template = self.portal_url_template.strip()
        if not template.startswith("https://"):
            raise ValueError("approval portal URL must use https")
        encoded = quote(approval_id, safe="")
        if "{approval_id}" in template:
            return template.replace("{approval_id}", encoded)
        separator = "&" if "?" in template else "?"
        return f"{template}{separator}jason_approval_id={encoded}"

    def deliver(self, request: ApprovalRequest) -> ApprovalDeliveryReceipt:
        request.validate()
        if len(request.authorized_approver_ids) != 1:
            raise PermissionError(
                "automatic Teams approval notification requires exactly one approver"
            )
        approver = request.authorized_approver_ids[0]
        binding = self.bindings.find_active_by_jason_identity(
            jason_identity_id=approver
        )
        if binding is None or binding.status != "active":
            raise PermissionError(
                "authorized approver has no unique active Teams identity binding"
            )

        portal_url = self.portal_url(request.approval_id)
        text = (
            "Jason needs your approval. "
            f"Approval {request.approval_id} for {request.capability}. "
            f"Review in Jason: {portal_url}"
        )
        card = {
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "type": "AdaptiveCard",
            "version": "1.4",
            "body": [
                {
                    "type": "TextBlock",
                    "text": "Jason needs your approval",
                    "weight": "Bolder",
                    "wrap": True,
                },
                {
                    "type": "TextBlock",
                    "text": (
                        f"Approval ID: {request.approval_id}\n"
                        f"Capability: {request.capability}\n"
                        f"Expires: {request.expires_at.astimezone(timezone.utc).isoformat()}"
                    ),
                    "wrap": True,
                },
                {
                    "type": "TextBlock",
                    "text": (
                        "Teams is notification-only. Approval or denial must be "
                        "completed in the authenticated Jason portal."
                    ),
                    "isSubtle": True,
                    "wrap": True,
                },
            ],
            "actions": [
                {
                    "type": "Action.OpenUrl",
                    "title": "Review in Jason",
                    "url": portal_url,
                }
            ],
        }
        token = Path(self.proactive_token_file).read_text(encoding="utf-8").strip()
        if not token:
            raise PermissionError("Teams proactive token unavailable")
        payload = json.dumps(
            {
                "aadObjectId": binding.microsoft_object_id,
                "tenantId": binding.microsoft_tenant_id,
                "text": text,
                "card": card,
            }
        ).encode("utf-8")
        outbound = Request(
            self.gateway_url.rstrip("/") + "/internal/proactive/send",
            data=payload,
            method="POST",
            headers={
                "Authorization": "Bearer " + token,
                "Content-Type": "application/json",
            },
        )
        with urlopen(outbound, timeout=20) as response:
            result = json.loads(response.read().decode("utf-8"))
        message_id = str(result.get("message_id") or "").strip()
        if result.get("status") != "succeeded" or not message_id:
            raise RuntimeError("Teams approval notification failed")
        return ApprovalDeliveryReceipt(
            channel="microsoft_teams",
            channel_reference_id=message_id,
            delivered_at=_utc_now(),
        )


@dataclass(frozen=True, slots=True)
class PortalApprovalDecisionResult:
    approval: AcceptedApproval
    orchestration_status: str | None
    orchestration_error_code: str | None


@dataclass(frozen=True, slots=True)
class PortalApprovalCoordinator:
    approval_service: ApprovalRequestService
    store: SQLitePortalApprovalStore
    notification: PortalTeamsApprovalNotificationChannel
    audit: ApprovalAuditRecorder
    resume_bridge: ApprovalResumeBridge
    continuation: ApprovalExecutionContinuation
    approval_id_factory: Any = lambda: f"approval_{uuid4().hex}"
    response_id_factory: Any = lambda: f"portal_{uuid4().hex}"

    def request_approval(
        self,
        *,
        original_request: OrchestrationRequest,
        authorized_approver_id: str,
        expires_in: timedelta = timedelta(minutes=15),
        now: datetime | None = None,
    ) -> tuple[ApprovalRequest, ApprovalDeliveryReceipt, str]:
        current = (now or _utc_now()).astimezone(timezone.utc)
        approval = ApprovalRequest(
            approval_id=self.approval_id_factory(),
            request_id=original_request.execution_id,
            correlation_id=original_request.correlation_id,
            organization_id=original_request.organization_id,
            client_id=original_request.client_id,
            requested_by=original_request.principal_id,
            capability=original_request.capability_name,
            requested_mode=original_request.permission_mode,
            requested_at=current,
            expires_at=current + expires_in,
            authorized_approver_ids=(authorized_approver_id,),
            status=ApprovalRequestStatus.PENDING,
        )
        created = self.approval_service.create(approval, now=current)
        portal_url = self.notification.portal_url(created.approval_id)
        self.store.bind_orchestration(
            approval_id=created.approval_id,
            request=original_request,
            portal_url=portal_url,
        )
        self._audit(
            event_type=ApprovalAuditEventType.REQUEST_CREATED,
            request=created,
            occurred_at=current,
            actor_identity_id=original_request.principal_id,
        )
        try:
            receipt = self.notification.deliver(created)
        except Exception as exc:
            self._audit(
                event_type=ApprovalAuditEventType.PROCESSING_FAILED,
                request=created,
                occurred_at=_utc_now(),
                actor_identity_id=None,
                reason_code=type(exc).__name__,
                metadata={"stage": "teams_notification", "error": str(exc)[:240]},
            )
            raise
        self._audit(
            event_type=ApprovalAuditEventType.DELIVERY_RECORDED,
            request=created,
            occurred_at=receipt.delivered_at,
            actor_identity_id=None,
            channel=receipt.channel,
            channel_reference_id=receipt.channel_reference_id,
        )
        return created, receipt, portal_url

    def list_pending(
        self,
        *,
        approver_identity_id: str,
        organization_id: str,
    ) -> tuple[ApprovalRequest, ...]:
        return self.store.list_pending_for_approver(
            approver_identity_id=approver_identity_id,
            organization_id=organization_id,
        )

    def review(
        self,
        *,
        approval_id: str,
        approver_identity_id: str,
        organization_id: str,
    ) -> ApprovalRequest:
        request = self.store.get(approval_id)
        if request is None:
            raise ValueError("approval request not found")
        if request.organization_id != organization_id:
            raise PermissionError("approval organization mismatch")
        if approver_identity_id not in request.authorized_approver_ids:
            raise PermissionError("authenticated technician is not an authorized approver")
        if request.status is not ApprovalRequestStatus.PENDING:
            raise ValueError("approval request is no longer pending")
        if _utc_now() >= request.expires_at:
            raise PermissionError("approval request expired")
        return request

    def decide(
        self,
        *,
        approval_id: str,
        approver_identity_id: str,
        organization_id: str,
        decision: str,
        authentication_assurance: str,
    ) -> PortalApprovalDecisionResult:
        pending = self.review(
            approval_id=approval_id,
            approver_identity_id=approver_identity_id,
            organization_id=organization_id,
        )
        try:
            selected = ApprovalDecision(str(decision).strip().casefold())
        except ValueError as exc:
            raise ValueError("decision must be approve or deny") from exc

        decided_at = _utc_now()
        accepted = self.approval_service.accept_response(
            ApprovalResponse(
                approval_id=pending.approval_id,
                organization_id=organization_id,
                approver_identity_id=approver_identity_id,
                decision=selected,
                decided_at=decided_at,
                channel="chatgpt_portal",
                channel_response_id=self.response_id_factory(),
            ),
            now=decided_at,
        )
        event_type = (
            ApprovalAuditEventType.RESPONSE_ACCEPTED
            if accepted.status == "approved"
            else ApprovalAuditEventType.RESPONSE_DENIED
        )
        self._audit(
            event_type=event_type,
            request=self.store.get(approval_id) or pending,
            occurred_at=decided_at,
            actor_identity_id=approver_identity_id,
            channel=accepted.channel,
            channel_reference_id=accepted.channel_response_id,
            metadata={"approval_status": accepted.status},
        )
        if accepted.status != "approved":
            return PortalApprovalDecisionResult(
                approval=accepted,
                orchestration_status=None,
                orchestration_error_code=None,
            )

        original = self.store.get_orchestration(approval_id)
        if original is None:
            raise RuntimeError("approval continuation request is missing")
        resumed = self.resume_bridge.resume(
            original_request=original,
            accepted=accepted,
            authentication_assurance=authentication_assurance,
        )
        result = self.continuation.execute(
            approval_id=approval_id,
            approved_by=approver_identity_id,
            request=resumed,
            channel=accepted.channel,
            channel_reference_id=accepted.channel_response_id,
        )
        return PortalApprovalDecisionResult(
            approval=accepted,
            orchestration_status=result.status.value,
            orchestration_error_code=result.error_code,
        )

    def _audit(
        self,
        *,
        event_type: ApprovalAuditEventType,
        request: ApprovalRequest,
        occurred_at: datetime,
        actor_identity_id: str | None,
        channel: str | None = None,
        channel_reference_id: str | None = None,
        reason_code: str | None = None,
        metadata: Mapping[str, str] | None = None,
    ) -> None:
        self.audit.record(
            ApprovalAuditEvent(
                event_id=str(uuid4()),
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
                reason_code=reason_code,
                evidence_references=request.evidence_references,
                metadata=dict(metadata or {}),
            )
        )
