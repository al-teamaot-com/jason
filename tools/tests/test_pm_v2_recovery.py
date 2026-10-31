from pathlib import Path
import json
import tempfile
import unittest

from pm_v2.recovery import create_snapshot, restore_snapshot, verify_snapshot
from pm_v2.store import PMV2Store


class PMV2RecoveryTests(unittest.TestCase):
    def test_snapshot_verifies_and_restores_state_and_config(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            store = PMV2Store(root / "live" / "pm-v2.sqlite3")
            store.initialize()
            store.upsert_assignment(
                assignment_id="a1", source="test", source_ref="1",
                title="recover me", priority=1, work_type="development",
                runnable=True, scope_hash="sha256:1", metadata={"x": 1},
            )
            config = root / "pm-v2.json"
            config.write_text('{"schema_version":"1.0"}\n', encoding="utf-8")
            snapshot = root / "snapshot"
            manifest = create_snapshot(
                store=store, destination=snapshot, config_path=config
            )
            self.assertEqual(verify_snapshot(snapshot)["database"]["sha256"],
                             manifest["database"]["sha256"])

            restored_db = root / "restored" / "state.sqlite3"
            restored_config = root / "restored" / "pm-v2.json"
            restore_snapshot(
                snapshot_dir=snapshot,
                database_path=restored_db,
                config_destination=restored_config,
            )
            restored = PMV2Store(restored_db)
            rows = restored.list_assignments()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].title, "recover me")
            self.assertEqual(restored_config.read_text(), config.read_text())

    def test_tampered_snapshot_fails_integrity(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            store = PMV2Store(root / "state.sqlite3")
            store.initialize()
            config = root / "config.json"
            config.write_text("{}\n", encoding="utf-8")
            snapshot = root / "snapshot"
            create_snapshot(store=store, destination=snapshot, config_path=config)
            with (snapshot / "pm-v2-config.json").open("ab") as handle:
                handle.write(b"tamper")
            with self.assertRaises(ValueError):
                verify_snapshot(snapshot)
