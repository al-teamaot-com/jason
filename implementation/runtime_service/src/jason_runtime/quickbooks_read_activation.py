from __future__ import annotations

import os
from dataclasses import dataclass

from kernel.capabilities import CapabilityLifecycle, CapabilityRegistryService
from kernel.execution_providers import (
    ExecutionProviderRegistryService,
    ProviderApproval,
    ProviderHealth,
    ProviderLifecycle,
    ProviderType,
)
from orchestrator.quickbooks_capability_catalog import (
    QUICKBOOKS_CAPABILITIES,
    QUICKBOOKS_PROVIDER,
)

QUICKBOOKS_READ_ACTIVATION_ENV = "JASON_QUICKBOOKS_READ_PROFILE"
QUICKBOOKS_READ_SANDBOX_PROFILE = "quickbooks-sandbox-read-v1"


class QuickBooksReadActivationError(RuntimeError):
    """Raised when QuickBooks read activation cannot prove its exact contract."""


@dataclass(frozen=True, slots=True)
class QuickBooksReadActivationState:
    profile: str
    enabled: bool
    capability_names: tuple[str, ...]


def apply_quickbooks_read_activation_profile(
    *,
    capabilities: CapabilityRegistryService,
    providers: ExecutionProviderRegistryService,
    profile: str | None,
) -> QuickBooksReadActivationState:
    normalized = str(profile or "").strip().casefold()
    if not normalized:
        return QuickBooksReadActivationState(
            profile="",
            enabled=False,
            capability_names=(),
        )
    if normalized != QUICKBOOKS_READ_SANDBOX_PROFILE:
        raise QuickBooksReadActivationError(
            "unsupported QuickBooks read activation profile"
        )

    provider = providers.get(QUICKBOOKS_PROVIDER)
    if provider.provider_type is not ProviderType.EXTERNAL_CONNECTOR:
        raise QuickBooksReadActivationError(
            "QuickBooks provider is not an external connector"
        )
    if provider.lifecycle_status is not ProviderLifecycle.PLANNED:
        raise QuickBooksReadActivationError(
            "QuickBooks provider is not planned before activation"
        )
    if provider.health_status is not ProviderHealth.UNKNOWN:
        raise QuickBooksReadActivationError(
            "QuickBooks provider health changed before activation"
        )
    if provider.approval_status is not ProviderApproval.PILOT:
        raise QuickBooksReadActivationError(
            "QuickBooks provider approval changed before activation"
        )
    if provider.execution_modes != frozenset({"deterministic"}):
        raise QuickBooksReadActivationError(
            "QuickBooks provider exposes a non-deterministic execution mode"
        )
    if provider.capabilities != QUICKBOOKS_CAPABILITIES:
        raise QuickBooksReadActivationError(
            "QuickBooks provider capability catalog drifted"
        )

    for capability_name in sorted(QUICKBOOKS_CAPABILITIES):
        capability = capabilities.get(
            capability_name=capability_name,
            version="1.0",
        )
        if capability.lifecycle_status is not CapabilityLifecycle.PILOT:
            raise QuickBooksReadActivationError(
                f"QuickBooks capability {capability_name!r} is not pilot"
            )
        if capability.metadata.get("read_only", "").casefold() != "true":
            raise QuickBooksReadActivationError(
                f"QuickBooks capability {capability_name!r} is not read-only"
            )
        if capability.metadata.get("provider_neutral", "").casefold() != "true":
            raise QuickBooksReadActivationError(
                f"QuickBooks capability {capability_name!r} is not provider-neutral"
            )
        if capability.approval.required:
            raise QuickBooksReadActivationError(
                f"QuickBooks capability {capability_name!r} unexpectedly requires approval"
            )

    for capability_name in sorted(QUICKBOOKS_CAPABILITIES):
        capabilities.set_lifecycle(
            capability_name=capability_name,
            version="1.0",
            lifecycle_status=CapabilityLifecycle.ACTIVE,
        )
    providers.set_approval(
        provider_id=QUICKBOOKS_PROVIDER,
        approval_status=ProviderApproval.APPROVED,
    )
    providers.set_health(
        provider_id=QUICKBOOKS_PROVIDER,
        health_status=ProviderHealth.HEALTHY,
    )
    providers.set_lifecycle(
        provider_id=QUICKBOOKS_PROVIDER,
        lifecycle_status=ProviderLifecycle.AVAILABLE,
    )
    return QuickBooksReadActivationState(
        profile=normalized,
        enabled=True,
        capability_names=tuple(sorted(QUICKBOOKS_CAPABILITIES)),
    )


def apply_quickbooks_read_activation_from_env(
    *,
    capabilities: CapabilityRegistryService,
    providers: ExecutionProviderRegistryService,
) -> QuickBooksReadActivationState:
    return apply_quickbooks_read_activation_profile(
        capabilities=capabilities,
        providers=providers,
        profile=os.getenv(QUICKBOOKS_READ_ACTIVATION_ENV, ""),
    )
