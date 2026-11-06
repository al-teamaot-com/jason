from dataclasses import replace
import json
import time
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pm_v2.config import load_config
from pm_v2.health import self_test
from pm_v2.store import PMV2Store
import production_drift_guard as drift_guard


ROOT = Path(__file__).resolve().parents[2]
UNIT = "jason-pm-v2-shadow.service"


class PMV2ProductionSafetyTests(unittest.TestCase):
    def test_shadow_unit_is_temporarily_deferred_for_teams_delivery_repair(self):
        policy = json.loads((ROOT / "config/production-desired-state.json").read_text())
        # The protected-core bootstrap is live, but the first normal Teams
        # approval request exposed a legacy-owner binding delivery defect. The
        # repair release must not activate PM V2 shadow at the same time; after
        # delivery is repaired, a fresh exact release re-adds this optional unit.
        self.assertNotIn(UNIT, policy["allowed_user_units"])
        self.assertNotIn(UNIT, policy["required_user_units"])
        unit = ROOT / "infrastructure/openclaw-operations/systemd/user" / UNIT
        text = unit.read_text()
        self.assertIn("/home/al/.local/lib/jason/engineering-worker-source", text)
        self.assertNotIn("/home/al/projects/jason", text)
        self.assertIn("ReadWritePaths=/var/lib/jason/pm-v2 /var/lib/jason/openclaw/pm-v2", text)
        migration = (ROOT / "tools/protected_root_policy_migration.py").read_text()
        self.assertIn('APPROVED_PM_V2_SHADOW_DELTA', migration)
        self.assertIn('frozenset({"jason-pm-v2-shadow.service"})', migration)
        reconcile = (ROOT / "tools/reconcile_production_host_services.sh").read_text()
        self.assertIn('PM_V2_SHADOW_DECLARED=', reconcile)
        self.assertIn('JASON_PM_V2_SHADOW_RECONCILIATION=PASS', reconcile)

    def test_declared_shadow_unit_does_not_trigger_undeclared_drift(self):
        policy = json.loads((ROOT / "config/production-desired-state.json").read_text())
        system_units = set(policy["required_system_units"]) | set(policy["allowed_system_units"])
        user_units = set(policy["required_user_units"]) | set(policy["allowed_user_units"])
        with (
            patch.object(drift_guard, "unit_names", side_effect=[system_units, user_units]),
            patch.object(drift_guard, "active_state", return_value="active"),
            patch.object(drift_guard, "unit_properties", return_value={
                "ExecStart": "/home/al/.local/lib/jason/engineering-worker-source/tools/approved.py",
                "WorkingDirectory": "/home/al/.local/lib/jason/engineering-worker-source",
            }),
            patch.object(drift_guard, "running_containers", return_value=set(policy["required_containers"])),
            patch.object(drift_guard, "stopped_rollback_containers", return_value=[]),
        ):
            report = drift_guard.evaluate(policy)
        undeclared = [
            item for item in report["problems"]
            if item["kind"] == "undeclared_installed_user_unit"
        ]
        self.assertEqual(undeclared, [])

    def test_pm_v2_health_fails_closed_on_protected_production_drift(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            drift = root / "production-drift.json"
            drift.write_text(json.dumps({
                "schema_version": "1.0",
                "status": "pass",
                "problems": [],
            }))
            config = load_config(ROOT / "config/pm-v2.json", repo=ROOT)
            config = replace(
                config,
                database_path=root / "pm-v2.sqlite3",
                production_drift_readback_path=drift,
                production_drift_maximum_age_seconds=90,
            )
            store = PMV2Store(config.database_path)
            healthy = self_test(config=config, store=store, repo=ROOT)
            self.assertEqual(healthy["status"], "healthy")
            self.assertTrue(healthy["checks"]["production_drift"]["ok"])

            drift.write_text(json.dumps({
                "schema_version": "1.0",
                "status": "drift_detected",
                "problems": [{
                    "kind": "undeclared_installed_user_unit",
                    "unit": UNIT,
                    "state": "active",
                }],
            }))
            degraded = self_test(config=config, store=store, repo=ROOT)
            self.assertEqual(degraded["status"], "degraded")
            self.assertFalse(degraded["checks"]["production_drift"]["ok"])
            self.assertEqual(
                degraded["checks"]["production_drift"]["problem_kinds"],
                ["undeclared_installed_user_unit"],
            )

    def test_pm_v2_health_rejects_stale_drift_readback(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            drift = root / "production-drift.json"
            drift.write_text(json.dumps({"schema_version": "1.0", "status": "pass", "problems": []}))
            old = time.time() - 120
            __import__("os").utime(drift, (old, old))
            config = load_config(ROOT / "config/pm-v2.json", repo=ROOT)
            config = replace(
                config,
                database_path=root / "pm-v2.sqlite3",
                production_drift_readback_path=drift,
                production_drift_maximum_age_seconds=90,
            )
            result = self_test(config=config, store=PMV2Store(config.database_path), repo=ROOT)
            self.assertEqual(result["status"], "degraded")
            self.assertFalse(result["checks"]["production_drift"]["ok"])
