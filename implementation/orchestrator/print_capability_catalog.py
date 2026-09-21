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


PRINT_DEVICE_SEARCH = "print.device.search"
PRINT_DEVICE_READ = "print.device.read"
PRINT_METER_READ = "print.meter.read"
PRINT_SUPPLIES_READ = "print.supplies.read"
PRINT_ALERT_SEARCH = "print.alert.search"
KYOCERA_KFS_PROVIDER = "kyocera_kfs"

_PRINT_CAPABILITIES = (
    PRINT_DEVICE_SEARCH,
    PRINT_DEVICE_READ,
    PRINT_METER_READ,
    PRINT_SUPPLIES_READ,
    PRINT_ALERT_SEARCH,
)


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
        owner_service="Jason Print Fleet Intelligence",
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
            requirements=("provider result", "source provider identity"),
            verification_requirements=("resource selector remains in authorized scope",),
        ),
        dependencies=frozenset(),
        idempotency_behavior=IdempotencyBehavior.IDEMPOTENT,
        idempotency_key_required=False,
        timeout_seconds=30,
        maximum_attempts=2,
        failure_behavior="Fail closed without shell, browser, or agent fallback.",
        tenant_isolation_required=True,
        client_isolation_required=True,
        stewardship=CapabilityStewardship(
            steward="technology-steward",
            business_justification=(
                "Use the approved copier fleet platform as the source of meter and "
                "device telemetry instead of duplicating collection logic."
            ),
            review_interval_days=90,
            retirement_criteria=(
                "KFS is no longer the approved copier fleet authority.",
                "A replacement provider satisfies the same canonical print capabilities.",
            ),
            authoritative_change_sources=(
                "Kyocera Fleet Services API documentation",
                "AOT Kyocera dealer integration contract",
            ),
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


def print_capabilities(now: datetime) -> tuple[CapabilityDefinition, ...]:
    return (
        _read_capability(
            now=now,
            name=PRINT_DEVICE_SEARCH,
            display_name="Search Managed Print Devices",
            purpose="Locate managed copier and MFP devices by client-scoped selectors.",
            resource_types="print_device",
            operation="search",
            selector_keys="serial_number,device_id,name,hostname,ip_address,client_id",
            fact_hints="copier printer MFP Kyocera serial model device customer location",
        ),
        _read_capability(
            now=now,
            name=PRINT_DEVICE_READ,
            display_name="Read Managed Print Device",
            purpose="Read identity and operational state for one managed copier or MFP.",
            resource_types="print_device",
            operation="read",
            selector_keys="resource_id,device_id,serial_number",
            fact_hints="model serial firmware status online location copier printer MFP",
        ),
        _read_capability(
            now=now,
            name=PRINT_METER_READ,
            display_name="Read Print Device Meters",
            purpose="Read governed meter and copy/print counts for a managed copier or MFP.",
            resource_types="print_meter,print_device",
            operation="read",
            selector_keys="resource_id,device_id,serial_number",
            fact_hints="meter count copy count print count mono black white color total impressions scan fax",
        ),
        _read_capability(
            now=now,
            name=PRINT_SUPPLIES_READ,
            display_name="Read Print Device Supplies",
            purpose="Read toner and supply state for a managed copier or MFP.",
            resource_types="print_supply,print_device",
            operation="read",
            selector_keys="resource_id,device_id,serial_number",
            fact_hints="toner supply black cyan magenta yellow waste maintenance level remaining",
        ),
        _read_capability(
            now=now,
            name=PRINT_ALERT_SEARCH,
            display_name="Search Print Device Alerts",
            purpose="Search current copier and MFP fault or service telemetry.",
            resource_types="print_alert,print_device",
            operation="search",
            selector_keys="resource_id,device_id,serial_number,client_id,status",
            fact_hints="fault error alert service code offline jam toner maintenance copier printer MFP",
        ),
    )


def kyocera_kfs_provider(now: datetime, *, enabled: bool) -> ExecutionProvider:
    return ExecutionProvider(
        provider_id=KYOCERA_KFS_PROVIDER,
        display_name="Kyocera Fleet Services",
        provider_type=ProviderType.EXTERNAL_CONNECTOR,
        lifecycle_status=(
            ProviderLifecycle.AVAILABLE if enabled else ProviderLifecycle.PLANNED
        ),
        health_status=(
            ProviderHealth.HEALTHY if enabled else ProviderHealth.UNAVAILABLE
        ),
        approval_status=(
            ProviderApproval.APPROVED if enabled else ProviderApproval.BLOCKED
        ),
        execution_modes=frozenset({"deterministic"}),
        capabilities=frozenset(_PRINT_CAPABILITIES),
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
            business_justification=(
                "KFS is AOT's intended authoritative Kyocera fleet data source for "
                "meter, supply, and device telemetry."
            ),
            review_interval_days=90,
            last_reviewed_at=now,
            retirement_criteria=(
                "KFS is no longer AOT's approved fleet telemetry source.",
                "A replacement satisfies the canonical print capability contracts.",
            ),
            vendor_change_sources=(
                "Kyocera Fleet Services API documentation",
                "AOT Kyocera dealer integration contract",
            ),
            operational_owner="AOT Copier Operations",
            approval_owner="Jason Architecture Authority",
        ),
        created_at=now,
        metadata={
            "connector_id": "kyocera_kfs",
            "resource_authority": "managed_print_fleet",
            "live_enablement": "enabled" if enabled else "blocked_pending_contract",
        },
    )


def register_print_resource_foundation(
    *,
    capabilities: CapabilityRegistryService,
    providers: ExecutionProviderRegistryService,
    now: datetime,
    enabled: bool,
) -> None:
    for capability in print_capabilities(now):
        capabilities.register(capability)
    providers.register(kyocera_kfs_provider(now, enabled=enabled))
