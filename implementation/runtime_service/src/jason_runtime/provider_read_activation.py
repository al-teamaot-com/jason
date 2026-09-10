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
from orchestrator.provider_read_capability_catalog import (
    AUTOTASK_CAPABILITIES,
    AUTOTASK_PROVIDER,
    IT_GLUE_CAPABILITIES,
    IT_GLUE_PROVIDER,
)


PROVIDER_READ_ACTIVATION_ENV = "JASON_PROVIDER_READ_ACTIVATION_PROFILE"
PROVIDER_READ_PRODUCTION_PROFILE = "itglue-autotask-read-v1"

_EXPECTED_PROVIDER_CAPABILITIES = {
    IT_GLUE_PROVIDER: IT_GLUE_CAPABILITIES,
    AUTOTASK_PROVIDER: AUTOTASK_CAPABILITIES,
}


class ProviderReadActivationError(RuntimeError):
    """Raised when provider-read activation cannot prove its exact safety contract."""


@dataclass(frozen=True, slots=True)
class ProviderReadActivationState:
    profile: str
    enabled: bool
    provider_ids: tuple[str, ...]
    capability_names: tuple[str, ...]


def _normalized_profile(profile: str | None) -> str:
    return str(profile or "").strip().casefold()


def _validate_exact_provider_read_contract(
    *,
    capabilities: CapabilityRegistryService,
    providers: ExecutionProviderRegistryService,
) -> None:
    """Prove the known read-only catalog before any lifecycle mutation occurs."""

    for provider_id, expected_capabilities in _EXPECTED_PROVIDER_CAPABILITIES.items():
        provider = providers.get(provider_id)

        if provider.provider_type is not ProviderType.EXTERNAL_CONNECTOR:
            raise ProviderReadActivationError(
                f"provider {provider_id!r} is not an external connector"
            )
        if provider.lifecycle_status is not ProviderLifecycle.PLANNED:
            raise ProviderReadActivationError(
                f"provider {provider_id!r} is not in the planned pre-activation state"
            )
        if provider.health_status is not ProviderHealth.UNKNOWN:
            raise ProviderReadActivationError(
                f"provider {provider_id!r} health changed before activation"
            )
        if provider.approval_status is not ProviderApproval.PILOT:
            raise ProviderReadActivationError(
                f"provider {provider_id!r} approval changed before activation"
            )
        if provider.execution_modes != frozenset({"deterministic"}):
            raise ProviderReadActivationError(
                f"provider {provider_id!r} exposes a non-deterministic execution mode"
            )
        if provider.capabilities != expected_capabilities:
            raise ProviderReadActivationError(
                f"provider {provider_id!r} capability set drifted from the approved profile"
            )
        if provider.pricing_profile_id != "zero-cost-foundation":
            raise ProviderReadActivationError(
                f"provider {provider_id!r} no longer has the zero-cost profile"
            )

        for capability_name in sorted(expected_capabilities):
            capability = capabilities.get(
                capability_name=capability_name,
                version="1.0",
            )
            metadata = capability.metadata

            if capability.lifecycle_status is not CapabilityLifecycle.PILOT:
                raise ProviderReadActivationError(
                    f"capability {capability_name!r} is not in the pilot pre-activation state"
                )
            if metadata.get("provider_neutral", "").strip().casefold() != "true":
                raise ProviderReadActivationError(
                    f"capability {capability_name!r} is not provider-neutral"
                )
            if metadata.get("read_only", "").strip().casefold() != "true":
                raise ProviderReadActivationError(
                    f"capability {capability_name!r} is not explicitly read-only"
                )
            if capability.permitted_execution_modes != frozenset({"deterministic"}):
                raise ProviderReadActivationError(
                    f"capability {capability_name!r} is not deterministic-only"
                )
            if capability.approval.required:
                raise ProviderReadActivationError(
                    f"capability {capability_name!r} unexpectedly requires per-call approval"
                )


def apply_provider_read_activation_profile(
    *,
    capabilities: CapabilityRegistryService,
    providers: ExecutionProviderRegistryService,
    profile: str | None,
) -> ProviderReadActivationState:
    """Activate the exact approved provider-read profile or remain fail-closed.

    Empty/unset means no activation. The only accepted non-empty profile is a
    source-controlled, exact capability set. Unknown profiles fail startup rather
    than partially activating provider access.
    """

    normalized = _normalized_profile(profile)
    if not normalized:
        return ProviderReadActivationState(
            profile="",
            enabled=False,
            provider_ids=(),
            capability_names=(),
        )

    if normalized != PROVIDER_READ_PRODUCTION_PROFILE:
        raise ProviderReadActivationError(
            "unsupported provider-read activation profile"
        )

    _validate_exact_provider_read_contract(
        capabilities=capabilities,
        providers=providers,
    )

    activated_capabilities = tuple(
        sorted(IT_GLUE_CAPABILITIES | AUTOTASK_CAPABILITIES)
    )
    activated_providers = tuple(sorted(_EXPECTED_PROVIDER_CAPABILITIES))

    # Registry state is in-memory and rebuilt on process start. All validation
    # occurs before these mutations, and provider availability is changed last.
    for capability_name in activated_capabilities:
        capabilities.set_lifecycle(
            capability_name=capability_name,
            version="1.0",
            lifecycle_status=CapabilityLifecycle.ACTIVE,
        )

    for provider_id in activated_providers:
        providers.set_approval(
            provider_id=provider_id,
            approval_status=ProviderApproval.APPROVED,
        )
        providers.set_health(
            provider_id=provider_id,
            health_status=ProviderHealth.HEALTHY,
        )
        providers.set_lifecycle(
            provider_id=provider_id,
            lifecycle_status=ProviderLifecycle.AVAILABLE,
        )

    return ProviderReadActivationState(
        profile=PROVIDER_READ_PRODUCTION_PROFILE,
        enabled=True,
        provider_ids=activated_providers,
        capability_names=activated_capabilities,
    )


def apply_provider_read_activation_from_env(
    *,
    capabilities: CapabilityRegistryService,
    providers: ExecutionProviderRegistryService,
) -> ProviderReadActivationState:
    return apply_provider_read_activation_profile(
        capabilities=capabilities,
        providers=providers,
        profile=os.getenv(PROVIDER_READ_ACTIVATION_ENV, ""),
    )
