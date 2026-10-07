from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path


def load_exporter():
    path = Path(__file__).resolve().parents[1] / "operations_configuration_exporter.py"
    spec = importlib.util.spec_from_file_location("jason_operations_configuration_exporter", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_runtime_environment_exports_only_allowlisted_setting(monkeypatch):
    module = load_exporter()
    payload = json.dumps(
        [
            "JASON_AUTONOMY_MAX_ACTIVE_WORK_ITEMS=2",
            "JASON_PROVIDER_SECRET=do-not-export",
            "PASSWORD=do-not-export",
        ]
    )

    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            args=[], returncode=0, stdout=payload, stderr=""
        ),
    )
    result = module.runtime_environment()
    assert result == {"JASON_AUTONOMY_MAX_ACTIVE_WORK_ITEMS": "2"}
    assert "do-not-export" not in json.dumps(result)


def test_runtime_environment_fails_closed_on_bad_docker_output(monkeypatch):
    module = load_exporter()
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="denied"
        ),
    )
    assert module.runtime_environment() == {}


def test_render_metrics_delegates_to_bounded_control_panel_metrics(monkeypatch):
    module = load_exporter()
    monkeypatch.setattr(module, "runtime_environment", lambda: {"JASON_AUTONOMY_MAX_ACTIVE_WORK_ITEMS": "2"})
    monkeypatch.setattr(
        module,
        "render_operations_metrics",
        lambda repo, records, env: [
            'jason_system_configuration_info{setting="autonomy.max_active_work_items",value="2",source="runtime",change_mode="governed_runtime_change"} 1',
            'jason_release_migration_info{release_id="r",source_revision="s",rollback_revision="x",state="development",blocker_class="none"} 1',
        ],
    )
    metrics = module.render_metrics()
    assert 'jason_system_configuration_info{setting="autonomy.max_active_work_items"' in metrics
    assert 'jason_release_migration_info{release_id="r"' in metrics
    assert 'jason_operations_configuration_exporter_build_info{version="1"} 1' in metrics
