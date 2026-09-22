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


ENDPOINT_DEVICE_SEARCH = "endpoint.device.search"
ENDPOINT_DEVICE_READ = "endpoint.device.read"
ENDPOINT_ALERT_SEARCH = "endpoint.alert.search"
ENDPOINT_ALERT_HISTORY_SEARCH = "endpoint.alert.history.search"
ENDPOINT_AUDIT_READ = "endpoint.audit.read"
ENDPOINT_SOFTWARE_SEARCH = "endpoint.software.search"
MANAGEMENT_ALERT_SEARCH = "management.alert.search"
MANAGEMENT_SITE_SEARCH = "management.site.search"
SHAREPOINT_SITE_SEARCH = "documentation.sharepoint.site.search"
SHAREPOINT_LIBRARY_LIST = "documentation.sharepoint.library.list"
SHAREPOINT_DOCUMENT_SEARCH = "documentation.sharepoint.document.search"
SHAREPOINT_ITEM_READ = "documentation.sharepoint.item.read"
DATTO_RMM_PROVIDER = "datto_rmm"
MICROSOFT_SHAREPOINT_PROVIDER = "microsoft_sharepoint"


def endpoint_device_search(now: datetime) -> CapabilityDefinition:
    """Broad provider-neutral endpoint discovery/read capability.

    A caller supplies a human-grounded selector and requested facts. The selected
    provider must preserve ambiguity. If exactly one authorized candidate remains and
    exposes a durable identity, the provider may perform an exact read of that resolved
    resource to satisfy the requested facts. A selector itself never becomes identity.
    """

    return CapabilityDefinition(
        capability_name=ENDPOINT_DEVICE_SEARCH,
        version="1.0",
        display_name="Search Managed Endpoints",
        lifecycle_status=CapabilityLifecycle.ACTIVE,
        business_purpose=(
            "Read the authorized managed-endpoint resource set. With a supplied "
            "provider-neutral selector, locate matching endpoints while preserving "
            "ambiguity and retrieve an exact read-only device record only after one "
            "authorized candidate is resolved to durable identity. Without a selector, "
            "enumerate the bounded authorized endpoint collection so collection-wide "
            "information requests can begin from the primary endpoint resource evidence."
        ),
        owner_service="Jason Resource Intelligence",
        architectural_capability_ids=frozenset({"JAC-005", "JAC-013"}),
        risk_level=CapabilityRisk.LOW,
        data_classifications=frozenset({"internal"}),
        permitted_execution_modes=frozenset({"deterministic"}),
        input_schema_reference="schema://jason/endpoint-device-search/1.0",
        output_schema_reference="schema://jason/endpoint-device-records/1.0",
        invoking_roles=frozenset({"orchestrator"}),
        approval=CapabilityApproval(required=False),
        evidence=CapabilityEvidence(
            required=True,
            requirements=("provider result", "source provider identity"),
            verification_requirements=(
                "resource selector remains in authorized scope",
                "ambiguous selectors never auto-select a resource",
                "a unique discovery candidate exposes a durable resource identifier",
                "requested facts come from the exact resolved resource read when available",
            ),
        ),
        dependencies=frozenset(),
        idempotency_behavior=IdempotencyBehavior.IDEMPOTENT,
        idempotency_key_required=False,
        # A provider implementation may perform bounded discovery followed by one
        # exact resource read. Each provider call remains independently bounded.
        timeout_seconds=60,
        maximum_attempts=2,
        failure_behavior="Fail closed without shell, node, agent, or first-match fallback.",
        tenant_isolation_required=True,
        client_isolation_required=False,
        stewardship=CapabilityStewardship(
            steward="technology-steward",
            business_justification=(
                "Use existing endpoint-management data dynamically instead of creating "
                "one-off scripts for each endpoint fact."
            ),
            review_interval_days=90,
            retirement_criteria=(
                "Replaced by a broader governed endpoint resource interface.",
            ),
            authoritative_change_sources=("Datto RMM API documentation",),
        ),
        created_at=now,
        metadata={
            "provider_neutral": "true",
            "read_only": "true",
            "resource_types": "endpoint",
            "operation": "search",
            "selector_keys": "hostname,name,resource_id,site,serial_number,user_identity",
            "selector_required": "false",
            "collection_scope": "authorized",
            "resource_role": "primary",
            "fact_hints": (
                "hostname,device name,last logged in user,username,site,status,"
                "online,offline,operating system,ip address,mac address,hardware,"
                "software,device identifier,serial number,inventory,bitlocker,"
                "bitlocker status,bitlocker state,reboot required,restart required,"
                "pending reboot,pending restart,udf,user defined field"
            ),
            "canonical_facts": (
                "hostname,endpoint hostname,LAN IP address,WAN IP address,"
                "last logged in user,operating system,"
                "operating system display version,operating system build,"
                "bitlocker status,reboot required"
            ),
            "identity_semantics": (
                "Human-readable names, hostnames, aliases, labels, serial-like tokens, and "
                "site labels are discovery selectors, not durable identity. Discovery must "
                "observe ambiguity and may proceed only after one authorized candidate is "
                "resolved to a durable resource_id. Requested facts should then come from "
                "an exact read of that resolved resource when the provider supports it. "
                "Never select the first provider result."
            ),
            "planning_guidance": (
                "Prefer this capability when the human names an endpoint but does not "
                "already supply its durable provider-neutral resource identifier. Treat "
                "the supplied name/hostname as discovery criteria and require explicit "
                "disambiguation when more than one authorized resource remains."
            ),
        },
    )


def endpoint_device_read(now: datetime) -> CapabilityDefinition:
    return CapabilityDefinition(
        capability_name=ENDPOINT_DEVICE_READ,
        version="1.0",
        display_name="Read Managed Endpoint",
        lifecycle_status=CapabilityLifecycle.ACTIVE,
        business_purpose=(
            "Retrieve a managed endpoint record by durable resource identifier for "
            "governed read-only resource inquiries."
        ),
        owner_service="Jason Resource Intelligence",
        architectural_capability_ids=frozenset({"JAC-005", "JAC-013"}),
        risk_level=CapabilityRisk.LOW,
        data_classifications=frozenset({"internal"}),
        permitted_execution_modes=frozenset({"deterministic"}),
        input_schema_reference="schema://jason/endpoint-device-read/1.0",
        output_schema_reference="schema://jason/endpoint-device-record/1.0",
        invoking_roles=frozenset({"orchestrator"}),
        approval=CapabilityApproval(required=False),
        evidence=CapabilityEvidence(
            required=True,
            requirements=("provider result", "source provider identity"),
            verification_requirements=("resource identifier remains in authorized scope",),
        ),
        dependencies=frozenset(),
        idempotency_behavior=IdempotencyBehavior.IDEMPOTENT,
        idempotency_key_required=False,
        timeout_seconds=30,
        maximum_attempts=2,
        failure_behavior="Fail closed without shell, node, or agent fallback.",
        tenant_isolation_required=True,
        client_isolation_required=False,
        stewardship=CapabilityStewardship(
            steward="technology-steward",
            business_justification="Read existing endpoint-management records through a reusable resource interface.",
            review_interval_days=90,
            retirement_criteria=(
                "Replaced by a broader governed endpoint resource interface.",
            ),
            authoritative_change_sources=("Datto RMM API documentation",),
        ),
        created_at=now,
        metadata={
            "provider_neutral": "true",
            "read_only": "true",
            "resource_types": "endpoint",
            "operation": "read",
            "selector_keys": "resource_id",
            "selector_source_policy": {
                "resource_id": (
                    "verified_entity_only"
                ),
            },
            "fact_hints": (
                "device details,hostname,last logged in user,site,status,online,offline,"
                "operating system,ip address,mac address,hardware,software,"
                "serial number,inventory,bitlocker,bitlocker status,bitlocker state,"
                "reboot required,restart required,pending reboot,pending restart,"
                "udf,user defined field"
            ),
            "canonical_facts": (
                "hostname,endpoint hostname,LAN IP address,WAN IP address,"
                "last logged in user,operating system,"
                "operating system display version,operating system build,"
                "bitlocker status,reboot required"
            ),
            "identity_semantics": "resource_id is a durable resolved endpoint identity",
            "planning_guidance": (
                "Prefer this capability when a durable endpoint resource identifier is already known."
            ),
        },
    )



def _read_resource_capability(
    *,
    now: datetime,
    capability_name: str,
    display_name: str,
    business_purpose: str,
    resource_types: str,
    operation: str,
    selector_keys: str,
    fact_hints: str,
    planning_guidance: str,
    canonical_facts: str = "",
    collection_fact: str | None = None,
    inquiry_hints: str | None = None,
) -> CapabilityDefinition:
    """Construct one governed provider-neutral read-only resource capability."""

    return CapabilityDefinition(
        capability_name=capability_name,
        version="1.0",
        display_name=display_name,
        lifecycle_status=CapabilityLifecycle.ACTIVE,
        business_purpose=business_purpose,
        owner_service="Jason Resource Intelligence",
        architectural_capability_ids=frozenset({"JAC-005", "JAC-013"}),
        risk_level=CapabilityRisk.LOW,
        data_classifications=frozenset({"internal"}),
        permitted_execution_modes=frozenset({"deterministic"}),
        input_schema_reference=f"schema://jason/{capability_name.replace('.', '-')}/1.0",
        output_schema_reference=f"schema://jason/{capability_name.replace('.', '-')}-result/1.0",
        invoking_roles=frozenset({"orchestrator"}),
        approval=CapabilityApproval(required=False),
        evidence=CapabilityEvidence(
            required=True,
            requirements=("provider result", "source provider identity"),
            verification_requirements=(
                "resource selectors remain in authorized scope",
                "returned facts originate from read-only provider evidence",
            ),
        ),
        dependencies=frozenset(),
        idempotency_behavior=IdempotencyBehavior.IDEMPOTENT,
        idempotency_key_required=False,
        timeout_seconds=60,
        maximum_attempts=2,
        failure_behavior="Fail closed without shell, node, agent, or mutation fallback.",
        tenant_isolation_required=True,
        client_isolation_required=False,
        stewardship=CapabilityStewardship(
            steward="technology-steward",
            business_justification=(
                "Expose existing endpoint-management read data through reusable governed "
                "resources instead of question-specific scripts."
            ),
            review_interval_days=90,
            retirement_criteria=(
                "Replaced by a broader governed resource interface.",
            ),
            authoritative_change_sources=("Datto RMM API documentation",),
        ),
        created_at=now,
        metadata={
            "provider_neutral": "true",
            "read_only": "true",
            "resource_types": resource_types,
            "operation": operation,
            "selector_keys": selector_keys,
            "fact_hints": fact_hints,
            "inquiry_hints": inquiry_hints or fact_hints,
            **(
                {"canonical_facts": canonical_facts}
                if canonical_facts
                else {}
            ),
            **({"collection_fact": collection_fact} if collection_fact else {}),
            "planning_guidance": planning_guidance,
        },
    )


def endpoint_alert_search(now: datetime) -> CapabilityDefinition:
    return _read_resource_capability(
        now=now,
        capability_name=ENDPOINT_ALERT_SEARCH,
        display_name="Read Endpoint Alerts",
        business_purpose=(
            "Read open or resolved monitoring alerts associated with one managed endpoint."
        ),
        resource_types="endpoint_alert,alert,endpoint",
        operation="search",
        selector_keys="hostname,name,resource_id,site,status",
        fact_hints=(
            "alert,alerts,open alert,open alerts,resolved alert,resolved alerts,"
            "alert status,severity,priority,message,monitor,diagnostic"
        ),
        canonical_facts="open alerts",
        planning_guidance=(
            "Use when the human asks whether a named endpoint has alerts or asks for "
            "alert details. Resolve a human endpoint selector before invoking the "
            "device-scoped provider alert operation."
        ),
        collection_fact="alerts",
    )




def endpoint_alert_history_search(
    now: datetime,
) -> CapabilityDefinition:
    """Read historical or resolved alerts for one governed endpoint."""

    return _read_resource_capability(
        now=now,
        capability_name=
            ENDPOINT_ALERT_HISTORY_SEARCH,
        display_name=
            "Read Endpoint Alert History",
        business_purpose=(
            "Read historical or resolved monitoring alerts associated "
            "with one managed endpoint."
        ),
        resource_types=
            "endpoint_alert,alert,endpoint",
        operation="search",
        selector_keys=
            "hostname,name,resource_id,site",
        fact_hints=(
            "historical alert,historical alerts,alert history,"
            "resolved alert,resolved alerts,disk error,disk errors,"
            "bad block,event log,event logs"
        ),
        canonical_facts=
            "disk error evidence",
        planning_guidance=(
            "Use when the human asks whether a named endpoint previously "
            "experienced an alert condition or requests historical or "
            "resolved alert evidence."
        ),
        collection_fact="resolved alerts",
    )

def endpoint_audit_read(now: datetime) -> CapabilityDefinition:
    return _read_resource_capability(
        now=now,
        capability_name=ENDPOINT_AUDIT_READ,
        display_name="Read Endpoint Audit",
        business_purpose=(
            "Read detailed audited hardware, system, disk, network, BIOS, memory, "
            "processor, display, and attached-device information for one endpoint."
        ),
        resource_types="endpoint_audit,endpoint",
        operation="search",
        selector_keys="hostname,name,resource_id,site",
        fact_hints=(
            "audit,system info,system information,bios,baseboard,motherboard,nic,nics,"
            "network adapter,network adapters,logical disk,logical disks,disk,disks,"
            "processor,processors,cpu,memory,ram,physical memory,display,displays,"
            "video board,video boards,graphics,attached device,attached devices,snmp"
        ),
        canonical_facts=(
            "processor model,logical processor count,total memory,"
            "motherboard model,bios version,network adapters,"
            "logical disks,display adapters,printers,free disk space"
        ),
        planning_guidance=(
            "Use for detailed audited endpoint hardware/system facts that are not "
            "contained in the endpoint summary record."
        ),
    )


def endpoint_software_search(now: datetime) -> CapabilityDefinition:
    return _read_resource_capability(
        now=now,
        capability_name=ENDPOINT_SOFTWARE_SEARCH,
        display_name="Read Endpoint Software",
        business_purpose="Read audited software inventory for one managed endpoint.",
        resource_types="endpoint_software,endpoint",
        operation="search",
        selector_keys="hostname,name,resource_id,site,software",
        fact_hints=(
            "software,installed software,application,applications,program,programs,"
            "software inventory,installed application,installed applications,version"
        ),
        canonical_facts="software",
        planning_guidance=(
            "Use when the human asks what software/applications/programs are installed "
            "on a managed endpoint or asks whether particular software is present."
        ),
        collection_fact="software",
    )


def management_alert_search(now: datetime) -> CapabilityDefinition:
    return _read_resource_capability(
        now=now,
        capability_name=MANAGEMENT_ALERT_SEARCH,
        display_name="Search Managed Alerts",
        business_purpose=(
            "Search read-only monitoring alerts across the authorized managed environment."
        ),
        resource_types="alert",
        operation="search",
        selector_keys="site,site_id,status,severity,priority",
        fact_hints=(
            "alert,alerts,open alert,open alerts,monitoring alert,monitoring alerts,"
            "severity,priority,status,message,device,site"
        ),
        planning_guidance=(
            "Use for account/site-wide alert questions rather than a question about "
            "one already identified endpoint."
        ),
        canonical_facts="open alerts",
        collection_fact="alerts",
        inquiry_hints=(
            "alert,alerts,open alert,open alerts,monitoring alert,monitoring alerts,"
            "severity,priority,status,message"
        ),
    )


def management_site_search(now: datetime) -> CapabilityDefinition:
    return _read_resource_capability(
        now=now,
        capability_name=MANAGEMENT_SITE_SEARCH,
        display_name="Search Managed Sites",
        business_purpose="Read Datto RMM managed-site records in authorized scope.",
        resource_types="management_site",
        operation="search",
        selector_keys="name,site,site_id",
        fact_hints=(
            "site,sites,client site,managed site,site name,site identifier,site details"
        ),
        planning_guidance=(
            "Use for questions about managed Datto RMM sites or site discovery."
        ),
        canonical_facts="sites",
        collection_fact="sites",
        inquiry_hints=(
            "site,sites,client site,managed site,site name,site identifier,site details"
        ),
    )



def _sharepoint_read_capability(
    *,
    now: datetime,
    capability_name: str,
    display_name: str,
    business_purpose: str,
    operation: str,
    selector_keys: str,
    fact_hints: str,
) -> CapabilityDefinition:
    return CapabilityDefinition(
        capability_name=capability_name,
        version="1.0",
        display_name=display_name,
        lifecycle_status=CapabilityLifecycle.ACTIVE,
        business_purpose=business_purpose,
        owner_service="Jason Documentation Intelligence",
        architectural_capability_ids=frozenset({"JAC-005", "JAC-013"}),
        risk_level=CapabilityRisk.LOW,
        data_classifications=frozenset({"internal"}),
        permitted_execution_modes=frozenset({"deterministic"}),
        input_schema_reference=f"schema://jason/{capability_name.replace('.', '-')}/1.0",
        output_schema_reference=f"schema://jason/{capability_name.replace('.', '-')}-result/1.0",
        invoking_roles=frozenset({"orchestrator"}),
        approval=CapabilityApproval(required=False),
        evidence=CapabilityEvidence(
            required=True,
            requirements=("Microsoft Graph provider result", "AOT tenant boundary"),
            verification_requirements=(
                "read-only Microsoft Graph method",
                "AOT organization boundary remains authoritative",
                "no interactive-user connector fallback",
            ),
        ),
        dependencies=frozenset(),
        idempotency_behavior=IdempotencyBehavior.IDEMPOTENT,
        idempotency_key_required=False,
        timeout_seconds=30,
        maximum_attempts=2,
        failure_behavior="Fail closed without browser, shell, delegated-user, or write fallback.",
        tenant_isolation_required=True,
        client_isolation_required=False,
        stewardship=CapabilityStewardship(
            steward="technology-steward",
            business_justification="Use AOT SharePoint as a governed read-only evidence source for Jason.",
            review_interval_days=90,
            retirement_criteria=("SharePoint is no longer an approved AOT documentation authority.",),
            authoritative_change_sources=("Microsoft Graph SharePoint API documentation",),
        ),
        created_at=now,
        metadata={
            "provider_neutral": "true",
            "read_only": "true",
            "resource_types": "sharepoint_document,document,file,sharepoint_site",
            "operation": operation,
            "selector_keys": selector_keys,
            "fact_hints": fact_hints,
            "inquiry_hints": fact_hints,
            "planning_guidance": "Use for AOT SharePoint documentation and evidence discovery only.",
        },
    )


def microsoft_sharepoint_provider(now: datetime) -> ExecutionProvider:
    return ExecutionProvider(
        provider_id=MICROSOFT_SHAREPOINT_PROVIDER,
        display_name="Microsoft SharePoint",
        provider_type=ProviderType.EXTERNAL_CONNECTOR,
        lifecycle_status=ProviderLifecycle.AVAILABLE,
        health_status=ProviderHealth.HEALTHY,
        approval_status=ProviderApproval.APPROVED,
        execution_modes=frozenset({"deterministic"}),
        capabilities=frozenset({
            SHAREPOINT_SITE_SEARCH,
            SHAREPOINT_LIBRARY_LIST,
            SHAREPOINT_DOCUMENT_SEARCH,
            SHAREPOINT_ITEM_READ,
        }),
        supported_classifications=frozenset({"internal"}),
        regions=frozenset(),
        limits=ProviderLimits(
            maximum_concurrent_executions=5,
            maximum_requests_per_minute=60,
            maximum_execution_seconds=30,
        ),
        features=ProviderFeatures(structured_output=True),
        pricing_profile_id="zero-cost-foundation",
        stewardship=ProviderStewardship(
            technology_steward="technology-steward",
            business_justification="Microsoft SharePoint is an approved AOT documentation source.",
            review_interval_days=90,
            last_reviewed_at=now,
            retirement_criteria=("AOT retires SharePoint as a documentation platform.",),
            vendor_change_sources=("Microsoft Graph documentation",),
            operational_owner="AOT IT Operations",
            approval_owner="Jason Architecture Authority",
        ),
        created_at=now,
        metadata={
            "connector_id": MICROSOFT_SHAREPOINT_PROVIDER,
            "resource_authority": "aot_sharepoint_documentation",
            "permission_profile": "sharepoint-read",
            "required_application_permission": "Sites.Read.All",
        },
    )


def register_sharepoint_read_foundation(
    *,
    capabilities: CapabilityRegistryService,
    providers: ExecutionProviderRegistryService,
    now: datetime,
) -> None:
    capabilities.register(_sharepoint_read_capability(
        now=now,
        capability_name=SHAREPOINT_SITE_SEARCH,
        display_name="Search AOT SharePoint Sites",
        business_purpose="Find authorized AOT SharePoint sites through Microsoft Graph.",
        operation="search",
        selector_keys="query",
        fact_hints="sharepoint,sharepoint site,site,documentation site",
    ))
    capabilities.register(_sharepoint_read_capability(
        now=now,
        capability_name=SHAREPOINT_LIBRARY_LIST,
        display_name="List AOT SharePoint Libraries",
        business_purpose="List document libraries for an authorized AOT SharePoint site.",
        operation="list",
        selector_keys="site_id",
        fact_hints="sharepoint library,document library,drive,documents",
    ))
    capabilities.register(_sharepoint_read_capability(
        now=now,
        capability_name=SHAREPOINT_DOCUMENT_SEARCH,
        display_name="Search AOT SharePoint Documents",
        business_purpose="Search AOT SharePoint and OneDrive business documents as governed evidence.",
        operation="search",
        selector_keys="query,page_size",
        fact_hints="sharepoint document,document,file,policy,procedure,spreadsheet,pdf",
    ))
    capabilities.register(_sharepoint_read_capability(
        now=now,
        capability_name=SHAREPOINT_ITEM_READ,
        display_name="Read AOT SharePoint Item Metadata",
        business_purpose="Read exact metadata for a resolved AOT SharePoint file or folder.",
        operation="read",
        selector_keys="drive_id,item_id",
        fact_hints="sharepoint file,file metadata,document metadata,modified,size,web url",
    ))
    providers.register(microsoft_sharepoint_provider(now))

def datto_rmm_endpoint_provider(now: datetime) -> ExecutionProvider:
    return ExecutionProvider(
        provider_id=DATTO_RMM_PROVIDER,
        display_name="Datto RMM",
        provider_type=ProviderType.EXTERNAL_CONNECTOR,
        lifecycle_status=ProviderLifecycle.AVAILABLE,
        health_status=ProviderHealth.HEALTHY,
        approval_status=ProviderApproval.APPROVED,
        execution_modes=frozenset({"deterministic"}),
        capabilities=frozenset(
            {
                ENDPOINT_DEVICE_SEARCH,
                ENDPOINT_DEVICE_READ,
                ENDPOINT_ALERT_SEARCH,
                ENDPOINT_ALERT_HISTORY_SEARCH,
                ENDPOINT_AUDIT_READ,
                ENDPOINT_SOFTWARE_SEARCH,
                MANAGEMENT_ALERT_SEARCH,
                MANAGEMENT_SITE_SEARCH,
            }
        ),
        supported_classifications=frozenset({"internal"}),
        regions=frozenset(),
        limits=ProviderLimits(
            maximum_concurrent_executions=10,
            maximum_requests_per_minute=120,
            maximum_execution_seconds=60,
        ),
        features=ProviderFeatures(structured_output=True),
        pricing_profile_id="zero-cost-foundation",
        stewardship=ProviderStewardship(
            technology_steward="technology-steward",
            business_justification=(
                "Datto RMM is the authoritative existing endpoint-management platform; "
                "Jason integrates with it instead of duplicating endpoint state collection."
            ),
            review_interval_days=90,
            last_reviewed_at=now,
            retirement_criteria=(
                "Datto RMM is no longer the approved managed-endpoint authority.",
                "A replacement provider satisfies the same canonical endpoint capabilities.",
            ),
            vendor_change_sources=("Datto RMM API documentation",),
            operational_owner="AOT IT Operations",
            approval_owner="Jason Architecture Authority",
        ),
        created_at=now,
        metadata={
            "connector_id": "datto_rmm",
            "resource_authority": "managed_endpoint",
        },
    )


def register_endpoint_resource_foundation(
    *,
    capabilities: CapabilityRegistryService,
    providers: ExecutionProviderRegistryService,
    now: datetime,
) -> None:
    """Register reusable endpoint resource primitives and the current approved provider."""

    capabilities.register(endpoint_device_search(now))
    capabilities.register(endpoint_device_read(now))
    capabilities.register(endpoint_alert_search(now))
    capabilities.register(endpoint_alert_history_search(now))
    capabilities.register(endpoint_audit_read(now))
    capabilities.register(endpoint_software_search(now))
    capabilities.register(management_alert_search(now))
    capabilities.register(management_site_search(now))
    providers.register(datto_rmm_endpoint_provider(now))