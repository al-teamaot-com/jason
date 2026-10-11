from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
import logging

import pytest

from jason_runtime.composition import RuntimeSettings
from jason_runtime.maintenance_process import (
    autonomy_maintenance_enabled,
    http_runtime_settings,
    run_autonomy_maintenance_process,
)


def test_autonomy_maintenance_enabled_for_any_runtime_maintenance(monkeypatch):
    monkeypatch.setenv("JASON_OLLAMA_MODEL", "qwen3:1.7b")
    monkeypatch.setenv("JASON_AUTONOMY_WORKER_ENABLED", "false")
    monkeypatch.setenv("JASON_AUTONOMY_SHADOW_ENABLED", "false")
    monkeypatch.setenv("JASON_PLAYBOOK_AUTONOMY_REVIEW_ENABLED", "false")
    settings = RuntimeSettings.from_env()
    assert autonomy_maintenance_enabled(settings) is False
    assert autonomy_maintenance_enabled(replace(settings, autonomy_worker_enabled=True))
    assert autonomy_maintenance_enabled(replace(settings, autonomy_shadow_enabled=True))
    assert autonomy_maintenance_enabled(replace(settings, autonomy_review_enabled=True))
    assert autonomy_maintenance_enabled(replace(settings, support_repair_autonomy_enabled=True))


def test_http_runtime_settings_disable_only_autonomy_maintenance(monkeypatch):
    monkeypatch.setenv("JASON_OLLAMA_MODEL", "qwen3:1.7b")
    monkeypatch.setenv("JASON_AUTONOMY_WORKER_ENABLED", "true")
    monkeypatch.setenv("JASON_AUTONOMY_SHADOW_ENABLED", "true")
    monkeypatch.setenv("JASON_PLAYBOOK_AUTONOMY_REVIEW_ENABLED", "true")
    monkeypatch.setenv("JASON_SUPPORT_REPAIR_AUTONOMY_ENABLED", "true")
    settings = RuntimeSettings.from_env()

    serving = http_runtime_settings(settings)

    assert serving.autonomy_worker_enabled is False
    assert serving.autonomy_shadow_enabled is False
    assert serving.autonomy_review_enabled is False
    assert serving.support_repair_autonomy_enabled is False
    assert serving.authority_db == settings.authority_db
    assert serving.port == settings.port
    assert serving.autonomy_worker_db == settings.autonomy_worker_db


def test_maintenance_failure_is_logged_and_process_retries(monkeypatch, caplog):
    attempts = []

    def tick():
        attempts.append(1)
        if len(attempts) == 1:
            raise RuntimeError("controlled tick failure")
        raise KeyboardInterrupt

    monkeypatch.setattr(
        "jason_runtime.maintenance_process.build_runtime_application",
        lambda settings: SimpleNamespace(maintenance=SimpleNamespace(tick=tick)),
    )
    monkeypatch.setattr("jason_runtime.maintenance_process.time.sleep", lambda seconds: None)

    with caplog.at_level(logging.ERROR), pytest.raises(KeyboardInterrupt):
        run_autonomy_maintenance_process(object())

    assert len(attempts) == 2
    assert "Autonomy maintenance cycle failed" in caplog.text
    assert "controlled tick failure" in caplog.text
    assert "RuntimeError: controlled tick failure" in caplog.text
