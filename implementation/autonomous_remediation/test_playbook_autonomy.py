from copy import deepcopy

from .playbook_autonomy import evaluate_autonomous_playbook


def approved_registry():
    return {
        "schema_version": 2,
        "autonomy": {"global_enabled": True, "default": "deny"},
        "playbooks": [
            {
                "id": "disk_space_alert",
                "version": "1.0.0",
                "enabled": True,
                "autonomy": {
                    "mode": "approved_autonomous",
                    "approval_status": "approved",
                    "approved_version": "1.0.0",
                    "approved_source_sha256": "abc123",
                    "approved_by": "idn_al",
                    "approved_at": "2026-09-21T14:00:00Z",
                    "allowed_capabilities": ["automation.component.execute"],
                    "maximum_targets": 1,
                },
            }
        ],
    }


def evaluate(registry):
    return evaluate_autonomous_playbook(
        registry,
        playbook_id="disk_space_alert",
        playbook_version="1.0.0",
        source_hash="abc123",
        capability="automation.component.execute",
        target_count=1,
    )


def test_all_matching_gates_allow():
    result = evaluate(approved_registry())
    assert result.allowed is True
    assert result.reason == "approved_autonomous_playbook"


def test_global_off_denies():
    registry = approved_registry()
    registry["autonomy"]["global_enabled"] = False
    assert evaluate(registry).reason == "global_autonomy_disabled"


def test_version_change_invalidates_approval():
    registry = approved_registry()
    registry["playbooks"][0]["version"] = "1.0.1"
    assert evaluate(registry).reason == "playbook_version_mismatch"


def test_source_change_invalidates_approval():
    registry = approved_registry()
    registry["playbooks"][0]["autonomy"]["approved_source_sha256"] = "changed"
    assert evaluate(registry).reason == "approved_source_hash_mismatch"


def test_unapproved_capability_denies():
    registry = approved_registry()
    registry["playbooks"][0]["autonomy"]["allowed_capabilities"] = ["service.ticket.note.create"]
    assert evaluate(registry).reason == "capability_not_in_playbook_autonomy_scope"


def test_blast_radius_limit_denies():
    registry = approved_registry()
    result = evaluate_autonomous_playbook(
        registry,
        playbook_id="disk_space_alert",
        playbook_version="1.0.0",
        source_hash="abc123",
        capability="automation.component.execute",
        target_count=2,
    )
    assert result.reason == "target_count_exceeds_playbook_scope"


def test_missing_autonomy_metadata_fails_closed():
    registry = approved_registry()
    del registry["playbooks"][0]["autonomy"]
    assert evaluate(registry).reason == "playbook_autonomy_policy_missing"


def test_disabled_playbook_denies():
    registry = approved_registry()
    registry["playbooks"][0]["enabled"] = False
    assert evaluate(registry).reason == "playbook_disabled"
