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
        self.assertTrue((root / "tools/release_manager_gate.py").is_file())

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

    def test_engineering_service_uses_immutable_installed_source(self):
        service = (
            self.root
            / "infrastructure/openclaw-operations/systemd/user/jason-support-repair-worker.service"
        ).read_text(encoding="utf-8")
        installer = (self.root / "tools/install_support_repair_host_worker.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("/home/al/.local/lib/jason/engineering-worker-source", service)
        self.assertNotIn("--repo /home/al/projects/jason", service)
        self.assertNotIn("WorkingDirectory=/home/al/projects/jason", service)
        self.assertIn("engineering-worker-source", installer)
        self.assertIn("_copy(change_integration_gate, install_root", installer)
        self.assertIn("_copy(documentation_impact_gate, install_root", installer)
        self.assertIn("source_link.symlink_to(repo, target_is_directory=True)", installer)

    def test_installer_copies_todo_release_gate_dependency(self):
        installer = (self.root / "tools/install_support_repair_host_worker.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("release_manager_gate = repo / 'tools' / 'release_manager_gate.py'", installer)
        self.assertIn("install_root / 'release_manager_gate.py'", installer)

    def test_installer_binds_nonlogin_systemd_user_bus(self):
        installer = (self.root / "tools/install_support_repair_host_worker.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("XDG_RUNTIME_DIR", installer)
        self.assertIn("DBUS_SESSION_BUS_ADDRESS", installer)
        self.assertIn("unix:path=/run/user/{uid}/bus", installer)
        self.assertIn("env=systemd_env", installer)

    def test_support_repair_timer_runs_24x7(self):
        timer = (
            self.root
            / "infrastructure/openclaw-operations/systemd/user/jason-support-repair-worker.timer"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "OnCalendar=*-*-* *:00/5:00 America/New_York",
            timer,
        )
        self.assertIn("AccuracySec=15s", timer)
        self.assertIn("Persistent=true", timer)
        self.assertNotIn("OnUnitInactiveSec=", timer)
        self.assertNotIn("OnBootSec=", timer)
        self.assertNotIn("OnUnitActiveSec=", timer)


if __name__ == "__main__":
    unittest.main()
