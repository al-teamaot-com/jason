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

# Immutable legacy profiles retained for rollback and compatibility.
PROVIDER_READ_PRODUCTION_PROFILE = "itglue-autotask-initial-read-v1"
PROVIDER_READ_DOCUMENT_PROFILE = "itglue-autotask-document-read-v2"

# Provider-class activation. This profile does not carry a per-capability allowlist.
# It activates the complete source-registered read catalog for the approved provider
# class, but only after every capability passes the generic read-safety contract.
# Information-release authorization remains independent and may still deny a result.
PROVIDER_READ_DYNAMIC_PROFILE = "governed-provider-read-v3"

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

# These are the installed provider catalogs, not a conversational/request allowlist.
# Adding a new governed read capability to an approved provider catalog therefore does
# not require adding the capability to a second production activation list.
_EXPECTED_PROVIDER_CATALOGS = {
    IT_GLUE_PROVIDER: IT_GLUE_CAPABILITIES,
    AUTOTASK_PROVIDER: AUTOTASK_CAPABILITIES,
}

# Legacy v1/v2 contracts remain unchanged so rollback preserves the previously proven
# authority boundary byte-for-byte.
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

_LEGACY_ACTIVATION_PROFILES = {
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
    """Raised when provider-read activation cannot prove its safety contract."""


@dataclass(frozen=True, slots=True)
class ProviderReadActivationState:
    profile: str
    enabled: bool
    provider_ids: tuple[str, ...]
    capability_names: tuple[str, ...]


def _normalized_profile(profile: str | None) -> str:
    return str(profile or "").strip().casefold()


def _dynamic_provider_contract() -> tuple[
    frozenset[str],
    dict[str, frozenset[str]],
]:
    """Derive the v3 activation contract from registered provider catalogs.

    Provider identities remain explicit because provider installation/trust is a
    governance boundary. Individual read capabilities are not re-enumerated here.
    The provider catalog is the source of truth for what that approved provider can
    expose through the generic governed read path.
    """

    provider_capabilities = {
        provider_id: frozenset(catalog)
        for provider_id, catalog in _EXPECTED_PROVIDER_CATALOGS.items()
    }
    approved_capabilities = frozenset().union(*provider_capabilities.values())
    return approved_capabilities, provider_capabilities


def _validate_provider_read_contract(
    *,
    capabilities: CapabilityRegistryService,
    providers: ExecutionProviderRegistryService,
    approved_capabilities: frozenset[str],
    provider_capabilities: dict[str, frozenset[str]],
    require_complete_catalog: bool,
) -> None:
    """Prove the selected provider-read contract before any lifecycle mutation."""

    if set(_EXPECTED_PROVIDER_CATALOGS) != set(provider_capabilities):
        raise ProviderReadActivationError("provider activation catalog identity drifted")

    approved_union = frozenset().union(*provider_capabilities.values())
    if approved_union != approved_capabilities:
        raise ProviderReadActivationError("provider capability contract drifted")

    for provider_id, expected_catalog in _EXPECTED_PROVIDER_CATALOGS.items():
        provider = providers.get(provider_id)
        selected_capabilities = provider_capabilities[provider_id]

        if not selected_capabilities:
            raise ProviderReadActivationError(
                f"provider {provider_id!r} has no selected read capability"
            )
        if not selected_capabilities.issubset(expected_catalog):
            raise ProviderReadActivationError(
                f"provider {provider_id!r} selected capabilities exceed its catalog"
            )
        if require_complete_catalog and selected_capabilities != expected_catalog:
            raise ProviderReadActivationError(
                f"provider {provider_id!r} dynamic activation omitted catalog capabilities"
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

        # Validate the entire installed catalog before making the provider available.
        # This is what allows v3 to avoid a second per-capability production allowlist
        # without turning provider registration into an authority bypass.
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
            if capability.risk_level.value.strip().casefold() != "low":
                raise ProviderReadActivationError(
                    f"capability {capability_name!r} is not low-risk"
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
    """Activate an approved provider-read class or remain fail-closed.

    Empty/unset means no activation. The legacy v1/v2 profiles preserve their exact
    historical subsets for rollback. The v3 profile activates the complete governed
    read catalog of each installed approved provider after generic contract validation;
    it does not require a per-resource/per-question production allowlist.

    Unknown profiles fail startup rather than partially activating provider access.
    Information-release authorization is a separate downstream decision and remains
    fail-closed for any provider/resource class without a positive requester basis.
    """

    normalized = _normalized_profile(profile)
    if not normalized:
        return ProviderReadActivationState(
            profile="",
            enabled=False,
            provider_ids=(),
            capability_names=(),
        )

    require_complete_catalog = normalized == PROVIDER_READ_DYNAMIC_PROFILE

    if require_complete_catalog:
        approved_capabilities, provider_capabilities = _dynamic_provider_contract()
    else:
        profile_contract = _LEGACY_ACTIVATION_PROFILES.get(normalized)
        if profile_contract is None:
            raise ProviderReadActivationError(
                "unsupported provider-read activation profile"
            )
        approved_capabilities, provider_capabilities = profile_contract

    _validate_provider_read_contract(
        capabilities=capabilities,
        providers=providers,
        approved_capabilities=approved_capabilities,
        provider_capabilities=provider_capabilities,
        require_complete_catalog=require_complete_catalog,
    )

    activated_capabilities = tuple(sorted(approved_capabilities))
    activated_providers = tuple(sorted(provider_capabilities))

    # Registry state is in-memory and rebuilt on process start. All validation occurs
    # before these mutations, and provider availability is changed last.
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
