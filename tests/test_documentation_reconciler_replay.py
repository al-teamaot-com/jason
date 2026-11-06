"""Regression tests for replay-safe documentation evidence, without host access."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import documentation_success_reconciler as reconciler


class ReplayEvidenceTest(unittest.TestCase):
    def test_source_replay_preserves_original_observation(self):
        state = {"schema_version": "1.0"}
        with patch.object(reconciler, "now_iso", return_value="2026-10-01T00:00:00+00:00"):
            reconciler.update_source(
                state, revision="a" * 40, run_id="111",
                run_url="https://example.invalid/111"
            )
        first = dict(state["validated_source"])
        with patch.object(reconciler, "now_iso", return_value="2026-10-02T00:00:00+00:00"):
            reconciler.update_source(
                state, revision="a" * 40, run_id="111",
                run_url="https://example.invalid/111"
            )
        self.assertEqual(state["validated_source"], first)

    def test_new_source_workflow_updates_observed_at(self):
        state = {"schema_version": "1.0"}
        with patch.object(reconciler, "now_iso", return_value="T1"):
            reconciler.update_source(state, revision="a" * 40, run_id="111", run_url="url")
        with patch.object(reconciler, "now_iso", return_value="T2"):
            reconciler.update_source(state, revision="a" * 40, run_id="112", run_url="url")
        self.assertEqual(state["validated_source"]["observed_at"], "T2")
        self.assertEqual(state["validated_source"]["workflow_run_id"], "112")

    def test_unchanged_production_replay_does_not_regenerate_state(self):
        old = {
            "revision": "a" * 40, "status": "aligned_and_healthy",
            "runtime": {"health": "healthy", "restart_count": 0},
            "observed_at": "T1",
        }
        new = dict(old, observed_at="T2")
        self.assertEqual(reconciler.retain_observation_on_replay(old, new), old)
        changed = dict(old, observed_at="T2", runtime={"health": "healthy", "restart_count": 1})
        self.assertEqual(
            reconciler.retain_observation_on_replay(old, changed)["observed_at"], "T2"
        )

    def test_replay_generates_identical_json_and_markdown_bytes(self):
        state = {"schema_version": "1.0"}
        with tempfile.TemporaryDirectory() as directory:
            json_path = Path(directory) / "state.json"
            md_path = Path(directory) / "state.md"
            with patch.object(reconciler, "now_iso", return_value="T1"):
                reconciler.update_source(state, revision="a" * 40, run_id="111", run_url="url")
            reconciler.write_state(json_path, md_path, state)
            first_json, first_md = json_path.read_bytes(), md_path.read_bytes()
            with patch.object(reconciler, "now_iso", return_value="T2"):
                reconciler.update_source(state, revision="a" * 40, run_id="111", run_url="url")
            reconciler.write_state(json_path, md_path, state)
            self.assertEqual(json_path.read_bytes(), first_json)
            self.assertEqual(md_path.read_bytes(), first_md)


if __name__ == "__main__":
    unittest.main()
