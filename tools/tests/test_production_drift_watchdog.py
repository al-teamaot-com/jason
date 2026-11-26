import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GUARD_PATH = ROOT / "tools" / "production_drift_guard.py"
WATCHDOG_PATH = ROOT / "tools" / "production_drift_watchdog.py"

guard_spec = importlib.util.spec_from_file_location("production_drift_guard", GUARD_PATH)
guard = importlib.util.module_from_spec(guard_spec)
assert guard_spec.loader is not None
sys.modules[guard_spec.name] = guard
guard_spec.loader.exec_module(guard)

watchdog_spec = importlib.util.spec_from_file_location("production_drift_watchdog", WATCHDOG_PATH)
watchdog = importlib.util.module_from_spec(watchdog_spec)
assert watchdog_spec.loader is not None
sys.modules[watchdog_spec.name] = watchdog
watchdog_spec.loader.exec_module(watchdog)


class ProductionDriftWatchdogTests(unittest.TestCase):
    def test_optional_documentation_advisory_is_durable_and_never_opens_breaker(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            control = root / "control.json"
            evidence = root / "evidence.json"
            state = root / "watchdog.json"
            control.write_text(json.dumps({
                "schema_version": "1.0", "circuit_breaker": {"state": "closed"}
            }))
            result = {
                "schema_version": "1.0",
                "status": "pass",
                "problems": [],
                "advisories": [{
                    "kind": "independent_optional_system_unit_failed",
                    "unit": "jason-documentation-reconciliation.service",
                    "state": "failed",
                }],
            }
            rc = watchdog.apply_result(result, control_state=control,
                                       evidence=evidence, watchdog_state=state)
            self.assertEqual(rc, 0)
            self.assertEqual(json.loads(state.read_text())["advisory_count"], 1)
            self.assertEqual(json.loads(state.read_text())["circuit_breaker_action"], "none")
            self.assertEqual(len(json.loads(evidence.read_text())["advisories"]), 1)
            self.assertEqual(json.loads(control.read_text())["circuit_breaker"]["state"],
                             "closed")

    def test_drift_opens_breaker_and_preserves_last_known_good(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            control = root / "control.json"
            evidence = root / "evidence.json"
            state = root / "watchdog.json"
            control.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "last_known_good": {
                            "release_id": "release-good",
                            "manifest": {"revision": "a" * 40, "complete": True},
                        },
                        "circuit_breaker": {"state": "closed"},
                    }
                ),
                encoding="utf-8",
            )
            result = {
                "schema_version": "1.0",
                "status": "drift_detected",
                "observed_at": "2026-10-07T20:30:00+00:00",
                "problems": [
                    {"kind": "forbidden_execution_path"},
                    {"kind": "undeclared_running_container"},
                ],
            }
            rc = watchdog.apply_result(
                result,
                control_state=control,
                evidence=evidence,
                watchdog_state=state,
            )
            self.assertEqual(rc, 2)
            payload = json.loads(control.read_text(encoding="utf-8"))
            self.assertEqual(payload["circuit_breaker"]["state"], "open")
            self.assertEqual(
                payload["circuit_breaker"]["source"],
                "production_drift_watchdog",
            )
            self.assertEqual(
                payload["last_known_good"]["release_id"],
                "release-good",
            )
            self.assertEqual(json.loads(state.read_text())["circuit_breaker_action"], "opened")

    def test_control_state_replacement_preserves_existing_file_owner(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            control = root / "control.json"
            evidence = root / "evidence.json"
            state = root / "watchdog.json"
            result = {"status": "drift_detected", "problems": [{"kind": "unexpected_unit"}]}
            control.write_text(json.dumps({"schema_version": "1.0", "circuit_breaker": {"state": "closed"}}))
            evidence.write_text(json.dumps({"schema_version": "1.0", "status": "pass"}))
            original_chown = watchdog.os.chown
            calls = []
            def checked_chown(path, uid, gid):
                calls.append((Path(path), uid, gid))
                original_chown(path, uid, gid)
            with patch.object(watchdog.os, "chown", side_effect=checked_chown):
                rc = watchdog.apply_result(result, control_state=control, evidence=evidence, watchdog_state=state)
            self.assertEqual(rc, 2)
            self.assertEqual(len(calls), 2)
            self.assertTrue(all(call[1:] == (root.stat().st_uid, root.stat().st_gid) for call in calls))
            self.assertEqual(evidence.stat().st_uid, root.stat().st_uid)
            self.assertEqual(control.stat().st_uid, root.stat().st_uid)
            self.assertEqual(control.stat().st_mode & 0o777, 0o600)
            self.assertEqual(json.loads(control.read_text())["circuit_breaker"]["state"], "open")

    def test_clean_result_never_auto_closes_open_breaker(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            control = root / "control.json"
            evidence = root / "evidence.json"
            state = root / "watchdog.json"
            control.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "last_known_good": None,
                        "circuit_breaker": {"state": "open", "reason": "prior drift"},
                    }
                ),
                encoding="utf-8",
            )
            result = {
                "schema_version": "1.0",
                "status": "pass",
                "observed_at": "2026-10-07T20:31:00+00:00",
                "problems": [],
            }
            rc = watchdog.apply_result(
                result,
                control_state=control,
                evidence=evidence,
                watchdog_state=state,
            )
            self.assertEqual(rc, 0)
            payload = json.loads(control.read_text(encoding="utf-8"))
            self.assertEqual(payload["circuit_breaker"]["state"], "open")
            self.assertEqual(json.loads(state.read_text())["circuit_breaker_action"], "none")


if __name__ == "__main__":
    unittest.main()

def test_watchdog_defers_while_production_transaction_is_active(monkeypatch, tmp_path):
    monkeypatch.setattr(watchdog, "production_transaction_active", lambda: True)
    monkeypatch.setattr(sys, "argv", [
        "production_drift_watchdog.py",
        "--config", str(tmp_path / "config.json"),
        "--evidence", str(tmp_path / "evidence.json"),
        "--control-state", str(tmp_path / "control.json"),
        "--watchdog-state", str(tmp_path / "watchdog.json"),
    ])
    rc = watchdog.main()
    assert rc == 0
    data = json.loads((tmp_path / "watchdog.json").read_text())
    assert data["status"] == "deferred"
    assert data["reason"] == "production_transaction_active"
    assert not (tmp_path / "control.json").exists()


def test_evidence_inherits_release_controller_owner(tmp_path):
    import os
    import stat
    control = tmp_path / 'control.json'
    control.write_text(json.dumps({'schema_version':'1.0', 'circuit_breaker':{'state':'open'}}))
    evidence = tmp_path / 'evidence.json'
    watchdog_state = tmp_path / 'watchdog.json'
    result = {'schema_version':'1.0', 'status':'pass', 'observed_at':'2026-10-09T16:32:07+00:00', 'problems':[] }
    assert watchdog.apply_result(result, control_state=control, evidence=evidence, watchdog_state=watchdog_state) == 0
    assert evidence.stat().st_uid == control.stat().st_uid
    assert evidence.stat().st_gid == control.stat().st_gid
    assert stat.S_IMODE(evidence.stat().st_mode) == 0o600
    assert json.loads(control.read_text())['circuit_breaker']['state'] == 'open'


def test_same_open_breaker_keeps_original_incident_timestamp(tmp_path, monkeypatch):
    control = tmp_path / "control.json"
    evidence = tmp_path / "evidence.json"
    state = tmp_path / "watchdog.json"
    control.write_text(json.dumps({
        "schema_version": "1.0",
        "last_known_good": {"release_id": "release-good"},
        "circuit_breaker": {"state": "closed"},
    }))
    result = {
        "schema_version": "1.0",
        "status": "drift_detected",
        "problems": [{"kind": "failed_system_unit",
                      "unit": "jason-openclaw-authority-health.service"}],
    }
    monkeypatch.setattr(watchdog, "now", lambda: "2026-11-13T14:05:00Z")
    assert watchdog.apply_result(result, control_state=control,
                                 evidence=evidence, watchdog_state=state)==2
    first = json.loads(control.read_text())
    assert first["circuit_breaker"]["opened_at"]=="2026-11-13T14:05:00Z"
    monkeypatch.setattr(watchdog, "now", lambda: "2026-11-13T14:06:00Z")
    assert watchdog.apply_result(result, control_state=control,
                                 evidence=evidence, watchdog_state=state)==2
    second = json.loads(control.read_text())
    assert second["circuit_breaker"]["opened_at"]=="2026-11-13T14:05:00Z"
    assert second["circuit_breaker"]["updated_at"]=="2026-11-13T14:06:00Z"
    assert second["last_known_good"]==first["last_known_good"]
    assert json.loads(state.read_text())["circuit_breaker_action"]=="opened"


def test_grafana_warning_does_not_close_previously_open_genuine_breaker(tmp_path):
    control = tmp_path / "control.json"
    evidence = tmp_path / "evidence.json"
    state = tmp_path / "watchdog.json"
    control.write_text(json.dumps({
        "schema_version": "1.0",
        "circuit_breaker": {"state": "open",
                            "reason": "prior_genuine_drift",
                            "opened_at": "2026-11-13T13:00:00Z"},
    }))
    result = {
        "schema_version": "1.0", "status": "pass",
        "problems": [], "advisories": [{
            "kind": "independent_optional_system_unit_failed",
            "unit": "jason-grafana-assurance.service", "state": "failed",
        }],
    }
    assert watchdog.apply_result(result, control_state=control,
                                 evidence=evidence, watchdog_state=state)==0
    assert json.loads(control.read_text())["circuit_breaker"]["state"]=="open"
    assert json.loads(state.read_text())["advisory_count"]==1
    assert json.loads(state.read_text())["circuit_breaker_action"]=="none"
    assert json.loads(evidence.read_text())["advisories"]==result["advisories"]


def test_watchdog_systemd_unit_treats_reported_drift_as_success_only():
    # Systemd must not turn a correct "drift found" result into an unrelated
    # failed_system_unit incident on the next watchdog cycle.
    from configparser import ConfigParser
    unit = ROOT / "infrastructure/openclaw-operations/systemd/jason-production-drift-watchdog.service"
    # systemd permits repeated ReadOnlyPaths= etc., unlike strict INI.
    config=ConfigParser(interpolation=None, strict=False)
    config.read(unit)
    assert config["Service"]["Type"]=="oneshot"
    assert config["Service"]["SuccessExitStatus"]=="2"
    assert "production_drift_watchdog.py" in config["Service"]["ExecStart"]
    assert "SuccessExitStatus=2" in unit.read_text()
    # The CLI return code remains nonzero to signal detected drift to
    # direct callers; only this systemd timer invocation treats it as a
    # completed observation.
