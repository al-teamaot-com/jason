from datetime import datetime, timezone

from kernel.capabilities import CapabilityLifecycle
from orchestrator.constant_contact_import_capability import (
    MARKETING_CONTACT_IMPORT, import_capability,
)


def test_import_is_building_and_requires_verified_owner_approval():
    c = import_capability(datetime(2026, 11, 9, tzinfo=timezone.utc))
    assert c.capability_name == MARKETING_CONTACT_IMPORT
    assert c.lifecycle_status is CapabilityLifecycle.BUILDING
    assert c.approval.required
    assert "owner" in c.approval.approver_classes
    assert c.maximum_attempts == 1
    assert c.idempotency_key_required
    assert c.metadata["read_only"] == "false"
    assert c.metadata["approval_channel"] == "canonical_verified_owner"
