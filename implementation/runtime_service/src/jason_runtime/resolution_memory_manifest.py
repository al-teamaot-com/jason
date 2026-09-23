from __future__ import annotations

from orchestrator.integration_broker import (
    IntegrationManifest,
    IntegrationOperation,
    OperationKind,
    ResourceDefinition,
    ResourceObservation,
    SelectorDefinition,
)

from .resolution_memory_runtime import (
    RESOLUTION_MEMORY_PROVIDER,
    RESOLUTION_MEMORY_READ,
    RESOLUTION_MEMORY_SEARCH,
)


def build_resolution_memory_manifest() -> IntegrationManifest:
    """Describe Resolution Memory to Jason's generic investigation broker.

    This is a descriptive read-only manifest. It creates no execution authority.
    Search is deliberately unavailable without current client scope at runtime.
    """
    return IntegrationManifest(
        integration_id="resolution_memory",
        display_name="Jason Operational Resolution Memory",
        manifest_version="1.0",
        provider_id=RESOLUTION_MEMORY_PROVIDER,
        resources=(
            ResourceDefinition(
                resource_type="resolution_memory",
                description=(
                    "Client-isolated historical troubleshooting outcomes. Use after "
                    "current incident facts are established to find materially similar "
                    "prior cases, successful diagnostics, and known failed approaches. "
                    "Historical evidence never grants action authority."
                ),
                selectors=(
                    SelectorDefinition(name="category", description="Normalized issue category."),
                    SelectorDefinition(name="product", description="Normalized affected product."),
                    SelectorDefinition(name="device_role", description="Normalized device role."),
                    SelectorDefinition(name="platform", description="Normalized platform."),
                    SelectorDefinition(name="product_version", description="Observed product version when known."),
                    SelectorDefinition(name="symptoms", description="Current normalized symptoms."),
                    SelectorDefinition(name="attributes", description="Bounded current evidence attributes."),
                    SelectorDefinition(name="limit", description="Maximum historical matches to return."),
                    SelectorDefinition(name="case_id", description="Previously returned resolution case identity.", verified_identity_required=True),
                ),
                operations=(
                    IntegrationOperation(
                        operation_id="resolution.search",
                        kind=OperationKind.SEARCH,
                        capability_name=RESOLUTION_MEMORY_SEARCH,
                        description=(
                            "Search same-client verified/observed resolution history using "
                            "the current incident signature. Prefer this only after current "
                            "facts are known. Returned steps are evidence-only and retain "
                            "their approval/disruption classifications."
                        ),
                        read_only=True,
                        selector_names=("category", "product", "device_role", "platform", "product_version", "symptoms", "attributes", "limit"),
                        collection_supported=True,
                    ),
                    IntegrationOperation(
                        operation_id="resolution.read",
                        kind=OperationKind.READ,
                        capability_name=RESOLUTION_MEMORY_READ,
                        description="Read one same-client historical resolution case returned by search.",
                        read_only=True,
                        selector_names=("case_id",),
                    ),
                ),
                observations=(
                    ResourceObservation(name="similar_cases", description="Ranked same-client historical cases with provenance and recency."),
                    ResourceObservation(name="step_evidence", description="Aggregated successful and failed historical troubleshooting-step evidence."),
                ),
            ),
        ),
        metadata={"authority":"evidence_only","client_isolation":"required","grants_authority":"false"},
    )
