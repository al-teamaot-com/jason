"""Dormant reusable group administration capability contract tests."""
from datetime import datetime, timezone

from kernel.capabilities import CapabilityLifecycle, CapabilityRisk, IdempotencyBehavior
from orchestrator.microsoft_group_admin_catalog import microsoft_group_admin_capabilities


def test_microsoft_group_admin_definitions_are_dormant_high_risk_and_bounded():
    defs = microsoft_group_admin_capabilities(now=datetime(2026, 11, 12, tzinfo=timezone.utc))
    assert {x.capability_name for x in defs} == {
        "identity.group.create", "identity.group.member.add",
    }
    assert all(x.lifecycle_status is CapabilityLifecycle.BUILDING for x in defs)
    assert all(x.risk_level is CapabilityRisk.HIGH for x in defs)
    assert all(x.approval.required for x in defs)
    assert all(x.evidence.required for x in defs)
    assert all(x.idempotency_key_required and x.maximum_attempts == 1 for x in defs)
    assert all(x.tenant_isolation_required and x.client_isolation_required for x in defs)
    assert all(x.metadata["mcp_action_enabled"] == "false" for x in defs)
    assert all(x.metadata["activation_state"] == "source_only_not_registered" for x in defs)
    assert defs[0].idempotency_behavior is IdempotencyBehavior.NON_IDEMPOTENT
    assert defs[1].idempotency_behavior is IdempotencyBehavior.CONDITIONALLY_IDEMPOTENT
