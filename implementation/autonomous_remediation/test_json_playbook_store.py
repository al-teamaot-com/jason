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


def test_lifecycle_receipts_and_generation_are_durable_and_idempotent(tmp_path):
    path = tmp_path / "runbook-registry.sqlite3"
    store = SQLitePlaybookRegistry(path)
    payload = sample()
    stage = store.stage(payload, actor="tech-with-existing-identity")
    store.stage(payload, actor="tech-with-existing-identity")
    assert store.generation() == 1  # duplicate stage creates no new receipt
    active = store.activate(stage.document.playbook_id, stage.document.version,
                            actor="verified-owner", expected_fingerprint=stage.document.fingerprint)
    store.activate(stage.document.playbook_id, stage.document.version, actor="verified-owner")
    assert store.generation() == 2
    assert store.retire(stage.document.playbook_id, actor="verified-owner")
    assert store.retire(stage.document.playbook_id, actor="verified-owner") is False
    assert store.generation() == 3
    events = store.lifecycle_events()
    assert [event["event_type"] for event in events] == ["staged", "activated", "retired"]
    assert [event["generation_before"] for event in events] == [0, 1, 2]
    assert [event["generation_after"] for event in events] == [1, 2, 3]
    assert [event["fingerprint"] for event in events] == [active.document.fingerprint] * 3
    store.close()
    reopened = SQLitePlaybookRegistry(path)
    assert reopened.generation() == 3
    assert reopened.lifecycle_events() == events
    assert reopened.get(stage.document.playbook_id, stage.document.version).state == "retired"
    reopened.close()


def test_failed_stage_receipt_rolls_back_version_and_generation(monkeypatch, tmp_path):
    store = SQLitePlaybookRegistry(tmp_path / "runbook-registry.sqlite3")
    def broken_receipt(**kwargs):
        raise RuntimeError("simulated durability failure")
    monkeypatch.setattr(store, "_audit_event", broken_receipt)
    with pytest.raises(RuntimeError, match="durability failure"):
        store.stage(sample(), actor="tech")
    assert store.generation() == 0
    assert store.list_all() == ()
    assert store.lifecycle_events() == ()


def test_failed_activation_receipt_preserves_prior_active_version(monkeypatch, tmp_path):
    store = SQLitePlaybookRegistry(tmp_path / "runbook-registry.sqlite3")
    first = store.stage(sample(), actor="tech")
    store.activate(first.document.playbook_id, first.document.version, actor="owner")
    newer_payload = sample()
    newer_payload["playbook"]["version"] = "1.1.0"
    newer = store.stage(newer_payload, actor="tech")
    generation_before = store.generation()
    receipts_before = store.lifecycle_events()
    def broken_receipt(**kwargs):
        raise RuntimeError("simulated audit write failure")
    monkeypatch.setattr(store, "_audit_event", broken_receipt)
    with pytest.raises(RuntimeError, match="audit write failure"):
        store.activate(newer.document.playbook_id, newer.document.version, actor="owner")
    assert store.active(first.document.playbook_id).document.version == first.document.version
    assert store.get(newer.document.playbook_id, newer.document.version).state == "draft"
    assert store.generation() == generation_before
    assert store.lifecycle_events() == receipts_before


def test_failed_retire_receipt_preserves_active_and_does_not_advance(monkeypatch, tmp_path):
    store = SQLitePlaybookRegistry(tmp_path / "runbook-registry.sqlite3")
    staged = store.stage(sample(), actor="tech")
    store.activate(staged.document.playbook_id, staged.document.version, actor="owner")
    original_generation = store.generation()
    def broken_receipt(**kwargs):
        raise RuntimeError("simulated evidence failure")
    monkeypatch.setattr(store, "_audit_event", broken_receipt)
    with pytest.raises(RuntimeError, match="evidence failure"):
        store.retire(staged.document.playbook_id, actor="owner")
    assert store.active(staged.document.playbook_id).state == "active"
    assert store.generation() == original_generation
    assert len(store.lifecycle_events()) == 2


def test_concurrent_registry_sessions_share_one_versioned_state(tmp_path):
    path = tmp_path / "runbooks.sqlite3"
    a = SQLitePlaybookRegistry(path)
    b = SQLitePlaybookRegistry(path)
    try:
        staged_a = a.stage(sample(), actor="tech")
        staged_b = b.stage(sample(), actor="tech")
        assert staged_a.document.fingerprint == staged_b.document.fingerprint
        assert a.generation() == 1
        b.activate(staged_a.document.playbook_id, staged_a.document.version, actor="owner")
        assert a.generation() == 2
        assert a.active(staged_a.document.playbook_id).document.version == "1.0.0"
    finally:
        a.close()
        b.close()
