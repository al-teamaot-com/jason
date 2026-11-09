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
    CAPABILITIES, PROVIDER,
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
    for name in sorted(CAPABILITIES):
        item = capabilities.get(capability_name=name, version="1.0")
        if (item.lifecycle_status is not CapabilityLifecycle.PILOT
                or item.metadata.get("read_only") != "true"
                or item.approval.required):
            raise ConstantContactActivationError("Constant Contact read registry contract drift")
    for name in sorted(CAPABILITIES):
        capabilities.set_lifecycle(
            capability_name=name, version="1.0", lifecycle_status=CapabilityLifecycle.ACTIVE,
        )
    providers.set_approval(provider_id=PROVIDER, approval_status=ProviderApproval.APPROVED)
    providers.set_health(provider_id=PROVIDER, health_status=ProviderHealth.HEALTHY)
    providers.set_lifecycle(provider_id=PROVIDER, lifecycle_status=ProviderLifecycle.AVAILABLE)
    return ActivationState(value, True, tuple(sorted(CAPABILITIES)))


def apply_read_from_env(*, capabilities: CapabilityRegistryService,
                        providers: ExecutionProviderRegistryService) -> ActivationState:
    return apply_read_profile(capabilities=capabilities, providers=providers,
                              profile=os.getenv(PROFILE_ENV, ""))
