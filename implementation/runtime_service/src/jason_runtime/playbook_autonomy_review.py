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
import os
import re
import stat
from dataclasses import dataclass
from typing import Iterable, Mapping, Protocol
from .teams_communication_service import ExistingTeamsGatewayTransport

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


@dataclass(frozen=True, slots=True)
class PlaybookOwnerApprovalPolicy:
    owner_identity_ids: frozenset[str]
    allowed_requested_modes: frozenset[str] | None = None


def load_playbook_owner_approval_policy(
    *,
    path: Path,
    legacy_owner_identity_ids: Iterable[str],
) -> PlaybookOwnerApprovalPolicy:
    """Read a narrowly scoped local owner-approved role; otherwise keep legacy gates.

    This file is not supplied by Teams, ticket text or a requester. It resides
    only in the existing local Jason authority volume. Invalid files fail
    closed instead of quietly granting broader or fallback authority.
    """
    policy_path = Path(path)
    try:
        metadata = policy_path.lstat()
    except FileNotFoundError:
        return PlaybookOwnerApprovalPolicy(
            frozenset(str(x).strip() for x in legacy_owner_identity_ids if str(x).strip())
        )
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or metadata.st_uid not in (0, os.geteuid())
    ):
        raise PermissionError("playbook owner policy must be an owned 0600 regular file")
    data = json.loads(policy_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or set(data) != {
        "schema_version", "organization_id", "capability", "policy_mode",
        "owner_identity_ids", "allowed_requested_modes",
    }:
        raise PermissionError("playbook owner policy schema not approved")
    if (
        data.get("schema_version") != "1.0"
        or data.get("organization_id") != "aot"
        or data.get("capability") != PLAYBOOK_AUTONOMY_PROMOTION_CAPABILITY
        or data.get("policy_mode") != "owner_only_test"
    ):
        raise PermissionError("playbook owner policy is outside bounded AOT pilot")
    identities = data.get("owner_identity_ids")
    modes = data.get("allowed_requested_modes")
    if (
        not isinstance(identities, list) or len(identities) != 1
        or not isinstance(modes, list) or len(modes) != 1
        or any(not isinstance(x, str) for x in identities + modes)
        or not re.fullmatch(r"person-[a-z0-9-]{1,80}", identities[0])
        or not re.fullmatch(r"promote:[a-z0-9_]+@[0-9]+\.[0-9]+\.[0-9]+", modes[0])
    ):
        raise PermissionError("playbook owner policy requires one exact owner and mode")
    return PlaybookOwnerApprovalPolicy(
        owner_identity_ids=frozenset(identities),
        allowed_requested_modes=frozenset(modes),
    )


class ActiveMicrosoftIdentityBindingReader(Protocol):
    def find_active_by_jason_identity(self, *, jason_identity_id: str): ...
    def find(self, *, microsoft_tenant_id: str, microsoft_object_id: str): ...


class OwnerOnlyPlaybookAutonomyAuthority:
    def __init__(
        self, owner_identity_ids, *, allowed_requested_modes: frozenset[str] | None = None
    ) -> None:
        self.owner_identity_ids = frozenset(str(x).strip() for x in owner_identity_ids if str(x).strip())
        self.allowed_requested_modes = allowed_requested_modes

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
            and (
                self.allowed_requested_modes is None
                or requested_mode in self.allowed_requested_modes
            )
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

    def _existing_transport(self) -> ExistingTeamsGatewayTransport:
        # Single canonical adapter to the already-approved Teams gateway.
        return ExistingTeamsGatewayTransport(
            gateway_url=self.gateway_url, token_file=self.token_file)

    def send(self, request: ApprovalRequest) -> tuple[str, ...]:
        card = render_approval_card(request)
        adaptive = self._adaptive_card(card)
        receipts: list[str] = []
        transport = self._existing_transport()
        for owner_id in self.owner_identity_ids:
            # The persisted ApprovalRequest is authoritative for audience.
            if (request.organization_id and owner_id not in request.authorized_approver_ids):
                raise PermissionError("Teams approver is not authorized for this approval")
            binding = self.bindings.find_active_by_jason_identity(
                jason_identity_id=owner_id)
            if binding is None or getattr(binding, "status", None) != "active":
                raise PermissionError(
                    f"owner Microsoft identity binding unavailable: {owner_id}")
            receipt = transport.send(binding=binding, text=card.summary, card=adaptive)
            receipts.append(receipt.message_id)
        return tuple(receipts)

    def send_status(self, *, text: str) -> tuple[str, ...]:
        """Existing governed owner status messaging, no approval implied."""
        if not isinstance(text, str) or not 1 <= len(text) <= 1200:
            raise ValueError("bounded Teams status text required")
        transport = self._existing_transport()
        receipts: list[str] = []
        for identity_id in self.owner_identity_ids:
            binding = self.bindings.find_active_by_jason_identity(
                jason_identity_id=identity_id)
            if binding is None or getattr(binding, "status", None) != "active":
                raise PermissionError("Teams status recipient binding unavailable")
            receipts.append(transport.send(binding=binding, text=text).message_id)
        return tuple(receipts)

    @staticmethod
    def _adaptive_card(card) -> dict:
        # Release approval cards arrive alongside ordinary release status
        # notifications. On narrow phone screens the full 14-field metadata
        # block pushes Approve/Deny out of view, making the owner mistake a
        # status-only notification for the actionable card. Keep a separate
        # concise, unambiguous release layout; authority always comes from
        # the original immutable request, never the displayed field count.
        is_mobile_release = (
            card.capability == "release.production.approve"
            and card.approval_id.startswith("relapproval-")
        )
        is_owner_uat = (
            card.capability == "interaction.owner.acceptance.record"
            and card.approval_id.startswith("owneruatapproval-")
            and card.requested_mode == "test:nonexecuting"
        )
        if is_mobile_release:
            # Presentation only: the immutable persisted approval, signed
            # Action.Submit payload and original host/CCC gates remain intact.
            # Put the human decision first, not an unbroken technical FactSet.
            review = dict(card.facts)
            purpose = str(card.title).removeprefix("Production + CCC: ").strip()
            top_facts = [
                {"title": label, "value": str(review[key])}
                for key, label in (
                    ("Highest risk", "Risk"),
                    ("Preproduction and rollback", "Checks"),
                )
                if key in review
            ]
            top_facts.append({"title": "Expires", "value": card.expires_at})
            detail_facts = [
                {"title": label, "value": str(review[key])}
                for key, label in (
                    ("Release", "Release ID"),
                    ("Affected services", "Affected systems"),
                    ("Changed files", "Changed files"),
                    ("Manifest fingerprint", "Manifest SHA-256"),
                    ("Release policy", "Policy SHA-256"),
                    ("Purpose", "Purpose"),
                )
                if key in review
            ]
            details = [
                {"type": "TextBlock", "text": "IMPACT AND EVIDENCE",
                 "size": "Small", "weight": "Bolder", "isSubtle": True},
            ]
            if detail_facts:
                details.append({"type": "FactSet", "facts": detail_facts})
            body = [
                {"type": "TextBlock", "text": "JASON \u00b7 AOT",
                 "size": "Small", "isSubtle": True, "spacing": "None"},
                {"type": "TextBlock", "text": "Approval required",
                 "size": "Large", "color": "Warning",
                 "weight": "Bolder", "wrap": True, "spacing": "Small"},
                {"type": "TextBlock", "text": purpose or str(card.title),
                 "weight": "Bolder", "wrap": True, "spacing": "Small"},
                {"type": "TextBlock",
                 "text": ("Approve authorizes this exact release and its CCC "
                          "material review. Deployment still requires "
                          "independent checks."),
                 "size": "Small", "isSubtle": True, "wrap": True,
                 "spacing": "Small"},
                {"type": "FactSet", "facts": top_facts},
            ]
            # Full exact identities stay visible without squeezing 40-character
            # SHA values into FactSet's narrow label/value columns on phones.
            for key, label in (
                ("Exact SHA", "Exact commit"),
                ("Rollback", "Rollback commit"),
            ):
                if key in review:
                    body.extend([
                        {"type": "TextBlock", "text": label,
                         "size": "Small", "weight": "Bolder", "isSubtle": True,
                         "spacing": "Small"},
                        {"type": "TextBlock", "text": str(review[key]),
                         "size": "Small", "fontType": "Monospace",
                         "wrap": True, "spacing": "None"},
                    ])
            body.extend([
                {"type": "ActionSet", "actions": [{
                    "type": "Action.ToggleVisibility",
                    "title": "Review impact and evidence",
                    "targetElements": ["jason_release_technical_details"],
                }]},
                {"type": "Container", "id": "jason_release_technical_details",
                 "isVisible": False, "items": details},
            ])
            actions = (("Approve", "approve"), ("Deny", "deny"))
        elif is_owner_uat:
            # This is a TWO-STAGE scripted nonexecuting acceptance test.
            # Never display both buttons when only one result can advance the
            # campaign. The signed server-side callback independently checks
            # the immutable phase, rather than trusting the card UI.
            review = dict(card.facts)
            if (review.get("Mode") != "TEST ONLY / NO EXECUTION"
                    or review.get("Impact") != "None: records one test approval decision"
                    or not review.get("Session")):
                raise PermissionError("unrecognized nonexecuting owner UAT card scope")
            if (card.title == "TEST ONLY: Jason owner approval in Teams (1/2: DENY)"
                    and review.get("Next action") == "Click DENY (test only)"):
                actions = (("Deny", "deny"),)
            elif (card.title == "TEST ONLY: Jason owner approval in Teams (2/2: APPROVE)"
                    and review.get("Next action") == "Click APPROVE (test only)"):
                actions = (("Approve", "approve"),)
            else:
                raise PermissionError("nonexecuting owner UAT phase was not verifiable")
            facts = [{"title": str(k), "value": str(v)} for k, v in card.facts]
            facts.append({"title": "Expires", "value": card.expires_at})
            body = [
                {"type": "TextBlock",
                 "text": "TEST ONLY: NO OPERATION WILL EXECUTE",
                 "weight": "Bolder", "color": "Warning", "wrap": True},
                {"type": "TextBlock", "text": card.title,
                 "weight": "Bolder", "wrap": True},
                {"type": "TextBlock", "text": card.summary, "wrap": True},
                {"type": "FactSet", "facts": facts},
            ]
        else:
            facts = [
                {"title": "Capability", "value": card.capability},
                {"title": "Mode", "value": card.requested_mode},
                {"title": "Expires", "value": card.expires_at},
                {"title": "Approval ID", "value": card.approval_id},
            ]
            facts.extend({"title": str(k), "value": str(v)} for k, v in card.facts)
            actions = (
                ("Approve", "approve"), ("Deny", "deny"),
                ("Request Changes", "request_changes"),
            )
            body = [
                {"type": "TextBlock", "text": card.title, "weight": "Bolder", "wrap": True},
                {"type": "TextBlock", "text": card.summary, "wrap": True},
                {"type": "FactSet", "facts": facts},
            ]
        if card.evidence_artifact_ids:
            evidence_label = {
                "type": "TextBlock",
                "text": "Evidence references: " + ", ".join(card.evidence_artifact_ids),
                "isSubtle": True,
                "wrap": True,
            }
            if is_mobile_release:
                body[-1]["items"].append(evidence_label)
            else:
                body.append(evidence_label)
        return {
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "type": "AdaptiveCard",
            "version": "1.4",
            "body": body,
            "actions": [
                {
                    "type": "Action.Submit",
                    "title": title,
                    **({"style": "positive"} if is_mobile_release and decision == "approve"
                       else {"style": "destructive"} if is_mobile_release and decision == "deny"
                       else {}),
                    "data": {
                        "approval_id": card.approval_id, "decision": decision,
                        **({"card_challenge": card.card_instance_challenge}
                           if card.card_instance_challenge is not None else {}),
                    },
                }
                for title, decision in actions
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
        selections: Mapping[str, str] | None = None,
        microsoft_tenant_id: str,
        microsoft_object_id: str,
        conversation_id: str,
        channel_response_id: str,
        decided_at: datetime,
    ) -> Mapping[str, object]:
        if selections:
            raise PermissionError(
                "playbook autonomy approval does not accept mutable card selections"
            )
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

        pilot_modes = getattr(
            self.approval_service.authority, "allowed_requested_modes", None
        )
        if pilot_modes is not None:
            # A bounded owner-only test may reuse an independently authorized
            # promotion, but must never create a new operational capability.
            pilot_scope = registered_autonomy_scope(
                registry_path=self.review_service.registry_path,
                playbook_id=str(request.metadata.get("playbook_id") or ""),
            )
            if (
                request.requested_mode != pilot_scope.requested_mode()
                or request.metadata.get("entry_sha256") != pilot_scope.entry_sha256
                or self.review_service.promotion_store.find_scope_approved(
                    playbook_id=pilot_scope.playbook_id,
                    playbook_version=pilot_scope.playbook_version,
                    policy_id=pilot_scope.policy_id,
                    required_capabilities=pilot_scope.allowed_capabilities,
                ) is None
            ):
                raise PermissionError("owner-only pilot requires existing exact promotion")

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
            result = self.review_service.promote_accepted(
                request=request, accepted=accepted,
                allow_new_promotion=(pilot_modes is None),
            )
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
