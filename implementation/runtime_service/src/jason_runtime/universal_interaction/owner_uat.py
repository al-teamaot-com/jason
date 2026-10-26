"""Nonexecuting owner Teams acceptance-test workflow.

Optional, NOT registered in production. Reuses:
- the universal owner interaction contract and existing governed Teams sender
- ApprovalRequestService, existing repository and owner authority binding
- the already authenticated ADR-009 gateway signed ingress and callback dispatcher

No post-decision executor exists; Approve and Deny both only write an approval
receipt. This module does NOT create source/release/CCC/provider permissions.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Any, Mapping

from connectors.src.jason_connectors.approval_requests import (
    ApprovalDecision, ApprovalPresentation, ApprovalRequest,
    ApprovalRequestService, ApprovalRequestStatus, ApprovalResponse,
)
from .owner_requests import interaction_from_owner_approval
from .service import UniversalInteractionService, InteractionDelivery

CAPABILITY = "interaction.owner.acceptance.record"
APPROVAL_PREFIX = "owneruatapproval-"
MODE = "test:nonexecuting"
REQUESTER = "svc-jason-acceptance-test"
ORGANIZATION = "aot"
OWNER = "person-al"
SESSION_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{4,100}$")
TTL_SECONDS = 600


@dataclass(frozen=True)
class OwnerUatAuthority:
    """Never authorizes any real-world action."""
    owner_identity_id: str = OWNER

    def can_approve(self, *, approver_identity_id: str,
                    organization_id: str, client_id: str | None,
                    capability: str, requested_mode: str) -> bool:
        return (
            approver_identity_id == self.owner_identity_id
            and organization_id == ORGANIZATION and client_id is None
            and capability == CAPABILITY and requested_mode == MODE
        )


def create_nonexecuting_approval(
    *, session_id: str, now: datetime,
    owner_identity_id: str = OWNER,
) -> ApprovalRequest:
    """Stable ID makes a repeated request fail, never send twice."""
    if not isinstance(session_id, str) or not SESSION_ID.fullmatch(session_id):
        raise ValueError("bounded authorized acceptance session ID required")
    if owner_identity_id != OWNER:
        raise PermissionError("test cannot broaden owner identity")
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("test issuance needs timezone-aware time")
    approval_id = APPROVAL_PREFIX + hashlib.sha256(
        ("owner-acceptance:1:" + session_id).encode("utf-8")
    ).hexdigest()[:32]
    followup = session_id.endswith(".approve")
    phase = "2/2: APPROVE" if followup else "1/2: DENY"
    return ApprovalRequest(
        approval_id=approval_id,
        request_id="owner-uat:" + session_id,
        correlation_id="owner-uat:" + session_id,
        organization_id=ORGANIZATION, client_id=None,
        requested_by=REQUESTER, capability=CAPABILITY,
        requested_mode=MODE, requested_at=now,
        expires_at=now + timedelta(seconds=TTL_SECONDS),
        authorized_approver_ids=(owner_identity_id,),
        presentation=ApprovalPresentation(
            title="TEST ONLY: Jason owner approval in Teams (" + phase + ")",
            summary=(
                "This is a NONEXECUTING acceptance test. Choose only "
                + ("APPROVE" if followup else "DENY")
                + " for this stage. No production, ticket, purchase order, "
                "service, or customer action will occur."
            ),
            facts=(
                ("Mode", "TEST ONLY / NO EXECUTION"),
                ("Session", session_id),
                ("Impact", "None: records one test approval decision"),
                ("Expires", (now + timedelta(seconds=TTL_SECONDS)).isoformat()),
                ("Next action", "Click APPROVE (test only)" if followup else "Click DENY (test only)"),
            ),
        ),
        metadata={"test_only": "true", "execution_permitted": "false"},
    )


def expected_owner_uat_decision(request: ApprovalRequest) -> str:
    """Derive the sole allowed test decision from the server-stored request.

    A Teams card title/selection is NOT authority; the signed callback must
    independently prove the exact immutable phase and stable approval ID.
    """
    prefix = "owner-uat:"
    if not isinstance(request.request_id, str) or not request.request_id.startswith(prefix):
        raise PermissionError("owner acceptance has no trusted phase")
    session_id = request.request_id[len(prefix):]
    if not SESSION_ID.fullmatch(session_id):
        raise PermissionError("owner acceptance phase has invalid session")
    expected = create_nonexecuting_approval(session_id=session_id, now=request.requested_at)
    if (request.approval_id != expected.approval_id
            or request.presentation != expected.presentation
            or request.expires_at != expected.expires_at):
        raise PermissionError("owner acceptance does not match its immutable phase")
    return "approve" if session_id.endswith(".approve") else "deny"


@dataclass
class OwnerUatIssuer:
    """Workflow creates approval then asks universal UI to send it.

    No endpoint, timer or production import creates requests automatically.
    A production registration would require a separate exact-SHA owner grant
    and resolved provenance and containment security blockers.
    """
    requests: ApprovalRequestService
    universal_interactions: UniversalInteractionService
    enabled: bool = False
    clock: Any = lambda: datetime.now(timezone.utc)

    def issue(self, *, session_id: str) -> InteractionDelivery:
        if not self.enabled:
            raise PermissionError("nonexecuting UAT issuance is disabled")
        request = create_nonexecuting_approval(
            session_id=session_id, now=self.clock(),
        )
        if self.requests.repository.get(request.approval_id) is not None:
            raise PermissionError("acceptance session already issued")
        self.requests.create(request, now=self.clock())
        return self.universal_interactions.dispatch(
            interaction_from_owner_approval(
                request, interaction_id="uat." + request.approval_id,
                workflow="owner_uat",
            )
        )


@dataclass
class OwnerUatDecisionFlow:
    """Existing signed Teams callback -> existing approval ledger ONLY.

    No accepted decision is ever used by production/CCC or an executor.
    """
    approvals: ApprovalRequestService
    signed_verifier: Any
    bindings: Any
    identities: Any
    enabled: bool = False
    owner_identity_id: str = OWNER
    clock: Any = lambda: datetime.now(timezone.utc)

    def handle(
        self, *, approval_id: str, decision: str,
        microsoft_tenant_id: str, microsoft_object_id: str,
        conversation_id: str, channel_response_id: str, decided_at: datetime,
        selections: Mapping[str, str] | None = None,
        signed_envelope: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.enabled:
            raise PermissionError("nonexecuting UAT callback is disabled")
        if (not isinstance(approval_id, str)
                or not approval_id.startswith(APPROVAL_PREFIX)
                or decision not in {"approve", "deny"}
                or selections
                or not isinstance(signed_envelope, Mapping)):
            raise PermissionError("exact signed UAT Approve/Deny required")
        token = json.dumps(dict(signed_envelope), ensure_ascii=False, separators=(",", ":"))
        machine, parsed = self.signed_verifier.parse(token)
        if not machine:
            raise PermissionError("unregistered signed Teams gateway")
        submit = parsed.approval_submit
        if (submit is None or submit.approval_id != approval_id
                or submit.decision != decision or submit.selections
                or parsed.microsoft_tenant_id != microsoft_tenant_id
                or parsed.microsoft_object_id != microsoft_object_id
                or parsed.conversation_id != conversation_id
                or submit.channel_response_id != channel_response_id
                or parsed.issued_at != decided_at
                or parsed.documents):
            raise PermissionError("signed UAT decision does not match callback")
        principal = self.signed_verifier.verify(token)
        binding = self.bindings.find(
            microsoft_tenant_id=principal.tenant_id,
            microsoft_object_id=principal.object_id,
        )
        if (binding is None or binding.status != "active"
                or binding.jason_identity_id != self.owner_identity_id):
            raise PermissionError("UAT click is not from the active owner")
        identity = self.identities.get(binding.jason_identity_id)
        if (identity is None or identity.status != "active"
                or identity.organization_id != ORGANIZATION
                or identity.identity_id != self.owner_identity_id):
            raise PermissionError("UAT owner identity is not active")
        request = self.approvals.repository.get(approval_id)
        if (request is None or request.status != ApprovalRequestStatus.PENDING
                or request.organization_id != ORGANIZATION
                or request.client_id is not None
                or request.requested_by != REQUESTER
                or request.capability != CAPABILITY
                or request.requested_mode != MODE
                or request.authorized_approver_ids != (self.owner_identity_id,)
                or request.metadata != {
                    "test_only": "true",
                    "execution_permitted": "false",
                }):
            raise PermissionError("not a pending, immutable nonexecuting UAT request")
        expected_decision = expected_owner_uat_decision(request)
        if decision != expected_decision:
            # This is a signed, correctly authenticated Owner click, but the
            # WRONG TEST PHASE choice. No ledger mutation, no success receipt.
            # Return an explicit noncommitting result so the existing Teams
            # gateway releases its short-lived processing claim, allowing the
            # Owner to select the intended action on this SAME pending card.
            return {
                "status": "denied",
                "approval_id": approval_id,
                "executed": False,
                "reply": {"text": (
                    "TEST ONLY: This stage accepts " + expected_decision.upper()
                    + " only. No decision was recorded. Choose "
                    + expected_decision.upper() + " on the original card."
                )},
            }
        result = self.approvals.accept_response(ApprovalResponse(
            approval_id=approval_id,
            organization_id=ORGANIZATION,
            approver_identity_id=identity.identity_id,
            decision=ApprovalDecision(decision),
            decided_at=decided_at,
            channel="microsoft_teams",
            channel_response_id=channel_response_id,
            authentication_evidence_hash=principal.authentication_evidence_hash,
        ), now=self.clock())
        return {
            "status": "completed",
            "approval_id": approval_id,
            "approval_status": result.status,
            "executed": False,
            "reply": {
                "text": (
                    "TEST ONLY: Your " + decision.upper() +
                    " choice was recorded through signed Teams. "
                    "No production, ticket, PO, service, or customer action was taken."
                ),
            },
        }


@dataclass(frozen=True)
class OwnerUatRouteAuthority:
    """Exact AOT owner recipient; not a general company-role shortcut."""

    def authorize(self, spec: Any):
        from communication.audience.models import AudienceType, MessagePurpose
        from .contracts import InteractionKind
        from .service import AuthorizedRoute
        if (getattr(spec, "workflow", None) != "owner_uat"
                or getattr(spec, "requester_identity_id", None) != REQUESTER
                or getattr(spec, "organization_id", None) != ORGANIZATION
                or getattr(spec, "client_id", None) is not None
                or getattr(spec, "kind", None) is not InteractionKind.APPROVAL
                or not str(getattr(spec, "approval_id", "")).startswith(APPROVAL_PREFIX)):
            raise PermissionError("only exact nonexecuting owner UAT may be routed")
        return AuthorizedRoute(
            recipient_identity_id=OWNER, organization_id=ORGANIZATION, client_id=None,
            audience_type=AudienceType.EXECUTIVE, purpose=MessagePurpose.APPROVAL_REQUEST,
            channels=("teams",), authorization_ref="owner-uat:signed-request",
            allowed=True,
        )


@dataclass(frozen=True)
class OwnerUatWorkflowSendAuthority:
    """Existing Teams facade still performs a separate send-authorization gate."""

    def can_communicate(self, *, workflow: str, sender_identity_id: str,
                        recipient_identity_id: str, organization_id: str,
                        client_id: str | None, kind: str, purpose: Any) -> bool:
        from communication.audience.models import MessagePurpose
        return (
            workflow == "owner_uat"
            and sender_identity_id == REQUESTER
            and recipient_identity_id == OWNER
            and organization_id == ORGANIZATION and client_id is None
            and kind == "approval" and purpose is MessagePurpose.APPROVAL_REQUEST
        )


@dataclass(frozen=True)
class OwnerUatReleaseGate:
    """No Teams card before root-verified exact-SHA release closeout.

    The runtime can READ these existing managed release records, but never
    transition release state or grant approval by reading them.
    """
    state_root: Path
    source_revision: str

    @staticmethod
    def _private_json(path: Path, *, owner_uid: int) -> dict[str, Any]:
        if path.is_symlink() or not path.is_file():
            raise PermissionError("Owner UAT needs a regular protected release record")
        info = path.stat()
        if info.st_uid != owner_uid or not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
            raise PermissionError("Owner UAT release proof has insecure ownership/mode")
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Owner UAT release proof is malformed")
        return data

    def ready(self) -> bool:
        sha = self.source_revision
        if not isinstance(sha, str) or re.fullmatch(r"[0-9a-f]{40}", sha) is None:
            return False
        try:
            uid = os.getuid()
            release = self._private_json(
                self.state_root / "records" / ("release-" + sha[:16] + ".json"),
                owner_uid=uid,
            )
            protected = self._private_json(
                self.state_root / "protected-readback" / "production-control-state.json",
                owner_uid=uid,
            )
            candidate = release.get("release_candidate") or {}
            production = release.get("production") or {}
            ccc = production.get("ccc_post_mutation") or {}
            lkg = (protected.get("last_known_good") or {}).get("manifest") or {}
            return (
                release.get("schema_version") == "2.0"
                and release.get("release_id") == "release-" + sha[:16]
                and release.get("state") == "closed"
                and candidate.get("candidate_sha") == sha
                and (release.get("owner_approval") or {}).get("candidate_sha") == sha
                and (release.get("owner_approval") or {}).get("approved") is True
                and production.get("live_sha") == sha
                and production.get("host_revision") == sha
                and production.get("runtime_revision") == sha
                and production.get("mcp_revision") == sha
                and production.get("release_manager_source_revision") == sha
                and ccc.get("status") == "PASS"
                and ccc.get("source_revision") == sha
                and ccc.get("runtime_revision") == sha
                and protected.get("schema_version") == "1.0"
                and (protected.get("circuit_breaker") or {}).get("state") == "closed"
                and lkg.get("revision") == sha
                and lkg.get("runtime_revision") == sha
                and lkg.get("mcp_revision") == sha
                and lkg.get("host_revision") == sha
            )
        except (OSError, ValueError, TypeError, KeyError, PermissionError):
            return False


@dataclass
class OwnerUatMaintenance:
    """Existing runtime maintenance cycle, one-shot per configured session.

    No new scheduler/endpoint/Teams app. On any send ambiguity, the persisted
    request stays pending and no repeated send is attempted automatically.
    """
    issuer: OwnerUatIssuer
    session_id: str
    enabled: bool = False
    release_ready: Any = lambda: False

    def tick(self) -> bool:
        if not self.enabled or not self.release_ready():
            return False
        if not SESSION_ID.fullmatch(self.session_id) or len(self.session_id) > 88:
            raise ValueError("invalid bounded UAT campaign session")
        candidate = create_nonexecuting_approval(
            session_id=self.session_id, now=self.issuer.clock()
        )
        first = self.issuer.requests.repository.get(candidate.approval_id)
        if first is None:
            self.issuer.issue(session_id=self.session_id)
            return True
        # The second card is contingent on the *verified* terminal DENY
        # receipt from the real signed gateway. Never send both at once,
        # infer a click from provider delivery, or resend ambiguous sends.
        if first.status != ApprovalRequestStatus.DENIED:
            return False
        followup_session = self.session_id + ".approve"
        followup = create_nonexecuting_approval(
            session_id=followup_session, now=self.issuer.clock()
        )
        if self.issuer.requests.repository.get(followup.approval_id) is not None:
            return False
        self.issuer.issue(session_id=followup_session)
        return True
