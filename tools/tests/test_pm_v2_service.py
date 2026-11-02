from pathlib import Path
import json
import tempfile
import unittest

from pm_v2.config import load_config
from pm_v2.service import run_service
from pm_v2.store import PMV2Store


class PMV2ServiceTests(unittest.TestCase):
    def test_one_cycle_is_persistent_healthy_and_nonexecuting_without_owned_work(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".git").mkdir()
            docs = root / "docs" / "roadmaps"
            docs.mkdir(parents=True)
            roadmap = (
                "# TODO\n\n"
                "### TODO-OPS-001 — Approved\n"
                "- **Priority:** P1\n"
                "- **Status:** Approved for Autonomous Engineering — owner-approved\n"
                "- **Autonomous engineering readiness:** Approved\n"
                "- **Idea:** Existing work.\n"
            )
            (docs / "Project-Jason-TODO-and-Future-Ideas.md").write_text(
                roadmap, encoding="utf-8"
            )
            (root / "SUPPORT.md").write_text("# Support\n", encoding="utf-8")
            spool = root / "legacy"
            spool.mkdir()
            release = root / "release"
            release.mkdir()
            config_path = root / "config.json"
            config_path.write_text(json.dumps({
                "schema_version": "1.0",
                "instance_id": "node-test",
                "poll_interval_seconds": 1,
                "lease_seconds": 10,
                "max_concurrent_jobs": 1,
            "max_concurrent_components": 1,
            "components": {},
                "state": {"database_path": str(root / "state.sqlite3")},
                "sources": {
                    "roadmap_path": "docs/roadmaps/Project-Jason-TODO-and-Future-Ideas.md",
                    "support_path": "SUPPORT.md"
                },
                "workers": {},
                "paths": {
                    "legacy_spool": str(spool),
                    "release_state": str(release)
                },
                "recovery": {
                    "snapshot_directory": str(root / "snapshot"),
                    "snapshot_interval_seconds": 60
                },
                "ownership": {"owned_todo_ids": []},
                "control": {
                    "status_snapshot_path": str(root / "control" / "status.json"),
                    "request_inbox": str(root / "control" / "requests"),
                    "result_directory": str(root / "control" / "results")
                },
                "communications": {
                    "required_status_fields": [
                        "Status", "Completed", "Still required",
                        "What I'm doing next", "What you need to do"
                    ],
                    "approval_channel": "microsoft_teams"
                }
            }), encoding="utf-8")
            self.assertEqual(
                run_service(repo=root, config_path=config_path, once=True), 0
            )
            config = load_config(config_path, repo=root)
            store = PMV2Store(config.database_path)
            rows = store.list_assignments()
            self.assertEqual(len(rows), 1)
            self.assertFalse(rows[0].runnable)
            self.assertEqual(rows[0].blocked_reason, "owned_by_other_controller")
            nodes = store.node_snapshot()
            self.assertEqual(nodes[0]["node_id"], "node-test")
            self.assertEqual(nodes[0]["status"], "healthy")
            self.assertTrue((root / "snapshot" / "manifest.json").is_file())
