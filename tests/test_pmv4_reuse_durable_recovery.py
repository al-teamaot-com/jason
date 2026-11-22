"""PMv4 preproduction acceptance of EXISTING PMV3 durable work engine.

Only disposable temp files and fresh Python child processes; no real providers,
OpenClaw Gateway, production work item, credential, restart, release or deployment.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PYTHONPATH = str(ROOT / "tools")

SCRIPT = r"""
import json
from pathlib import Path
import sys
import pmv3_work_engine as engine

stage, state_name, marker_name, safe = sys.argv[1:]
state_path = Path(state_name)
marker_path = Path(marker_name)
safe = (safe == "yes")
if stage == "init":
    state = engine.empty_state()
    engine.admit(state, engine.make_item("PMV4-OFFLINE-001", "nonproduction_source_review", idempotent=safe))
    engine.atomic_write(state_path, state)
elif stage == "crash":
    state = engine.load_state(state_path)
    def handler(item, key):
        raise RuntimeError("injected process failure BEFORE any external side effect")
    engine.execute_cycle(state, facts={}, handler=handler, checkpoint=lambda s:engine.atomic_write(state_path,s))
elif stage == "receipt":
    state = engine.load_state(state_path)
    item = state["items"]["PMV4-OFFLINE-001"]
    key = engine.action_key(item["id"], item["action"], item["generation"])
    item["phase"] = "running"
    state["receipts"][key] = {
        "item_id": item["id"], "receipt": "preexisting-independent-verification",
        "recorded_at": engine.iso(engine.utcnow()),
    }
    engine.atomic_write(state_path, state)
elif stage in {"recover","repeat"}:
    state = engine.load_state(state_path)
    def handler(item, key):
        with marker_path.open("a") as log:
            log.write(key + "\n")
        return engine.Outcome("complete", receipt="verified-readonly-review-001")
    engine.execute_cycle(state, facts={}, handler=handler, checkpoint=lambda s:engine.atomic_write(state_path,s))
    engine.atomic_write(state_path,state)
else:
    raise ValueError(stage)
"""

class DurableReuseAcceptance(unittest.TestCase):
    def run_stage(self, stage: str, state: Path, marker: Path, safe: bool, expect: int = 0):
        env = {**os.environ, "PYTHONPATH": PYTHONPATH}
        result = subprocess.run(
            [sys.executable, "-c", SCRIPT, stage, str(state), str(marker), "yes" if safe else "no"],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=12,
        )
        if expect == 0:
            self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        else:
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("injected process failure", result.stderr)
        return result

    def test_idempotent_item_recovers_after_actual_process_failure_without_duplicate(self):
        with tempfile.TemporaryDirectory(prefix="pmv4-durable-") as d:
            state, marker = Path(d)/"work-state.json", Path(d)/"handler-calls.txt"
            self.run_stage("init", state, marker, True)
            self.run_stage("crash", state, marker, True, expect=1)
            interrupted = json.loads(state.read_text())
            item = interrupted["items"]["PMV4-OFFLINE-001"]
            self.assertEqual(item["phase"], "running")
            self.assertEqual(interrupted["receipts"], {})
            self.assertFalse(marker.exists()) # no fake side-effect before failure
            self.run_stage("recover", state, marker, True)
            restored = json.loads(state.read_text())
            self.assertEqual(restored["items"]["PMV4-OFFLINE-001"]["phase"], "complete")
            self.assertEqual(len(restored["receipts"]), 1)
            self.assertEqual(len(marker.read_text().splitlines()), 1)
            self.run_stage("repeat", state, marker, True)
            self.assertEqual(len(marker.read_text().splitlines()), 1)
            self.assertEqual(len(json.loads(state.read_text())["receipts"]), 1)

    def test_existing_durable_receipt_prevents_duplicate_after_fresh_process(self):
        with tempfile.TemporaryDirectory(prefix="pmv4-receipted-") as d:
            state, marker = Path(d)/"work-state.json", Path(d)/"handler-calls.txt"
            self.run_stage("init", state, marker, True)
            self.run_stage("receipt", state, marker, True)
            self.run_stage("recover", state, marker, True)
            saved = json.loads(state.read_text())
            self.assertEqual(saved["items"]["PMV4-OFFLINE-001"]["phase"], "complete")
            self.assertFalse(marker.exists())
            self.assertEqual(len(saved["receipts"]), 1)
            self.run_stage("repeat", state, marker, True)
            self.assertFalse(marker.exists())

    def test_nonidempotent_interruption_never_automatically_retries(self):
        with tempfile.TemporaryDirectory(prefix="pmv4-uncertain-") as d:
            state, marker = Path(d)/"work-state.json", Path(d)/"handler-calls.txt"
            self.run_stage("init", state, marker, False)
            self.run_stage("crash", state, marker, False, expect=1)
            self.run_stage("recover", state, marker, False)
            record = json.loads(state.read_text())["items"]["PMV4-OFFLINE-001"]
            self.assertEqual(record["phase"], "waiting")
            self.assertEqual(record["reason"], "indeterminate_execution_requires_reconciliation")
            self.assertEqual(record["dependency"], "reconciliation_required")
            self.assertFalse(marker.exists())
            self.run_stage("repeat", state, marker, False)
            self.assertFalse(marker.exists())


if __name__ == "__main__":
    unittest.main()
