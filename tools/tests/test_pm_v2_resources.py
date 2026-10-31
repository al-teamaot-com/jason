from pathlib import Path
import json
import tempfile
import unittest

from pm_v2.config import load_config
from pm_v2.resources import wrap_subprocess_command


class PMV2ResourceTests(unittest.TestCase):
    def test_configured_subprocess_limits_wrap_execution(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "roadmap.md").write_text("")
            (root / "SUPPORT.md").write_text("")
            cfg = {
                "schema_version": "1.0",
                "instance_id": "resources",
                "poll_interval_seconds": 1,
                "lease_seconds": 10,
                "max_concurrent_jobs": 1,
                "max_concurrent_components": 1,
                "state": {"database_path": str(root / "state.sqlite3")},
                "sources": {"roadmap_path": "roadmap.md", "support_path": "SUPPORT.md"},
                "workers": {},
                "components": {},
                "paths": {"legacy_spool": "/tmp/a", "release_state": "/tmp/b"},
                "recovery": {
                    "snapshot_directory": str(root / "snapshot"),
                    "snapshot_interval_seconds": 60,
                    "replica_directories": []
                },
                "ownership": {"owned_todo_ids": []},
                "control": {
                    "status_snapshot_path": str(root / "status.json"),
                    "request_inbox": str(root / "requests"),
                    "result_directory": str(root / "results")
                },
                "resources": {
                    "subprocess_memory_mb": 512,
                    "subprocess_cpu_seconds": 30,
                    "subprocess_open_files": 256,
                    "cloud_spend_policy": "teams_approval_required",
                    "provider_authority_policy": "existing_governed_authority_only"
                },
                "communications": {
                    "required_status_fields": [
                        "Status","Completed","Still required",
                        "What I'm doing next","What you need to do"
                    ],
                    "approval_channel": "microsoft_teams"
                }
            }
            path=root/"config.json"
            path.write_text(json.dumps(cfg))
            config=load_config(path,repo=root)
            command=wrap_subprocess_command(config,["python3","-c","pass"])
            self.assertEqual(command[0],"/usr/bin/prlimit")
            self.assertIn("--as=536870912:536870912",command)
            self.assertIn("--cpu=30:30",command)
            self.assertIn("--nofile=256:256",command)
            self.assertEqual(command[-3:],["python3","-c","pass"])
