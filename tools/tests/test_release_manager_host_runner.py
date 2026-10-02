import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
GATE_PATH = ROOT / "tools" / "release_manager_gate.py"
RUNNER_PATH = ROOT / "tools" / "release_manager_host_runner.py"

gate_spec = importlib.util.spec_from_file_location("release_manager_gate", GATE_PATH)
gate_module = importlib.util.module_from_spec(gate_spec)
assert gate_spec.loader is not None
sys.modules["release_manager_gate"] = gate_module
gate_spec.loader.exec_module(gate_module)

runner_spec = importlib.util.spec_from_file_location("release_manager_host_runner", RUNNER_PATH)
runner = importlib.util.module_from_spec(runner_spec)
assert runner_spec.loader is not None
sys.modules["release_manager_host_runner"] = runner
runner_spec.loader.exec_module(runner)

SHA_A = "a" * 40
SHA_B = "b" * 40


class ReleaseManagerHostRunnerTests(unittest.TestCase):
    def test_release_id_is_deterministic(self):
        self.assertEqual(runner.record_id(SHA_A), "release-" + "a" * 16)

    def test_preprod_mutation_guards_disable_known_write_paths(self):
        self.assertEqual(runner.MUTATION_ENV_OVERRIDES["JASON_AUTOTASK_MUTATION_ENABLED"], "false")
        self.assertEqual(runner.MUTATION_ENV_OVERRIDES["JASON_AUTONOMY_WORKER_ENABLED"], "false")
        self.assertEqual(runner.MUTATION_ENV_OVERRIDES["JASON_SUPPORT_REPAIR_AUTONOMY_ENABLED"], "false")
        self.assertEqual(runner.MUTATION_ENV_OVERRIDES["JASON_AUTOTASK_PROCUREMENT_MCP_PROFILE"], "")

    def test_create_record_builds_once_after_protected_checks(self):
        with tempfile.TemporaryDirectory() as td:
            state_root = Path(td)
            with (
                patch.object(runner, "live_runtime", return_value={"revision": SHA_B, "image_id": "sha256:old"}),
                patch.object(runner, "verify_candidate_on_main"),
                patch.object(runner, "changed_files", return_value=["docs/operations/example.md"]),
                patch.object(runner, "required_checks", return_value=["runtime-service"]),
                patch.object(runner, "github_checks", return_value={"passed": True, "required": ["runtime-service"], "failures": []}),
                patch.object(runner, "build_candidate", return_value=("jason-runtime:release-test", "sha256:new")),
            ):
                record = runner.create_record(
                    repo=ROOT,
                    state_root=state_root,
                    candidate_sha=SHA_A,
                    rollback_sha=SHA_B,
                    change_class="release_blocker",
                    owner_approved=False,
                )
            self.assertEqual(record["state"], "release_candidate")
            self.assertEqual(record["release_candidate"]["candidate_sha"], SHA_A)
            self.assertEqual(record["release_candidate"]["artifact_digest"], "sha256:new")
            self.assertTrue((state_root / "records" / f"{record['release_id']}.json").exists())

    def test_create_record_rejects_required_check_failure(self):
        with tempfile.TemporaryDirectory() as td:
            with (
                patch.object(runner, "live_runtime", return_value={"revision": SHA_B, "image_id": "sha256:old"}),
                patch.object(runner, "verify_candidate_on_main"),
                patch.object(runner, "changed_files", return_value=[]),
                patch.object(runner, "required_checks", return_value=["runtime-service"]),
                patch.object(runner, "github_checks", return_value={"passed": False, "required": ["runtime-service"], "failures": ["runtime-service:failure"]}),
            ):
                with self.assertRaisesRegex(runner.ReleaseManagerError, "required protected checks"):
                    runner.create_record(
                        repo=ROOT,
                        state_root=Path(td),
                        candidate_sha=SHA_A,
                        rollback_sha=SHA_B,
                        change_class="release_blocker",
                        owner_approved=False,
                    )

    def test_promote_eligible_serializes_to_one_release(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            records = root / "records"
            records.mkdir()
            for index, sha in enumerate((SHA_A, "c" * 40), start=1):
                payload = {
                    "release_id": runner.record_id(sha),
                    "state": "production_eligible",
                    "created_at": f"2026-10-02T0{index}:00:00+00:00",
                }
                runner.atomic_json(records / f"{payload['release_id']}.json", payload)

            promoted = []
            def fake_deploy(repo, state_root, record):
                promoted.append(record["release_id"])
                return record

            with patch.object(runner, "deploy_production", side_effect=fake_deploy):
                self.assertTrue(runner.promote_eligible(ROOT, root))
            self.assertEqual(len(promoted), 1)

    def test_production_preflight_uses_exact_candidate_worktree(self):
        with tempfile.TemporaryDirectory() as td:
            state_root = Path(td)
            candidate_tree = state_root / "candidate-tree"
            script = candidate_tree / "infrastructure" / "jason-runtime" / "production-deploy.sh"
            script.parent.mkdir(parents=True)
            script.write_text("#!/bin/sh\n", encoding="utf-8")
            with (
                patch.object(runner, "worktree", return_value=candidate_tree) as make_tree,
                patch.object(runner, "remove_worktree") as remove_tree,
                patch.object(runner, "run", return_value="PREFLIGHT=PASS") as run_command,
            ):
                runner.production_preflight(ROOT, state_root, "image:test", SHA_A)
            make_tree.assert_called_once_with(ROOT, state_root, SHA_A)
            self.assertEqual(run_command.call_args.args[0][0], str(script))
            self.assertEqual(run_command.call_args.kwargs["cwd"], candidate_tree)
            remove_tree.assert_called_once_with(ROOT, candidate_tree)

    def test_installer_source_contains_non_login_user_bus_binding(self):
        installer = (ROOT / "tools" / "install_release_manager.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("XDG_RUNTIME_DIR", installer)
        self.assertIn("DBUS_SESSION_BUS_ADDRESS", installer)
        self.assertIn("unix:path=/run/user/{uid}/bus", installer)

    def test_service_uses_immutable_installed_source_link(self):
        service = (
            ROOT
            / "infrastructure"
            / "openclaw-operations"
            / "systemd"
            / "user"
            / "jason-release-manager.service"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "/home/al/.local/lib/jason/release-manager-source",
            service,
        )
        self.assertNotIn("/home/al/projects/jason", service)

    def test_preprod_state_clone_uses_live_container_not_host_cp(self):
        source = (ROOT / "tools" / "release_manager_host_runner.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('"docker",\n            "cp"', source)
        self.assertIn('f"jason-runtime:{container_path}/."', source)
        self.assertNotIn('run(["cp", "-a", source', source)

    def test_postcutover_verifier_waits_for_healthy_runtime(self):
        with patch.object(
            runner,
            "output",
            side_effect=[
                '[{"State":{"Health":{"Status":"starting"}}}]',
                '[{"State":{"Health":{"Status":"healthy"}},"Config":{"Labels":{"com.teamaot.jason.source_revision":"'
                + SHA_A
                + '"}},"Image":"sha256:test"}]',
                '[{"State":{"Health":{"Status":"healthy"}},"Config":{"Labels":{"com.teamaot.jason.source_revision":"'
                + SHA_A
                + '"}},"Image":"sha256:test"}]',
            ],
        ), patch.object(runner.time, "sleep"):
            result = runner.wait_live_runtime(attempts=2, interval_seconds=0)
        self.assertEqual(result["revision"], SHA_A)

    def test_exact_sha_rejects_symbolic_ref(self):
        with self.assertRaises(runner.ReleaseManagerError):
            runner.exact_sha("main", "candidate_sha")


if __name__ == "__main__":
    unittest.main()
