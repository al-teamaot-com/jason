"""Read-only exact-boundary tests for future secondary ledger migration."""
from __future__ import annotations

import os
import json
import subprocess
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jason_secondary_ledger_preflight as m


class SecondaryLedgerAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.legacy = base / "legacy"
        self.archive = base / "archive"
        self.legacy.mkdir(mode=0o700)
        self.archive.mkdir(mode=0o700)
        self.target = self.archive / "operational-ledgers"
        source = self.legacy / m.FILES[0]
        with sqlite3.connect(source) as db:
            db.execute(
                "CREATE TABLE orchestration_events "
                "(event_id TEXT PRIMARY KEY, occurred_at TEXT, payload TEXT)"
            )
            db.execute(
                "INSERT INTO orchestration_events VALUES ('event-1','2026-11-09T00:00:00Z','secret')"
            )
            db.commit()
        reflection = self.legacy / m.FILES[1]
        with sqlite3.connect(reflection) as db:
            db.execute("CREATE TABLE reflection_records (id INTEGER PRIMARY KEY)")
        for path in (source, reflection):
            os.chmod(path, 0o600)

    def _inspect(self, *, available_gib=190, separate=True):
        vfs = SimpleNamespace(
            f_frsize=4096,
            f_bavail=int(available_gib * m.GiB / 4096),
            f_files=100000,
            f_favail=20000,
        )
        def fake_device(path):
            if path == self.archive:
                return 22 if separate else 11
            return 11
        with (
            mock.patch.object(m.os.path, "ismount", return_value=True),
            mock.patch.object(m.os, "statvfs", return_value=vfs),
            mock.patch.object(m, "_device", side_effect=fake_device),
        ):
            return m.inspect(
                legacy=self.legacy,
                archive=self.archive,
                target=self.target,
                expected_uid=os.geteuid(),
            )

    def test_positive_admission_is_read_only_and_never_authorizes_cutover(self):
        source = self.legacy / m.FILES[0]
        before = (source.stat().st_ino, source.stat().st_size, source.stat().st_mtime_ns)
        result = self._inspect()
        self.assertEqual(result["status"], "preflight_pass")
        self.assertEqual(result["source_files"][m.FILES[0]]["sqlite"]["last_rowid"], 1)
        self.assertFalse(result["cutover_authorized"])
        self.assertFalse(result["data_mutated"])
        self.assertFalse(result["services_restarted"])
        self.assertFalse(self.target.exists())
        self.assertEqual(
            before,
            (source.stat().st_ino, source.stat().st_size, source.stat().st_mtime_ns),
        )
        self.assertNotIn("secret", str(result))

    def test_denies_archive_device_alias(self):
        self.assertIn("device", self._inspect(separate=False)["reason"])

    def test_denies_insufficient_full_snapshot_reserve(self):
        self.assertEqual(self._inspect(available_gib=1)["status"], "preflight_denied")

    def test_denies_existing_target(self):
        self.target.mkdir(mode=0o700)
        self.assertIn("target already exists", self._inspect()["reason"])

    def test_denies_symlinked_source_file(self):
        old = self.legacy / m.FILES[0]
        hidden = self.legacy / "protected-ledger"
        old.rename(hidden)
        old.symlink_to(hidden)
        self.assertIn("symlinked ledger", self._inspect()["reason"])

    def test_denies_unsafe_source_permissions(self):
        path = self.legacy / m.FILES[1]
        os.chmod(path, 0o644)
        self.assertIn("unsafe ledger file identity", self._inspect()["reason"])

    def test_denies_missing_archive_mount(self):
        with mock.patch.object(m.os.path, "ismount", return_value=False):
            res = m.inspect(
                legacy=self.legacy,
                archive=self.archive,
                target=self.target,
                expected_uid=os.geteuid(),
            )
        self.assertEqual(res["status"], "preflight_denied")

    def test_quiesced_synthetic_sqlite_backup_preserves_immutable_event_rows(self):
        """Rehearse SQLite backup API on synthetic small files only, not host ledgers."""
        source = self.legacy / m.FILES[0]
        dest = self.archive / "synthetic-archive.sqlite3"
        with sqlite3.connect(source) as src, sqlite3.connect(dest) as out:
            src.backup(out)
        with sqlite3.connect(dest) as test:
            rows = test.execute(
                "SELECT event_id,occurred_at,payload FROM orchestration_events ORDER BY rowid"
            ).fetchall()
            integrity = test.execute("PRAGMA integrity_check").fetchone()[0]
        self.assertEqual(rows, [("event-1", "2026-11-09T00:00:00Z", "secret")])
        self.assertEqual(integrity, "ok")
        self.assertEqual(sqlite3.connect(source).execute(
            "SELECT COUNT(*) FROM orchestration_events").fetchone()[0], 1)


class LiveRouteGuardTests(unittest.TestCase):
    @staticmethod
    def fixtures():
        return [
            {
                "Name": "/" + name,
                "State": {"Running": True},
                "Config": {"Env": [
                    "JASON_ORCHESTRATION_EVENTS_DB=/var/lib/jason/openclaw/orchestration-events.sqlite3",
                    "SECRET_UNRELATED_PROTECTED=never-expose-me",
                ]},
                "Mounts": [{
                    "Source": "/var/lib/jason/openclaw",
                    "Destination": "/var/lib/jason/openclaw",
                    "RW": True,
                }],
            }
            for name in ("jason-runtime", "jason-mcp-pilot")
        ]

    def test_dual_writer_route_proven_without_secret_leak(self):
        fixtures = self.fixtures()
        response = SimpleNamespace(stdout=json.dumps(fixtures))
        with mock.patch.object(m.subprocess, "run", return_value=response):
            result = m.inspect_container_routes()
        self.assertEqual(set(result), {"jason-runtime", "jason-mcp-pilot"})
        self.assertNotIn("never-expose-me", json.dumps(result))

    def test_split_writer_routes_refused(self):
        fixtures = self.fixtures()
        fixtures[1]["Config"]["Env"][0] = "JASON_ORCHESTRATION_EVENTS_DB=/srv/different"
        with mock.patch.object(m.subprocess, "run", return_value=SimpleNamespace(stdout=json.dumps(fixtures))):
            with self.assertRaisesRegex(m.MigrationAdmissionDenied, "split or unreviewed"):
                m.inspect_container_routes()

    def test_readonly_writer_mount_refused(self):
        fixtures = self.fixtures()
        fixtures[0]["Mounts"][0]["RW"] = False
        with mock.patch.object(m.subprocess, "run", return_value=SimpleNamespace(stdout=json.dumps(fixtures))):
            with self.assertRaisesRegex(m.MigrationAdmissionDenied, "data bind"):
                m.inspect_container_routes()


class ConsumerRouteContractTests(unittest.TestCase):
    @staticmethod
    def repo():
        return Path(__file__).resolve().parents[2]

    def test_health_default_remains_legacy_without_explicit_release_profile(self):
        script = "from openclaw_authority_operational_health import DEFAULT_ORCH; print(DEFAULT_ORCH)"
        env = dict(os.environ)
        env.pop("JASON_ORCHESTRATION_EVENTS_DB", None)
        env["PYTHONPATH"] = str(self.repo() / "tools")
        result = subprocess.run([sys.executable, "-c", script],
                                env=env, text=True, capture_output=True, check=True)
        self.assertEqual(result.stdout.strip(),
                         "/var/lib/jason/openclaw/orchestration-events.sqlite3")

    def test_health_can_follow_exact_released_secondary_route(self):
        script = "from openclaw_authority_operational_health import DEFAULT_ORCH; print(DEFAULT_ORCH)"
        env = dict(os.environ)
        env["JASON_ORCHESTRATION_EVENTS_DB"] = "/var/lib/jason/secondary-ledgers/events.sqlite3"
        env["PYTHONPATH"] = str(self.repo() / "tools")
        result = subprocess.run([sys.executable, "-c", script],
                                env=env, text=True, capture_output=True, check=True)
        self.assertEqual(result.stdout.strip(),
                         "/var/lib/jason/secondary-ledgers/events.sqlite3")

    def test_native_runtime_diagnostic_uses_container_environment(self):
        p = self.repo() / "infrastructure/jason-runtime/jason-ops.sh"
        content = p.read_text()
        self.assertIn('db_path = Path(os.environ.get(', content)
        self.assertIn('"JASON_ORCHESTRATION_EVENTS_DB",', content)
        subprocess.run(["bash", "-n", str(p)], check=True)


if __name__ == "__main__":
    unittest.main()
