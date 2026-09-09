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

DOCUMENTATION_ORGANIZATION_SEARCH = "documentation.organization.search"
DOCUMENTATION_ORGANIZATION_READ = "documentation.organization.read"
DOCUMENTATION_CONTACT_SEARCH = "documentation.contact.search"
DOCUMENTATION_CONTACT_READ = "documentation.contact.read"
DOCUMENTATION_LOCATION_SEARCH = "documentation.location.search"
DOCUMENTATION_LOCATION_READ = "documentation.location.read"
DOCUMENTATION_CONFIGURATION_SEARCH = "documentation.configuration.search"
DOCUMENTATION_CONFIGURATION_READ = "documentation.configuration.read"

SERVICE_COMPANY_SEARCH = "service.company.search"
SERVICE_COMPANY_READ = "service.company.read"
SERVICE_CONTACT_SEARCH = "service.contact.search"
SERVICE_CONTACT_READ = "service.contact.read"
SERVICE_TICKET_SEARCH = "service.ticket.search"
SERVICE_TICKET_READ = "service.ticket.read"
SERVICE_TICKET_NOTES_SEARCH = "service.ticket.notes.search"
SERVICE_CONFIGURATION_SEARCH = "service.configuration.search"
SERVICE_CONFIGURATION_READ = "service.configuration.read"
SERVICE_ENTITY_DESCRIBE = "service.entity.describe"


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
    }
)

AUTOTASK_CAPABILITIES = frozenset(
    {
        SERVICE_COMPANY_SEARCH,
        SERVICE_COMPANY_READ,
        SERVICE_CONTACT_SEARCH,
        SERVICE_CONTACT_READ,
        SERVICE_TICKET_SEARCH,
        SERVICE_TICKET_READ,
        SERVICE_TICKET_NOTES_SEARCH,
        SERVICE_CONFIGURATION_SEARCH,
        SERVICE_CONFIGURATION_READ,
        SERVICE_ENTITY_DESCRIBE,
    }
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
                "Expose existing client documentation and service-management records "
                "through reusable governed resources rather than question-specific code."
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
            business_purpose="Read one authorized IT documentation location.",
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
            capability_name=SERVICE_ENTITY_DESCRIBE,
            display_name="Describe Service Entity Schema",
            business_purpose=(
                "Read the provider schema for an approved service-management entity so "
                "new fields can be queried without question-specific code."
            ),
            resource_types="service_schema",
            operation="describe",
            selector_keys="entity",
            fact_hints="schema,fields,field names,entity metadata,entity information",
            authoritative_change_sources=at,
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
                f"{display_name} is no longer an approved authority for {authority}.",
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
    """Register IT Glue and Autotask read foundations without activating MCP reads."""

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
