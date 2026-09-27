from __future__ import annotations

from datetime import datetime

from kernel.capabilities import (
    CapabilityApproval,
    CapabilityDefinition,
    CapabilityEvidence,
    CapabilityLifecycle,
    CapabilityRisk,
    CapabilityStewardship,
    IdempotencyBehavior,
)
from kernel.execution_providers import (
    ExecutionProvider,
    ProviderApproval,
    ProviderFeatures,
    ProviderHealth,
    ProviderLifecycle,
    ProviderLimits,
    ProviderStewardship,
    ProviderType,
)


LAB_HOST_READ = "lab.host.read"
LAB_VM_READ = "lab.vm.read"
LAB_VM_CREATE = "lab.vm.create"
LAB_VM_START = "lab.vm.start"
LAB_VM_STOP = "lab.vm.stop"
LAB_VM_DELETE = "lab.vm.delete"
LAB_SNAPSHOT_CREATE = "lab.snapshot.create"
LAB_SNAPSHOT_REVERT = "lab.snapshot.revert"
LAB_SNAPSHOT_DELETE = "lab.snapshot.delete"
LAB_BASELINE_RESET = "lab.baseline.reset"
LIBVIRT_LAB_PROVIDER = "libvirt_lab"

LAB_CAPABILITIES = (
    LAB_HOST_READ,
    LAB_VM_READ,
    LAB_VM_CREATE,
    LAB_VM_START,
    LAB_VM_STOP,
    LAB_VM_DELETE,
    LAB_SNAPSHOT_CREATE,
    LAB_SNAPSHOT_REVERT,
    LAB_SNAPSHOT_DELETE,
    LAB_BASELINE_RESET,
)


def _capability(
    *,
    now: datetime,
    name: str,
    display_name: str,
    purpose: str,
    read_only: bool,
    idempotent: bool,
) -> CapabilityDefinition:
    return CapabilityDefinition(
        capability_name=name,
        version="1.0",
        display_name=display_name,
        lifecycle_status=CapabilityLifecycle.BUILDING,
        business_purpose=purpose,
        owner_service="Jason Governed Lab Infrastructure",
        architectural_capability_ids=frozenset({"JAC-005", "JAC-006"}),
        risk_level=CapabilityRisk.LOW if read_only else CapabilityRisk.MEDIUM,
        data_classifications=frozenset({"internal"}),
        permitted_execution_modes=frozenset({"deterministic"}),
        input_schema_reference=f"schema://jason/{name.replace('.', '-')}/1.0",
        output_schema_reference=f"schema://jason/{name.replace('.', '-')}-result/1.0",
        invoking_roles=frozenset({"orchestrator"}),
        approval=CapabilityApproval(
            required=not read_only,
            approver_classes=("owner",) if not read_only else (),
        ),
        evidence=CapabilityEvidence(
            required=True,
            requirements=(
                "approved lab host identity",
                "lab-only scope",
                "provider result",
            ),
            verification_requirements=(
                "no production/client asset scope",
                "fixed resource limits enforced",
                "isolated networking enforced",
            ),
        ),
        dependencies=frozenset(),
        idempotency_behavior=(
            IdempotencyBehavior.IDEMPOTENT
            if idempotent
            else IdempotencyBehavior.CONDITIONALLY_IDEMPOTENT
        ),
        idempotency_key_required=not read_only,
        timeout_seconds=600,
        maximum_attempts=1,
        failure_behavior=(
            "Fail closed without production-host fallback, direct shell bypass, "
            "or authority expansion."
        ),
        tenant_isolation_required=True,
        client_isolation_required=False,
        stewardship=CapabilityStewardship(
            steward="technology-steward",
            business_justification=(
                "Provide a disposable, isolated Windows lab for safe component "
                "and playbook validation."
            ),
            review_interval_days=90,
            retirement_criteria=(
                "The lab provider is no longer approved.",
                "Isolation or reproducibility requirements cannot be met.",
            ),
            authoritative_change_sources=(
                "Project Jason governed lab runbook",
                "approved hypervisor configuration",
            ),
            operational_owner="AOT Managed Services",
            approval_owner="AOT Owner",
        ),
        created_at=now,
        metadata={
            "provider_neutral": "true",
            "read_only": "true" if read_only else "false",
            "lab_only": "true",
            "production_assets_forbidden": "true",
            "client_data_forbidden": "true",
            "isolated_network_required": "true",
            "baseline_snapshot_required": "true",
            "production_domain_join_forbidden": "true",
            "operation": name.rsplit(".", 1)[-1],
        },
    )


def lab_capabilities(now: datetime) -> tuple[CapabilityDefinition, ...]:
    definitions = (
        (LAB_HOST_READ, "Read Lab Host", "Read approved lab-host readiness and capacity.", True, True),
        (LAB_VM_READ, "Read Lab VM", "Read governed lab VM state.", True, True),
        (LAB_VM_CREATE, "Create Lab VM", "Create one bounded disposable lab VM.", False, False),
        (LAB_VM_START, "Start Lab VM", "Start one approved lab VM.", False, True),
        (LAB_VM_STOP, "Stop Lab VM", "Stop one approved lab VM.", False, True),
        (LAB_VM_DELETE, "Delete Lab VM", "Delete one disposable lab VM and storage.", False, True),
        (LAB_SNAPSHOT_CREATE, "Create Lab Snapshot", "Create a reproducible lab VM snapshot.", False, False),
        (LAB_SNAPSHOT_REVERT, "Revert Lab Snapshot", "Revert a lab VM to an approved snapshot.", False, True),
        (LAB_SNAPSHOT_DELETE, "Delete Lab Snapshot", "Delete a lab VM snapshot.", False, True),
        (LAB_BASELINE_RESET, "Reset Lab Baseline", "Reset a lab VM to its known-good baseline.", False, True),
    )
    return tuple(
        _capability(
            now=now,
            name=name,
            display_name=display_name,
            purpose=purpose,
            read_only=read_only,
            idempotent=idempotent,
        )
        for name, display_name, purpose, read_only, idempotent in definitions
    )


def libvirt_lab_provider(now: datetime, *, ready: bool) -> ExecutionProvider:
    return ExecutionProvider(
        provider_id=LIBVIRT_LAB_PROVIDER,
        display_name="Jason Local Libvirt Lab",
        provider_type=ProviderType.DETERMINISTIC,
        lifecycle_status=(
            ProviderLifecycle.AVAILABLE if ready else ProviderLifecycle.PLANNED
        ),
        health_status=(
            ProviderHealth.HEALTHY if ready else ProviderHealth.UNAVAILABLE
        ),
        approval_status=(
            ProviderApproval.PILOT if ready else ProviderApproval.BLOCKED
        ),
        execution_modes=frozenset({"deterministic"}),
        capabilities=frozenset(LAB_CAPABILITIES),
        supported_classifications=frozenset({"internal"}),
        regions=frozenset({"local"}),
        limits=ProviderLimits(
            maximum_concurrent_executions=1,
            maximum_requests_per_minute=10,
            maximum_execution_seconds=600,
        ),
        features=ProviderFeatures(structured_output=True, stateful_sessions=True),
        pricing_profile_id="local-lab",
        stewardship=ProviderStewardship(
            technology_steward="technology-steward",
            business_justification=(
                "Use a local isolated hypervisor for reproducible non-production testing."
            ),
            review_interval_days=90,
            last_reviewed_at=now,
            retirement_criteria=(
                "Host can no longer guarantee lab isolation.",
                "A replacement governed lab provider is approved.",
            ),
            vendor_change_sources=("libvirt", "QEMU", "OVMF", "swtpm"),
            operational_owner="AOT Managed Services",
            approval_owner="Jason Architecture Authority",
        ),
        created_at=now,
        metadata={
            "lab_only": "true",
            "production_authority": "none",
            "activation_gate": "real_windows_11_acceptance_required",
        },
    )
