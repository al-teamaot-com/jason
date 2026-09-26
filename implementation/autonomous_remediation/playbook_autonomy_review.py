"""Owner-governed playbook autonomy review and mechanical promotion.

Technicians may submit an exact source-controlled playbook scope for review.  The
submission itself creates no authority.  A durable autonomy promotion is created
only after an accepted approval from an authorized owner and only if the current
registry entry still has the exact fingerprint reviewed by that owner.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Iterable
from uuid import uuid4

from connectors.src.jason_connectors.approval_requests import (
    AcceptedApproval,
    ApprovalEvidenceReference,
    ApprovalPresentation,
    ApprovalRequest,
)

from .playbook_autonomy_approval import (
    PlaybookAutonomyApproval,
    SQLitePlaybookAutonomyApprovalStore,
)
from .playbook_autonomy_scope import RegisteredAutonomyScope, registered_autonomy_scope


PLAYBOOK_AUTONOMY_PROMOTION_CAPABILITY = "playbook.autonomy.promote"
PLAYBOOK_AUTONOMY_REQUEST_CAPABILITY = "playbook.autonomy.request"


class PlaybookAutonomyReviewError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class PlaybookAutonomyPromotionResult:
    promotion: PlaybookAutonomyApproval
    created: bool
    scope: RegisteredAutonomyScope


@dataclass(frozen=True, slots=True)
class PlaybookAutonomyReviewService:
    registry_path: Path
    promotion_store: SQLitePlaybookAutonomyApprovalStore
    owner_identity_ids: frozenset[str]
    audit_path: Path | None = None

    def build_request(
        self,
        *,
        playbook_id: str,
        requested_by: str,
        organization_id: str = "aot",
        ttl: timedelta = timedelta(hours=24),
        now: datetime | None = None,
        request_id: str | None = None,
        approval_id: str | None = None,
        correlation_id: str | None = None,
    ) -> ApprovalRequest:
        actor = str(requested_by or "").strip()
        if not actor:
            raise PlaybookAutonomyReviewError("PLAYBOOK_AUTONOMY_REQUESTER_REQUIRED")
        owners = tuple(sorted(identity for identity in self.owner_identity_ids if identity.strip()))
        if not owners:
            raise PlaybookAutonomyReviewError("PLAYBOOK_AUTONOMY_OWNER_CONFIGURATION_REQUIRED")
        if ttl <= timedelta(0):
            raise PlaybookAutonomyReviewError("PLAYBOOK_AUTONOMY_REVIEW_TTL_INVALID")

        scope = registered_autonomy_scope(
            registry_path=self.registry_path,
            playbook_id=playbook_id,
        )
        current = self._now(now)
        evidence = ApprovalEvidenceReference(
            artifact_id=f"playbook:{scope.playbook_id}@{scope.playbook_version}",
            organization_id=organization_id,
            content_sha256=scope.entry_sha256,
        )
        capabilities_text = ", ".join(scope.allowed_capabilities)
        presentation = ApprovalPresentation(
            title=f"Approve Jason autonomy: {scope.name}",
            summary=(
                f"{actor} requests unattended production authority for the exact "
                f"{scope.playbook_id}@{scope.playbook_version} safe branch."
            ),
            facts=(
                ("Playbook", scope.playbook_id),
                ("Version", scope.playbook_version),
                ("Review status", scope.review_status or "not stated"),
                ("Allowed capabilities", capabilities_text),
                ("Source", scope.source or "not stated"),
                ("Scope fingerprint", scope.entry_sha256),
                ("Requested by", actor),
                ("Authority effect", "Creates exact durable autonomy promotion only"),
            ),
        )
        return ApprovalRequest(
            approval_id=approval_id or f"pbautreq_{uuid4().hex}",
            request_id=request_id or f"pbautreview_{uuid4().hex}",
            correlation_id=correlation_id or f"corr_pbautreview_{uuid4().hex}",
            organization_id=organization_id,
            client_id=None,
            requested_by=actor,
            capability=PLAYBOOK_AUTONOMY_PROMOTION_CAPABILITY,
            requested_mode=scope.requested_mode(),
            requested_at=current,
            expires_at=current + ttl,
            authorized_approver_ids=owners,
            evidence_references=(evidence,),
            presentation=presentation,
            metadata={
                "playbook_id": scope.playbook_id,
                "playbook_version": scope.playbook_version,
                "policy_id": scope.policy_id,
                "allowed_capabilities": capabilities_text,
                "entry_sha256": scope.entry_sha256,
                "source": scope.source or "not-stated",
            },
        )

    def promote_accepted(
        self,
        *,
        request: ApprovalRequest,
        accepted: AcceptedApproval,
    ) -> PlaybookAutonomyPromotionResult:
        if accepted.status != "approved":
            raise PlaybookAutonomyReviewError("PLAYBOOK_AUTONOMY_OWNER_APPROVAL_REQUIRED")
        if accepted.approval_id != request.approval_id:
            raise PlaybookAutonomyReviewError("PLAYBOOK_AUTONOMY_APPROVAL_ID_MISMATCH")
        if accepted.request_id != request.request_id:
            raise PlaybookAutonomyReviewError("PLAYBOOK_AUTONOMY_REQUEST_ID_MISMATCH")
        if accepted.capability != PLAYBOOK_AUTONOMY_PROMOTION_CAPABILITY:
            raise PlaybookAutonomyReviewError("PLAYBOOK_AUTONOMY_CAPABILITY_MISMATCH")
        if accepted.decided_by not in self.owner_identity_ids:
            raise PlaybookAutonomyReviewError("PLAYBOOK_AUTONOMY_OWNER_REQUIRED")

        playbook_id = request.metadata.get("playbook_id", "").strip()
        reviewed_version = request.metadata.get("playbook_version", "").strip()
        reviewed_policy = request.metadata.get("policy_id", "").strip()
        reviewed_fingerprint = request.metadata.get("entry_sha256", "").strip()
        if not all((playbook_id, reviewed_version, reviewed_policy, reviewed_fingerprint)):
            raise PlaybookAutonomyReviewError("PLAYBOOK_AUTONOMY_REVIEW_SCOPE_INCOMPLETE")

        current = registered_autonomy_scope(
            registry_path=self.registry_path,
            playbook_id=playbook_id,
        )
        if current.playbook_version != reviewed_version:
            raise PlaybookAutonomyReviewError("PLAYBOOK_AUTONOMY_VERSION_DRIFT")
        if current.policy_id != reviewed_policy:
            raise PlaybookAutonomyReviewError("PLAYBOOK_AUTONOMY_POLICY_DRIFT")
        if current.entry_sha256 != reviewed_fingerprint:
            raise PlaybookAutonomyReviewError("PLAYBOOK_AUTONOMY_FINGERPRINT_DRIFT")
        if request.requested_mode != current.requested_mode():
            raise PlaybookAutonomyReviewError("PLAYBOOK_AUTONOMY_REQUEST_MODE_DRIFT")

        reviewed_caps = tuple(
            value.strip()
            for value in request.metadata.get("allowed_capabilities", "").split(",")
            if value.strip()
        )
        if reviewed_caps != current.allowed_capabilities:
            raise PlaybookAutonomyReviewError("PLAYBOOK_AUTONOMY_CAPABILITY_DRIFT")

        existing = self.promotion_store.find_scope_approved(
            playbook_id=current.playbook_id,
            playbook_version=current.playbook_version,
            policy_id=current.policy_id,
            required_capabilities=current.allowed_capabilities,
        )
        if existing is not None:
            result = PlaybookAutonomyPromotionResult(existing, False, current)
            self._append_audit(request=request, accepted=accepted, result=result)
            return result

        promotion = self.promotion_store.new(
            playbook_id=current.playbook_id,
            playbook_version=current.playbook_version,
            policy_id=current.policy_id,
            allowed_capabilities=current.allowed_capabilities,
            approved_by=accepted.decided_by,
            expires_at=None,
        )
        self.promotion_store.put(promotion)
        result = PlaybookAutonomyPromotionResult(promotion, True, current)
        self._append_audit(request=request, accepted=accepted, result=result)
        return result

    def _append_audit(
        self,
        *,
        request: ApprovalRequest,
        accepted: AcceptedApproval,
        result: PlaybookAutonomyPromotionResult,
    ) -> None:
        if self.audit_path is None:
            return
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": (
                "playbook.autonomy.owner_approved_and_promoted"
                if result.created
                else "playbook.autonomy.owner_approved_existing_promotion_reused"
            ),
            "approval_request_id": request.approval_id,
            "requested_by": request.requested_by,
            "approved_by": accepted.decided_by,
            "channel": accepted.channel,
            "channel_response_id": accepted.channel_response_id,
            "promotion_approval_id": result.promotion.approval_id,
            "playbook_id": result.scope.playbook_id,
            "playbook_version": result.scope.playbook_version,
            "policy_id": result.scope.policy_id,
            "allowed_capabilities": list(result.scope.allowed_capabilities),
            "entry_sha256": result.scope.entry_sha256,
        }
        with self.audit_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n")

    @staticmethod
    def _now(value: datetime | None) -> datetime:
        current = value or datetime.now(timezone.utc)
        if current.tzinfo is None:
            raise PlaybookAutonomyReviewError("PLAYBOOK_AUTONOMY_REVIEW_CLOCK_MUST_BE_AWARE")
        return current.astimezone(timezone.utc)
