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
    SERVICE_NOTIFICATION_HISTORY_SEARCH,
    SERVICE_PRODUCT_SEARCH,
    SERVICE_PRODUCT_READ,
    SERVICE_PRODUCT_VENDOR_SEARCH,
    SERVICE_SERVICE_SEARCH,
    SERVICE_SERVICE_READ,
    SERVICE_SERVICE_BUNDLE_SEARCH,
    SERVICE_SERVICE_BUNDLE_READ,
    SERVICE_PURCHASE_ORDER_SEARCH,
    SERVICE_PURCHASE_ORDER_READ,
    SERVICE_PURCHASE_ORDER_ITEM_SEARCH,
    SERVICE_TICKET_CHARGE_SEARCH,
    SERVICE_TICKET_CHARGE_READ,
    SERVICE_TICKET_COUNT,
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
        SelectorDefinition("status", "Ticket status discovery selector; human labels are resolved against the live Autotask picklist."),
        SelectorDefinition("template_name", "Exact Autotask notification template name observed in notification history."),
        SelectorDefinition("sku", "Exact product SKU discovery selector."),
        SelectorDefinition("vendor_id", "Durable Autotask vendor company identifier."),
        SelectorDefinition("product_id", "Durable Autotask product identifier."),
        SelectorDefinition("purchase_order_id", "Durable Autotask purchase order identifier."),
        SelectorDefinition("purchase_order_number", "Human-visible Autotask purchase order number."),
        SelectorDefinition("vendor_invoice_number", "Vendor invoice number recorded on an Autotask purchase order."),
        SelectorDefinition("is_billed", "Whether an Autotask ticket charge has already been approved and posted."),
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
                    IntegrationOperation(
                        operation_id="service.ticket.count",
                        kind=OperationKind.SEARCH,
                        capability_name=SERVICE_TICKET_COUNT,
                        description=(
                            "Count authorized Autotask tickets matching bounded selectors "
                            "without retrieving ticket records."
                        ),
                        read_only=True,
                        selector_names=(
                            "ticket_number",
                            "company_id",
                            "status",
                            "filters",
                            "resource_id",
                        ),
                        collection_supported=False,
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
                resource_type="service_notification",
                description="Autotask notification history, bounded to an authorized company or ticket.",
                selectors=selectors,
                operations=(
                    _search("service.notification.history.search", SERVICE_NOTIFICATION_HISTORY_SEARCH, ("company_id", "ticket_id", "template_name", "page_size", "after_resource_id")),
                ),
                observations=(ResourceObservation("communication", "Template name, recipient, sent time, and related ticket/company."),),
                relationships=("notification -> company", "notification -> ticket"),
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
                resource_type="service_product",
                description="Autotask product catalog records.",
                selectors=selectors,
                operations=(
                    _search("service.product.search", SERVICE_PRODUCT_SEARCH, ("name", "sku", "filters", "page_size", "after_resource_id", "resource_id")),
                    _read("service.product.read", SERVICE_PRODUCT_READ),
                ),
                observations=(ResourceObservation("catalog", "Product identity, SKU, cost, price, and inventory/procurement metadata."),),
                relationships=("product -> vendor", "product -> purchase order item"),
            ),
            ResourceDefinition(
                resource_type="service_product_vendor",
                description="Autotask product-to-vendor associations.",
                selectors=selectors,
                operations=(
                    _search("service.product.vendor.search", SERVICE_PRODUCT_VENDOR_SEARCH, ("product_id", "vendor_id", "filters", "page_size", "after_resource_id")),
                ),
                observations=(ResourceObservation("procurement", "Approved product/vendor association evidence."),),
                relationships=("product vendor -> product", "product vendor -> vendor company"),
            ),
            ResourceDefinition(
                resource_type="service_catalog_service",
                description="Autotask recurring service catalog records.",
                selectors=selectors,
                operations=(
                    _search("service.service.search", SERVICE_SERVICE_SEARCH, ("name", "filters", "page_size", "after_resource_id", "resource_id")),
                    _read("service.service.read", SERVICE_SERVICE_READ),
                ),
                observations=(ResourceObservation("catalog", "Recurring service definition and pricing metadata."),),
            ),
            ResourceDefinition(
                resource_type="service_bundle",
                description="Autotask service bundle catalog records.",
                selectors=selectors,
                operations=(
                    _search("service.service.bundle.search", SERVICE_SERVICE_BUNDLE_SEARCH, ("name", "filters", "page_size", "after_resource_id", "resource_id")),
                    _read("service.service.bundle.read", SERVICE_SERVICE_BUNDLE_READ),
                ),
                observations=(ResourceObservation("catalog", "Recurring service bundle definition and pricing metadata."),),
            ),
            ResourceDefinition(
                resource_type="service_purchase_order",
                description="Autotask purchase orders and line items.",
                selectors=selectors,
                operations=(
                    _search("service.purchase.order.search", SERVICE_PURCHASE_ORDER_SEARCH, ("purchase_order_number", "vendor_id", "vendor_invoice_number", "filters", "page_size", "after_resource_id", "resource_id")),
                    _read("service.purchase.order.read", SERVICE_PURCHASE_ORDER_READ),
                    _search("service.purchase.order.item.search", SERVICE_PURCHASE_ORDER_ITEM_SEARCH, ("purchase_order_id", "product_id", "filters", "page_size", "after_resource_id", "resource_id")),
                ),
                observations=(ResourceObservation("procurement", "PO vendor, invoice, status, freight, totals context, and ordered line-item evidence."),),
                relationships=("purchase order -> vendor company", "purchase order -> product"),
            ),
            ResourceDefinition(
                resource_type="service_ticket_charge",
                description="Autotask product/material billing charges associated with authorized tickets.",
                selectors=selectors,
                operations=(
                    _search("service.ticket.charge.search", SERVICE_TICKET_CHARGE_SEARCH, ("ticket_id", "product_id", "is_billed", "filters", "page_size", "after_resource_id", "resource_id")),
                    _read("service.ticket.charge.read", SERVICE_TICKET_CHARGE_READ),
                ),
                observations=(ResourceObservation("billing", "Ticket product/material charge, quantity, cost, price, billable state, and PO references."),),
                relationships=("ticket charge -> ticket", "ticket charge -> product"),
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
