from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path


def load_module():
    path = Path(__file__).resolve().parents[1] / "operations_configuration_metrics.py"
    spec = importlib.util.spec_from_file_location("operations_configuration_metrics_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def completed(stdout: str, returncode: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr="")


def test_scheduled_tasks_combines_system_and_user_timers(monkeypatch):
    module = load_module()

    system_payload = json.dumps([
        {
            "next": 1791378629000000,
            "last": 1791377659000000,
            "unit": "jason-provider-health-canary.timer",
            "activates": "jason-provider-health-canary.service",
        },
        {
            "next": 1791379000000000,
            "last": 1791378000000000,
            "unit": "apt-daily.timer",
            "activates": "apt-daily.service",
        },
    ])
    user_payload = json.dumps([
        {
            "next": 1791378600000000,
            "last": 1791378300000000,
            "unit": "jason-release-manager.timer",
            "activates": "jason-release-manager.service",
        }
    ])

    def fake_run(args, *, user_scope=False, timeout=3.0):
        if "list-timers" in args:
            return completed(user_payload if user_scope else system_payload)
        if "show" in args and user_scope:
            return completed("Result=success\nId=jason-release-manager.service\n")
        if "show" in args:
            return completed("Result=failed\nId=jason-provider-health-canary.service\n")
        raise AssertionError(args)

    monkeypatch.setattr(module, "_run", fake_run)
    rows = module.scheduled_tasks()
    assert [row["unit"] for row in rows] == [
        "jason-provider-health-canary.timer",
        "jason-release-manager.timer",
    ]
    assert rows[0]["scope"] == "system"
    assert rows[0]["last_result"] == "failed"
    assert rows[1]["scope"] == "user"
    assert rows[1]["last_result"] == "success"
    assert rows[1]["next"] == 1791378600.0


def test_configuration_rows_are_curated_and_secret_safe(tmp_path):
    module = load_module()
    config = tmp_path / "config"
    config.mkdir()
    (config / "release-manager-policy.json").write_text(
        json.dumps(
            {
                "schedule": {
                    "automatic_promotion_enabled": True,
                    "reconcile_interval_minutes": 5,
                    "max_concurrent_releases": 1,
                },
                "production": {"protected_core_requires_owner_approval": True},
            }
        ),
        encoding="utf-8",
    )
    (config / "development-release-coordinator.json").write_text(
        json.dumps(
            {
                "support_autonomy": {"max_active_items": 2},
                "todo_autonomy": {"max_active_items": 1},
                "integration_automation": {"max_prs_per_run": 3},
            }
        ),
        encoding="utf-8",
    )
    rows = module.configuration_rows(
        tmp_path,
        {"JASON_AUTONOMY_MAX_ACTIVE_WORK_ITEMS": "2", "SECRET": "never-export"},
    )
    by_name = {row["setting"]: row for row in rows}
    assert by_name["autonomy.max_active_work_items"]["value"] == "2"
    assert by_name["release.automatic_promotion_enabled"]["value"] == "true"
    assert by_name["support.max_active_items"]["value"] == "2"
    assert by_name["todo.max_active_items"]["value"] == "1"
    assert "SECRET" not in json.dumps(rows)
    assert "never-export" not in json.dumps(rows)


def test_release_migrations_show_real_stage_and_bounded_blocker(tmp_path):
    module = load_module()
    records = tmp_path / "records"
    records.mkdir()
    failed = {
        "release_id": "release-bbbbbbbbbbbbbbbb",
        "state": "failed",
        "updated_at": "2026-10-07T12:03:03+00:00",
        "rollback_sha": "a" * 40,
        "development": {"source_sha": "b" * 40},
        "failure": {
            "message": "host reconciliation failed: developer checkout dependency",
            "rollback_verified": False,
        },
    }
    closed = {
        "release_id": "release-cccccccccccccccc",
        "state": "closed",
        "updated_at": "2026-10-07T10:54:13+00:00",
        "rollback_sha": "b" * 40,
        "production": {"live_sha": "c" * 40, "alignment_verified": True},
    }
    (records / "release-failed.json").write_text(json.dumps(failed), encoding="utf-8")
    (records / "release-closed.json").write_text(json.dumps(closed), encoding="utf-8")
    rows = module.release_migrations(records)
    by_id = {row["release_id"]: row for row in rows}
    assert by_id["release-bbbbbbbbbbbbbbbb"]["state"] == "failed"
    assert by_id["release-bbbbbbbbbbbbbbbb"]["blocker_class"] == "host_reconciliation"
    assert by_id["release-bbbbbbbbbbbbbbbb"]["rollback_verified"] == 0
    assert by_id["release-cccccccccccccccc"]["state"] == "closed"
    assert by_id["release-cccccccccccccccc"]["verified"] == 1


def test_render_metrics_contains_scheduled_configuration_and_migration_contracts(monkeypatch, tmp_path):
    module = load_module()
    config = tmp_path / "config"
    records = tmp_path / "records"
    config.mkdir()
    records.mkdir()
    (config / "release-manager-policy.json").write_text(
        json.dumps({"schedule": {"automatic_promotion_enabled": True}}), encoding="utf-8"
    )
    (config / "development-release-coordinator.json").write_text("{}", encoding="utf-8")
    (records / "release-test.json").write_text(
        json.dumps(
            {
                "release_id": "release-test",
                "state": "production_eligible",
                "updated_at": "2026-10-07T12:00:00+00:00",
                "development": {"source_sha": "d" * 40},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        module,
        "scheduled_tasks",
        lambda: [
            {
                "unit": "jason-release-manager.timer",
                "service": "jason-release-manager.service",
                "scope": "user",
                "description": "Promote releases",
                "next": 100.0,
                "last": 50.0,
                "last_result": "success",
            }
        ],
    )
    metrics = "\n".join(module.render_metrics(tmp_path, records, {"JASON_AUTONOMY_MAX_ACTIVE_WORK_ITEMS": "2"}))
    assert 'jason_scheduled_task_info{unit="jason-release-manager.timer"' in metrics
    assert 'jason_system_configuration_info{setting="autonomy.max_active_work_items",value="2"' in metrics
    assert 'jason_release_migration_info{release_id="release-test",source_revision="' in metrics
    assert 'state="production_eligible",blocker_class="none"' in metrics
    assert "password" not in metrics.casefold()
