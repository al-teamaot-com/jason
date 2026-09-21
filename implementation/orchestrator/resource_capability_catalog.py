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
SITE_VARIABLE_LIST = "management.site.variable.list"
AUTOMATION_COMPONENT_SEARCH = "automation.component.search"
AUTOMATION_JOB_READ = "automation.job.read"
AUTOMATION_JOB_OUTPUT_READ = "automation.job.output.read"
ENDPOINT_SECURITY_STATUS_READ = "endpoint.security.status.read"
ENDPOINT_SECURITY_DETECTION_SEARCH = "endpoint.security.detection.search"
ENDPOINT_SECURITY_DETECTION_READ = "endpoint.security.detection.read"
ENDPOINT_SECURITY_POLICY_READ = "endpoint.security.policy.read"
ENDPOINT_SECURITY_SCAN_HISTORY_SEARCH = "endpoint.security.scan.history.search"
ENDPOINT_SECURITY_QUARANTINE_SEARCH = "endpoint.security.quarantine.search"
DATTO_RMM_PROVIDER = "datto_rmm"
DATTO_EDR_PROVIDER = "datto_edr"


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
    authoritative_change_sources: tuple[str, ...] = (
        "Datto RMM API documentation",
    ),
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


def site_variable_list(now: datetime) -> CapabilityDefinition:
    return CapabilityDefinition(
        capability_name=SITE_VARIABLE_LIST,
        version="1.0",
        display_name="Read Managed Site Variables",
        lifecycle_status=CapabilityLifecycle.ACTIVE,
        business_purpose=(
            "Read Datto RMM site variables for governed automation while separating "
            "internal secret use from requester disclosure."
        ),
        owner_service="Jason Resource Intelligence",
        architectural_capability_ids=frozenset({"JAC-005", "JAC-013"}),
        risk_level=CapabilityRisk.MEDIUM,
        data_classifications=frozenset({"internal", "secret"}),
        permitted_execution_modes=frozenset({"deterministic"}),
        input_schema_reference="schema://jason/site-variable-list/1.0",
        output_schema_reference="schema://jason/site-variable-list-result/1.0",
        invoking_roles=frozenset({"orchestrator"}),
        approval=CapabilityApproval(required=False),
        evidence=CapabilityEvidence(
            required=True,
            requirements=("provider result", "source provider identity"),
            verification_requirements=("site remains in authorized scope",),
        ),
        dependencies=frozenset(),
        idempotency_behavior=IdempotencyBehavior.IDEMPOTENT,
        idempotency_key_required=False,
        timeout_seconds=30,
        maximum_attempts=2,
        failure_behavior=(
            "Fail closed. Secret values may be consumed internally but may be "
            "disclosed only when the authenticated principal has administer authority."
        ),
        tenant_isolation_required=True,
        client_isolation_required=False,
        stewardship=CapabilityStewardship(
            steward="technology-steward",
            business_justification=(
                "Playbooks need site-scoped configuration values without exposing "
                "those values to non-administrative requesters."
            ),
            review_interval_days=90,
            retirement_criteria=("Datto RMM is no longer the site-variable authority.",),
            authoritative_change_sources=("Datto RMM API documentation",),
        ),
        created_at=now,
        metadata={
            "provider_neutral": "true",
            "read_only": "true",
            "resource_types": "management_site_variable",
            "operation": "list",
            "selector_keys": "site_uid,resource_id",
            "fact_hints": "site variable,site variables,configured,present,value",
            "inquiry_hints": "site variable,site variables",
            "collection_fact": "site variables",
            "value_disclosure_permission": "administer",
            "non_admin_view": "presence_status_only",
            "secret_logging": "forbidden",
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


def automation_component_search(now: datetime) -> CapabilityDefinition:
    return _read_resource_capability(
        now=now,
        capability_name=AUTOMATION_COMPONENT_SEARCH,
        display_name="Search Automation Components",
        business_purpose=(
            "Read the governed automation component catalog so Jason can identify an "
            "existing provider component before any separate execution decision."
        ),
        resource_types="automation_component",
        operation="search",
        selector_keys="name",
        fact_hints=(
            "component,components,automation component,automation components,"
            "component name,component catalog,read only tool,read-only tool,"
            "diagnostic component,diagnostic tool,component variable,component variables"
        ),
        canonical_facts="automation components",
        planning_guidance=(
            "Use only to discover/read existing automation components. This capability "
            "does not authorize or imply component execution."
        ),
        collection_fact="automation components",
        inquiry_hints=(
            "component,components,automation component,automation components,"
            "component catalog,read only tool,read-only tool,diagnostic component,"
            "diagnostic tool"
        ),
    )


def automation_job_read(now: datetime) -> CapabilityDefinition:
    return _read_resource_capability(
        now=now,
        capability_name=AUTOMATION_JOB_READ,
        display_name="Read Automation Job",
        business_purpose=(
            "Read the current status of one known automation job by durable job identity "
            "for governed post-execution verification."
        ),
        resource_types="automation_job",
        operation="read",
        selector_keys="resource_id",
        fact_hints=(
            "automation job,job status,component job,quick job,job state,"
            "job result,job verification"
        ),
        canonical_facts="automation job status",
        planning_guidance=(
            "Use only when a durable automation job resource_id is already known. "
            "This read cannot create, modify, cancel, or rerun a job."
        ),
        inquiry_hints=(
            "automation job,job status,component job,quick job,job state,job verification"
        ),
    )



def automation_job_output_read(now: datetime) -> CapabilityDefinition:
    return _read_resource_capability(
        now=now,
        capability_name=AUTOMATION_JOB_OUTPUT_READ,
        display_name="Read Automation Job Output",
        business_purpose=(
            "Read bounded StdOut or StdErr evidence from one known "
            "automation job, endpoint, and component without changing "
            "the job or endpoint."
        ),
        resource_types=(
            "automation_job_output,automation_job,"
            "automation_component,endpoint"
        ),
        operation="read",
        selector_keys=(
            "resource_id,device_uid,component_uid,stream"
        ),
        fact_hints=(
            "job output,component output,stdout,stderr,"
            "standard output,standard error,script output,"
            "automation result,component result"
        ),
        canonical_facts="automation job output",
        planning_guidance=(
            "Use only after a durable job resource_id, endpoint "
            "device_uid, and component_uid are known. stream may be "
            "stdout or stderr. This capability cannot create, change, "
            "cancel, or rerun a job."
        ),
        inquiry_hints=(
            "job output,component output,stdout,stderr,"
            "standard output,standard error,script output,"
            "automation result,component result"
        ),
    )


def endpoint_security_status_read(now: datetime) -> CapabilityDefinition:
    return _read_resource_capability(
        now=now,
        capability_name=ENDPOINT_SECURITY_STATUS_READ,
        display_name="Read Endpoint Security Status",
        business_purpose=(
            "Read authoritative endpoint EDR/AV health, licensing, version, "
            "signature, scan, and isolation state by durable endpoint identity."
        ),
        resource_types="endpoint_security,endpoint",
        operation="read",
        selector_keys="resource_id",
        fact_hints=(
            "edr status,av status,antivirus status,security status,agent version,"
            "engine version,vdf version,signature version,definitions,license,"
            "isolation,reboot required,last antivirus scan"
        ),
        canonical_facts=(
            "endpoint security status,edr agent version,antivirus engine version,"
            "antivirus definition version,security isolation state"
        ),
        planning_guidance=(
            "Use after the managed endpoint has a durable resource_id. "
            "The provider must map that identity exactly and preserve ambiguity."
        ),
        authoritative_change_sources=(
            "Datto EDR/AV API documentation",
            "Datto EDR tenant LoopBack OpenAPI",
        ),
    )


def endpoint_security_detection_search(now: datetime) -> CapabilityDefinition:
    return _read_resource_capability(
        now=now,
        capability_name=ENDPOINT_SECURITY_DETECTION_SEARCH,
        display_name="Search Endpoint Security Detections",
        business_purpose="Read bounded EDR/AV detections for one resolved security agent.",
        resource_types="endpoint_security_detection,endpoint_security,endpoint",
        operation="search",
        selector_keys="agent_id,archived,limit",
        fact_hints=(
            "security detection,edr alert,av alert,malware alert,threat,"
            "security alert,detection history"
        ),
        collection_fact="security detections",
        planning_guidance=(
            "Use the agent_id returned by endpoint.security.status.read; "
            "do not resolve an agent from hostname alone."
        ),
        authoritative_change_sources=(
            "Datto EDR/AV API documentation",
            "Datto EDR tenant LoopBack OpenAPI",
        ),
    )


def endpoint_security_detection_read(now: datetime) -> CapabilityDefinition:
    return _read_resource_capability(
        now=now,
        capability_name=ENDPOINT_SECURITY_DETECTION_READ,
        display_name="Read Endpoint Security Detection",
        business_purpose=(
            "Read one Datto EDR/AV detection plus its quarantine/containment evidence."
        ),
        resource_types="endpoint_security_detection,endpoint_security,endpoint",
        operation="read",
        selector_keys="alert_id,threat_reference,resource_id,drmm_alert_uid",
        fact_hints=(
            "detection detail,threat detail,quarantine status,sha256,"
            "malicious,suspicious,containment,DRMM threat reference"
        ),
        canonical_facts="security detection disposition,quarantine state",
        planning_guidance=(
            "Use an exact provider alert_id when already known. When a Datto RMM "
            "ticket/alert supplies only a numeric threat reference, supply that "
            "threat_reference plus the authoritative endpoint resource_id; Jason "
            "must correlate to exactly one provider-native EDR alert and fail closed "
            "on ambiguity. Never select EDR identity by hostname alone. A detection "
            "or quarantine state must not be relabeled as compromise."
        ),
        authoritative_change_sources=(
            "Datto EDR/AV API documentation",
            "Datto EDR tenant LoopBack OpenAPI",
        ),
    )


def endpoint_security_policy_read(now: datetime) -> CapabilityDefinition:
    return _read_resource_capability(
        now=now,
        capability_name=ENDPOINT_SECURITY_POLICY_READ,
        display_name="Read Endpoint Security Policies",
        business_purpose="Read security policies assigned to one resolved Datto EDR agent.",
        resource_types="endpoint_security_policy,endpoint_security,endpoint",
        operation="read",
        selector_keys="agent_id",
        fact_hints="edr policy,av policy,response policy,ransomware policy,assigned policy",
        collection_fact="assigned security policies",
        planning_guidance="Use the exact Datto EDR agent_id returned by status resolution.",
        authoritative_change_sources=(
            "Datto EDR/AV API documentation",
            "Datto EDR tenant LoopBack OpenAPI",
        ),
    )


def endpoint_security_scan_history_search(now: datetime) -> CapabilityDefinition:
    return _read_resource_capability(
        now=now,
        capability_name=ENDPOINT_SECURITY_SCAN_HISTORY_SEARCH,
        display_name="Read Endpoint Security Scan History",
        business_purpose="Read bounded Datto AV scan history for one resolved agent.",
        resource_types="endpoint_security_scan,endpoint_security,endpoint",
        operation="search",
        selector_keys="agent_id,limit",
        fact_hints="av scan,antivirus scan,quick scan,full scan,scan history,scan status",
        collection_fact="security scans",
        planning_guidance="Use the exact Datto EDR agent_id returned by status resolution.",
        authoritative_change_sources=(
            "Datto EDR/AV API documentation",
            "Datto EDR tenant LoopBack OpenAPI",
        ),
    )


def endpoint_security_quarantine_search(now: datetime) -> CapabilityDefinition:
    return _read_resource_capability(
        now=now,
        capability_name=ENDPOINT_SECURITY_QUARANTINE_SEARCH,
        display_name="Read Endpoint Security Quarantine",
        business_purpose="Read bounded Datto AV quarantine history for an agent or alert.",
        resource_types="endpoint_security_quarantine,endpoint_security_detection,endpoint",
        operation="search",
        selector_keys="agent_id,alert_id,limit",
        fact_hints="quarantine,quarantined file,restored file,containment,detection disposition",
        collection_fact="quarantine records",
        planning_guidance=(
            "Require an exact agent_id or alert_id. Quarantine is containment evidence, "
            "not independent proof of endpoint compromise."
        ),
        authoritative_change_sources=(
            "Datto EDR/AV API documentation",
            "Datto EDR tenant LoopBack OpenAPI",
        ),
    )


def datto_edr_endpoint_security_provider(now: datetime) -> ExecutionProvider:
    capabilities = frozenset(
        {
            ENDPOINT_SECURITY_STATUS_READ,
            ENDPOINT_SECURITY_DETECTION_SEARCH,
            ENDPOINT_SECURITY_DETECTION_READ,
            ENDPOINT_SECURITY_POLICY_READ,
            ENDPOINT_SECURITY_SCAN_HISTORY_SEARCH,
            ENDPOINT_SECURITY_QUARANTINE_SEARCH,
        }
    )
    return ExecutionProvider(
        provider_id=DATTO_EDR_PROVIDER,
        display_name="Datto EDR/AV",
        provider_type=ProviderType.EXTERNAL_CONNECTOR,
        lifecycle_status=ProviderLifecycle.AVAILABLE,
        health_status=ProviderHealth.HEALTHY,
        approval_status=ProviderApproval.APPROVED,
        execution_modes=frozenset({"deterministic"}),
        capabilities=capabilities,
        supported_classifications=frozenset({"internal"}),
        regions=frozenset(),
        limits=ProviderLimits(
            maximum_concurrent_executions=5,
            maximum_requests_per_minute=120,
            maximum_execution_seconds=60,
        ),
        features=ProviderFeatures(structured_output=True),
        pricing_profile_id="zero-cost-foundation",
        stewardship=ProviderStewardship(
            technology_steward="technology-steward",
            business_justification=(
                "Use Datto EDR/AV as authoritative provider evidence for endpoint "
                "security health and detections without duplicating provider state."
            ),
            review_interval_days=90,
            last_reviewed_at=now,
            retirement_criteria=(
                "Datto EDR/AV is no longer the approved endpoint-security provider.",
            ),
            vendor_change_sources=(
                "Datto EDR/AV API documentation",
                "Datto EDR tenant LoopBack OpenAPI",
            ),
            operational_owner="AOT IT Operations",
            approval_owner="Jason Architecture Authority",
        ),
        created_at=now,
        metadata={
            "connector_id": "datto_edr",
            "resource_authority": "endpoint_security",
            "read_only": "true",
        },
    )


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
                SITE_VARIABLE_LIST,
                AUTOMATION_COMPONENT_SEARCH,
                AUTOMATION_JOB_READ,
                AUTOMATION_JOB_OUTPUT_READ,
            }
        ),
        supported_classifications=frozenset({"internal", "secret"}),
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
    """Register reusable endpoint/automation read primitives and the approved provider."""

    capabilities.register(endpoint_device_search(now))
    capabilities.register(endpoint_device_read(now))
    capabilities.register(endpoint_alert_search(now))
    capabilities.register(endpoint_alert_history_search(now))
    capabilities.register(endpoint_audit_read(now))
    capabilities.register(endpoint_software_search(now))
    capabilities.register(management_alert_search(now))
    capabilities.register(management_site_search(now))
    capabilities.register(site_variable_list(now))
    capabilities.register(automation_component_search(now))
    capabilities.register(automation_job_read(now))
    capabilities.register(automation_job_output_read(now))
    capabilities.register(endpoint_security_status_read(now))
    capabilities.register(endpoint_security_detection_search(now))
    capabilities.register(endpoint_security_detection_read(now))
    capabilities.register(endpoint_security_policy_read(now))
    capabilities.register(endpoint_security_scan_history_search(now))
    capabilities.register(endpoint_security_quarantine_search(now))
    providers.register(datto_rmm_endpoint_provider(now))
    providers.register(datto_edr_endpoint_security_provider(now))
