"""Runtime composition for governed Teams approval delivery through OpenClaw.

The runtime intentionally accepts an injected OpenClaw Gateway client. OpenClaw is
transport only; Jason approval policy, audit, identity/authority, and orchestration
remain authoritative.
"""

from __future__ import annotations

from dataclasses import dataclass

from orchestrator.approval_audit import ApprovalAuditRecorder
from orchestrator.approval_delivery import ApprovalRequestDeliveryCoordinator
from connectors.src.jason_connectors.approval_requests import ApprovalRequestService

from .openclaw_teams_approval_transport import (
    OpenClawGatewayClient,
    OpenClawTeamsApprovalDeliveryChannel,
    OpenClawTeamsApprovalTargetResolver,
)


@dataclass(frozen=True, slots=True)
class OpenClawTeamsApprovalRuntimeConfig:
    targets: OpenClawTeamsApprovalTargetResolver

    def validate(self) -> None:
        if self.targets is None:
            raise ValueError("OpenClaw Teams approval target resolver is required")


def build_openclaw_teams_approval_delivery_coordinator(
    *,
    config: OpenClawTeamsApprovalRuntimeConfig,
    gateway: OpenClawGatewayClient,
    approval_service: ApprovalRequestService,
    audit: ApprovalAuditRecorder,
) -> ApprovalRequestDeliveryCoordinator:
    """Assemble the governed Teams delivery path using OpenClaw transport."""

    config.validate()
    channel = OpenClawTeamsApprovalDeliveryChannel(
        gateway=gateway,
        targets=config.targets,
    )
    return ApprovalRequestDeliveryCoordinator(
        approval_service=approval_service,
        audit=audit,
        channel=channel,
    )
