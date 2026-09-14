"""Generic governed capabilities for metadata-discovered provider resources.

These capabilities describe *how* Jason may read an already-discovered provider
resource.  They deliberately do not enumerate provider products, entity names, fields,
URLs, or business-question mappings.  Provider adapters remain responsible for proving
that an opaque resource handle and selected fields exist in authoritative provider
metadata before any request is made.
"""

from __future__ import annotations

from datetime import datetime

from kernel.capabilities import (
    CapabilityApproval,
    CapabilityDefinition,
    CapabilityEvidence,
    CapabilityLifecycle,
    CapabilityRegistryService,
    CapabilityRisk,
    CapabilityStewardship,
    IdempotencyBehavior,
)


PROVIDER_RESOURCE_SEARCH = "provider.resource.search"
PROVIDER_RESOURCE_READ = "provider.resource.read"
PROVIDER_RESOURCE_CAPABILITIES = frozenset(
    {PROVIDER_RESOURCE_SEARCH, PROVIDER_RESOURCE_READ}
)


def _definition(
    *,
    now: datetime,
    capability_name: str,
    operation: str,
) -> CapabilityDefinition:
    return CapabilityDefinition(
        capability_name=capability_name,
        version="1.0",
        display_name=(
            "Search Discovered Provider Resource"
            if operation == "search"
            else "Read Discovered Provider Resource"
        ),
        lifecycle_status=CapabilityLifecycle.PILOT,
        business_purpose=(
            "Read an authorized operational resource whose structure was learned from "
            "provider-published metadata, without creating entity-specific Jason code."
        ),
        owner_service="Jason Resource Intelligence",
        architectural_capability_ids=frozenset({"JAC-005", "JAC-013"}),
        risk_level=CapabilityRisk.LOW,
        data_classifications=frozenset({"internal"}),
        permitted_execution_modes=frozenset({"deterministic"}),
        input_schema_reference=f"schema://jason/{capability_name.replace('.', '-')}/1.0",
        output_schema_reference=(
            f"schema://jason/{capability_name.replace('.', '-')}-result/1.0"
        ),
        invoking_roles=frozenset({"orchestrator"}),
        approval=CapabilityApproval(required=False),
        evidence=CapabilityEvidence(
            required=True,
            requirements=(
                "authoritative provider metadata binding",
                "provider read result",
                "source provider identity",
            ),
            verification_requirements=(
                "opaque provider resource handle was derived from trusted provider metadata",
                "requested fields exist in the current governed provider schema",
                "selected execution provider matches the provider that published the resource",
                "provider adapter permits observe-only execution",
            ),
        ),
        dependencies=frozenset(),
        idempotency_behavior=IdempotencyBehavior.IDEMPOTENT,
        idempotency_key_required=False,
        timeout_seconds=60,
        maximum_attempts=1,
        failure_behavior=(
            "Fail closed on unknown resource, unknown field, provider mismatch, authority "
            "failure, or unavailable provider metadata. Never fall back to arbitrary URLs."
        ),
        tenant_isolation_required=True,
        client_isolation_required=False,
        stewardship=CapabilityStewardship(
            steward="technology-steward",
            business_justification=(
                "Allow Jason to learn provider resource structure at runtime and compose "
                "bounded reads instead of accumulating provider/entity-specific workflows."
            ),
            review_interval_days=90,
            retirement_criteria=(
                "Replaced by a safer provider-neutral metadata-discovery execution contract.",
            ),
            authoritative_change_sources=(
                "provider-published schemas and governed connector manifests",
            ),
        ),
        created_at=now,
        metadata={
            "provider_neutral": "true",
            "read_only": "true",
            "resource_types": "provider_resource",
            "operation": operation,
            "selector_keys": (
                "provider_resource_handle,field_paths,filters,order_by,top"
                if operation == "search"
                else "provider_resource_handle,resource_id,field_paths"
            ),
            "selector_required": "false" if operation == "search" else "true",
            "resource_role": "structural",
            "dynamic_schema_required": "true",
            "model_may_supply_provider_resource_handle": "false",
            "planning_guidance": (
                "Use only after a trusted provider resource catalog has produced an opaque "
                "Jason resource handle. Provider-specific handles and request paths are "
                "trusted orchestration state and are never accepted from model output."
            ),
        },
    )


def register_provider_resource_capabilities(
    *,
    capabilities: CapabilityRegistryService,
    now: datetime,
) -> None:
    """Register the generic resource read contract as PILOT source-only capability data."""

    capabilities.register(
        _definition(
            now=now,
            capability_name=PROVIDER_RESOURCE_SEARCH,
            operation="search",
        )
    )
    capabilities.register(
        _definition(
            now=now,
            capability_name=PROVIDER_RESOURCE_READ,
            operation="read",
        )
    )
