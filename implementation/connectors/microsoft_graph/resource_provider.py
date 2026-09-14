"""Kernel execution-provider description for Microsoft metadata-driven reads.

The provider advertises only Jason's generic resource read/search capabilities.  It
contains no Microsoft entity inventory.  The inventory is supplied at runtime by the
provider-published Graph metadata catalog.
"""

from __future__ import annotations

from datetime import datetime

from kernel.execution_providers import (
    ExecutionProvider,
    ProviderApproval,
    ProviderFeatures,
    ProviderHealth,
    ProviderLifecycle,
    ProviderLimits,
    ProviderStewardship,
    ProviderType,
)
from orchestrator.provider_resource_capability_catalog import (
    PROVIDER_RESOURCE_CAPABILITIES,
)


MICROSOFT_GRAPH_RESOURCE_PROVIDER = "microsoft_graph"


def build_microsoft_graph_resource_provider(*, now: datetime) -> ExecutionProvider:
    """Return source-only PILOT provider state pending live acceptance/consent."""

    return ExecutionProvider(
        provider_id=MICROSOFT_GRAPH_RESOURCE_PROVIDER,
        display_name="Microsoft Graph metadata-driven resource provider",
        provider_type=ProviderType.EXTERNAL_CONNECTOR,
        lifecycle_status=ProviderLifecycle.PLANNED,
        health_status=ProviderHealth.UNKNOWN,
        approval_status=ProviderApproval.PILOT,
        execution_modes=frozenset({"deterministic"}),
        capabilities=PROVIDER_RESOURCE_CAPABILITIES,
        supported_classifications=frozenset({"internal"}),
        regions=frozenset(),
        limits=ProviderLimits(
            maximum_concurrent_executions=4,
            maximum_requests_per_minute=120,
            maximum_execution_seconds=60,
        ),
        features=ProviderFeatures(structured_output=True),
        pricing_profile_id="zero-cost-foundation",
        stewardship=ProviderStewardship(
            technology_steward="technology-steward",
            business_justification=(
                "Read Microsoft operational state through provider-published resource "
                "metadata rather than entity-specific Jason request mappings."
            ),
            review_interval_days=90,
            last_reviewed_at=now,
            retirement_criteria=(
                "Microsoft Graph is no longer an approved operational data authority.",
                "A safer provider-neutral Microsoft resource adapter replaces this provider.",
            ),
            vendor_change_sources=(
                "Microsoft Graph OData metadata",
                "Microsoft Graph permissions reference",
            ),
            operational_owner="AOT IT Operations",
            approval_owner="Jason Architecture Authority",
        ),
        created_at=now,
        metadata={
            "connector_id": MICROSOFT_GRAPH_RESOURCE_PROVIDER,
            "resource_authority": "microsoft_cloud",
            "resource_catalog": "provider_metadata",
            "activation_state": "awaiting_provider_backed_acceptance",
            "entity_inventory": "dynamic",
        },
    )
