"""OpenClaw-backed Microsoft Teams transport for governed Jason approvals.

OpenClaw is a replaceable transport/interface provider only. This module maps a
provider-neutral Jason approval card into the supported OpenClaw Gateway `send`
boundary. It never decides whether an approval is valid and never creates execution
authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Protocol

from connectors.src.jason_connectors.approval_requests import ApprovalRequest
from orchestrator.approval_delivery import ApprovalDeliveryReceipt

from .teams_approval_channel import render_approval_card


class OpenClawGatewayClient(Protocol):
    """Minimal supported OpenClaw Gateway request boundary used by Jason."""

    def request(self, *, method: str, params: Mapping[str, Any]) -> Mapping[str, Any]: ...


@dataclass(frozen=True, slots=True)
class OpenClawTeamsApprovalTarget:
    organization_id: str
    to: str
    account_id: str | None = None

    def validate(self) -> None:
        if not self.organization_id.strip():
            raise ValueError("organization_id must be non-empty")
        if not self.to.strip():
            raise ValueError("OpenClaw Teams target must be non-empty")
        if self.account_id is not None and not self.account_id.strip():
            raise ValueError("OpenClaw Teams account_id must be non-empty when supplied")


class OpenClawTeamsApprovalTargetResolver(Protocol):
    def resolve(self, *, organization_id: str) -> OpenClawTeamsApprovalTarget | None: ...


@dataclass(frozen=True, slots=True)
class OpenClawTeamsApprovalDeliveryChannel:
    gateway: OpenClawGatewayClient
    targets: OpenClawTeamsApprovalTargetResolver

    def deliver(self, request: ApprovalRequest) -> ApprovalDeliveryReceipt:
        request.validate()
        target = self.targets.resolve(organization_id=request.organization_id)
        if target is None:
            raise PermissionError("no governed OpenClaw Teams approval target for organization")
        target.validate()
        if target.organization_id != request.organization_id:
            raise PermissionError("OpenClaw Teams target organization mismatch")

        card = render_approval_card(request)
        params = self._build_send_params(request=request, target=target, card=card)
        response = self.gateway.request(method="send", params=params)
        message_id = response.get("messageId")
        if not isinstance(message_id, str) or not message_id.strip():
            raise RuntimeError("OpenClaw Teams delivery did not return a messageId")
        channel = response.get("channel")
        if channel not in (None, "msteams"):
            raise RuntimeError("OpenClaw Teams delivery returned an unexpected channel")

        return ApprovalDeliveryReceipt(
            channel="microsoft_teams",
            channel_reference_id=message_id.strip(),
            delivered_at=datetime.now(timezone.utc),
        )

    @staticmethod
    def _build_send_params(*, request: ApprovalRequest, target: OpenClawTeamsApprovalTarget, card) -> Mapping[str, Any]:
        presentation = {
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
            presentation["body"].append(
                {
                    "type": "TextBlock",
                    "text": "Evidence references: " + ", ".join(card.evidence_artifact_ids),
                    "isSubtle": True,
                    "wrap": True,
                }
            )

        params: dict[str, Any] = {
            "to": target.to.strip(),
            "channel": "msteams",
            "idempotencyKey": f"jason-approval:{request.organization_id}:{request.approval_id}",
            "text": card.summary,
            "payload": {
                "text": card.summary,
                "channelData": {
                    "msteams": {
                        "presentationCard": presentation,
                    }
                },
            },
        }
        if target.account_id:
            params["accountId"] = target.account_id.strip()
        return params


@dataclass
class InMemoryOpenClawTeamsApprovalTargetResolver:
    records: dict[str, OpenClawTeamsApprovalTarget]

    def resolve(self, *, organization_id: str) -> OpenClawTeamsApprovalTarget | None:
        return self.records.get(organization_id)
