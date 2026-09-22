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

CLAW_PROVIDER = "claw"
OPERATIONS_SOURCE_CAPABILITIES_READ = "operations.source.capabilities.read"
OPERATIONS_SOURCE_STATUS_READ = "operations.source.status.read"
OPERATIONS_ARTIFACT_READ = "operations.artifact.read"
OPERATIONS_TASK_REQUEST_SEARCH = "operations.task.request.search"
OPERATIONS_TASK_REQUEST_CREATE = "operations.task.request.create"

CLAW_READ_CAPABILITIES = (
    OPERATIONS_SOURCE_CAPABILITIES_READ,
    OPERATIONS_SOURCE_STATUS_READ,
    OPERATIONS_ARTIFACT_READ,
    OPERATIONS_TASK_REQUEST_SEARCH,
)
CLAW_ALL_CAPABILITIES = CLAW_READ_CAPABILITIES + (OPERATIONS_TASK_REQUEST_CREATE,)


def _read_capability(
    *,
    now: datetime,
    name: str,
    display_name: str,
    purpose: str,
    resource_types: str,
    operation: str,
    selector_keys: str,
    fact_hints: str,
) -> CapabilityDefinition:
    return CapabilityDefinition(
        capability_name=name,
        version="1.0",
        display_name=display_name,
        lifecycle_status=CapabilityLifecycle.ACTIVE,
        business_purpose=purpose,
        owner_service="Jason Operational Source Intelligence",
        architectural_capability_ids=frozenset({"JAC-005", "JAC-013"}),
        risk_level=CapabilityRisk.LOW,
        data_classifications=frozenset({"internal"}),
        permitted_execution_modes=frozenset({"deterministic"}),
        input_schema_reference=f"schema://jason/{name.replace('.', '-')}/1.0",
        output_schema_reference=f"schema://jason/{name.replace('.', '-')}-result/1.0",
        invoking_roles=frozenset({"orchestrator"}),
        approval=CapabilityApproval(required=False),
        evidence=CapabilityEvidence(
            required=True,
            requirements=("governed provider result", "source provider identity"),
            verification_requirements=("Claw bridge authentication remains valid",),
        ),
        dependencies=frozenset(),
        idempotency_behavior=IdempotencyBehavior.IDEMPOTENT,
        idempotency_key_required=False,
        timeout_seconds=30,
        maximum_attempts=1,
        failure_behavior="Fail closed without shell, arbitrary file, or browser fallback.",
        tenant_isolation_required=True,
        client_isolation_required=False,
        stewardship=CapabilityStewardship(
            steward="technology-steward",
            business_justification=(
                "Read operational state from an approved legacy automation source while "
                "Jason progressively assumes its responsibilities."
            ),
            review_interval_days=30,
            retirement_criteria=(
                "Claw has been fully migrated into Jason.",
                "The governed Claw bridge is no longer an approved evidence source.",
            ),
            authoritative_change_sources=("AOT Claw governed MCP bridge contract",),
        ),
        created_at=now,
        metadata={
            "provider_neutral": "true",
            "read_only": "true",
            "resource_types": resource_types,
            "operation": operation,
            "selector_keys": selector_keys,
            "fact_hints": fact_hints,
        },
    )


def claw_capabilities(now: datetime) -> tuple[CapabilityDefinition, ...]:
    return (
        _read_capability(
            now=now,
            name=OPERATIONS_SOURCE_CAPABILITIES_READ,
            display_name="Read Operational Source Capabilities",
            purpose="Read the governed capability and artifact boundary of an operational source.",
            resource_types="operations_source,claw",
            operation="read",
            selector_keys="",
            fact_hints="Claw external OpenClaw bridge capabilities artifacts guardrails",
        ),
        _read_capability(
            now=now,
            name=OPERATIONS_SOURCE_STATUS_READ,
            display_name="Read Operational Source Status",
            purpose="Read current status and automation health from an approved operational source.",
            resource_types="operations_status,operations_source,claw",
            operation="read",
            selector_keys="",
            fact_hints="Claw status automation health daily operations external OpenClaw",
        ),
        _read_capability(
            now=now,
            name=OPERATIONS_ARTIFACT_READ,
            display_name="Read Operational Artifact",
            purpose="Read one allowlisted report, status, log, or evidence artifact.",
            resource_types="operations_artifact,claw",
            operation="read",
            selector_keys="key,max_bytes",
            fact_hints="Claw artifact report log todo worklog dashboard evidence",
        ),
        _read_capability(
            now=now,
            name=OPERATIONS_TASK_REQUEST_SEARCH,
            display_name="Search Operational Task Requests",
            purpose="List recent governed task requests sent to an operational source.",
            resource_types="operations_task_request,claw",
            operation="search",
            selector_keys="limit",
            fact_hints="Claw task request queue request history",
        ),
        CapabilityDefinition(
            capability_name=OPERATIONS_TASK_REQUEST_CREATE,
            version="1.0",
            display_name="Create Operational Task Request",
            lifecycle_status=CapabilityLifecycle.BUILDING,
            business_purpose="Create one governed internal task request for Claw.",
            owner_service="Jason Governed Actions",
            architectural_capability_ids=frozenset({"JAC-005", "JAC-006"}),
            risk_level=CapabilityRisk.MEDIUM,
            data_classifications=frozenset({"internal"}),
            permitted_execution_modes=frozenset({"deterministic"}),
            input_schema_reference="schema://jason/operations-task-request-create/1.0",
            output_schema_reference="schema://jason/operations-task-request-create-result/1.0",
            invoking_roles=frozenset({"orchestrator"}),
            approval=CapabilityApproval(required=True, approver_classes=("owner",)),
            evidence=CapabilityEvidence(
                required=True,
                requirements=("authenticated requester", "Claw task request id"),
                verification_requirements=("task request appears in Claw queue",),
            ),
            dependencies=frozenset({"identity.authorization.resolve"}),
            idempotency_behavior=IdempotencyBehavior.NON_IDEMPOTENT,
            idempotency_key_required=True,
            timeout_seconds=30,
            maximum_attempts=1,
            failure_behavior="Fail closed without direct Claw action fallback.",
            tenant_isolation_required=True,
            client_isolation_required=False,
            stewardship=CapabilityStewardship(
                steward="technology-steward",
                business_justification="Permit governed delegation to Claw during migration.",
                review_interval_days=30,
                retirement_criteria=("Claw task delegation is retired.",),
                authoritative_change_sources=("AOT Claw governed MCP bridge contract",),
            ),
            created_at=now,
            metadata={
                "provider_neutral": "true",
                "read_only": "false",
                "write_capability": "true",
                "resource_types": "operations_task_request,claw",
                "operation": "create",
                "selector_keys": "title,body,priority",
                "fact_hints": "Claw task request delegate work",
                "mcp_action_enabled": "false",
            },
        ),
    )


def claw_provider(now: datetime, *, enabled: bool) -> ExecutionProvider:
    return ExecutionProvider(
        provider_id=CLAW_PROVIDER,
        display_name="Claw",
        provider_type=ProviderType.EXTERNAL_CONNECTOR,
        lifecycle_status=ProviderLifecycle.AVAILABLE if enabled else ProviderLifecycle.PLANNED,
        health_status=ProviderHealth.HEALTHY if enabled else ProviderHealth.UNAVAILABLE,
        approval_status=ProviderApproval.APPROVED if enabled else ProviderApproval.BLOCKED,
        execution_modes=frozenset({"deterministic"}),
        capabilities=frozenset(CLAW_ALL_CAPABILITIES),
        supported_classifications=frozenset({"internal"}),
        regions=frozenset(),
        limits=ProviderLimits(
            maximum_concurrent_executions=2,
            maximum_requests_per_minute=30,
            maximum_execution_seconds=30,
        ),
        features=ProviderFeatures(structured_output=True),
        pricing_profile_id="zero-cost-foundation",
        stewardship=ProviderStewardship(
            technology_steward="technology-steward",
            business_justification=(
                "Use the governed external Claw bridge as a temporary authoritative "
                "source while its automations and data are migrated into Jason."
            ),
            review_interval_days=30,
            last_reviewed_at=now,
            retirement_criteria=("Claw migration is complete.",),
            vendor_change_sources=("AOT Claw governed MCP bridge contract",),
            operational_owner="AOT IT Operations",
            approval_owner="AOT Owner",
        ),
        created_at=now,
        metadata={
            "connector_id": "claw",
            "source_identity": "external_claw",
            "migration_role": "legacy_automation_source",
            "task_request_write": "staged_not_active",
        },
    )


def register_claw_resource_foundation(
    *,
    capabilities: CapabilityRegistryService,
    providers: ExecutionProviderRegistryService,
    now: datetime,
    enabled: bool,
) -> None:
    for capability in claw_capabilities(now):
        capabilities.register(capability)
    providers.register(claw_provider(now, enabled=enabled))
