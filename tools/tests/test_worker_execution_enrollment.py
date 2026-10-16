import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "worker_execution_enrollment", ROOT / "tools" / "worker_execution_enrollment.py"
)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class WorkerEnrollmentTests(unittest.TestCase):
    def test_real_pilot_policy_is_diagnostic_only(self):
        self.assertEqual(
            module.approved_diagnostic_uid(ROOT),
            "13eda165-08e0-ec79-026a-985b37e2eb9e",
        )

    def test_missing_policy_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            self.assertEqual(module.approved_diagnostic_uid(Path(temporary)), "")

    def _policy_repo(self):
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        (root / "config" / "worker-roles").mkdir(parents=True)
        (root / "config" / "worker-execution-enrollment.json").write_text(
            (ROOT / "config" / "worker-execution-enrollment.json").read_text()
        )
        (root / "config" / "worker-roles" / "jason-development-worker-v1.json").write_text(
            (ROOT / "config" / "worker-roles" / "jason-development-worker-v1.json").read_text()
        )
        return temp, root

    def test_reject_changed_target(self):
        temp, root = self._policy_repo()
        with temp:
            f = root / "config" / "worker-execution-enrollment.json"
            p = json.loads(f.read_text())
            p["device_uid"] = "00000000-0000-0000-0000-000000000000"
            f.write_text(json.dumps(p))
            with self.assertRaisesRegex(module.WorkerEnrollmentError, "contract"):
                module.approved_diagnostic_uid(root)

    def test_reject_autonomous_shell_classification(self):
        temp, root = self._policy_repo()
        with temp:
            f = root / "config" / "worker-execution-enrollment.json"
            p = json.loads(f.read_text())
            p["approval_mode"] = "standing_safe"
            f.write_text(json.dumps(p))
            with self.assertRaisesRegex(module.WorkerEnrollmentError, "scope"):
                module.approved_diagnostic_uid(root)

    def test_reject_unexpected_fields(self):
        temp, root = self._policy_repo()
        with temp:
            f = root / "config" / "worker-execution-enrollment.json"
            p = json.loads(f.read_text())
            p["arbitrary_commands_allowed"] = True
            f.write_text(json.dumps(p))
            with self.assertRaisesRegex(module.WorkerEnrollmentError, "unknown"):
                module.approved_diagnostic_uid(root)

    @staticmethod
    def fake_docker_env(runtime, mcp):
        def response(command):
            if command[2] == "jason-runtime":
                return json.dumps(runtime)
            return json.dumps(mcp)
        return response

    def test_same_exact_device_uid_both_planes(self):
        entry = module.ENV_NAME + "=13eda165-08e0-ec79-026a-985b37e2eb9e"
        self.assertEqual(
            module.live_diagnostic_uid(self.fake_docker_env([entry], [entry])),
            "13eda165-08e0-ec79-026a-985b37e2eb9e",
        )

    def test_reject_missing_and_duplicate(self):
        entry = module.ENV_NAME + "=a"
        with self.assertRaisesRegex(module.WorkerEnrollmentError, "missing or duplicated"):
            module.live_diagnostic_uid(self.fake_docker_env([], [entry]))
        with self.assertRaisesRegex(module.WorkerEnrollmentError, "missing or duplicated"):
            module.live_diagnostic_uid(self.fake_docker_env([entry, entry], [entry]))

    def test_reject_mismatched_planes(self):
        with self.assertRaisesRegex(module.WorkerEnrollmentError, "differs"):
            module.live_diagnostic_uid(self.fake_docker_env([
                module.ENV_NAME + "=a"
            ], [module.ENV_NAME + "=b"]))

    def test_release_manager_threads_binding_through_both_deployers(self):
        runner = (ROOT / "tools" / "release_manager_host_runner.py").read_text()
        mcp = (ROOT / "infrastructure" / "jason-mcp" / "production-deploy.sh").read_text()
        runtime = (ROOT / "infrastructure" / "jason-runtime" / "production-deploy.sh").read_text()
        self.assertIn("approved_diagnostic_uid(deploy_worktree)", runner)
        self.assertIn("env[worker_enrollment.ENV_NAME] = candidate_worker_uid", runner)
        self.assertIn("live_diagnostic_uid(output) != candidate_worker_uid", runner)
        self.assertIn("rollback_env[worker_enrollment.ENV_NAME] = previous_worker_uid", runner)
        self.assertIn("--set-env \"JASON_DATTO_LINUX_SHELL_WORKER_DEVICE_UID=", mcp)
        self.assertIn("--set-env \"JASON_DATTO_LINUX_SHELL_WORKER_DEVICE_UID=", runtime)


if __name__ == "__main__":
    unittest.main()
