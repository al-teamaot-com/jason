"""Runtime composition for governed Teams approval delivery.

This module assembles existing boundaries; it does not create new authority. Secrets
remain behind the secret provider, Microsoft Graph remains transport, target records
remain organization-scoped configuration, and the provider-neutral approval service
and Central Orchestrator remain authoritative.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from orchestrator.approval_audit import ApprovalAuditRecorder
from orchestrator.approval_delivery import ApprovalRequestDeliveryCoordinator
from connectors.src.jason_connectors.approval_requests import ApprovalRequestService

from .graph_client_credentials import (
    MicrosoftGraphClientCredentialConfig,
    MicrosoftGraphClientCredentialTokenProvider,
    SecretValueProvider,
)
from .teams_approval_delivery import TeamsApprovalDeliveryChannel
from .teams_approval_targets import TeamsApprovalTargetRegistry
from .teams_graph_transport import JsonHttpTransport, MicrosoftGraphTeamsMessageTransport, UrllibJsonHttpTransport


class ConfidentialClientFactory(Protocol):
    def __call__(self, *, client_id: str, authority: str, client_credential: str): ...


@dataclass(frozen=True, slots=True)
class TeamsApprovalDeliveryRuntimeConfig:
    tenant_id: str
    client_id: str
    client_secret_reference: str
    target_registry: TeamsApprovalTargetRegistry
    graph_timeout_seconds: float = 20.0

    def validate(self) -> None:
        for name, value in (
            ("tenant_id", self.tenant_id),
            ("client_id", self.client_id),
            ("client_secret_reference", self.client_secret_reference),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be non-empty")
        if self.graph_timeout_seconds <= 0 or self.graph_timeout_seconds > 60:
            raise ValueError("graph_timeout_seconds must be greater than 0 and at most 60")


def build_teams_approval_delivery_coordinator(
    *,
    config: TeamsApprovalDeliveryRuntimeConfig,
    secret_provider: SecretValueProvider,
    confidential_client_factory: ConfidentialClientFactory,
    approval_service: ApprovalRequestService,
    audit: ApprovalAuditRecorder,
    http: JsonHttpTransport | None = None,
) -> ApprovalRequestDeliveryCoordinator:
    """Assemble the governed Teams delivery path from existing components."""

    config.validate()
    token_provider = MicrosoftGraphClientCredentialTokenProvider(
        config=MicrosoftGraphClientCredentialConfig(
            tenant_id=config.tenant_id.strip(),
            client_id=config.client_id.strip(),
            client_secret_reference=config.client_secret_reference.strip(),
        ),
        secret_provider=secret_provider,
        confidential_client_factory=confidential_client_factory,
    )
    graph = MicrosoftGraphTeamsMessageTransport(
        token_provider=token_provider,
        http=http or UrllibJsonHttpTransport(),
        timeout_seconds=config.graph_timeout_seconds,
    )
    channel = TeamsApprovalDeliveryChannel(
        transport=graph,
        targets=config.target_registry,
    )
    return ApprovalRequestDeliveryCoordinator(
        approval_service=approval_service,
        audit=audit,
        channel=channel,
    )
