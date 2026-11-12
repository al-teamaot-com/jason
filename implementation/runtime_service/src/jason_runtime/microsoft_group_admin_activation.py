"""Opt-in, AOT-only Microsoft 365 group administration capability activation.

Does not grant authority. The existing central ledger, JKD-001 identity and
exact-action approval must independently authorize every write.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
import os

from kernel.capabilities import CapabilityLifecycle, CapabilityRegistryService
from kernel.execution_providers import (
    ExecutionProvider, ExecutionProviderRegistryService, ProviderApproval,
    ProviderFeatures, ProviderHealth, ProviderLifecycle, ProviderLimits,
    ProviderStewardship, ProviderType,
)
from orchestrator.microsoft_group_admin_catalog import (
    AOT_PILOT_CLIENT_ID, AOT_PILOT_TENANT_ID, GROUP_ADMIN_CAPABILITIES,
    GROUP_ADMIN_PROVIDER, microsoft_group_admin_capabilities,
)

PROFILE_ENV = "JASON_M365_GROUP_ADMIN_PROFILE"
PROFILE = "aot-group-admin-exact-pilot-v1"


@dataclass(frozen=True, slots=True)
class GroupAdminActivation:
    enabled: bool
    profile: str = ""


def register_group_admin_foundation(
    *, capabilities: CapabilityRegistryService,
    providers: ExecutionProviderRegistryService,
    now: datetime,
    profile: str | None = None,
) -> GroupAdminActivation:
    normalized = str(profile or "").strip().casefold()
    if normalized not in {"", PROFILE}:
        raise PermissionError("M365_GROUP_ADMIN_UNAPPROVED_ACTIVATION_PROFILE")
    definitions = microsoft_group_admin_capabilities(now=now)
    if {x.capability_name for x in definitions} != set(GROUP_ADMIN_CAPABILITIES):
        raise RuntimeError("M365_GROUP_ADMIN_CATALOG_DRIFT")
    for definition in definitions:
        meta = dict(definition.metadata)
        meta.update({
            "mcp_action_enabled": "true",
            "mcp_tool_name": "execute_governed_capability",
            "conversation_authenticated_imperative_is_approval": "false",
            "pilot_scope": "aot_internal_client_only",
            "tenant_id": AOT_PILOT_TENANT_ID,
            "client_id": AOT_PILOT_CLIENT_ID,
        })
        capabilities.register(replace(definition, metadata=meta))
    providers.register(ExecutionProvider(
        provider_id=GROUP_ADMIN_PROVIDER,
        display_name="AOT Governed Microsoft 365 Group Administration",
        provider_type=ProviderType.EXTERNAL_CONNECTOR,
        lifecycle_status=ProviderLifecycle.PLANNED,
        health_status=ProviderHealth.UNKNOWN,
        approval_status=ProviderApproval.PILOT,
        execution_modes=frozenset({"deterministic"}),
        capabilities=GROUP_ADMIN_CAPABILITIES,
        supported_classifications=frozenset({"internal"}),
        regions=frozenset({"US"}),
        limits=ProviderLimits(
            maximum_concurrent_executions=1,
            maximum_requests_per_minute=10,
            maximum_execution_seconds=60,
        ),
        features=ProviderFeatures(structured_output=True),
        pricing_profile_id="zero-cost-foundation",
        stewardship=ProviderStewardship(
            technology_steward="Microsoft Platform Steward",
            business_justification="Approved AOT security-group pilot with separately consented Graph identities",
            review_interval_days=30,
            last_reviewed_at=now,
            retirement_criteria=("Pilot authorization or AOT tenant binding revoked.",),
            vendor_change_sources=("Microsoft Graph v1.0 Groups",),
            operational_owner="AOT IT Operations",
            approval_owner="AOT Owner",
        ),
        created_at=now,
        metadata={"resource_authority": "aot_only",
                  "activation_state": "default_disabled_pilot_only"},
    ))
    if not normalized:
        return GroupAdminActivation(enabled=False)

    provider = providers.get(GROUP_ADMIN_PROVIDER)
    if (provider.capabilities != GROUP_ADMIN_CAPABILITIES
            or provider.lifecycle_status is not ProviderLifecycle.PLANNED
            or provider.approval_status is not ProviderApproval.PILOT
            or provider.health_status is not ProviderHealth.UNKNOWN):
        raise PermissionError("M365_GROUP_ADMIN_PROVIDER_CONTRACT_DRIFT")
    for name in sorted(GROUP_ADMIN_CAPABILITIES):
        capability = capabilities.get(capability_name=name, version="1.0")
        if (capability.lifecycle_status is not CapabilityLifecycle.BUILDING
                or not capability.approval.required or not capability.evidence.required
                or capability.maximum_attempts != 1
                or capability.metadata.get("write_capability") != "true"
                or capability.metadata.get("mcp_action_enabled") != "true"
                or capability.metadata.get("conversation_authenticated_imperative_is_approval") != "false"
                or capability.metadata.get("client_id") != AOT_PILOT_CLIENT_ID
                or capability.metadata.get("tenant_id") != AOT_PILOT_TENANT_ID):
            raise PermissionError("M365_GROUP_ADMIN_CAPABILITY_CONTRACT_DRIFT")
    for name in sorted(GROUP_ADMIN_CAPABILITIES):
        capabilities.set_lifecycle(
            capability_name=name, version="1.0",
            lifecycle_status=CapabilityLifecycle.ACTIVE,
        )
    providers.set_approval(
        provider_id=GROUP_ADMIN_PROVIDER, approval_status=ProviderApproval.PILOT,
    )
    providers.set_health(
        provider_id=GROUP_ADMIN_PROVIDER, health_status=ProviderHealth.HEALTHY,
    )
    providers.set_lifecycle(
        provider_id=GROUP_ADMIN_PROVIDER, lifecycle_status=ProviderLifecycle.AVAILABLE,
    )
    return GroupAdminActivation(enabled=True, profile=normalized)


def register_group_admin_from_env(
    *, capabilities: CapabilityRegistryService,
    providers: ExecutionProviderRegistryService,
    now: datetime,
) -> GroupAdminActivation:
    return register_group_admin_foundation(
        capabilities=capabilities,
        providers=providers, now=now,
        profile=os.getenv(PROFILE_ENV, ""),
    )
