"""Offline snapshot rehearsal only: never production data, releases or services."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jason_secondary_ledger_snapshot as snapshot


class SyntheticStageTests(unittest.TestCase):
    def setUp(self):
        self.fixture = tempfile.TemporaryDirectory(
            prefix=".jason-ledger-snapshot-test-",
        )
        self.addCleanup(self.fixture.cleanup)
        self.root = Path(self.fixture.name)
        self.source = self.root / "source"
        self.target = self.root / "staged"
        self.source.mkdir(mode=0o700)
        self.event = self.source / "orchestration-events.sqlite3"
        self.reflection = self.source / "reflection.sqlite3"
        with sqlite3.connect(self.event) as db:
            db.execute(
                "CREATE TABLE orchestration_events "
                "(event_id TEXT PRIMARY KEY,occurred_at TEXT,payload TEXT)"
            )
            db.executemany(
                "INSERT INTO orchestration_events VALUES (?,?,?)",
                [
                    ("canonical-001", "2026-11-09T10:01:00Z", "private-event-1"),
                    ("canonical-002", "2026-11-09T10:02:00Z", "private-event-2"),
                ],
            )
        with sqlite3.connect(self.reflection) as db:
            db.execute(
                "CREATE TABLE reflection_records "
                "(record_id TEXT PRIMARY KEY,summary TEXT)"
            )
            db.execute(
                "INSERT INTO reflection_records VALUES (?,?)",
                ("reflection-001", "private-reflection"),
            )
        for p in (self.event,self.reflection):
            os.chmod(p,0o600)

    def test_successful_two_ledger_synthetic_snapshot_is_private_and_exact(self):
        orig = self.event.read_bytes()
        reflect = self.reflection.read_bytes()
        result = snapshot.stage_synthetic_quiesced_copy(self.source,self.target)
        self.assertEqual(result["status"],"synthetic_snapshot_staged_and_verified")
        self.assertTrue(result["test_only"])
        self.assertFalse(result["cutover_authorized"])
        self.assertFalse(result["source_retired"])
        self.assertEqual(self.event.read_bytes(),orig)
        self.assertEqual(self.reflection.read_bytes(),reflect)
        self.assertEqual(result["files"]["orchestration-events.sqlite3"]["logical_identity"]["event_count"],2)
        self.assertEqual(result["files"]["reflection.sqlite3"]["logical_identity"]["table_counts"]["reflection_records"],1)
        with sqlite3.connect(self.target / "orchestration-events.sqlite3") as db:
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone(),("ok",))
            self.assertEqual(db.execute("SELECT COUNT(*) FROM orchestration_events").fetchone(),(2,))
        for name in ("orchestration-events.sqlite3","reflection.sqlite3"):
            copied = self.target/name
            self.assertEqual(copied.stat().st_mode & 0o777,0o600)
            self.assertEqual(hashlib.sha256(copied.read_bytes()).hexdigest(),result["files"][name]["sha256"])
        manifest=self.target/"synthetic-manifest.json"
        self.assertEqual(manifest.stat().st_mode & 0o777,0o600)
        self.assertEqual(json.loads(manifest.read_text()),result)
        self.assertNotIn("private-event",manifest.read_text())
        self.assertNotIn("canonical-001",manifest.read_text())
        self.assertEqual(self.target.stat().st_dev,self.source.stat().st_dev)

    def test_existing_destination_denied_and_preserved(self):
        self.target.mkdir()
        (self.target/"owner-data.txt").write_text("do-not-touch")
        with self.assertRaisesRegex(snapshot.StagingDenied,"unsafe source/target"):
            snapshot.stage_synthetic_quiesced_copy(self.source,self.target)
        self.assertEqual((self.target/"owner-data.txt").read_text(),"do-not-touch")

    def test_production_source_and_target_denied_prior_to_mutation(self):
        forbidden_sources = (
            Path("/var/lib/jason/openclaw"),
            Path("/opt/jason/current"),
            Path("/home/al/projects/jason"),
        )
        for source in forbidden_sources:
            with self.subTest(source=source):
                with self.assertRaisesRegex(snapshot.StagingDenied, "unsafe source/target"):
                    snapshot.stage_synthetic_quiesced_copy(source,self.target)
                self.assertFalse(self.target.exists())
        with self.assertRaisesRegex(snapshot.StagingDenied,"unsafe source/target"):
            snapshot.stage_synthetic_quiesced_copy(
                self.source,Path("/srv/jason/archive/operational-ledgers"),
            )
        self.assertTrue(self.event.is_file())

    def test_symlinked_source_denied_and_does_not_touch_real_source(self):
        actual=self.root/"real"
        self.source.rename(actual)
        self.source.symlink_to(actual,target_is_directory=True)
        with self.assertRaises(snapshot.StagingDenied):
            snapshot.stage_synthetic_quiesced_copy(self.source,self.target)
        self.assertFalse(self.target.exists())
        self.assertTrue((actual/"orchestration-events.sqlite3").is_file())

    def test_unsafe_file_mode_denied(self):
        os.chmod(self.reflection,0o644)
        with self.assertRaisesRegex(snapshot.StagingDenied,"source database identity denied"):
            snapshot.stage_synthetic_quiesced_copy(self.source,self.target)
        self.assertFalse(self.target.exists())

    def test_missing_reflection_database_denied(self):
        self.reflection.unlink()
        with self.assertRaisesRegex(snapshot.StagingDenied,"source database missing"):
            snapshot.stage_synthetic_quiesced_copy(self.source,self.target)
        self.assertFalse(self.target.exists())

    def test_inconsistent_source_stamp_denies_and_removes_only_synthetic_stage(self):
        original=snapshot._source_identity
        call_count=0
        def changed(path):
            nonlocal call_count
            call_count+=1
            identity=original(path)
            if call_count>=3:
                return identity+((123,123,123,123),)
            return identity
        with mock.patch.object(snapshot,"_source_identity",side_effect=changed):
            with self.assertRaisesRegex(snapshot.StagingDenied,"source mutated"):
                snapshot.stage_synthetic_quiesced_copy(self.source,self.target)
        self.assertFalse(self.target.exists())
        self.assertTrue(self.event.exists())
        self.assertTrue(self.reflection.exists())

    def test_snapshot_schema_mismatch_denied_without_root_data_changes(self):
        with sqlite3.connect(self.reflection) as db:
            db.execute("DROP TABLE reflection_records")
            db.execute("CREATE TABLE unrelated (id INTEGER)")
        with self.assertRaisesRegex(snapshot.StagingDenied,"unexpected snapshot schema"):
            snapshot.stage_synthetic_quiesced_copy(self.source,self.target)
        self.assertFalse(self.target.exists())

    def test_wal_read_preserves_committed_events(self):
        # A quiescent (no uncommitted writes) open connection keeps the WAL
        # sidecar present while read-only SQLite backups run.
        with sqlite3.connect(self.event,timeout=2) as source:
            source.execute("PRAGMA journal_mode=WAL")
            source.execute(
                "INSERT INTO orchestration_events VALUES (?,?,?)",
                ("canonical-wal-003","2026-11-09T10:03:00Z","private-wal"),
            )
            source.commit()
            self.assertTrue(self.event.with_name(self.event.name+"-wal").exists())
            result=snapshot.stage_synthetic_quiesced_copy(self.source,self.target)
            self.assertEqual(
                result["files"]["orchestration-events.sqlite3"]["logical_identity"]["event_count"],
                3,
            )
            with sqlite3.connect(self.target/"orchestration-events.sqlite3") as copied:
                self.assertEqual(copied.execute(
                    "SELECT payload FROM orchestration_events WHERE event_id='canonical-wal-003'"
                ).fetchone(),("private-wal",))
        self.assertTrue(self.event.exists())

if __name__=="__main__":
    unittest.main()
