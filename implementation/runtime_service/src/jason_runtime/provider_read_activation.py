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
    DOCUMENTATION_DOCUMENT_READ,
    DOCUMENTATION_DOCUMENT_SEARCH,
    DOCUMENTATION_ORGANIZATION_SEARCH,
    IT_GLUE_CAPABILITIES,
    IT_GLUE_PROVIDER,
    SERVICE_COMPANY_READ,
    SERVICE_TICKET_SEARCH,
)


PROVIDER_READ_ACTIVATION_ENV = "JASON_PROVIDER_READ_ACTIVATION_PROFILE"

# Immutable activation profile retained for rollback and compatibility.
PROVIDER_READ_PRODUCTION_PROFILE = "itglue-autotask-initial-read-v1"

# Expanded profile adds only the IT Glue document reads that completed
# bounded provider-backed acceptance on 2026-09-11.
PROVIDER_READ_DOCUMENT_PROFILE = "itglue-autotask-document-read-v2"

PROVIDER_READ_PRODUCTION_CAPABILITIES = frozenset(
    {
        DOCUMENTATION_ORGANIZATION_SEARCH,
        SERVICE_COMPANY_READ,
        SERVICE_TICKET_SEARCH,
    }
)

PROVIDER_READ_DOCUMENT_CAPABILITIES = frozenset(
    {
        *PROVIDER_READ_PRODUCTION_CAPABILITIES,
        DOCUMENTATION_DOCUMENT_SEARCH,
        DOCUMENTATION_DOCUMENT_READ,
    }
)

_EXPECTED_PROVIDER_CATALOGS = {
    IT_GLUE_PROVIDER: IT_GLUE_CAPABILITIES,
    AUTOTASK_PROVIDER: AUTOTASK_CAPABILITIES,
}

# v1 remains byte-for-byte equivalent in authority: one IT Glue organization
# read and two Autotask reads.
_PRODUCTION_PROVIDER_CAPABILITIES = {
    IT_GLUE_PROVIDER: frozenset({DOCUMENTATION_ORGANIZATION_SEARCH}),
    AUTOTASK_PROVIDER: frozenset({SERVICE_COMPANY_READ, SERVICE_TICKET_SEARCH}),
}

_DOCUMENT_PROVIDER_CAPABILITIES = {
    IT_GLUE_PROVIDER: frozenset(
        {
            DOCUMENTATION_ORGANIZATION_SEARCH,
            DOCUMENTATION_DOCUMENT_SEARCH,
            DOCUMENTATION_DOCUMENT_READ,
        }
    ),
    AUTOTASK_PROVIDER: frozenset({SERVICE_COMPANY_READ, SERVICE_TICKET_SEARCH}),
}

_ACTIVATION_PROFILES = {
    PROVIDER_READ_PRODUCTION_PROFILE: (
        PROVIDER_READ_PRODUCTION_CAPABILITIES,
        _PRODUCTION_PROVIDER_CAPABILITIES,
    ),
    PROVIDER_READ_DOCUMENT_PROFILE: (
        PROVIDER_READ_DOCUMENT_CAPABILITIES,
        _DOCUMENT_PROVIDER_CAPABILITIES,
    ),
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
    approved_capabilities: frozenset[str],
    provider_capabilities: dict[str, frozenset[str]],
) -> None:
    """Prove the catalog and selected profile before any lifecycle mutation."""

    if set(_EXPECTED_PROVIDER_CATALOGS) != set(provider_capabilities):
        raise ProviderReadActivationError("provider activation catalog identity drifted")

    approved_union = frozenset().union(*provider_capabilities.values())
    if approved_union != approved_capabilities:
        raise ProviderReadActivationError("production capability allowlist drifted")

    for provider_id, expected_catalog in _EXPECTED_PROVIDER_CATALOGS.items():
        provider = providers.get(provider_id)
        provider_approved_capabilities = provider_capabilities[provider_id]

        if not provider_approved_capabilities:
            raise ProviderReadActivationError(
                f"provider {provider_id!r} has no approved production capability"
            )
        if not provider_approved_capabilities.issubset(expected_catalog):
            raise ProviderReadActivationError(
                f"provider {provider_id!r} production allowlist exceeds its catalog"
            )
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
        if provider.capabilities != expected_catalog:
            raise ProviderReadActivationError(
                f"provider {provider_id!r} capability catalog drifted from source"
            )
        if provider.pricing_profile_id != "zero-cost-foundation":
            raise ProviderReadActivationError(
                f"provider {provider_id!r} no longer has the zero-cost profile"
            )

        # Validate the entire implemented catalog remains fail-closed before
        # selectively promoting the approved initial production subset.
        for capability_name in sorted(expected_catalog):
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
    """Activate only the exact approved provider-read subset or remain fail-closed.

    Empty/unset means no activation. Accepted non-empty profiles are
    source-controlled immutable capability allowlists. Unknown profiles fail
    startup rather than partially activating provider access.
    """

    normalized = _normalized_profile(profile)
    if not normalized:
        return ProviderReadActivationState(
            profile="",
            enabled=False,
            provider_ids=(),
            capability_names=(),
        )

    profile_contract = _ACTIVATION_PROFILES.get(normalized)
    if profile_contract is None:
        raise ProviderReadActivationError(
            "unsupported provider-read activation profile"
        )

    approved_capabilities, provider_capabilities = profile_contract

    _validate_exact_provider_read_contract(
        capabilities=capabilities,
        providers=providers,
        approved_capabilities=approved_capabilities,
        provider_capabilities=provider_capabilities,
    )

    activated_capabilities = tuple(sorted(approved_capabilities))
    activated_providers = tuple(sorted(provider_capabilities))

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
        profile=normalized,
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
