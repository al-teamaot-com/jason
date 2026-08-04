from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from kernel.execution_providers.contracts import (
    ExecutionProvider,
    ProviderApproval,
    ProviderCandidateQuery,
    ProviderHealth,
    ProviderLifecycle,
)


class DuplicateProviderError(ValueError):
    """Raised when an immutable provider ID is already registered."""


class ProviderNotFoundError(LookupError):
    """Raised when a provider does not exist."""


class InMemoryExecutionProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, ExecutionProvider] = {}

    def register(self, provider: ExecutionProvider) -> None:
        if provider.provider_id in self._providers:
            raise DuplicateProviderError(
                f"Provider ID already exists: {provider.provider_id}"
            )
        self._providers[provider.provider_id] = provider

    def get(self, provider_id: str) -> ExecutionProvider:
        try:
            return self._providers[provider_id]
        except KeyError as error:
            raise ProviderNotFoundError(
                f"Provider was not found: {provider_id}"
            ) from error

    def list_all(self) -> tuple[ExecutionProvider, ...]:
        return tuple(
            sorted(
                self._providers.values(),
                key=lambda provider: provider.provider_id,
            )
        )

    def find_candidates(
        self,
        query: ProviderCandidateQuery,
    ) -> tuple[ExecutionProvider, ...]:
        matches: list[ExecutionProvider] = []

        for provider in self._providers.values():
            if query.capability not in provider.capabilities:
                continue

            if (
                query.execution_mode is not None
                and query.execution_mode not in provider.execution_modes
            ):
                continue

            if (
                query.classification is not None
                and query.classification
                not in provider.supported_classifications
            ):
                continue

            if (
                query.region is not None
                and provider.regions
                and query.region not in provider.regions
            ):
                continue

            if provider.lifecycle_status is ProviderLifecycle.RETIRED:
                continue

            if (
                provider.lifecycle_status is ProviderLifecycle.DEPRECATED
                and not query.include_deprecated
            ):
                continue

            if provider.lifecycle_status is ProviderLifecycle.PLANNED:
                continue

            if provider.approval_status in {
                ProviderApproval.BLOCKED,
                ProviderApproval.RETIRED,
            }:
                continue

            if (
                provider.approval_status is ProviderApproval.PILOT
                and not query.allow_pilot
            ):
                continue

            if provider.health_status in {
                ProviderHealth.UNAVAILABLE,
                ProviderHealth.MAINTENANCE,
                ProviderHealth.UNKNOWN,
            }:
                continue

            if (
                provider.health_status is ProviderHealth.WARNING
                and not query.include_warning
            ):
                continue

            matches.append(provider)

        return tuple(
            sorted(
                matches,
                key=lambda provider: provider.provider_id,
            )
        )

    def update_health(
        self,
        *,
        provider_id: str,
        health_status: ProviderHealth,
    ) -> ExecutionProvider:
        current = self.get(provider_id)
        updated = replace(
            current,
            health_status=health_status,
        )
        self._providers[provider_id] = updated
        return updated

    def update_approval(
        self,
        *,
        provider_id: str,
        approval_status: ProviderApproval,
    ) -> ExecutionProvider:
        current = self.get(provider_id)
        updated = replace(
            current,
            approval_status=approval_status,
        )
        self._providers[provider_id] = updated
        return updated

    def update_lifecycle(
        self,
        *,
        provider_id: str,
        lifecycle_status: ProviderLifecycle,
    ) -> ExecutionProvider:
        current = self.get(provider_id)
        updated = replace(
            current,
            lifecycle_status=lifecycle_status,
        )
        self._providers[provider_id] = updated
        return updated

    def update_review(
        self,
        *,
        provider_id: str,
        reviewed_at: datetime,
    ) -> ExecutionProvider:
        current = self.get(provider_id)
        updated = replace(
            current,
            stewardship=replace(
                current.stewardship,
                last_reviewed_at=reviewed_at,
            ),
        )
        self._providers[provider_id] = updated
        return updated
