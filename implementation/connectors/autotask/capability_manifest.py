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
    AUTOTASK_PROVIDER,
    SERVICE_COMPANY_READ,
    SERVICE_COMPANY_SEARCH,
    SERVICE_CONFIGURATION_READ,
    SERVICE_CONFIGURATION_SEARCH,
    SERVICE_CONTACT_READ,
    SERVICE_CONTACT_SEARCH,
    SERVICE_ENTITY_DESCRIBE,
    SERVICE_TICKET_NOTES_SEARCH,
    SERVICE_TICKET_READ,
    SERVICE_TICKET_SEARCH,
)


def _search(operation_id: str, capability: str, selectors: tuple[str, ...]) -> IntegrationOperation:
    return IntegrationOperation(
        operation_id=operation_id,
        kind=OperationKind.SEARCH,
        capability_name=capability,
        description="Search a bounded authorized Autotask resource collection.",
        read_only=True,
        selector_names=selectors,
        collection_supported=True,
    )


def _read(operation_id: str, capability: str) -> IntegrationOperation:
    return IntegrationOperation(
        operation_id=operation_id,
        kind=OperationKind.READ,
        capability_name=capability,
        description="Read one Autotask resource by verified durable identifier.",
        read_only=True,
        selector_names=("resource_id",),
    )


def build_autotask_manifest() -> IntegrationManifest:
    selectors = (
        SelectorDefinition("name", "Human-readable discovery selector; never durable identity."),
        SelectorDefinition("company_id", "Authorized Autotask company scope selector."),
        SelectorDefinition("ticket_number", "Human-visible Autotask ticket number selector."),
        SelectorDefinition("first_name", "Contact first-name discovery selector."),
        SelectorDefinition("last_name", "Contact last-name discovery selector."),
        SelectorDefinition("email", "Contact email discovery selector."),
        SelectorDefinition("status", "Ticket status discovery selector."),
        SelectorDefinition("filters", "Bounded schema-driven equality filters."),
        SelectorDefinition(
            "page_size",
            "Maximum records returned by one Autotask query; bounded to 1-500.",
        ),
        SelectorDefinition(
            "after_resource_id",
            "Safe continuation selector that resumes after a returned durable resource id.",
        ),
        SelectorDefinition(
            "resource_id",
            "Durable provider resource identifier.",
            verified_identity_required=True,
        ),
        SelectorDefinition(
            "ticket_id",
            "Durable Autotask ticket identifier used for related note reads.",
            verified_identity_required=True,
        ),
        SelectorDefinition("entity", "Approved Autotask entity family for schema description."),
    )

    return IntegrationManifest(
        integration_id="autotask",
        display_name="Autotask PSA",
        manifest_version="1.0",
        provider_id=AUTOTASK_PROVIDER,
        resources=(
            ResourceDefinition(
                resource_type="service_company",
                description="Autotask company records in authorized scope.",
                selectors=selectors,
                operations=(
                    _search(
                        "service.company.search",
                        SERVICE_COMPANY_SEARCH,
                        ("name", "filters", "page_size", "after_resource_id", "resource_id"),
                    ),
                    _read("service.company.read", SERVICE_COMPANY_READ),
                ),
                observations=(
                    ResourceObservation("identity", "Company identity/name/status fields."),
                    ResourceObservation("service_context", "Company service-management context."),
                ),
                relationships=("company -> contact", "company -> ticket", "company -> configuration"),
            ),
            ResourceDefinition(
                resource_type="service_contact",
                description="Autotask contact records in authorized scope.",
                selectors=selectors,
                operations=(
                    _search(
                        "service.contact.search",
                        SERVICE_CONTACT_SEARCH,
                        (
                            "company_id",
                            "first_name",
                            "last_name",
                            "email",
                            "filters",
                            "page_size",
                            "after_resource_id",
                            "resource_id",
                        ),
                    ),
                    _read("service.contact.read", SERVICE_CONTACT_READ),
                ),
                observations=(
                    ResourceObservation("identity", "Contact identity and display fields."),
                    ResourceObservation("communication", "Service contact email/phone/title fields."),
                ),
                relationships=("contact -> company",),
            ),
            ResourceDefinition(
                resource_type="service_ticket",
                description="Autotask service tickets and their notes.",
                selectors=selectors,
                operations=(
                    _search(
                        "service.ticket.search",
                        SERVICE_TICKET_SEARCH,
                        (
                            "ticket_number",
                            "company_id",
                            "status",
                            "filters",
                            "page_size",
                            "after_resource_id",
                            "resource_id",
                        ),
                    ),
                    _read("service.ticket.read", SERVICE_TICKET_READ),
                    IntegrationOperation(
                        operation_id="service.ticket.notes.search",
                        kind=OperationKind.SEARCH,
                        capability_name=SERVICE_TICKET_NOTES_SEARCH,
                        description="Read notes associated with one verified Autotask ticket.",
                        read_only=True,
                        selector_names=("ticket_id", "resource_id"),
                        collection_supported=True,
                    ),
                ),
                observations=(
                    ResourceObservation("identity", "Ticket number and durable identity."),
                    ResourceObservation("workflow", "Status, queue, priority, assignee, and due-date fields."),
                    ResourceObservation("notes", "Ticket note evidence."),
                ),
                relationships=("ticket -> company", "ticket -> contact", "ticket -> configuration"),
            ),
            ResourceDefinition(
                resource_type="service_configuration",
                description="Autotask configuration items in authorized scope.",
                selectors=selectors,
                operations=(
                    _search(
                        "service.configuration.search",
                        SERVICE_CONFIGURATION_SEARCH,
                        (
                            "company_id",
                            "name",
                            "filters",
                            "page_size",
                            "after_resource_id",
                            "resource_id",
                        ),
                    ),
                    _read("service.configuration.read", SERVICE_CONFIGURATION_READ),
                ),
                observations=(
                    ResourceObservation("identity", "Configuration item identity/reference fields."),
                    ResourceObservation("inventory", "Product, serial, status, and company association."),
                ),
                relationships=("configuration -> company", "configuration -> contact"),
            ),
            ResourceDefinition(
                resource_type="service_schema",
                description="Autotask approved entity schema metadata.",
                selectors=selectors,
                operations=(
                    IntegrationOperation(
                        operation_id="service.entity.describe",
                        kind=OperationKind.READ,
                        capability_name=SERVICE_ENTITY_DESCRIBE,
                        description="Describe fields for one approved Autotask entity family.",
                        read_only=True,
                        selector_names=("entity",),
                    ),
                ),
                observations=(
                    ResourceObservation("schema", "Provider field and entity metadata."),
                ),
            ),
        ),
        metadata={
            "mode": "read_only",
            "credential_surface": "internal_openbao_only",
            "schema_discovery": "approved_entities_only",
            "pagination": "durable_id_continuation",
        },
    )
