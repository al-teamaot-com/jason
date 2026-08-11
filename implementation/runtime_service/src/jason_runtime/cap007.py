from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from connectors.core.contracts import ConnectorContext
from connectors.core.openbao_secrets import OpenBaoSecretResolver
from jason_cap_007.service import SecretLease
from orchestrator.event_store import SQLiteOrchestrationEventStore


@dataclass(frozen=True, slots=True)
class Cap007OpenBaoSecretBroker:
    """Adapt the connector OpenBao resolver to CAP-007's JKD-003 lease contract.

    OpenBaoSecretResolver revokes its short-lived service token immediately after
    the allow-listed KV read. The returned SecretLease therefore contains only
    the resolved provider fields and does not represent a persistent OpenBao
    token that must be retained by the orchestrator or capability.
    """

    resolver: OpenBaoSecretResolver

    @classmethod
    def build(
        cls,
        *,
        base_url: str,
        role_id_path: Path,
        secret_id_path: Path,
    ) -> "Cap007OpenBaoSecretBroker":
        return cls(
            resolver=OpenBaoSecretResolver(
                base_url=base_url,
                role_id_path=role_id_path,
                secret_id_path=secret_id_path,
            )
        )

    def resolve(
        self,
        *,
        secret_name: str,
        purpose: str,
        execution_context_id: str,
        requester_id: str,
        organization_id: str,
        client_id: str | None,
        capability: str,
        correlation_id: str,
    ) -> SecretLease:
        del purpose, execution_context_id
        context = ConnectorContext(
            correlation_id=correlation_id,
            principal_id=requester_id,
            organization_id=organization_id,
            client_id=client_id,
            capability=capability,
            mode="execute",
        )
        values = self.resolver.resolve(secret_name, context)
        return SecretLease(values=dict(values), lease_id=None)

    def revoke(self, lease: SecretLease) -> None:
        # The resolver already revoked the short-lived OpenBao service token
        # before returning the secret values. Clear semantics are intentionally
        # explicit: there is no retained runtime token to revoke here.
        del lease


@dataclass(frozen=True, slots=True)
class Cap007EventAudit:
    """Translate CAP-007 safe audit metadata into ORCH-001 event-store records."""

    events: SQLiteOrchestrationEventStore

    def append(self, event_type: str, payload: Mapping[str, Any]) -> None:
        stage = {
            "email.send.attempted": "invoking",
            "email.send.completed": "completed",
            "email.send.failed": "failed",
        }.get(event_type, "completed")

        self.events.append(
            event_type,
            {
                "execution_id": str(payload["execution_id"]),
                "correlation_id": str(payload["correlation_id"]),
                "organization_id": str(payload["organization_id"]),
                "principal_id": str(payload["principal_id"]),
                "capability_name": str(payload["capability"]),
                "stage": stage,
                **dict(payload),
            },
        )
