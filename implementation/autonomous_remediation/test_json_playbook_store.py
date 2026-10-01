import json

import pytest

from .playbook_store import SQLitePlaybookRegistry
from .test_json_playbook_document import sample


def test_registry_stages_activates_and_hot_swaps_without_process_reload(tmp_path):
    store = SQLitePlaybookRegistry(tmp_path / "playbooks.sqlite3")
    first = sample()
    staged = store.stage(first, actor="tech-a")
    assert staged.state == "draft"
    generation_after_stage = store.generation()

    active = store.activate(
        staged.document.playbook_id,
        staged.document.version,
        actor="owner-a",
        expected_fingerprint=staged.document.fingerprint,
    )
    assert active.state == "active"
    generation_after_activate = store.generation()
    assert generation_after_activate > generation_after_stage

    second = sample()
    second["playbook"]["version"] = "1.1.0"
    second["expected_state"]["service"] = "running-and-stable"
    staged_second = store.stage(second, actor="tech-a")
    promoted = store.activate(
        staged_second.document.playbook_id,
        staged_second.document.version,
        actor="owner-a",
    )
    assert promoted.document.version == "1.1.0"
    assert store.active("sample_service_repair").document.version == "1.1.0"
    assert store.get("sample_service_repair", "1.0.0").state == "retired"


def test_same_version_is_immutable(tmp_path):
    store = SQLitePlaybookRegistry(tmp_path / "playbooks.sqlite3")
    payload = sample()
    store.stage(payload, actor="tech-a")
    changed = sample()
    changed["expected_state"]["service"] = "different"
    with pytest.raises(ValueError, match="PLAYBOOK_VERSION_IMMUTABLE"):
        store.stage(changed, actor="tech-a")


def test_activation_can_bind_exact_validated_fingerprint(tmp_path):
    store = SQLitePlaybookRegistry(tmp_path / "playbooks.sqlite3")
    staged = store.stage(sample(), actor="tech-a")
    with pytest.raises(ValueError, match="PLAYBOOK_ACTIVATION_FINGERPRINT_MISMATCH"):
        store.activate(
            staged.document.playbook_id,
            staged.document.version,
            actor="owner-a",
            expected_fingerprint="0" * 64,
        )
