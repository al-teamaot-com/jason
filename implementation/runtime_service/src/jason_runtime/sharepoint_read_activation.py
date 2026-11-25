"""Explicit opt-in for Jason's governed SharePoint reader, off by default."""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from kernel.capabilities import CapabilityLifecycle, CapabilityRegistryService
from kernel.execution_providers import (
    ExecutionProviderRegistryService, ProviderApproval, ProviderHealth, ProviderLifecycle,
)
from orchestrator.sharepoint_capability_catalog import (
    SHAREPOINT_CAPABILITIES, SHAREPOINT_PROVIDER, register_sharepoint_read_foundation,
)

PROFILE_ENV = "JASON_SHAREPOINT_READER_PROFILE"
APPROVED_PROFILE = "aot-sharepoint-read-v1"


def register_sharepoint_runtime_foundation(
    *, capabilities: CapabilityRegistryService,
    providers: ExecutionProviderRegistryService,
    now: datetime, app_boundary_approved: bool = False,
    app_credential_present: bool = False,
    site_registry_present: bool = False,
) -> bool:
    profile = os.environ.get(PROFILE_ENV, "").strip()
    if not profile:
        return False  # zero registry/provider changes to protected runtime by default
    if profile != APPROVED_PROFILE:
        raise PermissionError("Unsupported SharePoint activation profile")
    # Never advertise a live capability without verified site policy and app identity.
    if not (app_boundary_approved and app_credential_present and site_registry_present):
        raise PermissionError("SharePoint dedicated app identity/site gate unavailable")
    register_sharepoint_read_foundation(
        capabilities=capabilities, providers=providers, now=now)
    for name in sorted(SHAREPOINT_CAPABILITIES):
        capabilities.set_lifecycle(
            capability_name=name, version="1.0",
            lifecycle_status=CapabilityLifecycle.ACTIVE)
    providers.set_approval(provider_id=SHAREPOINT_PROVIDER,
                           approval_status=ProviderApproval.APPROVED)
    providers.set_health(provider_id=SHAREPOINT_PROVIDER,
                         health_status=ProviderHealth.HEALTHY)
    providers.set_lifecycle(provider_id=SHAREPOINT_PROVIDER,
                            lifecycle_status=ProviderLifecycle.AVAILABLE)
    return True
