"""Microsoft Teams delivery adapter for provider-neutral Jason approvals.

Teams remains transport only. This adapter renders approved non-secret request
metadata, sends it through an injected Microsoft Graph transport, and returns an
opaque delivery receipt for the audit chain. It does not accept approval responses
or create authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Protocol

from connectors.src.jason_connectors.approval_requests import ApprovalRequest
from orchestrator.approval_delivery import ApprovalDeliveryReceipt

from .teams_approval_channel import render_approval_card


class TeamsGraphMessageTransport(Protocol):
    def post_channel_message(
        self,
        *,
        team_id: str,
        channel_id: str,
        message: Mapping[str, Any],
    ) -> Mapping[str, Any]: ...


@dataclass(frozen=True, slots=True)
class TeamsApprovalDeliveryTarget:
    organization_id: str
    team_id: str
    channel_id: str

    def validate(self) -> None:
        for value in (self.organization_id, self.team_id, self.channel_id):
            if not value.strip():
                raise ValueError("Teams approval delivery target values must be non-empty")


class TeamsApprovalTargetResolver(Protocol):
    def resolve(self, *, organization_id: str) -> TeamsApprovalDeliveryTarget | None: ...


@dataclass(frozen=True, slots=True)
class TeamsApprovalDeliveryChannel:
    transport: TeamsGraphMessageTransport
    targets: TeamsApprovalTargetResolver

    def deliver(self, request: ApprovalRequest) -> ApprovalDeliveryReceipt:
        request.validate()
        target = self.targets.resolve(organization_id=request.organization_id)
        if target is None:
            raise PermissionError("no governed Teams approval delivery target for organization")
        target.validate()
        if target.organization_id != request.organization_id:
            raise PermissionError("Teams delivery target organization mismatch")

        card = render_approval_card(request)
        message = self._build_message(card)
        response = self.transport.post_channel_message(
            team_id=target.team_id,
            channel_id=target.channel_id,
            message=message,
        )
        message_id = response.get("id")
        if not isinstance(message_id, str) or not message_id.strip():
            raise RuntimeError("Teams delivery did not return a message id")
        delivered_at = self._response_time(response)
        return ApprovalDeliveryReceipt(
            channel="microsoft_teams",
            channel_reference_id=message_id.strip(),
            delivered_at=delivered_at,
        )

    @staticmethod
    def _build_message(card) -> Mapping[str, Any]:
        adaptive_card = {
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "type": "AdaptiveCard",
            "version": "1.4",
            "body": [
                {"type": "TextBlock", "text": card.title, "weight": "Bolder", "wrap": True},
                {"type": "TextBlock", "text": card.summary, "wrap": True},
                {
                    "type": "FactSet",
                    "facts": [
                        {"title": "Capability", "value": card.capability},
                        {"title": "Mode", "value": card.requested_mode},
                        {"title": "Expires", "value": card.expires_at},
                        {"title": "Approval ID", "value": card.approval_id},
                    ],
                },
            ],
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
            ],
        }
        if card.evidence_artifact_ids:
            adaptive_card["body"].append(
                {
                    "type": "TextBlock",
                    "text": "Evidence references: " + ", ".join(card.evidence_artifact_ids),
                    "isSubtle": True,
                    "wrap": True,
                }
            )
        return {
            "body": {
                "contentType": "html",
                "content": "<attachment id=\"jason-approval-card\"></attachment>",
            },
            "attachments": [
                {
                    "id": "jason-approval-card",
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": adaptive_card,
                }
            ],
        }

    @staticmethod
    def _response_time(response: Mapping[str, Any]) -> datetime:
        raw = response.get("createdDateTime")
        if isinstance(raw, str) and raw.strip():
            try:
                value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError as exc:
                raise RuntimeError("Teams delivery returned invalid createdDateTime") from exc
            if value.tzinfo is None:
                raise RuntimeError("Teams delivery returned timezone-naive createdDateTime")
            return value.astimezone(timezone.utc)
        return datetime.now(timezone.utc)


@dataclass
class InMemoryTeamsApprovalTargetResolver:
    records: dict[str, TeamsApprovalDeliveryTarget]

    def resolve(self, *, organization_id: str) -> TeamsApprovalDeliveryTarget | None:
        return self.records.get(organization_id)
