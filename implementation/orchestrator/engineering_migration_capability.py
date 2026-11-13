"""Source-only canonical migration action contract; NOT live registry admission.

The existing native Release Manager still owns exact-SHA production release,
installation and rollback. This capability represents a separately reviewable
engineering-worker migration and can only become PILOT after a governed release
with identity, Teams and native cutover acceptance. It is not self-enabling.
"""
from __future__ import annotations

from datetime import datetime

from kernel.capabilities import (
    CapabilityApproval, CapabilityDefinition, CapabilityEvidence,
    CapabilityLifecycle, CapabilityRisk, CapabilityStewardship,
    IdempotencyBehavior,
)
from .contracts import OrchestrationMode

ENGINEERING_MIGRATION_ACTIVATE = "engineering.migration.activate"


def migration_capability(now: datetime) -> CapabilityDefinition:
    return CapabilityDefinition(
        capability_name=ENGINEERING_MIGRATION_ACTIVATE,
        version="1.0",
        display_name="Activate Exact Independent Engineering Migration",
        lifecycle_status=CapabilityLifecycle.BUILDING,
        business_purpose=(
            "Approve one immutable PMV3 independent engineering worker cutover "
            "through signed Teams evidence and native release controls."
        ),
        owner_service="Project Jason Engineering Governance",
        architectural_capability_ids=frozenset({"JAC-005", "JAC-006", "JAC-013"}),
        risk_level=CapabilityRisk.CRITICAL,
        data_classifications=frozenset({"internal"}),
        permitted_execution_modes=frozenset({"deterministic"}),
        input_schema_reference="schema://jason/engineering-migration-activate/1.0",
        output_schema_reference="schema://jason/engineering-migration-activate-result/1.0",
        invoking_roles=frozenset({"orchestrator"}),
        approval=CapabilityApproval(required=True, approver_classes=("owner",)),
        evidence=CapabilityEvidence(
            required=True,
            requirements=(
                "exact reviewed candidate SHA, rollback SHA and complete scope digest",
                "independently verified migration and ticket-continuity evidence",
                "separately authenticated authorized Teams Owner",
                "unmodified preexisting production freeze and incident holds",
            ),
            verification_requirements=(
                "valid original signed Teams decision and no replay",
                "native PMV3 release record production-eligible",
                "single native production transaction and exact rollback identity",
                "legacy monolithic worker remains paused",
                "no duplicate support or ticket claims",
                "two independent post-migration acceptance cycles",
                "automatic promotion hold and original freeze retained",
            ),
        ),
        dependencies=frozenset({"identity.authorization.resolve", "governance.action.evaluate"}),
        idempotency_behavior=IdempotencyBehavior.IDEMPOTENT,
        idempotency_key_required=True,
        timeout_seconds=60,
        maximum_attempts=1,
        failure_behavior=(
            "Fail closed; no manual pause removal, direct systemd enable, unsigned "
            "chat approval, recipient fallback, or automatic resubmission."
        ),
        tenant_isolation_required=True,
        client_isolation_required=False,
        stewardship=CapabilityStewardship(
            steward="technology-steward",
            business_justification="Ensure exact Teams authority before controlled worker migration.",
            review_interval_days=30,
            retirement_criteria=("Independent engineering migration is completed and verified",),
            authoritative_change_sources=(
                "Project Jason Governance Handbook",
                "Project Jason Issue #2300",
            ),
        ),
        created_at=now,
        metadata={
            "provider_neutral": "true",
            "read_only": "false",
            "write_capability": "true",
            "resource_types": "jason_engineering_migration",
            "operation": "activate",
            "selector_keys": "candidate_sha,rollback_sha,reviewed_scope_sha256,continuity_evidence_sha256,migration_phase",
            "approval_channel": "microsoft_teams",
            "live_enablement": "source_only_not_registered",
            "migration_phase": "independent_engineering_lanes",
        },
    )
