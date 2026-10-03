from __future__ import annotations

from dataclasses import replace

from jason_runtime.composition import RuntimeSettings
from jason_runtime.maintenance_process import (
    auxiliary_maintenance_runtime_settings,
    autonomy_maintenance_enabled,
    http_runtime_settings,
    ticket_worker_runtime_settings,
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


def test_ticket_worker_runtime_settings_isolate_operational_worker(monkeypatch):
    monkeypatch.setenv("JASON_OLLAMA_MODEL", "qwen3:1.7b")
    monkeypatch.setenv("JASON_AUTONOMY_WORKER_ENABLED", "true")
    monkeypatch.setenv("JASON_AUTONOMY_SHADOW_ENABLED", "true")
    monkeypatch.setenv("JASON_PLAYBOOK_AUTONOMY_REVIEW_ENABLED", "true")
    monkeypatch.setenv("JASON_SUPPORT_REPAIR_AUTONOMY_ENABLED", "true")
    settings = RuntimeSettings.from_env()

    isolated = ticket_worker_runtime_settings(settings)

    assert isolated.autonomy_worker_enabled is True
    assert isolated.autonomy_shadow_enabled is False
    assert isolated.autonomy_review_enabled is False
    assert isolated.support_repair_autonomy_enabled is False
    assert isolated.autonomy_worker_db == settings.autonomy_worker_db


def test_auxiliary_runtime_settings_exclude_ticket_worker(monkeypatch):
    monkeypatch.setenv("JASON_OLLAMA_MODEL", "qwen3:1.7b")
    monkeypatch.setenv("JASON_AUTONOMY_WORKER_ENABLED", "true")
    monkeypatch.setenv("JASON_AUTONOMY_SHADOW_ENABLED", "true")
    monkeypatch.setenv("JASON_PLAYBOOK_AUTONOMY_REVIEW_ENABLED", "true")
    monkeypatch.setenv("JASON_SUPPORT_REPAIR_AUTONOMY_ENABLED", "true")
    settings = RuntimeSettings.from_env()

    auxiliary = auxiliary_maintenance_runtime_settings(settings)

    assert auxiliary.autonomy_worker_enabled is False
    assert auxiliary.autonomy_shadow_enabled is True
    assert auxiliary.autonomy_review_enabled is True
    assert auxiliary.support_repair_autonomy_enabled is True
