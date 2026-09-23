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

BACKUP_ENDPOINT_ASSET_SEARCH = "backup.endpoint.asset.search"
BACKUP_ENDPOINT_ASSET_READ = "backup.endpoint.asset.read"
BACKUP_ENDPOINT_BACKUP_SEARCH = "backup.endpoint.backup.search"
BACKUP_BACKUPIQ_ALERT_SEARCH = "backup.backupiq.alert.search"
BACKUP_NET_PROVIDER = "backup_net"

_BACKUP_CAPABILITIES = (
    BACKUP_ENDPOINT_ASSET_SEARCH,
    BACKUP_ENDPOINT_ASSET_READ,
    BACKUP_ENDPOINT_BACKUP_SEARCH,
    BACKUP_BACKUPIQ_ALERT_SEARCH,
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
        owner_service="Jason Backup Intelligence",
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
            requirements=("provider result", "validated client boundary"),
            verification_requirements=(
                "Autotask company maps to one validated Backup.net customer UUID",
                "all returned records match the mapped customer UUID",
            ),
        ),
        dependencies=frozenset(),
        idempotency_behavior=IdempotencyBehavior.IDEMPOTENT,
        idempotency_key_required=False,
        timeout_seconds=30,
        maximum_attempts=2,
        failure_behavior="Fail closed without shell, browser, or unscoped provider fallback.",
        tenant_isolation_required=True,
        client_isolation_required=False,
        stewardship=CapabilityStewardship(
            steward="technology-steward",
            business_justification=(
                "Use UniView/Backup.net as the authoritative provider-native "
                "source for Endpoint Backup and BackupIQ state."
            ),
            review_interval_days=90,
            retirement_criteria=(
                "Backup.net is no longer AOT's approved Endpoint Backup authority.",
                "A replacement satisfies the canonical backup capability contracts.",
            ),
            authoritative_change_sources=(
                "Kaseya UniView Public API documentation",
                "AOT BackupIQ Endpoint Backup playbook",
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
            "scope_model": "aot_internal_msp_client_partitioned",
            "client_partition_enforced_by": "validated_backup_net_customer_boundary",
        },
    )


def backup_capabilities(now: datetime) -> tuple[CapabilityDefinition, ...]:
    return (
        _read_capability(
            now=now,
            name=BACKUP_ENDPOINT_ASSET_SEARCH,
            display_name="Search Endpoint Backup Assets",
            purpose="Search provider-native Endpoint Backup assets for one mapped AOT client.",
            resource_types="backup_endpoint_asset,backup_asset",
            operation="search",
            selector_keys="company_id,id,name,page_number,page_size",
            fact_hints=(
                "endpoint backup asset device backup enabled last successful backup "
                "last online policy status storage"
            ),
        ),
        _read_capability(
            now=now,
            name=BACKUP_ENDPOINT_ASSET_READ,
            display_name="Read Endpoint Backup Asset",
            purpose="Read one provider-native Endpoint Backup asset for one mapped AOT client.",
            resource_types="backup_endpoint_asset,backup_asset",
            operation="read",
            selector_keys="company_id,resource_id,id",
            fact_hints=(
                "endpoint backup asset device backup enabled last successful backup "
                "last online policy status storage"
            ),
        ),
        _read_capability(
            now=now,
            name=BACKUP_ENDPOINT_BACKUP_SEARCH,
            display_name="Search Endpoint Backup History",
            purpose="Search provider-native backup history for one mapped AOT client.",
            resource_types="backup_endpoint_backup,backup_record",
            operation="search",
            selector_keys=(
                "company_id,asset_tag,asset_key,status,type,start_time_from,"
                "start_time_to,complete_time_from,complete_time_to,page_number,page_size"
            ),
            fact_hints=(
                "backup history successful failed warning in progress replication "
                "backup time size endpoint"
            ),
        ),
        _read_capability(
            now=now,
            name=BACKUP_BACKUPIQ_ALERT_SEARCH,
            display_name="Search BackupIQ Alerts",
            purpose="Search provider-native BackupIQ alerts for one mapped AOT client.",
            resource_types="backup_backupiq_alert,backup_alert",
            operation="search",
            selector_keys=(
                "company_id,type,severity,asset_name,asset_key,asset_tag,"
                "is_muted,is_dismissed,page_number,page_size"
            ),
            fact_hints=(
                "BackupIQ alert backup missing not completed severity muted dismissed "
                "asset job conditional helix"
            ),
        ),
    )


def backup_net_provider(now: datetime, *, enabled: bool) -> ExecutionProvider:
    return ExecutionProvider(
        provider_id=BACKUP_NET_PROVIDER,
        display_name="UniView Backup.net Public API",
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
        capabilities=frozenset(_BACKUP_CAPABILITIES),
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
                "UniView is AOT's provider-native source for Endpoint Backup "
                "asset, backup, and BackupIQ evidence."
            ),
            review_interval_days=90,
            last_reviewed_at=now,
            retirement_criteria=(
                "UniView is no longer AOT's approved backup telemetry source.",
                "A replacement satisfies the canonical backup contracts.",
            ),
            vendor_change_sources=(
                "Kaseya UniView Public API documentation",
                "Kaseya Backup Portal authentication documentation",
            ),
            operational_owner="AOT Managed Services",
            approval_owner="Jason Architecture Authority",
        ),
        created_at=now,
        metadata={
            "connector_id": BACKUP_NET_PROVIDER,
            "resource_authority": "endpoint_backup",
            "live_enablement": (
                "enabled" if enabled else "blocked_pending_credentials_and_boundaries"
            ),
        },
    )


def register_backup_resource_foundation(
    *,
    capabilities: CapabilityRegistryService,
    providers: ExecutionProviderRegistryService,
    now: datetime,
    enabled: bool,
) -> None:
    for capability in backup_capabilities(now):
        capabilities.register(capability)
    providers.register(backup_net_provider(now, enabled=enabled))
