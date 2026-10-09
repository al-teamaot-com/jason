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

    def test_control_state_replacement_inherits_release_directory_owner(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            control = root / "control.json"
            evidence = root / "evidence.json"
            state = root / "watchdog.json"
            result = {"status": "drift_detected", "problems": [{"kind": "unexpected_unit"}]}
            original_chown = watchdog.os.chown
            calls = []
            def checked_chown(path, uid, gid):
                calls.append((Path(path), uid, gid))
                original_chown(path, uid, gid)
            with patch.object(watchdog.os, "chown", side_effect=checked_chown):
                rc = watchdog.apply_result(result, control_state=control, evidence=evidence, watchdog_state=state)
            self.assertEqual(rc, 2)
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0][1:], (root.stat().st_uid, root.stat().st_gid))
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
