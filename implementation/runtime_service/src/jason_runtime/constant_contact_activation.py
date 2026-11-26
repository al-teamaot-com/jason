"""Fail-closed activation profile for Constant Contact read capabilities.

Default is disabled and does not contact Constant Contact or imply that the
OAuth account is verified. A separately approved deployment must set the
exact read-only profile, provision credentials, and complete live acceptance.
"""
from __future__ import annotations
import os
from dataclasses import dataclass
from kernel.capabilities import CapabilityLifecycle, CapabilityRegistryService
from kernel.execution_providers import (
    ExecutionProviderRegistryService, ProviderApproval, ProviderHealth,
    ProviderLifecycle, ProviderType,
)
from orchestrator.constant_contact_capability_catalog import (
    CAPABILITIES, READ_CAPABILITIES, PROVIDER, MARKETING_CONTACT_IMPORT,
)

PROFILE_ENV = "JASON_CONSTANT_CONTACT_READ_PROFILE"
READ_PROFILE = "constant-contact-aot-read-v1"


class ConstantContactActivationError(RuntimeError):
    """Activation failed closed."""


@dataclass(frozen=True)
class ActivationState:
    profile: str
    enabled: bool
    capability_names: tuple[str, ...]


def apply_read_profile(*, capabilities: CapabilityRegistryService,
                       providers: ExecutionProviderRegistryService,
                       profile: str | None) -> ActivationState:
    value = str(profile or "").strip().casefold()
    if not value:
        return ActivationState(profile="", enabled=False, capability_names=())
    if value != READ_PROFILE:
        raise ConstantContactActivationError("Unsupported Constant Contact read activation profile")
    provider = providers.get(PROVIDER)
    if (provider.provider_type is not ProviderType.EXTERNAL_CONNECTOR
            or provider.lifecycle_status is not ProviderLifecycle.PLANNED
            or provider.health_status is not ProviderHealth.UNKNOWN
            or provider.approval_status is not ProviderApproval.PILOT
            or provider.capabilities != CAPABILITIES):
        raise ConstantContactActivationError("Constant Contact provider registry drift")
    for name in sorted(READ_CAPABILITIES):
        item = capabilities.get(capability_name=name, version="1.0")
        if (item.lifecycle_status is not CapabilityLifecycle.PILOT
                or item.metadata.get("read_only") != "true"
                or item.approval.required):
            raise ConstantContactActivationError("Constant Contact read registry contract drift")
    for name in sorted(READ_CAPABILITIES):
        capabilities.set_lifecycle(
            capability_name=name, version="1.0", lifecycle_status=CapabilityLifecycle.ACTIVE,
        )
    providers.set_approval(provider_id=PROVIDER, approval_status=ProviderApproval.APPROVED)
    providers.set_health(provider_id=PROVIDER, health_status=ProviderHealth.HEALTHY)
    providers.set_lifecycle(provider_id=PROVIDER, lifecycle_status=ProviderLifecycle.AVAILABLE)
    return ActivationState(value, True, tuple(sorted(READ_CAPABILITIES)))


def apply_read_from_env(*, capabilities: CapabilityRegistryService,
                        providers: ExecutionProviderRegistryService) -> ActivationState:
    return apply_read_profile(capabilities=capabilities, providers=providers,
                              profile=os.getenv(PROFILE_ENV, ""))


# Requires the separately reviewed exact pilot import activation, protected
# OpenBao account binding, encrypted work ledger and verified approval issuer.
# Merely enabling read access NEVER enables writes.
IMPORT_PROFILE_ENV = "JASON_CONSTANT_CONTACT_IMPORT_PROFILE"
IMPORT_PROFILE = "constant-contact-aot-import-pilot-v1"


def apply_import_profile(*, capabilities: CapabilityRegistryService,
                         providers: ExecutionProviderRegistryService,
                         read_enabled: bool, profile: str | None) -> ActivationState:
    value = str(profile or "").strip().casefold()
    if not value:
        return ActivationState(profile="", enabled=False, capability_names=())
    if value != IMPORT_PROFILE or not read_enabled:
        raise ConstantContactActivationError("Constant Contact import activation is not approved")
    provider = providers.get(PROVIDER)
    item = capabilities.get(capability_name=MARKETING_CONTACT_IMPORT, version="1.0")
    if (provider.capabilities != CAPABILITIES
            or provider.lifecycle_status is not ProviderLifecycle.AVAILABLE
            or provider.approval_status is not ProviderApproval.APPROVED
            or item.lifecycle_status is not CapabilityLifecycle.BUILDING
            or not item.approval.required or item.metadata.get("read_only") != "false"):
        raise ConstantContactActivationError("Constant Contact import provider drift")
    capabilities.set_lifecycle(
        capability_name=MARKETING_CONTACT_IMPORT,
        version="1.0", lifecycle_status=CapabilityLifecycle.PILOT,
    )
    return ActivationState(value, True, (MARKETING_CONTACT_IMPORT,))


def apply_import_from_env(*, capabilities: CapabilityRegistryService,
                          providers: ExecutionProviderRegistryService,
                          read_enabled: bool) -> ActivationState:
    return apply_import_profile(
        capabilities=capabilities, providers=providers,
        read_enabled=read_enabled, profile=os.getenv(IMPORT_PROFILE_ENV, ""),
    )
