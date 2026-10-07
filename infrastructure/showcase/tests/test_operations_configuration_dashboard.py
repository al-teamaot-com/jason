from __future__ import annotations

import json
from pathlib import Path


def load_dashboard():
    path = Path(__file__).resolve().parents[1] / "grafana" / "dashboards" / "jason-operations-configuration.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_control_panel_keeps_stable_uid_and_adds_migration_visibility():
    dashboard = load_dashboard()
    assert dashboard["uid"] == "jason-operations-configuration"
    assert dashboard["title"] == "Jason Control Panel — Operations & Configuration"
    panels = {panel["id"]: panel for panel in dashboard["panels"]}
    assert panels[9]["title"] == "Migration & Upgrade Status — Recent Releases"
    assert panels[9]["targets"][0]["expr"] == "jason_release_migration_info"
    assert panels[10]["targets"][0]["expr"] == "jason_release_migration_verified"
    assert panels[11]["targets"][0]["expr"] == "jason_release_migration_rollback_verified"
    assert panels[12]["targets"][0]["expr"] == "jason_release_migration_updated_timestamp_seconds * 1000"


def test_control_panel_uses_authoritative_timer_and_config_metrics():
    dashboard = load_dashboard()
    panels = {panel["id"]: panel for panel in dashboard["panels"]}
    assert panels[2]["targets"][0]["expr"] == "jason_scheduled_task_info"
    assert panels[3]["targets"][0]["expr"] == "jason_scheduled_task_next_run_timestamp_seconds * 1000"
    assert panels[4]["targets"][0]["expr"] == "jason_scheduled_task_last_run_timestamp_seconds * 1000"
    assert panels[6]["targets"][0]["expr"] == "jason_system_configuration_info"
    intro = panels[1]["options"]["content"]
    assert "Component Control" in intro
    assert "Playbook Control" in intro
    assert "Credential Management" in intro
    assert "percentage" not in panels[9]["description"].casefold() or "synthetic completion percentage" in panels[9]["description"].casefold()
