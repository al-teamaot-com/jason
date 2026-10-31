from pathlib import Path
import json
import tempfile
import unittest

from pm_v2.config import ConfigError, load_config


class PMV2ConfigTests(unittest.TestCase):
    def _base(self, root: Path):
        return {
            "schema_version": "1.0",
            "instance_id": "test",
            "poll_interval_seconds": 15,
            "lease_seconds": 300,
            "max_concurrent_jobs": 1,
            "state": {"database_path": str(root / "x.sqlite3")},
            "sources": {"roadmap_path": "roadmap.md", "support_path": "SUPPORT.md"},
            "workers": {
                "development": {
                    "enabled": True,
                    "max_concurrency": 1,
                    "command": ["true"]
                }
            },
            "paths": {"legacy_spool": "/tmp/legacy", "release_state": "/tmp/release"},
            "communications": {
                "required_status_fields": [
                    "Status","Completed","Still required",
                    "What I'm doing next","What you need to do"
                ],
                "approval_channel": "microsoft_teams"
            }
        }

    def test_teams_is_mandatory_approval_channel(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            config = self._base(root)
            config["communications"]["approval_channel"] = "terminal"
            path = root / "config.json"
            path.write_text(json.dumps(config), encoding="utf-8")
            with self.assertRaises(ConfigError):
                load_config(path, repo=root)

    def test_config_is_portable_by_path_and_worker_definition(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = root / "config.json"
            path.write_text(json.dumps(self._base(root)), encoding="utf-8")
            config = load_config(path, repo=root)
            self.assertEqual(config.instance_id, "test")
            self.assertEqual(config.workers[0].name, "development")
