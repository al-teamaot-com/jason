from __future__ import annotations

from dataclasses import replace

import pytest

from jason_runtime.composition import RuntimeSettings


def _settings(tmp_path):
    return RuntimeSettings(
        authority_db=tmp_path / "authority.sqlite3",
        bindings_db=tmp_path / "bindings.sqlite3",
        continuation_db=tmp_path / "continuation.sqlite3",
        replay_db=tmp_path / "replay.sqlite3",
        security_audit_db=tmp_path / "security.sqlite3",
        orchestration_events_db=tmp_path / "events.sqlite3",
        trusted_keys_registry=tmp_path / "trusted.json",
        openbao_url="http://openbao:8200",
        openbao_role_id_path=tmp_path / "role_id",
        openbao_secret_id_path=tmp_path / "secret_id",
        ollama_url="http://ollama:11434",
        ollama_model="test-model",
        allowed_machine_identities=frozenset({"svc-openclaw-gateway"}),
    )


def test_autonomy_shadow_is_disabled_by_default(tmp_path):
    settings = _settings(tmp_path)
    assert settings.autonomy_shadow_enabled is False
    assert settings.autonomy_max_active_work_items == 2
    assert settings.autonomy_shadow_interval_seconds == 1800
    assert settings.autonomy_shadow_failure_retry_seconds == 300
    assert settings.autonomy_targeted_wake_retry_seconds == 300
    assert settings.autonomy_targeted_wake_db.name == "autonomy-targeted-wakes.sqlite3"
    assert settings.autonomy_owned_autotask_resource_ids == ()


@pytest.mark.parametrize("value", [0, 101])
def test_active_work_limit_is_bounded(tmp_path, value):
    settings = replace(
        _settings(tmp_path),
        autonomy_max_active_work_items=value,
    )
    with pytest.raises(ValueError):
        settings.validate()


def test_failure_retry_cannot_exceed_shadow_interval(tmp_path):
    settings = replace(
        _settings(tmp_path),
        autonomy_shadow_interval_seconds=300,
        autonomy_shadow_failure_retry_seconds=301,
    )
    with pytest.raises(ValueError):
        settings.validate()


def test_targeted_wake_retry_is_bounded(tmp_path):
    settings = replace(
        _settings(tmp_path),
        autonomy_targeted_wake_retry_seconds=59,
    )
    with pytest.raises(ValueError):
        settings.validate()
