"""Migrate only the legacy CCC developer checkout; preserve configured owners."""
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

from tools.ccc_config_source_migration import (
    LEGACY_SOURCE, MANAGED_SOURCE, migrate_legacy_source,
)


class CCCSourceMigrationTests(unittest.TestCase):
    def test_legacy_default_migrates_once_with_private_permissions(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "ccc.json"
            path.write_text(json.dumps({
                "repository_root": LEGACY_SOURCE, "cadence_days": 30,
                "provider_canaries": [{"name": "read-only"}],
            }))
            path.chmod(0o600)
            owner = (path.stat().st_uid, path.stat().st_gid)
            self.assertTrue(migrate_legacy_source(path))
            migrated = json.loads(path.read_text())
            self.assertEqual(migrated["repository_root"], MANAGED_SOURCE)
            self.assertEqual(migrated["cadence_days"], 30)
            self.assertEqual(migrated["provider_canaries"], [{"name": "read-only"}])
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual((path.stat().st_uid, path.stat().st_gid), owner)
            self.assertFalse(migrate_legacy_source(path))

    def test_custom_repo_remains_authoritative(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "ccc.json"
            original = {"repository_root": "/trusted/custom-repo", "enabled": True}
            path.write_text(json.dumps(original))
            path.chmod(0o600)
            self.assertFalse(migrate_legacy_source(path))
            self.assertEqual(json.loads(path.read_text()), original)

    def test_symlink_cannot_replace_real_configuration(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            target = root / "target.json"
            target.write_text(json.dumps({"repository_root": LEGACY_SOURCE}))
            target.chmod(0o600)
            link = root / "ccc.json"
            link.symlink_to(target)
            with self.assertRaises(OSError):
                migrate_legacy_source(link)
            self.assertEqual(json.loads(target.read_text())["repository_root"], LEGACY_SOURCE)

    def test_canonical_installer_migrates_only_after_review_preflight(self):
        root = Path(__file__).resolve().parents[2]
        source = (root / "tools/install_ccc_scheduler.sh").read_text()
        review = source.index('git -C "$REPO_ROOT" show "$SOURCE_REVISION:tools/ccc_install_preflight.py"')
        migration = source.index('tools/ccc_config_source_migration.py')
        self.assertLess(review, migration)
        self.assertIn('REPO_ROOT="/home/al/.local/lib/jason/engineering-worker-source"', source)
        unit = (root / "infrastructure/ccc/systemd/jason-ccc.service").read_text()
        self.assertIn("/home/al/.local/lib/jason/engineering-worker-source/.git", unit)
        self.assertNotIn("/home/al/projects/jason/.git", unit)
        template = json.loads((root / "config/ccc/default.json").read_text())
        self.assertEqual(template["repository_root"], MANAGED_SOURCE)

    def test_world_readable_config_cannot_migrate(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "ccc.json"
            path.write_text(json.dumps({"repository_root": LEGACY_SOURCE}))
            path.chmod(0o644)
            with self.assertRaises(PermissionError):
                migrate_legacy_source(path)
            self.assertEqual(json.loads(path.read_text())["repository_root"], LEGACY_SOURCE)


if __name__ == "__main__":
    unittest.main()
