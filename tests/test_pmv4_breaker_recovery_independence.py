"""PMv4 source-only acceptance: breaker recovery does not depend on PM engineering."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
UNITS = ROOT / "infrastructure/openclaw-operations/systemd/user"


class BreakerRecoveryIndependenceTests(unittest.TestCase):
    def test_bounded_recovery_unit_uses_existing_native_manager(self):
        unit = (UNITS / "jason-release-breaker-recovery.service").read_text()
        self.assertIn("release_breaker_recovery_manager.py", unit)
        self.assertIn("--repo /home/al/.local/lib/jason/engineering-source-repo", unit)
        self.assertIn("--spool /var/lib/jason/openclaw/support-repair", unit)
        self.assertIn("--release-state /var/lib/jason/openclaw/release-manager", unit)
        self.assertIn("NoNewPrivileges=true", unit)
        self.assertIn("ProtectSystem=strict", unit)
        self.assertNotIn("pmv3_engineering_controller.py", unit)
        self.assertNotIn("pmv3-engineering-owner-pause", unit)
        self.assertNotIn("root_revalidate_release_breaker.py", unit)
        self.assertNotIn("sudo ", unit)

    def test_timer_does_not_resume_engineering(self):
        timer = (UNITS / "jason-release-breaker-recovery.timer").read_text()
        self.assertIn("OnUnitInactiveSec=60s", timer)
        self.assertIn("Unit=jason-release-breaker-recovery.service", timer)
        self.assertNotIn("jason-support-repair-worker", timer)
        self.assertNotIn("pmv3-engineering", timer)

    def test_competing_scheduler_cannot_execute_recovery_simultaneously(self):
        import fcntl
        import os
        import sys
        import tempfile
        from unittest.mock import patch
        from tools import release_breaker_recovery_manager as recovery

        with tempfile.TemporaryDirectory() as tmp:
            lock = Path(tmp) / "release-breaker-recovery.lock"
            fd = os.open(lock, os.O_CREAT | os.O_RDWR, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with patch.object(sys, "argv", [
                    "recovery", "--repo", tmp, "--spool", tmp,
                    "--release-state", tmp,
                ]), patch.object(recovery, "_run_once") as runner:
                    self.assertEqual(recovery.main(), 0)
                    runner.assert_not_called()
            finally:
                os.close(fd)

    def test_single_recovery_owner_enters_guarded_existing_path(self):
        import sys
        import tempfile
        from unittest.mock import patch
        from tools import release_breaker_recovery_manager as recovery

        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(sys, "argv", [
                "recovery", "--repo", tmp, "--spool", tmp,
                "--release-state", tmp,
            ]), patch.object(recovery, "_run_once", return_value=0) as runner:
                self.assertEqual(recovery.main(), 0)
                runner.assert_called_once()

    def test_existing_recovery_policy_still_requires_clean_root_observations(self):
        import json
        policy = json.loads((ROOT / "config/release-breaker-self-recovery-policy.json").read_text())
        self.assertTrue(policy["enabled"])
        self.assertGreaterEqual(policy["minimum_distinct_clean_observations"], 3)
        manager = (ROOT / "tools/release_breaker_recovery_manager.py").read_text()
        self.assertIn("native_root_transition(root, expected_sha)", manager)
        self.assertIn("load_pinned_policy(args.repo.resolve(), expected_sha)", manager)
        self.assertIn("minimum_observation_interval_seconds", manager)


if __name__ == "__main__":
    unittest.main()
