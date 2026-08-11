from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from kernel.capabilities.service import CapabilityRegistryService
from kernel.execution_providers.service import ExecutionProviderRegistryService
from orchestrator.event_store import OrchestrationEventStore


@dataclass(frozen=True, slots=True)
class ManagementReadContext:
    principal_id: str
    organization_id: str

    def __post_init__(self) -> None:
        if not self.principal_id.strip():
            raise ValueError("principal_id must be non-empty")
        if not self.organization_id.strip():
            raise ValueError("organization_id must be non-empty")


class ReadAuthorizer(Protocol):
    def may_read(
        self,
        *,
        context: ManagementReadContext,
        resource: str,
    ) -> bool: ...


class ManagementReadDenied(PermissionError):
    pass


class ManagementApiService:
    """Read-only management projection over authoritative Jason services.

    The service never selects or invokes providers. It only projects already-
    governed registry and audit state for an authenticated/authorized principal.
    """

    def __init__(
        self,
        *,
        capabilities: CapabilityRegistryService,
        providers: ExecutionProviderRegistryService,
        events: OrchestrationEventStore,
        authorizer: ReadAuthorizer,
        kernel_version: str = "0.1.0",
    ) -> None:
        self._capabilities = capabilities
        self._providers = providers
        self._events = events
        self._authorizer = authorizer
        self._kernel_version = kernel_version

    def system_health(self, context: ManagementReadContext) -> dict[str, object]:
        self._require(context, "system.health")
        return {
            "status": "healthy",
            "version": self._kernel_version,
            "components": [
                {"name": "capability_registry", "status": "healthy"},
                {"name": "execution_provider_registry", "status": "healthy"},
                {"name": "orchestration_event_store", "status": "healthy"},
            ],
        }

    def list_capabilities(self, context: ManagementReadContext) -> list[dict[str, object]]:
        self._require(context, "capabilities")
        result: list[dict[str, object]] = []
        for item in self._capabilities.list_all():
            result.append(
                {
                    "name": item.capability_name,
                    "display_name": item.display_name,
                    "version": item.version,
                    "mode": sorted(item.permitted_execution_modes),
                    "status": item.lifecycle_status.value,
                    "risk_level": item.risk_level.value,
                    "approval_required": item.approval.required,
                    "owner_service": item.owner_service,
                    "architectural_capability_ids": sorted(
                        item.architectural_capability_ids
                    ),
                }
            )
        return result

    def list_providers(self, context: ManagementReadContext) -> list[dict[str, object]]:
        self._require(context, "providers")
        result: list[dict[str, object]] = []
        for item in self._providers.list_all():
            result.append(
                {
                    "name": item.display_name,
                    "provider_id": item.provider_id,
                    "provider_type": item.provider_type.value,
                    "status": item.lifecycle_status.value,
                    "health": item.health_status.value,
                    "approval_status": item.approval_status.value,
                    "capabilities": sorted(item.capabilities),
                    "execution_modes": sorted(item.execution_modes),
                    "credential_reference_present": bool(
                        item.metadata.get("credential_reference")
                    ),
                }
            )
        return result

    def search_audit_events(
        self,
        context: ManagementReadContext,
        *,
        execution_id: str | None = None,
        correlation_id: str | None = None,
    ) -> list[dict[str, object]]:
        self._require(context, "audit.events")
        if execution_id:
            events = self._events.list_by_execution(execution_id)
        elif correlation_id:
            events = self._events.list_by_correlation(correlation_id)
        else:
            list_recent = getattr(self._events, "list_recent", None)
            events = () if list_recent is None else list_recent(limit=100)

        visible = []
        for event in events:
            if event.organization_id != context.organization_id:
                continue
            visible.append(
                {
                    "event_id": event.event_id,
                    "event_type": event.event_type,
                    "execution_id": event.execution_id,
                    "correlation_id": event.correlation_id,
                    "principal_id": event.principal_id,
                    "organization_id": event.organization_id,
                    "capability_name": event.capability_name,
                    "stage": event.stage,
                    "outcome": event.payload.get("outcome"),
                    "evidence_reference": event.payload.get("evidence_reference"),
                    "occurred_at": event.occurred_at.isoformat(),
                }
            )
        return visible

    def overview(self, context: ManagementReadContext) -> dict[str, object]:
        self._require(context, "overview")
        capabilities = self.list_capabilities(context)
        return {
            "kernel_status": "healthy",
            "kernel_version": self._kernel_version,
            "capability_count": len(capabilities),
            "pending_approval_count": 0,
            "audit_status": "recording",
        }

    def _require(self, context: ManagementReadContext, resource: str) -> None:
        if not self._authorizer.may_read(context=context, resource=resource):
            raise ManagementReadDenied(
                f"Management read denied for resource: {resource}"
            )
