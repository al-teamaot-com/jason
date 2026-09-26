"""Production Teams owner-review loop for playbook autonomy promotion.

Autonomy-ready playbooks are detected from the source-controlled registry.  Missing
exact durable promotions generate a persistent owner approval request and a Teams
Adaptive Card.  A signed, Bot-Framework-authenticated card response is mapped to a
Jason identity and only an authorized owner approval can mechanically create the
exact durable promotion.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Mapping, Protocol
from urllib.request import Request, urlopen

from autonomous_remediation.playbook_autonomy_approval import (
    SQLitePlaybookAutonomyApprovalStore,
)
from autonomous_remediation.playbook_autonomy_review import (
    PLAYBOOK_AUTONOMY_PROMOTION_CAPABILITY,
    PlaybookAutonomyReviewService,
)
from autonomous_remediation.playbook_autonomy_scope import (
    PlaybookAutonomyScopeError,
    registered_autonomy_scope,
)
from connectors.microsoft_graph.teams_approval_channel import render_approval_card
from connectors.src.jason_connectors.approval_requests import (
    ApprovalDecision,
    ApprovalRequest,
    ApprovalRequestService,
    ApprovalRequestStatus,
    ApprovalResponse,
    SQLiteApprovalRequestRepository,
)


class ActiveMicrosoftIdentityBindingReader(Protocol):
    def find_active_by_jason_identity(self, *, jason_identity_id: str): ...
    def find(self, *, microsoft_tenant_id: str, microsoft_object_id: str): ...


class OwnerOnlyPlaybookAutonomyAuthority:
    def __init__(self, owner_identity_ids) -> None:
        self.owner_identity_ids = frozenset(str(x).strip() for x in owner_identity_ids if str(x).strip())

    def can_approve(
        self,
        *,
        approver_identity_id: str,
        organization_id: str,
        client_id: str | None,
        capability: str,
        requested_mode: str,
    ) -> bool:
        return (
            organization_id == "aot"
            and client_id is None
            and capability == PLAYBOOK_AUTONOMY_PROMOTION_CAPABILITY
            and requested_mode.startswith("promote:")
            and approver_identity_id in self.owner_identity_ids
        )


class TeamsGatewayPlaybookApprovalSender:
    def __init__(
        self,
        *,
        gateway_url: str,
        token_file: str | Path,
        bindings: ActiveMicrosoftIdentityBindingReader,
        owner_identity_ids,
    ) -> None:
        self.gateway_url = str(gateway_url).rstrip("/")
        self.token_file = Path(token_file)
        self.bindings = bindings
        self.owner_identity_ids = tuple(sorted(str(x).strip() for x in owner_identity_ids if str(x).strip()))

    def send(self, request: ApprovalRequest) -> tuple[str, ...]:
        card = render_approval_card(request)
        adaptive = self._adaptive_card(card)
        token = self.token_file.read_text(encoding="utf-8").strip()
        if not token:
            raise PermissionError("Teams proactive token unavailable")
        message_ids: list[str] = []
        for owner_id in self.owner_identity_ids:
            binding = self.bindings.find_active_by_jason_identity(jason_identity_id=owner_id)
            if binding is None or getattr(binding, "status", None) != "active":
                raise PermissionError(f"owner Microsoft identity binding unavailable: {owner_id}")
            payload = {
                "aadObjectId": binding.microsoft_object_id,
                "tenantId": binding.microsoft_tenant_id,
                "text": card.summary,
                "card": adaptive,
            }
            body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
            http_request = Request(
                self.gateway_url + "/internal/proactive/send",
                data=body,
                method="POST",
                headers={
                    "Authorization": "Bearer " + token,
                    "Content-Type": "application/json",
                },
            )
            with urlopen(http_request, timeout=20) as response:
                result = json.loads(response.read().decode("utf-8"))
            if result.get("status") != "succeeded" or not result.get("message_id"):
                raise RuntimeError("Teams playbook approval delivery failed")
            message_ids.append(str(result["message_id"]).strip())
        return tuple(message_ids)

    @staticmethod
    def _adaptive_card(card) -> dict:
        facts = [
            {"title": "Capability", "value": card.capability},
            {"title": "Mode", "value": card.requested_mode},
            {"title": "Expires", "value": card.expires_at},
            {"title": "Approval ID", "value": card.approval_id},
        ]
        facts.extend({"title": str(k), "value": str(v)} for k, v in card.facts)
        body = [
            {"type": "TextBlock", "text": card.title, "weight": "Bolder", "wrap": True},
            {"type": "TextBlock", "text": card.summary, "wrap": True},
            {"type": "FactSet", "facts": facts},
        ]
        if card.evidence_artifact_ids:
            body.append(
                {
                    "type": "TextBlock",
                    "text": "Evidence references: " + ", ".join(card.evidence_artifact_ids),
                    "isSubtle": True,
                    "wrap": True,
                }
            )
        return {
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "type": "AdaptiveCard",
            "version": "1.4",
            "body": body,
            "actions": [
                {
                    "type": "Action.Submit",
                    "title": "Approve",
                    "data": {
                        "approval_id": card.approval_id,
                        "organization_id": card.organization_id,
                        "decision": "approve",
                    },
                },
                {
                    "type": "Action.Submit",
                    "title": "Deny",
                    "data": {
                        "approval_id": card.approval_id,
                        "organization_id": card.organization_id,
                        "decision": "deny",
                    },
                },
                {
                    "type": "Action.Submit",
                    "title": "Request Changes",
                    "data": {
                        "approval_id": card.approval_id,
                        "organization_id": card.organization_id,
                        "decision": "request_changes",
                    },
                },
            ],
        }


class PlaybookAutonomyReviewMaintenance:
    """Detect autonomy-ready scopes lacking durable promotion and notify owners once."""

    def __init__(
        self,
        *,
        enabled: bool,
        registry_path: Path,
        request_repository: SQLiteApprovalRequestRepository,
        approval_service: ApprovalRequestService,
        review_service: PlaybookAutonomyReviewService,
        sender: TeamsGatewayPlaybookApprovalSender,
        promotion_store: SQLitePlaybookAutonomyApprovalStore,
        interval_seconds: int = 300,
        now=None,
    ) -> None:
        if interval_seconds < 60:
            raise ValueError("playbook autonomy review interval must be at least 60 seconds")
        self.enabled = bool(enabled)
        self.registry_path = Path(registry_path)
        self.request_repository = request_repository
        self.approval_service = approval_service
        self.review_service = review_service
        self.sender = sender
        self.promotion_store = promotion_store
        self.interval_seconds = interval_seconds
        self.now = now or (lambda: datetime.now(timezone.utc))
        self._next_due: datetime | None = None

    def tick(self) -> bool:
        if not self.enabled:
            return False
        current = self.now()
        if self._next_due is not None and current < self._next_due:
            return False
        self._next_due = current + timedelta(seconds=self.interval_seconds)

        document = json.loads(self.registry_path.read_text(encoding="utf-8"))
        raw_playbooks = document.get("playbooks")
        if not isinstance(raw_playbooks, list):
            raise RuntimeError("playbook registry is invalid")
        handled = False
        requests = self.request_repository.list_all()

        for raw in raw_playbooks:
            if not isinstance(raw, Mapping):
                continue
            playbook_id = str(raw.get("id") or "").strip()
            if not playbook_id:
                continue
            try:
                scope = registered_autonomy_scope(
                    registry_path=self.registry_path,
                    playbook_id=playbook_id,
                )
            except PlaybookAutonomyScopeError:
                continue
            if self.promotion_store.find_scope_approved(
                playbook_id=scope.playbook_id,
                playbook_version=scope.playbook_version,
                policy_id=scope.policy_id,
                required_capabilities=scope.allowed_capabilities,
            ) is not None:
                continue

            exact = [
                request
                for request in requests
                if request.capability == PLAYBOOK_AUTONOMY_PROMOTION_CAPABILITY
                and request.metadata.get("playbook_id") == scope.playbook_id
                and request.metadata.get("playbook_version") == scope.playbook_version
                and request.metadata.get("entry_sha256") == scope.entry_sha256
            ]
            pending = [
                request for request in exact
                if request.status is ApprovalRequestStatus.PENDING
            ]
            if len(pending) > 1:
                raise RuntimeError(
                    f"multiple pending autonomy reviews match {scope.playbook_id}@{scope.playbook_version}"
                )
            if pending:
                request = pending[0]
                if not request.metadata.get("delivery_message_ids"):
                    message_ids = self.sender.send(request)
                    self.request_repository.put(
                        replace(
                            request,
                            metadata={
                                **request.metadata,
                                "delivery_message_ids": ",".join(message_ids),
                            },
                        )
                    )
                    handled = True
                continue

            if any(
                request.status in {
                    ApprovalRequestStatus.APPROVED,
                    ApprovalRequestStatus.DENIED,
                    ApprovalRequestStatus.CHANGES_REQUESTED,
                }
                for request in exact
            ):
                # An owner decision on this exact fingerprint is terminal.  A tech must
                # change the reviewed scope/fingerprint before a denied or changes-requested
                # playbook can return for approval.  Approved-without-promotion is a
                # control-plane repair condition and must not generate another owner click.
                continue

            # Expired/cancelled requests may be recreated for the same unchanged scope.
            request = self.review_service.build_request(
                playbook_id=scope.playbook_id,
                requested_by="jason-playbook-review",
                organization_id="aot",
                ttl=timedelta(hours=24),
                now=current,
            )
            self.approval_service.create(request, now=current)
            message_ids = self.sender.send(request)
            self.request_repository.put(
                replace(
                    request,
                    metadata={
                        **request.metadata,
                        "delivery_message_ids": ",".join(message_ids),
                    },
                )
            )
            requests = (*requests, request)
            handled = True
        return handled


class PlaybookAutonomyApprovalInteractionFlow:
    """Consume authenticated card-submit evidence and promote only on owner approval."""

    def __init__(
        self,
        *,
        bindings: ActiveMicrosoftIdentityBindingReader,
        approval_service: ApprovalRequestService,
        review_service: PlaybookAutonomyReviewService,
    ) -> None:
        self.bindings = bindings
        self.approval_service = approval_service
        self.review_service = review_service

    def handle(
        self,
        *,
        approval_id: str,
        decision: str,
        microsoft_tenant_id: str,
        microsoft_object_id: str,
        conversation_id: str,
        channel_response_id: str,
        decided_at: datetime,
    ) -> Mapping[str, object]:
        binding = self.bindings.find(
            microsoft_tenant_id=microsoft_tenant_id,
            microsoft_object_id=microsoft_object_id,
        )
        if binding is None or getattr(binding, "status", None) != "active":
            raise PermissionError("authenticated Microsoft principal is not bound to an active Jason identity")

        request = self.approval_service.repository.get(approval_id)
        if request is None:
            raise PermissionError("playbook autonomy approval request not found")
        if request.organization_id != "aot":
            raise PermissionError("playbook autonomy approval organization mismatch")

        try:
            parsed_decision = ApprovalDecision(decision)
        except ValueError as exc:
            raise PermissionError("invalid playbook autonomy approval decision") from exc

        accepted = self.approval_service.accept_response(
            ApprovalResponse(
                approval_id=approval_id,
                organization_id=request.organization_id,
                approver_identity_id=binding.jason_identity_id,
                decision=parsed_decision,
                decided_at=decided_at,
                channel="microsoft_teams",
                channel_response_id=channel_response_id,
            ),
            now=decided_at,
        )
        if accepted.status == "approved":
            result = self.review_service.promote_accepted(request=request, accepted=accepted)
            return {
                "status": "completed",
                "reply": {
                    "text": (
                        f"Approved. Jason autonomy is now promoted for "
                        f"{result.scope.playbook_id}@{result.scope.playbook_version}."
                    )
                },
                "approval_id": approval_id,
                "promotion_approval_id": result.promotion.approval_id,
            }
        if accepted.status == "changes_requested":
            return {
                "status": "completed",
                "reply": {"text": "Changes requested. The playbook was not promoted."},
                "approval_id": approval_id,
            }
        return {
            "status": "completed",
            "reply": {"text": "Denied. The playbook was not promoted."},
            "approval_id": approval_id,
        }
