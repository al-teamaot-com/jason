"""Microsoft Teams delivery adapter for provider-neutral Jason approval requests.

This module owns Teams-specific rendering and transport only. Approval semantics,
authority, persistence, and lifecycle remain owned by the orchestrator.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol
from urllib.request import Request, urlopen

from connectors.microsoft_graph.teams_approval_channel import render_approval_card
from orchestrator.approval_requests import ApprovalRequest


class ActiveMicrosoftIdentityBindingReader(Protocol):
    def find_active_by_jason_identity(self, *, jason_identity_id: str): ...


class TeamsGatewayApprovalSender:
    """Deliver an existing provider-neutral approval request to exact Teams identities."""

    def __init__(
        self,
        *,
        gateway_url: str,
        token_file: str | Path,
        bindings: ActiveMicrosoftIdentityBindingReader,
        recipient_identity_ids,
    ) -> None:
        self.gateway_url = str(gateway_url).rstrip("/")
        self.token_file = Path(token_file)
        self.bindings = bindings
        self.recipient_identity_ids = tuple(
            sorted(
                str(value).strip()
                for value in recipient_identity_ids
                if str(value).strip()
            )
        )
        if not self.recipient_identity_ids:
            raise ValueError("approval delivery requires at least one recipient identity")

    def send(self, request: ApprovalRequest) -> tuple[str, ...]:
        card = render_approval_card(request)
        adaptive = self._adaptive_card(card)
        token = self.token_file.read_text(encoding="utf-8").strip()
        if not token:
            raise PermissionError("Teams proactive token unavailable")

        message_ids: list[str] = []
        for recipient_id in self.recipient_identity_ids:
            binding = self.bindings.find_active_by_jason_identity(
                jason_identity_id=recipient_id
            )
            if binding is None or getattr(binding, "status", None) != "active":
                raise PermissionError(
                    f"approval recipient Microsoft identity binding unavailable: {recipient_id}"
                )
            payload = {
                "aadObjectId": binding.microsoft_object_id,
                "tenantId": binding.microsoft_tenant_id,
                "text": card.summary,
                "card": adaptive,
            }
            body = json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
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
                raise RuntimeError("Teams approval delivery failed")
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
        facts.extend(
            {"title": str(label), "value": str(value)}
            for label, value in card.facts
        )
        body = [
            {
                "type": "TextBlock",
                "text": card.title,
                "weight": "Bolder",
                "wrap": True,
            },
            {"type": "TextBlock", "text": card.summary, "wrap": True},
            {"type": "FactSet", "facts": facts},
        ]
        if card.evidence_artifact_ids:
            body.append(
                {
                    "type": "TextBlock",
                    "text": (
                        "Evidence references: "
                        + ", ".join(card.evidence_artifact_ids)
                    ),
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
