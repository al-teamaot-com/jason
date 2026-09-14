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
    MICROSOFT_GRAPH_CAPABILITIES,
    MICROSOFT_GRAPH_PROVIDER,
    SERVICE_COMPANY_READ,
    SERVICE_TICKET_SEARCH,
)


PROVIDER_READ_ACTIVATION_ENV = "JASON_PROVIDER_READ_ACTIVATION_PROFILE"

# Immutable activation profiles retained for rollback and compatibility.
PROVIDER_READ_PRODUCTION_PROFILE = "itglue-autotask-initial-read-v1"
PROVIDER_READ_DOCUMENT_PROFILE = "itglue-autotask-document-read-v2"
PROVIDER_READ_GOVERNED_CATALOG_PROFILE = "itglue-autotask-governed-catalog-v3"

# v4 is deliberately a new explicit trust decision. It preserves every v3 provider and
# adds only the narrow Microsoft Graph directory-read catalog. Existing v3 deployments
# therefore do not gain Microsoft access merely because the source contains the provider.
PROVIDER_READ_ENTRA_GOVERNED_CATALOG_PROFILE = (
    "itglue-autotask-entra-governed-catalog-v4"
)

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

_V3_EXPECTED_PROVIDER_CATALOGS = {
    IT_GLUE_PROVIDER: IT_GLUE_CAPABILITIES,
    AUTOTASK_PROVIDER: AUTOTASK_CAPABILITIES,
}

_V4_EXPECTED_PROVIDER_CATALOGS = {
    **_V3_EXPECTED_PROVIDER_CATALOGS,
    MICROSOFT_GRAPH_PROVIDER: MICROSOFT_GRAPH_CAPABILITIES,
}

# Kept for compatibility with existing tests/importers that inspect the current v3
# governed catalog directly.
_EXPECTED_PROVIDER_CATALOGS = _V3_EXPECTED_PROVIDER_CATALOGS
_GOVERNED_CATALOG_PROVIDER_IDS = frozenset(_V3_EXPECTED_PROVIDER_CATALOGS)
PROVIDER_READ_GOVERNED_CATALOG_CAPABILITIES = frozenset().union(
    *(
        _V3_EXPECTED_PROVIDER_CATALOGS[provider_id]
        for provider_id in sorted(_GOVERNED_CATALOG_PROVIDER_IDS)
    )
)

PROVIDER_READ_ENTRA_GOVERNED_CATALOG_CAPABILITIES = frozenset().union(
    *(
        _V4_EXPECTED_PROVIDER_CATALOGS[provider_id]
        for provider_id in sorted(_V4_EXPECTED_PROVIDER_CATALOGS)
    )
)

# v1 remains byte-for-byte equivalent in authority: one IT Glue organization read and
# two Autotask reads.
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
        _V3_EXPECTED_PROVIDER_CATALOGS,
    ),
    PROVIDER_READ_DOCUMENT_PROFILE: (
        PROVIDER_READ_DOCUMENT_CAPABILITIES,
        _DOCUMENT_PROVIDER_CAPABILITIES,
        _V3_EXPECTED_PROVIDER_CATALOGS,
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


def _governed_catalog_contract(
    expected_provider_catalogs: dict[str, frozenset[str]],
) -> tuple[frozenset[str], dict[str, frozenset[str]]]:
    """Derive the read surface from an explicitly trusted provider catalog set."""

    provider_capabilities = {
        provider_id: frozenset(expected_provider_catalogs[provider_id])
        for provider_id in sorted(expected_provider_catalogs)
    }
    approved_capabilities = frozenset().union(*provider_capabilities.values())
    return approved_capabilities, provider_capabilities


def _validate_exact_provider_read_contract(
    *,
    capabilities: CapabilityRegistryService,
    providers: ExecutionProviderRegistryService,
    approved_capabilities: frozenset[str],
    provider_capabilities: dict[str, frozenset[str]],
    expected_provider_catalogs: dict[str, frozenset[str]] | None = None,
) -> None:
    """Prove the selected catalog and profile before any lifecycle mutation."""

    expected_catalogs = expected_provider_catalogs or _V3_EXPECTED_PROVIDER_CATALOGS

    if set(expected_catalogs) != set(provider_capabilities):
        raise ProviderReadActivationError("provider activation catalog identity drifted")

    approved_union = frozenset().union(*provider_capabilities.values())
    if approved_union != approved_capabilities:
        raise ProviderReadActivationError("production capability allowlist drifted")

    for provider_id, expected_catalog in expected_catalogs.items():
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
    """Activate a proven governed provider-read surface or remain fail-closed."""

    normalized = _normalized_profile(profile)
    if not normalized:
        return ProviderReadActivationState(
            profile="",
            enabled=False,
            provider_ids=(),
            capability_names=(),
        )

    if normalized == PROVIDER_READ_GOVERNED_CATALOG_PROFILE:
        expected_catalogs = _V3_EXPECTED_PROVIDER_CATALOGS
        approved_capabilities, provider_capabilities = _governed_catalog_contract(
            expected_catalogs
        )
    elif normalized == PROVIDER_READ_ENTRA_GOVERNED_CATALOG_PROFILE:
        expected_catalogs = _V4_EXPECTED_PROVIDER_CATALOGS
        approved_capabilities, provider_capabilities = _governed_catalog_contract(
            expected_catalogs
        )
    else:
        profile_contract = _ACTIVATION_PROFILES.get(normalized)
        if profile_contract is None:
            raise ProviderReadActivationError(
                "unsupported provider-read activation profile"
            )
        approved_capabilities, provider_capabilities, expected_catalogs = profile_contract

    _validate_exact_provider_read_contract(
        capabilities=capabilities,
        providers=providers,
        approved_capabilities=approved_capabilities,
        provider_capabilities=provider_capabilities,
        expected_provider_catalogs=expected_catalogs,
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
