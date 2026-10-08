"""Shared per-run playbook action approval and resume coordination."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Mapping, Protocol
from uuid import uuid4

from autonomous_remediation.autonomous_principal import PerRunApprovalAuthorization
from connectors.src.jason_connectors.approval_requests import (
    ApprovalDecision,
    ApprovalPresentation,
    ApprovalRequest,
    ApprovalRequestService,
    ApprovalRequestStatus,
    ApprovalResponse,
)

from .playbook_approval_resume import (
    PlaybookActionProposal,
    ProposalState,
    SQLitePlaybookActionProposalStore,
)


class ApprovalSender(Protocol):
    def send(self, request: ApprovalRequest) -> tuple[str, ...]: ...


class ActiveMicrosoftIdentityBindingReader(Protocol):
    def find(self, *, microsoft_tenant_id: str, microsoft_object_id: str): ...


class OwnerOnlyPlaybookActionAuthority:
    def __init__(self, owner_identity_ids) -> None:
        self.owner_identity_ids = frozenset(
            str(value).strip() for value in owner_identity_ids if str(value).strip()
        )

    def can_approve(
        self,
        *,
        approver_identity_id: str,
        organization_id: str,
        client_id: str | None,
        capability: str,
        requested_mode: str,
    ) -> bool:
        del client_id
        return (
            organization_id == "aot"
            and capability == "automation.component.execute"
            and str(requested_mode).startswith("proposal:")
            and approver_identity_id in self.owner_identity_ids
        )


class PlaybookActionApprovalCoordinator:
    def __init__(
        self,
        *,
        proposal_store: SQLitePlaybookActionProposalStore,
        approval_service: ApprovalRequestService,
        sender: ApprovalSender,
        owner_identity_ids,
    ) -> None:
        self.proposal_store = proposal_store
        self.approval_service = approval_service
        self.sender = sender
        self.owner_identity_ids = tuple(
            sorted(str(value).strip() for value in owner_identity_ids if str(value).strip())
        )
        if not self.owner_identity_ids:
            raise ValueError("at least one owner identity is required")

    @staticmethod
    def approval_id_for(proposal: PlaybookActionProposal) -> str:
        return "playaction-" + proposal.fingerprint[:32]

    def ensure_pending(self, proposal: PlaybookActionProposal) -> ProposalState:
        state = self.proposal_store.create(proposal)
        if state.status != "pending":
            return state

        approval_id = self.approval_id_for(proposal)
        request = self.approval_service.repository.get(approval_id)
        if request is None:
            request = ApprovalRequest(
                approval_id=approval_id,
                request_id="req-" + uuid4().hex,
                correlation_id="corr-" + uuid4().hex,
                organization_id="aot",
                client_id=proposal.client_id,
                requested_by="jason-autonomy-worker",
                capability=proposal.capability,
                requested_mode="proposal:" + proposal.fingerprint,
                requested_at=proposal.created_at,
                expires_at=proposal.expires_at,
                authorized_approver_ids=self.owner_identity_ids,
                presentation=ApprovalPresentation(
                    title=f"Approve {proposal.playbook_id} remediation",
                    summary=(
                        f"Approve one exact {proposal.action_id} execution for "
                        f"ticket {proposal.ticket_id} on target {proposal.target_id}."
                    ),
                    facts=(
                        ("Playbook", f"{proposal.playbook_id}@{proposal.playbook_version}"),
                        ("Ticket", str(proposal.ticket_id)),
                        ("Target", proposal.target_id),
                        ("Action", proposal.action_id),
                        ("Disruption", proposal.disruption_classification),
                        ("Proposal fingerprint", proposal.fingerprint),
                    ),
                ),
                metadata={
                    "proposal_id": proposal.proposal_id,
                    "proposal_fingerprint": proposal.fingerprint,
                    "playbook_id": proposal.playbook_id,
                    "playbook_version": proposal.playbook_version,
                    "policy_id": proposal.policy_id,
                    "ticket_id": str(proposal.ticket_id),
                    "target_id": proposal.target_id,
                    "action_id": proposal.action_id,
                },
                status=ApprovalRequestStatus.PENDING,
            )
            self.approval_service.create(request, now=proposal.created_at)
        else:
            if request.metadata.get("proposal_fingerprint") != proposal.fingerprint:
                raise PermissionError("existing approval request does not match proposal")
            if request.status is not ApprovalRequestStatus.PENDING:
                return state

        if not request.metadata.get("delivery_message_ids"):
            message_ids = self.sender.send(request)
            self.approval_service.repository.put(
                replace(
                    request,
                    metadata={
                        **request.metadata,
                        "delivery_message_ids": ",".join(message_ids),
                    },
                )
            )
        return state

    def state_for_ticket(self, ticket_id: int) -> ProposalState | None:
        return self.proposal_store.find_for_ticket(ticket_id)

    def authorization_for(
        self,
        *,
        ticket_id: int,
        capability: str,
        action_id: str,
        target_id: str,
        arguments: Mapping[str, object],
    ) -> PerRunApprovalAuthorization:
        state = self.proposal_store.find_for_ticket(ticket_id)
        if state is None:
            raise PermissionError("no per-run playbook action proposal exists")
        proposal = state.proposal
        if state.status != "approved":
            raise PermissionError("playbook action proposal is not approved")
        if (
            proposal.capability != str(capability)
            or proposal.action_id != str(action_id)
            or proposal.target_id != str(target_id)
            or dict(proposal.arguments) != dict(arguments)
        ):
            raise PermissionError("approved proposal no longer matches exact execution intent")
        if not state.approval_id or not state.decided_by:
            raise PermissionError("approved proposal is missing approval identity")
        return PerRunApprovalAuthorization(
            approval_request_id=state.approval_id,
            approved_by=state.decided_by,
            proposal_fingerprint=proposal.fingerprint,
            playbook_id=proposal.playbook_id,
            playbook_version=proposal.playbook_version,
            policy_id=proposal.policy_id,
        )

    def mark_consumed(
        self,
        *,
        ticket_id: int,
        execution_id: str,
        correlation_id: str,
        now: datetime | None = None,
    ) -> ProposalState:
        state = self.proposal_store.find_for_ticket(ticket_id)
        if state is None:
            raise LookupError("playbook action proposal not found")
        return self.proposal_store.consume_approved(
            proposal_id=state.proposal.proposal_id,
            proposal_fingerprint=state.proposal.fingerprint,
            execution_id=execution_id,
            correlation_id=correlation_id,
            now=now,
        )


class PlaybookActionApprovalInteractionFlow:
    def __init__(
        self,
        *,
        bindings: ActiveMicrosoftIdentityBindingReader,
        approval_service: ApprovalRequestService,
        proposal_store: SQLitePlaybookActionProposalStore,
    ) -> None:
        self.bindings = bindings
        self.approval_service = approval_service
        self.proposal_store = proposal_store

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
        del conversation_id
        if selections:
            raise PermissionError(
                "playbook action approval does not accept mutable card selections"
            )
        binding = self.bindings.find(
            microsoft_tenant_id=microsoft_tenant_id,
            microsoft_object_id=microsoft_object_id,
        )
        if binding is None or getattr(binding, "status", None) != "active":
            raise PermissionError(
                "authenticated Microsoft principal is not bound to an active Jason identity"
            )

        request = self.approval_service.repository.get(approval_id)
        if request is None:
            raise PermissionError("playbook action approval request not found")
        proposal_id = str(request.metadata.get("proposal_id") or "")
        fingerprint = str(request.metadata.get("proposal_fingerprint") or "")
        proposal_state = self.proposal_store.get(proposal_id)
        if proposal_state is None:
            raise PermissionError("playbook action proposal is missing")
        if proposal_state.proposal.fingerprint != fingerprint:
            raise PermissionError("approval request does not match persisted proposal")

        try:
            parsed = ApprovalDecision(decision)
        except ValueError as exc:
            raise PermissionError("invalid playbook action approval decision") from exc

        accepted = self.approval_service.accept_response(
            ApprovalResponse(
                approval_id=approval_id,
                organization_id=request.organization_id,
                approver_identity_id=binding.jason_identity_id,
                decision=parsed,
                decided_at=decided_at,
                channel="microsoft_teams",
                channel_response_id=channel_response_id,
            ),
            now=decided_at,
        )
        state = self.proposal_store.decide(
            proposal_id=proposal_id,
            proposal_fingerprint=fingerprint,
            approval_id=approval_id,
            decision=accepted.status,
            decided_by=accepted.decided_by,
            decided_at=accepted.decided_at,
        )
        if state.status == "approved":
            text = "Approved. Jason will resume the exact persisted playbook action."
        elif state.status == "denied":
            text = "Denied. Jason will not execute the proposed playbook action."
        else:
            text = "Changes requested. Jason will not execute the unchanged proposal."
        return {
            "status": "completed",
            "approval_id": approval_id,
            "proposal_id": proposal_id,
            "reply": {"text": text},
        }
