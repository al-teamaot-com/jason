from datetime import datetime, timezone

from kernel.capabilities import CapabilityLifecycle, CapabilityRisk
from orchestrator.engineering_migration_capability import (
    ENGINEERING_MIGRATION_ACTIVATE, migration_capability,
)


def test_migration_stays_building_and_owner_teams_approval_required():
    capability = migration_capability(datetime(2026, 11, 9, tzinfo=timezone.utc))
    assert capability.capability_name == ENGINEERING_MIGRATION_ACTIVATE
    assert capability.lifecycle_status is CapabilityLifecycle.BUILDING
    assert capability.risk_level is CapabilityRisk.CRITICAL
    assert capability.approval.required
    assert "owner" in capability.approval.approver_classes
    assert capability.maximum_attempts == 1
    assert capability.idempotency_key_required
    assert capability.metadata["approval_channel"] == "microsoft_teams"
    assert capability.metadata["live_enablement"] == "source_only_not_registered"


def test_migration_requires_real_signed_identity_and_continuity_evidence():
    capability = migration_capability(datetime(2026, 11, 9, tzinfo=timezone.utc))
    requirements = " ".join(capability.evidence.requirements).lower()
    verification = " ".join(capability.evidence.verification_requirements).lower()
    assert "teams" in requirements
    assert "continuity" in requirements
    assert "signed teams" in verification
    assert "rollback" in verification
    assert "two independent" in verification
