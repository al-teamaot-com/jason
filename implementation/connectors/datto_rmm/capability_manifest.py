"""Datto RMM Integration Broker manifest.

Provider-specific API knowledge remains in the Datto integration.
Jason consumes only the generic manifest contract.
"""

from __future__ import annotations

from orchestrator.integration_broker import (
    IntegrationManifest,
    IntegrationOperation,
    OperationKind,
    ResourceDefinition,
    ResourceObservation,
    SelectorDefinition,
)


def build_datto_rmm_manifest() -> IntegrationManifest:
    endpoint = ResourceDefinition(
        resource_type="endpoint",
        description=(
            "Managed endpoint observed through the Datto RMM integration."
        ),
        selectors=(
            SelectorDefinition(
                name="resource_id",
                description="Verified durable endpoint identity.",
                verified_identity_required=True,
            ),
            SelectorDefinition(
                name="hostname",
                description="Endpoint hostname used for discovery.",
            ),
        ),
        operations=(
            IntegrationOperation(
                operation_id="endpoint.search",
                kind=OperationKind.SEARCH,
                capability_name="endpoint.device.search",
                description=(
                    "Search managed endpoints using governed discovery "
                    "selectors."
                ),
                read_only=True,
                selector_names=("hostname",),
                collection_supported=True,
            ),
            IntegrationOperation(
                operation_id="endpoint.read",
                kind=OperationKind.READ,
                capability_name="endpoint.device.read",
                description=(
                    "Read the current governed endpoint record, including "
                    "endpoint identity, operating state, operating system, "
                    "network information, and current user/session association "
                    "when reported by the provider."
                ),
                read_only=True,
                selector_names=("resource_id",),
            ),
            IntegrationOperation(
                operation_id="endpoint.alerts.open",
                kind=OperationKind.SEARCH,
                capability_name="endpoint.alert.search",
                description="Read open alerts associated with an endpoint.",
                read_only=True,
                selector_names=("resource_id",),
            ),
            IntegrationOperation(
                operation_id="endpoint.alerts.history",
                kind=OperationKind.SEARCH,
                capability_name="endpoint.alert.history.search",
                description=(
                    "Read resolved or historical alerts associated with an "
                    "endpoint."
                ),
                read_only=True,
                selector_names=("resource_id",),
            ),
            IntegrationOperation(
                operation_id="endpoint.audit.read",
                kind=OperationKind.READ,
                capability_name="endpoint.audit.read",
                description=(
                    "Read detailed governed endpoint audit and inventory "
                    "evidence, including hardware, memory, processors, disks, "
                    "system inventory, and other audited device details."
                ),
                read_only=True,
                selector_names=("resource_id",),
            ),
            IntegrationOperation(
                operation_id="endpoint.software.search",
                kind=OperationKind.SEARCH,
                capability_name="endpoint.software.search",
                description=(
                    "Read the governed installed-software inventory for an "
                    "endpoint."
                ),
                read_only=True,
                selector_names=("resource_id",),
            ),
        ),
        observations=(
            ResourceObservation(
                name="identity",
                description=(
                    "Provider-observed endpoint identifiers, names and "
                    "association data."
                ),
            ),
            ResourceObservation(
                name="operational_state",
                description=(
                    "Current endpoint state exposed by governed Datto "
                    "endpoint records."
                ),
            ),
            ResourceObservation(
                name="hardware",
                description=(
                    "Hardware and system information exposed by endpoint "
                    "audit evidence."
                ),
            ),
            ResourceObservation(
                name="software",
                description=(
                    "Installed software evidence exposed by endpoint audits."
                ),
            ),
            ResourceObservation(
                name="networking",
                description=(
                    "Network information present in governed endpoint "
                    "evidence."
                ),
            ),
            ResourceObservation(
                name="user_association",
                description=(
                    "User or session-related information present in governed "
                    "endpoint evidence."
                ),
            ),
            ResourceObservation(
                name="alerts",
                description=(
                    "Current and historical monitoring alerts associated "
                    "with endpoints."
                ),
            ),
        ),
        relationships=(
            "endpoint -> site",
            "endpoint -> user",
        ),
    )

    site = ResourceDefinition(
        resource_type="site",
        description=(
            "Managed customer/site context observed through Datto RMM."
        ),
        selectors=(
            SelectorDefinition(
                name="name",
                description="Human-readable site name used for discovery.",
            ),
        ),
        operations=(
            IntegrationOperation(
                operation_id="site.search",
                kind=OperationKind.SEARCH,
                capability_name="management.site.search",
                description="Search governed Datto RMM site records.",
                read_only=True,
                selector_names=("name",),
                collection_supported=True,
            ),
        ),
        observations=(
            ResourceObservation(
                name="identity",
                description="Site identity and descriptive information.",
            ),
            ResourceObservation(
                name="endpoint_membership",
                description=(
                    "Relationships between managed sites and endpoints."
                ),
            ),
        ),
        relationships=("site -> endpoint",),
    )

    management = ResourceDefinition(
        resource_type="management",
        description=(
            "Datto RMM account-level operational observations."
        ),
        operations=(
            IntegrationOperation(
                operation_id="management.alerts.open",
                kind=OperationKind.SEARCH,
                capability_name="management.alert.search",
                description=(
                    "Read governed account-level open alert evidence."
                ),
                read_only=True,
                collection_supported=True,
            ),
        ),
        observations=(
            ResourceObservation(
                name="alerts",
                description="Account-level operational alert evidence.",
            ),
        ),
    )

    return IntegrationManifest(
        integration_id="datto_rmm",
        display_name="Datto RMM",
        manifest_version="1.0",
        provider_id="datto_rmm",
        resources=(endpoint, site, management),
        metadata={
            "manifest_source": "integration",
            "authority": "descriptive_only",
            "documentation_url": (
                "https://rmm.datto.com/help/en/Content/"
                "2SETUP/APIv2.htm"
            ),
            "documentation_type": "html",
        },
    )
