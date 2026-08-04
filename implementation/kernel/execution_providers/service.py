from __future__ import annotations

from kernel.execution_providers.contracts import (
    ExecutionProvider,
    ProviderApproval,
    ProviderCandidateQuery,
    ProviderHealth,
    ProviderLifecycle,
)
from kernel.execution_providers.repository import (
    InMemoryExecutionProviderRegistry,
)


class ExecutionProviderRegistryService:
    def __init__(
        self,
        *,
        registry: InMemoryExecutionProviderRegistry,
    ) -> None:
        self._registry = registry

    def register(self, provider: ExecutionProvider) -> None:
        self._validate_governance(provider)
        self._registry.register(provider)

    def get(self, provider_id: str) -> ExecutionProvider:
        return self._registry.get(provider_id)

    def list_all(self) -> tuple[ExecutionProvider, ...]:
        return self._registry.list_all()

    def find_candidates(
        self,
        query: ProviderCandidateQuery,
    ) -> tuple[ExecutionProvider, ...]:
        return self._registry.find_candidates(query)

    def set_health(
        self,
        *,
        provider_id: str,
        health_status: ProviderHealth,
    ) -> ExecutionProvider:
        return self._registry.update_health(
            provider_id=provider_id,
            health_status=health_status,
        )

    def set_approval(
        self,
        *,
        provider_id: str,
        approval_status: ProviderApproval,
    ) -> ExecutionProvider:
        return self._registry.update_approval(
            provider_id=provider_id,
            approval_status=approval_status,
        )

    def set_lifecycle(
        self,
        *,
        provider_id: str,
        lifecycle_status: ProviderLifecycle,
    ) -> ExecutionProvider:
        return self._registry.update_lifecycle(
            provider_id=provider_id,
            lifecycle_status=lifecycle_status,
        )

    @staticmethod
    def _validate_governance(
        provider: ExecutionProvider,
    ) -> None:
        if (
            provider.lifecycle_status
            is ProviderLifecycle.AVAILABLE
        ):
            if (
                provider.approval_status
                not in {
                    ProviderApproval.APPROVED,
                    ProviderApproval.PILOT,
                }
            ):
                raise ValueError(
                    "Available providers must be approved or pilot."
                )

            if (
                provider.health_status
                is ProviderHealth.UNKNOWN
            ):
                raise ValueError(
                    "Available providers must not have unknown health."
                )

            if not provider.pricing_profile_id:
                raise ValueError(
                    "Available providers require a pricing profile ID."
                )
