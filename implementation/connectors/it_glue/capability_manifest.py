from __future__ import annotations

from orchestrator.integration_broker import (
    IntegrationManifest,
    IntegrationOperation,
    OperationKind,
    ResourceDefinition,
    ResourceObservation,
    SelectorDefinition,
)
from orchestrator.provider_read_capability_catalog import (
    DOCUMENTATION_CONFIGURATION_READ,
    DOCUMENTATION_CONFIGURATION_SEARCH,
    DOCUMENTATION_CONTACT_READ,
    DOCUMENTATION_CONTACT_SEARCH,
    DOCUMENTATION_DOCUMENT_READ,
    DOCUMENTATION_DOCUMENT_SEARCH,
    DOCUMENTATION_LOCATION_READ,
    DOCUMENTATION_LOCATION_SEARCH,
    DOCUMENTATION_ORGANIZATION_READ,
    DOCUMENTATION_ORGANIZATION_SEARCH,
    IT_GLUE_PROVIDER,
)


def _search_operation(
    operation_id: str,
    capability: str,
    selectors: tuple[str, ...],
) -> IntegrationOperation:
    return IntegrationOperation(
        operation_id=operation_id,
        kind=OperationKind.SEARCH,
        capability_name=capability,
        description="Search the bounded authorized IT Glue resource collection.",
        read_only=True,
        selector_names=selectors,
        collection_supported=True,
    )


def _read_operation(operation_id: str, capability: str) -> IntegrationOperation:
    return IntegrationOperation(
        operation_id=operation_id,
        kind=OperationKind.READ,
        capability_name=capability,
        description="Read one IT Glue resource by verified durable identifier.",
        read_only=True,
        selector_names=("resource_id",),
        collection_supported=False,
    )


def _selectors() -> tuple[SelectorDefinition, ...]:
    return (
        SelectorDefinition(
            name="name",
            description="Human-readable discovery selector; never durable identity.",
        ),
        SelectorDefinition(
            name="organization_id",
            description="Authorized IT Glue organization scope selector.",
        ),
        SelectorDefinition(
            name="filters",
            description="Bounded schema-driven IT Glue equality filters.",
        ),
        SelectorDefinition(
            name="page_number",
            description="Provider page number for a bounded collection read.",
        ),
        SelectorDefinition(
            name="page_size",
            description="Maximum records requested from one IT Glue page; bounded to 1-1000.",
        ),
        SelectorDefinition(
            name="resource_id",
            description="Durable provider resource identifier.",
            verified_identity_required=True,
        ),
    )


def build_it_glue_manifest() -> IntegrationManifest:
    selectors = _selectors()
    return IntegrationManifest(
        integration_id="it_glue",
        display_name="IT Glue",
        manifest_version="1.0",
        provider_id=IT_GLUE_PROVIDER,
        resources=(
            ResourceDefinition(
                resource_type="documentation_organization",
                description="Client organization records documented in IT Glue.",
                selectors=selectors,
                operations=(
                    _search_operation(
                        "documentation.organization.search",
                        DOCUMENTATION_ORGANIZATION_SEARCH,
                        ("name", "filters", "page_number", "page_size", "resource_id"),
                    ),
                    _read_operation(
                        "documentation.organization.read",
                        DOCUMENTATION_ORGANIZATION_READ,
                    ),
                ),
                observations=(
                    ResourceObservation("identity", "Organization identity and name."),
                    ResourceObservation("contact_context", "Organization contact/location context."),
                ),
                relationships=("organization -> contact", "organization -> location", "organization -> configuration"),
            ),
            ResourceDefinition(
                resource_type="documentation_contact",
                description="Client contacts documented in IT Glue.",
                selectors=selectors,
                operations=(
                    _search_operation(
                        "documentation.contact.search",
                        DOCUMENTATION_CONTACT_SEARCH,
                        (
                            "organization_id",
                            "name",
                            "filters",
                            "page_number",
                            "page_size",
                            "resource_id",
                        ),
                    ),
                    _read_operation("documentation.contact.read", DOCUMENTATION_CONTACT_READ),
                ),
                observations=(
                    ResourceObservation("identity", "Contact identity and display fields."),
                    ResourceObservation("communication", "Documented email/phone/title fields."),
                ),
                relationships=("contact -> organization",),
            ),
            ResourceDefinition(
                resource_type="documentation_location",
                description="Client locations documented in IT Glue.",
                selectors=selectors,
                operations=(
                    _search_operation(
                        "documentation.location.search",
                        DOCUMENTATION_LOCATION_SEARCH,
                        (
                            "organization_id",
                            "name",
                            "filters",
                            "page_number",
                            "page_size",
                            "resource_id",
                        ),
                    ),
                    _read_operation("documentation.location.read", DOCUMENTATION_LOCATION_READ),
                ),
                observations=(
                    ResourceObservation("identity", "Location identity and name."),
                    ResourceObservation("address", "Documented physical location fields."),
                ),
                relationships=("location -> organization",),
            ),
            ResourceDefinition(
                resource_type="documentation_configuration",
                description="Client configuration records documented in IT Glue.",
                selectors=selectors,
                operations=(
                    _search_operation(
                        "documentation.configuration.search",
                        DOCUMENTATION_CONFIGURATION_SEARCH,
                        (
                            "organization_id",
                            "name",
                            "filters",
                            "page_number",
                            "page_size",
                            "resource_id",
                        ),
                    ),
                    _read_operation(
                        "documentation.configuration.read",
                        DOCUMENTATION_CONFIGURATION_READ,
                    ),
                ),
                observations=(
                    ResourceObservation("identity", "Configuration identity/reference fields."),
                    ResourceObservation("inventory", "Documented asset/configuration attributes."),
                ),
                relationships=("configuration -> organization", "configuration -> related resource"),
            ),
            ResourceDefinition(
                resource_type="documentation_document",
                description="Client documentation records, including policies and SOPs, documented in IT Glue.",
                selectors=selectors,
                operations=(
                    _search_operation(
                        "documentation.document.search",
                        DOCUMENTATION_DOCUMENT_SEARCH,
                        (
                            "organization_id",
                            "filters",
                            "page_number",
                            "page_size",
                        ),
                    ),
                    _read_operation(
                        "documentation.document.read",
                        DOCUMENTATION_DOCUMENT_READ,
                    ),
                ),
                observations=(
                    ResourceObservation("identity", "Document identity, title, and organization context."),
                    ResourceObservation("content", "Sanitized document content and metadata."),
                    ResourceObservation("version", "Provider source version/hash evidence when available."),
                ),
                relationships=("document -> organization",),
            ),
        ),
        metadata={
            "mode": "read_only",
            "credential_surface": "internal_openbao_only",
            "excluded_sensitive_resources": "passwords,credential_vault",
            "pagination": "page_number_and_size",
        },
    )
