import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "tools" / "production_drift_guard.py"
SPEC = importlib.util.spec_from_file_location("production_drift_guard", MODULE_PATH)
guard = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = guard
SPEC.loader.exec_module(guard)


def config():
    return {
        "forbidden_execution_prefixes": ["/home/al/projects/jason", "/home/al/jason-worktrees/", "/tmp/"],
        "required_containers": ["jason-runtime", "jason-mcp-pilot"],
        "allowed_running_containers": ["jason-runtime", "jason-mcp-pilot"],
        "required_system_units": ["jason-core.service"],
        "allowed_system_units": [],
        "required_user_units": ["jason-release-manager.timer"],
        "allowed_user_units": ["jason-release-manager.service"],
        "rollback_container_prefixes": ["jason-runtime-rollback-"],
        "max_stopped_rollback_containers": 20,
    }


class ProductionDriftGuardTests(unittest.TestCase):

    def test_root_user_systemd_queries_switch_to_al_context(self):
        outputs = [
            "jason-release-manager.timer loaded active waiting\n",
            "jason-release-manager.timer enabled enabled\n",
        ]
        with (
            patch.object(guard.os, "geteuid", return_value=0),
            patch.object(guard, "run", side_effect=outputs) as run_call,
        ):
            names = guard.unit_names(user=True)
        self.assertIn("jason-release-manager.timer", names)
        self.assertEqual(run_call.call_count, 2)
        for call in run_call.call_args_list:
            args = call.args[0]
            self.assertEqual(args[:4], ["runuser", "-u", "al", "--"])
            self.assertIn("systemctl", args)
            self.assertIn("--user", args)
            self.assertIsNone(call.kwargs.get("env"))

    def test_nonroot_user_systemd_queries_use_user_bus_environment(self):
        with (
            patch.object(guard.os, "geteuid", return_value=1000),
            patch.object(guard, "run", return_value="active") as run_call,
        ):
            state = guard.active_state("jason-release-manager.timer", user=True)
        self.assertEqual(state, "active")
        args = run_call.call_args.args[0]
        self.assertEqual(args[:2], ["systemctl", "--user"])
        env = run_call.call_args.kwargs["env"]
        self.assertEqual(env["HOME"], "/home/al")
        self.assertEqual(env["XDG_RUNTIME_DIR"], "/run/user/1000")

    def test_clean_declared_state_passes(self):
        with (
            patch.object(guard, "unit_names", side_effect=[{"jason-core.service"}, {"jason-release-manager.timer", "jason-release-manager.service"}]),
            patch.object(guard, "active_state", return_value="active"),
            patch.object(guard, "unit_properties", return_value={"ExecStart": "/opt/jason/current/tool.py", "WorkingDirectory": "/opt/jason/current"}),
            patch.object(guard, "running_containers", return_value={"jason-runtime", "jason-mcp-pilot"}),
            patch.object(guard, "stopped_rollback_containers", return_value=[]),
        ):
            result = guard.evaluate(config())
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["problems"], [])

    def test_forbidden_developer_path_fails_closed(self):
        with (
            patch.object(guard, "unit_names", side_effect=[{"jason-core.service"}, {"jason-release-manager.timer", "jason-release-manager.service"}]),
            patch.object(guard, "active_state", return_value="active"),
            patch.object(guard, "unit_properties", side_effect=lambda unit, user: {
                "ExecStart": "/usr/bin/python3 /home/al/projects/jason/tool.py" if unit == "jason-release-manager.service" else "/opt/jason/current/tool.py",
                "WorkingDirectory": "/home/al/projects/jason" if unit == "jason-release-manager.service" else "/opt/jason/current",
            }),
            patch.object(guard, "running_containers", return_value={"jason-runtime", "jason-mcp-pilot"}),
            patch.object(guard, "stopped_rollback_containers", return_value=[]),
        ):
            result = guard.evaluate(config())
        self.assertEqual(result["status"], "drift_detected")
        self.assertTrue(any(p["kind"] == "forbidden_execution_path" for p in result["problems"]))

    def test_undeclared_running_container_fails_closed(self):
        with (
            patch.object(guard, "unit_names", side_effect=[{"jason-core.service"}, {"jason-release-manager.timer", "jason-release-manager.service"}]),
            patch.object(guard, "active_state", return_value="active"),
            patch.object(guard, "unit_properties", return_value={"ExecStart": "/opt/jason/current/tool.py", "WorkingDirectory": "/opt/jason/current"}),
            patch.object(guard, "running_containers", return_value={"jason-runtime", "jason-mcp-pilot", "jason-rogue"}),
            patch.object(guard, "stopped_rollback_containers", return_value=[]),
        ):
            result = guard.evaluate(config())
        self.assertTrue(any(p["kind"] == "undeclared_running_container" and p["container"] == "jason-rogue" for p in result["problems"]))

    def test_undeclared_active_unit_fails_closed(self):
        with (
            patch.object(guard, "unit_names", side_effect=[{"jason-core.service", "jason-rogue.service"}, {"jason-release-manager.timer", "jason-release-manager.service"}]),
            patch.object(guard, "active_state", return_value="active"),
            patch.object(guard, "unit_properties", return_value={"ExecStart": "/opt/jason/current/tool.py", "WorkingDirectory": "/opt/jason/current"}),
            patch.object(guard, "running_containers", return_value={"jason-runtime", "jason-mcp-pilot"}),
            patch.object(guard, "stopped_rollback_containers", return_value=[]),
        ):
            result = guard.evaluate(config())
        self.assertTrue(any(p["kind"] == "undeclared_installed_system_unit" and p["unit"] == "jason-rogue.service" for p in result["problems"]))

    def test_failed_allowlisted_user_unit_still_fails_closed(self):
        def state(unit, user):
            if user and unit == "jason-release-manager.service":
                return "failed"
            return "active"

        with (
            patch.object(guard, "unit_names", side_effect=[{"jason-core.service"}, {"jason-release-manager.timer", "jason-release-manager.service"}]),
            patch.object(guard, "active_state", side_effect=state),
            patch.object(guard, "unit_properties", return_value={"ExecStart": "/opt/jason/current/tool.py", "WorkingDirectory": "/opt/jason/current"}),
            patch.object(guard, "running_containers", return_value={"jason-runtime", "jason-mcp-pilot"}),
            patch.object(guard, "stopped_rollback_containers", return_value=[]),
        ):
            result = guard.evaluate(config())
        self.assertTrue(any(p["kind"] == "failed_user_unit" and p["unit"] == "jason-release-manager.service" for p in result["problems"]))

    def test_rollback_retention_excess_fails_closed(self):
        with (
            patch.object(guard, "unit_names", side_effect=[{"jason-core.service"}, {"jason-release-manager.timer", "jason-release-manager.service"}]),
            patch.object(guard, "active_state", return_value="active"),
            patch.object(guard, "unit_properties", return_value={"ExecStart": "/opt/jason/current/tool.py", "WorkingDirectory": "/opt/jason/current"}),
            patch.object(guard, "running_containers", return_value={"jason-runtime", "jason-mcp-pilot"}),
            patch.object(guard, "stopped_rollback_containers", return_value=[f"jason-runtime-rollback-{i}" for i in range(21)]),
        ):
            result = guard.evaluate(config())
        self.assertTrue(any(p["kind"] == "rollback_container_retention_exceeded" for p in result["problems"]))


if __name__ == "__main__":
    unittest.main()
