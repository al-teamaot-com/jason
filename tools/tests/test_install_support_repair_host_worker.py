import unittest
from pathlib import Path


class InstallSupportRepairHostWorkerTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[2]

    def test_support_repair_units_exist(self):
        root = self.root
        self.assertTrue(
            (
                root
                / "infrastructure/openclaw-operations/systemd/user/jason-support-repair-worker.service"
            ).is_file()
        )
        self.assertTrue(
            (
                root
                / "infrastructure/openclaw-operations/systemd/user/jason-support-repair-worker.timer"
            ).is_file()
        )
        self.assertTrue((root / "tools/support_repair_host_worker.py").is_file())
        self.assertTrue((root / "tools/owner_approved_development_worker.py").is_file())
        self.assertTrue((root / "tools/todo_engineering_intake.py").is_file())
        self.assertTrue((root / "tools/todo_release_bridge.py").is_file())

    def test_engineering_service_runs_support_before_owner_approved_development(self):
        service = (
            self.root
            / "infrastructure/openclaw-operations/systemd/user/jason-support-repair-worker.service"
        ).read_text(encoding="utf-8")
        support_index = service.index("support_repair_host_worker.py")
        development_index = service.index("owner_approved_development_worker.py")
        self.assertLess(support_index, development_index)
        self.assertIn("/home/al/jason-worktrees/owner-approved-development", service)
        self.assertIn("/home/al/jason-worktrees/todo-closure", service)
        self.assertIn("/var/lib/jason/openclaw/release-manager", service)

    def test_engineering_service_orders_support_todo_development_and_release_bridge(self):
        service = (
            self.root
            / "infrastructure/openclaw-operations/systemd/user/jason-support-repair-worker.service"
        ).read_text(encoding="utf-8")
        support_index = service.index("support_repair_host_worker.py")
        todo_index = service.index("todo_engineering_intake.py")
        development_index = service.index("owner_approved_development_worker.py")
        bridge_index = service.index("todo_release_bridge.py")
        self.assertLess(support_index, todo_index)
        self.assertLess(todo_index, development_index)
        self.assertLess(development_index, bridge_index)

    def test_support_repair_timer_runs_daily_at_0230_and_remains_persistent(self):
        timer = (
            self.root
            / "infrastructure/openclaw-operations/systemd/user/jason-support-repair-worker.timer"
        ).read_text(encoding="utf-8")
        self.assertIn("OnCalendar=*-*-* 02:30:00", timer)
        self.assertIn("AccuracySec=1min", timer)
        self.assertIn("Persistent=true", timer)
        self.assertNotIn("OnUnitInactiveSec=", timer)
        self.assertNotIn("OnBootSec=", timer)
        self.assertNotIn("OnUnitActiveSec=", timer)


if __name__ == "__main__":
    unittest.main()
