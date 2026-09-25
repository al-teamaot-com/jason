import json

from .playbook_catalog import AutonomyActivation, PlaybookCatalog


def write(tmp_path, payload):
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_missing_autonomy_metadata_fails_closed_to_disabled(tmp_path):
    catalog = PlaybookCatalog.load(write(tmp_path, {
        "schema_version": 1,
        "playbooks": [{
            "id": "old",
            "name": "Old",
            "version": "1.0.0",
            "lifecycle": "production",
            "enabled": True,
            "source": "x",
        }],
    }))
    entry = catalog.get("old")
    assert entry.autonomy_activation is AutonomyActivation.DISABLED
    assert not entry.standing_authority_active


def test_shadow_playbook_can_investigate_but_has_no_standing_authority(tmp_path):
    catalog = PlaybookCatalog.load(write(tmp_path, {
        "schema_version": 2,
        "playbooks": [{
            "id": "pb",
            "name": "PB",
            "version": "1.0.0",
            "lifecycle": "production",
            "enabled": True,
            "source": "x",
            "autonomy": {"activation": "shadow"},
        }],
    }))
    entry = catalog.get("pb")
    assert entry.investigation_enabled
    assert not entry.standing_authority_active


def test_autonomous_playbook_allows_only_explicit_capabilities(tmp_path):
    catalog = PlaybookCatalog.load(write(tmp_path, {
        "schema_version": 2,
        "playbooks": [{
            "id": "pb",
            "name": "PB",
            "version": "1.0.0",
            "lifecycle": "production",
            "enabled": True,
            "source": "x",
            "autonomy": {
                "activation": "autonomous",
                "allowed_capabilities": ["service.ticket.update"],
            },
        }],
    }))
    entry = catalog.get("pb")
    assert entry.standing_authority_active
    assert entry.capability_allowed("service.ticket.update")
    assert not entry.capability_allowed("automation.component.execute")


def test_suspended_playbook_has_no_investigation_or_execution(tmp_path):
    catalog = PlaybookCatalog.load(write(tmp_path, {
        "schema_version": 2,
        "playbooks": [{
            "id": "pb",
            "name": "PB",
            "version": "1.0.0",
            "lifecycle": "production",
            "enabled": True,
            "source": "x",
            "autonomy": {"activation": "suspended"},
        }],
    }))
    entry = catalog.get("pb")
    assert not entry.investigation_enabled
    assert not entry.standing_authority_active
