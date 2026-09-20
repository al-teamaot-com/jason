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
from kernel.execution_providers import (
    ExecutionProvider,
    ExecutionProviderRegistryService,
    ProviderApproval,
    ProviderFeatures,
    ProviderHealth,
    ProviderLifecycle,
    ProviderLimits,
    ProviderStewardship,
    ProviderType,
)


IT_GLUE_PROVIDER = "it_glue"
AUTOTASK_PROVIDER = "autotask"
MICROSOFT_GRAPH_PROVIDER = "microsoft_graph"

DOCUMENTATION_ORGANIZATION_SEARCH = "documentation.organization.search"
DOCUMENTATION_ORGANIZATION_READ = "documentation.organization.read"
DOCUMENTATION_CONTACT_SEARCH = "documentation.contact.search"
DOCUMENTATION_CONTACT_READ = "documentation.contact.read"
DOCUMENTATION_LOCATION_SEARCH = "documentation.location.search"
DOCUMENTATION_LOCATION_READ = "documentation.location.read"
DOCUMENTATION_CONFIGURATION_SEARCH = "documentation.configuration.search"
DOCUMENTATION_CONFIGURATION_READ = "documentation.configuration.read"
DOCUMENTATION_DOCUMENT_SEARCH = "documentation.document.search"
DOCUMENTATION_DOCUMENT_READ = "documentation.document.read"

SERVICE_COMPANY_SEARCH = "service.company.search"
SERVICE_COMPANY_READ = "service.company.read"
SERVICE_CONTACT_SEARCH = "service.contact.search"
SERVICE_CONTACT_READ = "service.contact.read"
SERVICE_TICKET_SEARCH = "service.ticket.search"
SERVICE_TICKET_COUNT = "service.ticket.count"
SERVICE_TICKET_READ = "service.ticket.read"
SERVICE_TICKET_NOTES_SEARCH = "service.ticket.notes.search"
SERVICE_CONFIGURATION_SEARCH = "service.configuration.search"
SERVICE_CONFIGURATION_READ = "service.configuration.read"
SERVICE_ENTITY_DESCRIBE = "service.entity.describe"
SERVICE_ENTITY_FIELDS_DESCRIBE = "service.entity.fields.describe"
SERVICE_NOTIFICATION_HISTORY_SEARCH = "service.notification.history.search"
SERVICE_PRODUCT_SEARCH = "service.product.search"
SERVICE_PRODUCT_READ = "service.product.read"
SERVICE_PRODUCT_VENDOR_SEARCH = "service.product.vendor.search"
SERVICE_SERVICE_SEARCH = "service.service.search"
SERVICE_SERVICE_READ = "service.service.read"
SERVICE_SERVICE_BUNDLE_SEARCH = "service.service.bundle.search"
SERVICE_SERVICE_BUNDLE_READ = "service.service.bundle.read"
SERVICE_PURCHASE_ORDER_SEARCH = "service.purchase.order.search"
SERVICE_PURCHASE_ORDER_READ = "service.purchase.order.read"
SERVICE_PURCHASE_ORDER_ITEM_SEARCH = "service.purchase.order.item.search"
SERVICE_TICKET_CHARGE_SEARCH = "service.ticket.charge.search"
SERVICE_TICKET_CHARGE_READ = "service.ticket.charge.read"

IDENTITY_USER_SEARCH = "identity.user.search"
IDENTITY_USER_READ = "identity.user.read"
IDENTITY_AUTHENTICATION_METHODS_READ = "identity.authentication.methods.read"
IDENTITY_CONDITIONAL_ACCESS_SEARCH = "identity.conditional.access.search"
IDENTITY_DIRECTORY_ROLE_SEARCH = "identity.directory.role.search"
IDENTITY_DIRECTORY_ROLE_MEMBERS_SEARCH = "identity.directory.role.members.search"
COMMUNICATION_MAIL_MESSAGE_SEARCH = "communication.mail.message.search"
COMMUNICATION_MAIL_MESSAGE_READ = "communication.mail.message.read"
COMMUNICATION_MAIL_ATTACHMENT_SEARCH = "communication.mail.attachment.search"


IT_GLUE_CAPABILITIES = frozenset(
    {
        DOCUMENTATION_ORGANIZATION_SEARCH,
        DOCUMENTATION_ORGANIZATION_READ,
        DOCUMENTATION_CONTACT_SEARCH,
        DOCUMENTATION_CONTACT_READ,
        DOCUMENTATION_LOCATION_SEARCH,
        DOCUMENTATION_LOCATION_READ,
        DOCUMENTATION_CONFIGURATION_SEARCH,
        DOCUMENTATION_CONFIGURATION_READ,
        DOCUMENTATION_DOCUMENT_SEARCH,
        DOCUMENTATION_DOCUMENT_READ,
    }
)

AUTOTASK_CAPABILITIES = frozenset(
    {
        SERVICE_COMPANY_SEARCH,
        SERVICE_COMPANY_READ,
        SERVICE_CONTACT_SEARCH,
        SERVICE_CONTACT_READ,
        SERVICE_TICKET_SEARCH,
        SERVICE_TICKET_COUNT,
        SERVICE_TICKET_READ,
        SERVICE_TICKET_NOTES_SEARCH,
        SERVICE_CONFIGURATION_SEARCH,
        SERVICE_CONFIGURATION_READ,
        SERVICE_ENTITY_DESCRIBE,
        SERVICE_ENTITY_FIELDS_DESCRIBE,
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
    }
)

MICROSOFT_GRAPH_DIRECTORY_CAPABILITIES = frozenset(
    {
        IDENTITY_USER_SEARCH,
        IDENTITY_USER_READ,
        IDENTITY_AUTHENTICATION_METHODS_READ,
        IDENTITY_CONDITIONAL_ACCESS_SEARCH,
        IDENTITY_DIRECTORY_ROLE_SEARCH,
        IDENTITY_DIRECTORY_ROLE_MEMBERS_SEARCH,
    }
)

MICROSOFT_GRAPH_MAIL_CAPABILITIES = frozenset(
    {
        COMMUNICATION_MAIL_MESSAGE_SEARCH,
        COMMUNICATION_MAIL_MESSAGE_READ,
        COMMUNICATION_MAIL_ATTACHMENT_SEARCH,
    }
)

MICROSOFT_GRAPH_CAPABILITIES = (
    MICROSOFT_GRAPH_DIRECTORY_CAPABILITIES | MICROSOFT_GRAPH_MAIL_CAPABILITIES
)


def _read_capability(
    *,
    now: datetime,
    capability_name: str,
    display_name: str,
    business_purpose: str,
    resource_types: str,
    operation: str,
    selector_keys: str,
    fact_hints: str,
    authoritative_change_sources: tuple[str, ...],
    collection_fact: str = "",
    canonical_facts: str = "",
) -> CapabilityDefinition:
    """Build a provider-neutral, read-only capability awaiting live acceptance.

    These capabilities intentionally enter the registry as PILOT rather than ACTIVE.
    MCP capability discovery only publishes ACTIVE reads, so source composition can be
    tested without advertising a provider path before provider-backed acceptance proof.
    """

    metadata = {
        "provider_neutral": "true",
        "read_only": "true",
        "resource_types": resource_types,
        "operation": operation,
        "selector_keys": selector_keys,
        "fact_hints": fact_hints,
        "inquiry_hints": fact_hints,
        "planning_guidance": (
            "Use this governed read capability for the declared resource family. "
            "Human labels are selectors; durable resource identifiers are required "
            "for exact reads. Preserve ambiguity and never select the first match."
        ),
    }
    if collection_fact:
        metadata["collection_fact"] = collection_fact
    if canonical_facts:
        metadata["canonical_facts"] = canonical_facts

    return CapabilityDefinition(
        capability_name=capability_name,
        version="1.0",
        display_name=display_name,
        lifecycle_status=CapabilityLifecycle.PILOT,
        business_purpose=business_purpose,
        owner_service="Jason Resource Intelligence",
        architectural_capability_ids=frozenset({"JAC-005", "JAC-013"}),
        risk_level=CapabilityRisk.LOW,
        data_classifications=frozenset({"internal"}),
        permitted_execution_modes=frozenset({"deterministic"}),
        input_schema_reference=(
            f"schema://jason/{capability_name.replace('.', '-')}/1.0"
        ),
        output_schema_reference=(
            f"schema://jason/{capability_name.replace('.', '-')}-result/1.0"
        ),
        invoking_roles=frozenset({"orchestrator"}),
        approval=CapabilityApproval(required=False),
        evidence=CapabilityEvidence(
            required=True,
            requirements=("provider result", "source provider identity"),
            verification_requirements=(
                "resource selector remains in authorized organization scope",
                "returned facts originate from read-only provider evidence",
                "ambiguous selectors never auto-select a resource",
            ),
        ),
        dependencies=frozenset(),
        idempotency_behavior=IdempotencyBehavior.IDEMPOTENT,
        idempotency_key_required=False,
        timeout_seconds=60,
        maximum_attempts=2,
        failure_behavior=(
            "Fail closed without shell, agent, mutation, or first-match fallback."
        ),
        tenant_isolation_required=True,
        client_isolation_required=False,
        stewardship=CapabilityStewardship(
            steward="technology-steward",
            business_justification=(
                "Expose existing authoritative operational records through reusable "
                "governed resources rather than question-specific code."
            ),
            review_interval_days=90,
            retirement_criteria=(
                "Replaced by a broader governed resource interface.",
            ),
            authoritative_change_sources=authoritative_change_sources,
        ),
        created_at=now,
        metadata=metadata,
    )


def _capability_definitions(now: datetime) -> tuple[CapabilityDefinition, ...]:
    itg = ("IT Glue API documentation",)
    at = ("Autotask REST API documentation",)
    ms = ("Microsoft Graph v1.0 documentation",)
    return (
        _read_capability(
            now=now,
            capability_name=DOCUMENTATION_ORGANIZATION_SEARCH,
            display_name="Search Documented Organizations",
            business_purpose="Search authorized IT documentation organization records.",
            resource_types="documentation_organization,organization",
            operation="search",
            selector_keys="name,resource_id,filters,page_number,page_size",
            fact_hints="organization,client,company,name,organization id",
            authoritative_change_sources=itg,
            collection_fact="organizations",
        ),
        _read_capability(
            now=now,
            capability_name=DOCUMENTATION_ORGANIZATION_READ,
            display_name="Read Documented Organization",
            business_purpose="Read one authorized IT documentation organization record.",
            resource_types="documentation_organization,organization",
            operation="read",
            selector_keys="resource_id",
            fact_hints="organization,client,company,name,organization details",
            authoritative_change_sources=itg,
        ),
        _read_capability(
            now=now,
            capability_name=DOCUMENTATION_CONTACT_SEARCH,
            display_name="Search Documented Contacts",
            business_purpose="Search authorized IT documentation contacts.",
            resource_types="documentation_contact,contact",
            operation="search",
            selector_keys=(
                "organization_id,name,resource_id,filters,page_number,page_size"
            ),
            fact_hints="contact,contacts,user,email,phone,title,organization",
            authoritative_change_sources=itg,
            collection_fact="contacts",
        ),
        _read_capability(
            now=now,
            capability_name=DOCUMENTATION_CONTACT_READ,
            display_name="Read Documented Contact",
            business_purpose="Read one authorized IT documentation contact.",
            resource_types="documentation_contact,contact",
            operation="read",
            selector_keys="resource_id",
            fact_hints="contact,user,email,phone,title,organization",
            authoritative_change_sources=itg,
        ),
        _read_capability(
            now=now,
            capability_name=DOCUMENTATION_LOCATION_SEARCH,
            display_name="Search Documented Locations",
            business_purpose="Search authorized IT documentation locations.",
            resource_types="documentation_location,location",
            operation="search",
            selector_keys=(
                "organization_id,name,resource_id,filters,page_number,page_size"
            ),
            fact_hints="location,locations,address,site,office,organization",
            authoritative_change_sources=itg,
            collection_fact="locations",
        ),
        _read_capability(
            now=now,
            capability_name=DOCUMENTATION_LOCATION_READ,
            display_name="Read Documented Location",
            business_purpose="Read one authorized IT documentation location record.",
            resource_types="documentation_location,location",
            operation="read",
            selector_keys="resource_id",
            fact_hints="location,address,site,office,organization",
            authoritative_change_sources=itg,
        ),
        _read_capability(
            now=now,
            capability_name=DOCUMENTATION_CONFIGURATION_SEARCH,
            display_name="Search Documented Configurations",
            business_purpose="Search authorized IT Glue configuration records.",
            resource_types="documentation_configuration,configuration",
            operation="search",
            selector_keys=(
                "organization_id,name,resource_id,filters,page_number,page_size"
            ),
            fact_hints=(
                "configuration,configurations,device,asset,serial number,model,"
                "manufacturer,operating system,organization"
            ),
            authoritative_change_sources=itg,
            collection_fact="configurations",
        ),
        _read_capability(
            now=now,
            capability_name=DOCUMENTATION_CONFIGURATION_READ,
            display_name="Read Documented Configuration",
            business_purpose="Read one authorized IT Glue configuration record.",
            resource_types="documentation_configuration,configuration",
            operation="read",
            selector_keys="resource_id",
            fact_hints=(
                "configuration,device,asset,serial number,model,manufacturer,"
                "operating system,organization"
            ),
            authoritative_change_sources=itg,
        ),
        _read_capability(
            now=now,
            capability_name=DOCUMENTATION_DOCUMENT_SEARCH,
            display_name="Search Documented Policies and Procedures",
            business_purpose="Search authorized IT Glue documents, policies, standards, and SOPs.",
            resource_types="documentation_document,document,policy,procedure,sop",
            operation="search",
            selector_keys=(
                "organization_id,filters,page_number,page_size"
            ),
            fact_hints=(
                "document,documents,policy,policies,procedure,procedures,sop,standard,"
                "guideline,documentation,title,organization"
            ),
            authoritative_change_sources=itg,
            collection_fact="documents",
        ),
        _read_capability(
            now=now,
            capability_name=DOCUMENTATION_DOCUMENT_READ,
            display_name="Read Documented Policy or Procedure",
            business_purpose="Read one authorized IT Glue document by durable identifier.",
            resource_types="documentation_document,document,policy,procedure,sop",
            operation="read",
            selector_keys="resource_id",
            fact_hints=(
                "document,policy,procedure,sop,standard,guideline,documentation,content,title"
            ),
            authoritative_change_sources=itg,
        ),
        _read_capability(
            now=now,
            capability_name=SERVICE_COMPANY_SEARCH,
            display_name="Search Service Companies",
            business_purpose="Search authorized service-management company records.",
            resource_types="service_company,organization",
            operation="search",
            selector_keys=(
                "name,resource_id,filters,page_size,after_resource_id"
            ),
            fact_hints="company,client,organization,account,status,phone,address",
            authoritative_change_sources=at,
            collection_fact="companies",
        ),
        _read_capability(
            now=now,
            capability_name=SERVICE_COMPANY_READ,
            display_name="Read Service Company",
            business_purpose="Read one authorized service-management company record.",
            resource_types="service_company,organization",
            operation="read",
            selector_keys="resource_id",
            fact_hints="company,client,organization,account,status,phone,address",
            authoritative_change_sources=at,
        ),
        _read_capability(
            now=now,
            capability_name=SERVICE_CONTACT_SEARCH,
            display_name="Search Service Contacts",
            business_purpose="Search authorized service-management contacts.",
            resource_types="service_contact,contact",
            operation="search",
            selector_keys=(
                "company_id,first_name,last_name,email,resource_id,filters,"
                "page_size,after_resource_id"
            ),
            fact_hints="contact,contacts,user,email,phone,title,company",
            authoritative_change_sources=at,
            collection_fact="contacts",
        ),
        _read_capability(
            now=now,
            capability_name=SERVICE_CONTACT_READ,
            display_name="Read Service Contact",
            business_purpose="Read one authorized service-management contact.",
            resource_types="service_contact,contact",
            operation="read",
            selector_keys="resource_id",
            fact_hints="contact,user,email,phone,title,company",
            authoritative_change_sources=at,
        ),
        _read_capability(
            now=now,
            capability_name=SERVICE_TICKET_SEARCH,
            display_name="Search Service Tickets",
            business_purpose="Search authorized service-management tickets.",
            resource_types="service_ticket,ticket",
            operation="search",
            selector_keys=(
                "ticket_number,company_id,status,resource_id,filters,page_size,"
                "after_resource_id"
            ),
            fact_hints=(
                "ticket,tickets,ticket number,title,status,queue,priority,assigned,"
                "due date,issue,description,company"
            ),
            authoritative_change_sources=at,
            collection_fact="tickets",
        ),
        _read_capability(
            now=now,
            capability_name=SERVICE_TICKET_COUNT,
            display_name="Count Service Tickets",
            business_purpose=(
                "Count authorized service-management tickets matching bounded selectors "
                "without retrieving ticket records."
            ),
            resource_types="service_ticket,ticket",
            operation="count",
            selector_keys="ticket_number,company_id,status,resource_id,filters",
            fact_hints=(
                "count,how many,number of tickets,ticket count,tickets,status,new tickets,"
                "open tickets,company"
            ),
            authoritative_change_sources=at,
            canonical_facts="count",
        ),
        _read_capability(
            now=now,
            capability_name=SERVICE_TICKET_READ,
            display_name="Read Service Ticket",
            business_purpose="Read one authorized service-management ticket.",
            resource_types="service_ticket,ticket",
            operation="read",
            selector_keys="resource_id,ticket_id",
            fact_hints=(
                "ticket,ticket number,title,status,queue,priority,assigned,due date,"
                "issue,description,company"
            ),
            authoritative_change_sources=at,
        ),
        _read_capability(
            now=now,
            capability_name=SERVICE_TICKET_NOTES_SEARCH,
            display_name="Read Service Ticket Notes",
            business_purpose="Read notes associated with one authorized service ticket.",
            resource_types="service_ticket_note,ticket_note,ticket",
            operation="search",
            selector_keys="ticket_id,resource_id",
            fact_hints="ticket note,ticket notes,note,notes,update,work note,description",
            authoritative_change_sources=at,
            collection_fact="ticket notes",
        ),
        _read_capability(
            now=now,
            capability_name=SERVICE_NOTIFICATION_HISTORY_SEARCH,
            display_name="Search Service Notification History",
            business_purpose="Search bounded Autotask notification history for one authorized company or ticket.",
            resource_types="service_notification,notification_history,notification_template",
            operation="search",
            selector_keys="company_id,ticket_id,template_name,page_size,after_resource_id",
            fact_hints="notification,notification history,notification template,template,email sent,recipient",
            authoritative_change_sources=at,
            collection_fact="notification history",
        ),
        _read_capability(
            now=now,
            capability_name=SERVICE_CONFIGURATION_SEARCH,
            display_name="Search Service Configuration Items",
            business_purpose="Search authorized service-management configuration items.",
            resource_types="service_configuration,configuration",
            operation="search",
            selector_keys=(
                "company_id,name,resource_id,filters,page_size,after_resource_id"
            ),
            fact_hints=(
                "configuration item,configuration items,device,asset,serial number,"
                "reference name,product,company,status"
            ),
            authoritative_change_sources=at,
            collection_fact="configuration items",
        ),
        _read_capability(
            now=now,
            capability_name=SERVICE_CONFIGURATION_READ,
            display_name="Read Service Configuration Item",
            business_purpose="Read one authorized service-management configuration item.",
            resource_types="service_configuration,configuration",
            operation="read",
            selector_keys="resource_id",
            fact_hints=(
                "configuration item,device,asset,serial number,reference name,"
                "product,company,status"
            ),
            authoritative_change_sources=at,
        ),
        _read_capability(
            now=now,
            capability_name=SERVICE_PRODUCT_SEARCH,
            display_name="Search Service Products",
            business_purpose="Search authorized Autotask product catalog records.",
            resource_types="service_product,product,catalog_item",
            operation="search",
            selector_keys="name,sku,resource_id,filters,page_size,after_resource_id",
            fact_hints="product,products,catalog,item,sku,part number,unit cost,unit price,inventory",
            authoritative_change_sources=at,
            collection_fact="products",
        ),
        _read_capability(
            now=now,
            capability_name=SERVICE_PRODUCT_READ,
            display_name="Read Service Product",
            business_purpose="Read one authorized Autotask product catalog record.",
            resource_types="service_product,product,catalog_item",
            operation="read",
            selector_keys="resource_id",
            fact_hints="product,catalog item,sku,part number,unit cost,unit price,inventory",
            authoritative_change_sources=at,
        ),
        _read_capability(
            now=now,
            capability_name=SERVICE_PRODUCT_VENDOR_SEARCH,
            display_name="Search Product Vendors",
            business_purpose="Search vendor associations for one authorized Autotask product.",
            resource_types="service_product_vendor,product_vendor,vendor",
            operation="search",
            selector_keys="product_id,vendor_id,filters,page_size,after_resource_id",
            fact_hints="product vendor,vendor association,supplier,product supplier",
            authoritative_change_sources=at,
            collection_fact="product vendors",
        ),
        _read_capability(
            now=now,
            capability_name=SERVICE_SERVICE_SEARCH,
            display_name="Search Service Catalog Services",
            business_purpose="Search authorized Autotask recurring service catalog records.",
            resource_types="service_catalog_service,service,catalog_item",
            operation="search",
            selector_keys="name,resource_id,filters,page_size,after_resource_id",
            fact_hints="service,services,recurring service,catalog,billing service",
            authoritative_change_sources=at,
            collection_fact="services",
        ),
        _read_capability(
            now=now,
            capability_name=SERVICE_SERVICE_READ,
            display_name="Read Service Catalog Service",
            business_purpose="Read one authorized Autotask recurring service catalog record.",
            resource_types="service_catalog_service,service,catalog_item",
            operation="read",
            selector_keys="resource_id",
            fact_hints="service,recurring service,catalog,billing service",
            authoritative_change_sources=at,
        ),
        _read_capability(
            now=now,
            capability_name=SERVICE_SERVICE_BUNDLE_SEARCH,
            display_name="Search Service Bundles",
            business_purpose="Search authorized Autotask service bundle catalog records.",
            resource_types="service_bundle,catalog_item",
            operation="search",
            selector_keys="name,resource_id,filters,page_size,after_resource_id",
            fact_hints="service bundle,bundle,recurring service bundle,catalog",
            authoritative_change_sources=at,
            collection_fact="service bundles",
        ),
        _read_capability(
            now=now,
            capability_name=SERVICE_SERVICE_BUNDLE_READ,
            display_name="Read Service Bundle",
            business_purpose="Read one authorized Autotask service bundle catalog record.",
            resource_types="service_bundle,catalog_item",
            operation="read",
            selector_keys="resource_id",
            fact_hints="service bundle,bundle,recurring service bundle,catalog",
            authoritative_change_sources=at,
        ),
        _read_capability(
            now=now,
            capability_name=SERVICE_PURCHASE_ORDER_SEARCH,
            display_name="Search Purchase Orders",
            business_purpose="Search authorized Autotask purchase orders.",
            resource_types="service_purchase_order,purchase_order,procurement",
            operation="search",
            selector_keys="purchase_order_number,vendor_id,vendor_invoice_number,resource_id,filters,page_size,after_resource_id",
            fact_hints="purchase order,po,vendor invoice,procurement,vendor,supplier",
            authoritative_change_sources=at,
            collection_fact="purchase orders",
        ),
        _read_capability(
            now=now,
            capability_name=SERVICE_PURCHASE_ORDER_READ,
            display_name="Read Purchase Order",
            business_purpose="Read one authorized Autotask purchase order.",
            resource_types="service_purchase_order,purchase_order,procurement",
            operation="read",
            selector_keys="resource_id",
            fact_hints="purchase order,po,vendor invoice,procurement,vendor,supplier",
            authoritative_change_sources=at,
        ),
        _read_capability(
            now=now,
            capability_name=SERVICE_PURCHASE_ORDER_ITEM_SEARCH,
            display_name="Search Purchase Order Items",
            business_purpose="Search line items associated with one authorized Autotask purchase order.",
            resource_types="service_purchase_order_item,purchase_order_item,procurement",
            operation="search",
            selector_keys="purchase_order_id,product_id,resource_id,filters,page_size,after_resource_id",
            fact_hints="purchase order item,po line,line item,ordered product,quantity,unit cost",
            authoritative_change_sources=at,
            collection_fact="purchase order items",
        ),
        _read_capability(
            now=now,
            capability_name=SERVICE_TICKET_CHARGE_SEARCH,
            display_name="Search Ticket Charges",
            business_purpose="Search authorized Autotask product/material charges on service tickets.",
            resource_types="service_ticket_charge,ticket_charge,billing_item",
            operation="search",
            selector_keys="ticket_id,product_id,resource_id,is_billed,filters,page_size,after_resource_id",
            fact_hints="ticket charge,billable product,material cost,ticket billing,product charge,quantity,unit price",
            authoritative_change_sources=at,
            collection_fact="ticket charges",
        ),
        _read_capability(
            now=now,
            capability_name=SERVICE_TICKET_CHARGE_READ,
            display_name="Read Ticket Charge",
            business_purpose="Read one authorized Autotask product/material charge on a service ticket.",
            resource_types="service_ticket_charge,ticket_charge,billing_item",
            operation="read",
            selector_keys="resource_id",
            fact_hints="ticket charge,billable product,material cost,ticket billing,product charge,quantity,unit price",
            authoritative_change_sources=at,
        ),
        _read_capability(
            now=now,
            capability_name=SERVICE_ENTITY_DESCRIBE,
            display_name="Describe Service Entity Schema",
            business_purpose=(
                "Read the provider schema for an approved service-management entity so "
                "new fields can be queried without question-specific code."
            ),
            resource_types="service_schema",
            operation="describe",
            selector_keys="entity",
            fact_hints="schema,entity metadata,entity information,permissions",
            authoritative_change_sources=at,
        ),
        _read_capability(
            now=now,
            capability_name=SERVICE_ENTITY_FIELDS_DESCRIBE,
            display_name="Describe Service Entity Fields",
            business_purpose=(
                "Read provider field metadata and tenant-specific picklist values for an "
                "approved service-management entity."
            ),
            resource_types="service_schema,service_field_schema",
            operation="describe_fields",
            selector_keys="entity",
            fact_hints="fields,field names,picklist,picklist values,field metadata,schema",
            authoritative_change_sources=at,
        ),
        _read_capability(
            now=now,
            capability_name=IDENTITY_USER_SEARCH,
            display_name="Search Microsoft Entra Users",
            business_purpose=(
                "Search the authenticated tenant's Microsoft Entra users by one exact "
                "identity selector."
            ),
            resource_types="identity_user,user,entra_user",
            operation="search",
            selector_keys="email,user_principal_name,display_name,page_size",
            fact_hints=(
                "Microsoft Entra user,Entra user,user account,UPN,email,display name,"
                "enabled account,directory user"
            ),
            authoritative_change_sources=ms,
            collection_fact="users",
            canonical_facts="id,display_name,email,user_principal_name,account_enabled",
        ),
        _read_capability(
            now=now, capability_name=IDENTITY_AUTHENTICATION_METHODS_READ, display_name="Read Entra Authentication Methods",
            business_purpose="Read registered authentication method types for one exact Entra user in the authenticated tenant.",
            resource_types="identity_authentication_methods,identity_user,entra_user", operation="read", selector_keys="user_id",
            fact_hints="MFA,authentication methods,registered methods,passwordless,FIDO2,Authenticator", authoritative_change_sources=ms,
            canonical_facts="user_id,method_type,count",
        ),
        _read_capability(
            now=now, capability_name=IDENTITY_CONDITIONAL_ACCESS_SEARCH, display_name="Search Entra Conditional Access Policies",
            business_purpose="Read bounded Conditional Access policy configuration in the authenticated tenant.",
            resource_types="identity_conditional_access,conditional_access,policy", operation="search", selector_keys="page_size",
            fact_hints="Conditional Access,MFA policy,legacy authentication,grant controls,session controls", authoritative_change_sources=ms,
            collection_fact="conditional access policies", canonical_facts="id,display_name,state,conditions,grant_controls,session_controls",
        ),
        _read_capability(
            now=now, capability_name=IDENTITY_DIRECTORY_ROLE_SEARCH, display_name="Search Entra Directory Roles",
            business_purpose="Read bounded activated directory roles in the authenticated tenant.", resource_types="identity_directory_role,directory_role,privileged_role",
            operation="search", selector_keys="page_size", fact_hints="directory roles,privileged roles,Global Administrator,admin roles", authoritative_change_sources=ms,
            collection_fact="directory roles", canonical_facts="id,display_name,role_template_id",
        ),
        _read_capability(
            now=now, capability_name=IDENTITY_DIRECTORY_ROLE_MEMBERS_SEARCH, display_name="Search Entra Directory Role Members",
            business_purpose="Read bounded members of one exact activated Entra directory role.", resource_types="identity_directory_role_member,directory_role_member,privileged_identity",
            operation="search", selector_keys="role_id,page_size", fact_hints="role members,privileged accounts,Global Administrator members,admin accounts", authoritative_change_sources=ms,
            collection_fact="directory role members", canonical_facts="id,display_name,user_principal_name,account_enabled,object_type",
        ),
        _read_capability(
            now=now,
            capability_name=IDENTITY_USER_READ,
            display_name="Read Microsoft Entra User",
            business_purpose=(
                "Read one Microsoft Entra user from the authenticated tenant by durable "
                "Microsoft object identifier."
            ),
            resource_types="identity_user,user,entra_user",
            operation="read",
            selector_keys="resource_id",
            fact_hints=(
                "Microsoft Entra user,Entra user,user account,UPN,email,display name,"
                "enabled account,directory user"
            ),
            authoritative_change_sources=ms,
            canonical_facts="id,display_name,email,user_principal_name,account_enabled",
        ),
        _read_capability(
            now=now,
            capability_name=COMMUNICATION_MAIL_MESSAGE_SEARCH,
            display_name="Search Approved Mailbox Messages",
            business_purpose="Search bounded messages in one explicitly approved AOT mailbox for operational evidence.",
            resource_types="communication_mail_message,email_message,mailbox_message",
            operation="search",
            selector_keys="mailbox,sender,received_after,received_before,page_size",
            fact_hints="mailbox,email,message,vendor order,ETA,shipping,tracking,backorder,invoice,delivery",
            authoritative_change_sources=ms,
            collection_fact="mail messages",
            canonical_facts="id,subject,sender,received_at,has_attachments,internet_message_id,conversation_id",
        ),
        _read_capability(
            now=now,
            capability_name=COMMUNICATION_MAIL_MESSAGE_READ,
            display_name="Read Approved Mailbox Message",
            business_purpose="Read one exact message from one explicitly approved AOT mailbox.",
            resource_types="communication_mail_message,email_message,mailbox_message",
            operation="read",
            selector_keys="mailbox,message_id",
            fact_hints="email body,message body,vendor update,order confirmation,ETA,shipping,tracking,invoice",
            authoritative_change_sources=ms,
            canonical_facts="id,subject,sender,received_at,body_type,body,body_preview",
        ),
        _read_capability(
            now=now,
            capability_name=COMMUNICATION_MAIL_ATTACHMENT_SEARCH,
            display_name="Search Mail Attachment Metadata",
            business_purpose="Read bounded attachment metadata for one exact approved mailbox message without exposing attachment content.",
            resource_types="communication_mail_attachment,email_attachment",
            operation="search",
            selector_keys="mailbox,message_id,page_size",
            fact_hints="attachment,invoice attachment,packing slip,shipping document",
            authoritative_change_sources=ms,
            collection_fact="mail attachment metadata",
            canonical_facts="id,name,content_type,size,is_inline,modified_at",
        ),
    )


def _provider(
    *,
    now: datetime,
    provider_id: str,
    display_name: str,
    capabilities: frozenset[str],
    authority: str,
    vendor_change_sources: tuple[str, ...],
) -> ExecutionProvider:
    return ExecutionProvider(
        provider_id=provider_id,
        display_name=display_name,
        provider_type=ProviderType.EXTERNAL_CONNECTOR,
        lifecycle_status=ProviderLifecycle.PLANNED,
        health_status=ProviderHealth.UNKNOWN,
        approval_status=ProviderApproval.PILOT,
        execution_modes=frozenset({"deterministic"}),
        capabilities=capabilities,
        supported_classifications=frozenset({"internal"}),
        regions=frozenset(),
        limits=ProviderLimits(
            maximum_concurrent_executions=5,
            maximum_requests_per_minute=60,
            maximum_execution_seconds=60,
        ),
        features=ProviderFeatures(structured_output=True),
        pricing_profile_id="zero-cost-foundation",
        stewardship=ProviderStewardship(
            technology_steward="technology-steward",
            business_justification=(
                f"{display_name} is an existing operational authority; Jason reads it "
                "through the governed connector boundary instead of duplicating state."
            ),
            review_interval_days=90,
            last_reviewed_at=now,
            retirement_criteria=(
                f"{display_name} is no longer an approved authority for {authority}."
            ),
            vendor_change_sources=vendor_change_sources,
            operational_owner="AOT IT Operations",
            approval_owner="Jason Architecture Authority",
        ),
        created_at=now,
        metadata={
            "connector_id": provider_id,
            "resource_authority": authority,
            "activation_state": "awaiting_provider_backed_acceptance",
        },
    )


def register_provider_read_foundation(
    *,
    capabilities: CapabilityRegistryService,
    providers: ExecutionProviderRegistryService,
    now: datetime,
) -> None:
    """Register governed provider read foundations without activating MCP reads."""

    for definition in _capability_definitions(now):
        capabilities.register(definition)

    providers.register(
        _provider(
            now=now,
            provider_id=IT_GLUE_PROVIDER,
            display_name="IT Glue",
            capabilities=IT_GLUE_CAPABILITIES,
            authority="client_documentation",
            vendor_change_sources=("IT Glue API documentation",),
        )
    )
    providers.register(
        _provider(
            now=now,
            provider_id=AUTOTASK_PROVIDER,
            display_name="Autotask PSA",
            capabilities=AUTOTASK_CAPABILITIES,
            authority="service_management",
            vendor_change_sources=("Autotask REST API documentation",),
        )
    )
    providers.register(
        _provider(
            now=now,
            provider_id=MICROSOFT_GRAPH_PROVIDER,
            display_name="Microsoft Entra Directory",
            capabilities=MICROSOFT_GRAPH_CAPABILITIES,
            authority="identity_directory",
            vendor_change_sources=("Microsoft Graph v1.0 documentation",),
        )
    )
