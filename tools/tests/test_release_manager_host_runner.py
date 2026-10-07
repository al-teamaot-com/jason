import importlib.util
import sys
import tempfile
import unittest
from datetime import datetime, timezone
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

    def test_production_window_is_continuous_24x7(self):
        for observed in (
            datetime(2026, 10, 5, 13, 0, tzinfo=timezone.utc),
            datetime(2026, 10, 5, 21, 0, tzinfo=timezone.utc),
            datetime(2026, 10, 6, 9, 0, tzinfo=timezone.utc),
            datetime(2026, 10, 6, 20, 59, tzinfo=timezone.utc),
            datetime(2026, 10, 4, 12, 0, tzinfo=timezone.utc),
        ):
            self.assertTrue(runner.production_window_open(observed))

    def test_production_window_rejects_naive_time(self):
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            runner.production_window_open(datetime(2026, 10, 5, 12, 0))

    def test_preprod_mutation_guards_disable_known_write_paths(self):
        self.assertEqual(runner.MUTATION_ENV_OVERRIDES["JASON_AUTOTASK_MUTATION_ENABLED"], "false")
        self.assertEqual(runner.MUTATION_ENV_OVERRIDES["JASON_AUTONOMY_WORKER_ENABLED"], "false")
        self.assertEqual(runner.MUTATION_ENV_OVERRIDES["JASON_SUPPORT_REPAIR_AUTONOMY_ENABLED"], "false")
        self.assertEqual(runner.MUTATION_ENV_OVERRIDES["JASON_AUTOTASK_PROCUREMENT_MCP_PROFILE"], "")

    def test_github_checks_reads_required_check_beyond_first_page(self):
        import io
        import json

        first_page = {
            "check_runs": [
                {
                    "id": index + 1000,
                    "name": f"noise-{index}",
                    "status": "completed",
                    "conclusion": "success",
                }
                for index in range(100)
            ]
        }
        second_page = {
            "check_runs": [
                {
                    "id": 5000,
                    "name": "runtime-service",
                    "status": "completed",
                    "conclusion": "success",
                }
            ]
        }
        responses = [
            io.BytesIO(json.dumps(first_page).encode("utf-8")),
            io.BytesIO(json.dumps(second_page).encode("utf-8")),
        ]
        with patch.object(runner.urllib.request, "urlopen", side_effect=responses) as urlopen:
            result = runner.github_checks(SHA_A, ["runtime-service"])
        self.assertTrue(result["passed"])
        self.assertEqual(result["failures"], [])
        self.assertEqual(urlopen.call_count, 2)
        self.assertIn("per_page=100&page=2", urlopen.call_args_list[1].args[0].full_url)

    def test_support_repair_state_context_classifies_active_and_blocked(self):
        import json

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state_root = root / "release-manager"
            support_root = root / "support-repair"
            support_root.mkdir(parents=True)
            (support_root / "state.json").write_text(
                json.dumps(
                    {
                        "items": {
                            "SUPPORT-AUTO-A": {"phase": "blocked"},
                            "SUPPORT-AUTO-B": {"phase": "implementing"},
                            "SUPPORT-AUTO-C": {"phase": "identified"},
                        }
                    }
                ),
                encoding="utf-8",
            )
            active, blocked = runner.support_repair_state_context(state_root)
            self.assertEqual(active, ["SUPPORT-AUTO-B"])
            self.assertEqual(blocked, ["SUPPORT-AUTO-A"])

    def test_feature_gate_ignores_support_rows_without_open_repair_issue(self):
        with tempfile.TemporaryDirectory() as td:
            record = {
                "state": "requested",
                "change_class": "feature",
                "active_support_repairs": [],
            }
            with (
                patch.object(runner, "open_support_issue_ids", return_value=set()),
                patch.object(
                    runner,
                    "support_repair_state_context",
                    return_value=([], []),
                ),
            ):
                runner.gate_transition(
                    ROOT,
                    Path(td),
                    record,
                    "development",
                )
            self.assertEqual(record["state"], "development")
            self.assertEqual(record["eligible_support_items"], [])

    def test_create_record_builds_once_after_protected_checks(self):
        with tempfile.TemporaryDirectory() as td:
            state_root = Path(td)
            with (
                patch.object(
                    runner,
                    "live_production_alignment",
                    return_value={
                        "runtime_revision": SHA_B,
                        "mcp_revision": SHA_B,
                        "host_revision": SHA_B,
                    },
                ),
                patch.object(runner, "verify_candidate_on_main"),
                patch.object(runner, "changed_files", return_value=["docs/operations/example.md"]),
                patch.object(runner, "required_checks", return_value=["runtime-service"]),
                patch.object(runner, "github_checks", return_value={"passed": True, "required": ["runtime-service"], "failures": []}),
                patch.object(
                    runner,
                    "build_candidate",
                    return_value=("jason-runtime:release-test", "sha256:new"),
                ),
                patch.object(
                    runner,
                    "build_mcp_candidate",
                    return_value=(
                        "jason-mcp:release-test",
                        "sha256:mcp-new",
                        "sha256:mcp-base",
                    ),
                ),
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
            self.assertEqual(
                record["release_candidate"]["mcp_artifact_digest"],
                "sha256:mcp-new",
            )
            self.assertTrue((state_root / "records" / f"{record['release_id']}.json").exists())

    def test_create_record_rejects_required_check_failure(self):
        with tempfile.TemporaryDirectory() as td:
            with (
                patch.object(
                    runner,
                    "live_production_alignment",
                    return_value={
                        "runtime_revision": SHA_B,
                        "mcp_revision": SHA_B,
                        "host_revision": SHA_B,
                    },
                ),
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

    def test_create_record_fails_closed_on_divergent_baseline(self):
        with tempfile.TemporaryDirectory() as td:
            with (
                patch.object(
                    runner,
                    "live_production_alignment",
                    side_effect=runner.ReleaseManagerError(
                        "production alignment mismatch"
                    ),
                ),
                patch.object(runner, "build_candidate") as build_runtime,
                patch.object(runner, "build_mcp_candidate") as build_mcp,
            ):
                with self.assertRaisesRegex(
                    runner.ReleaseManagerError,
                    "production alignment mismatch",
                ):
                    runner.create_record(
                        repo=ROOT,
                        state_root=Path(td),
                        candidate_sha=SHA_A,
                        rollback_sha=SHA_B,
                        change_class="release_blocker",
                        owner_approved=True,
                    )
            build_runtime.assert_not_called()
            build_mcp.assert_not_called()



    def test_approve_release_records_exact_sha_and_is_auditable(self):
        with tempfile.TemporaryDirectory() as td:
            state_root = Path(td)
            record = {
                "state": "production_eligible",
                "release_candidate": {
                    "candidate_sha": SHA_A,
                    "image": "jason-runtime:test",
                    "artifact_digest": "sha256:runtime",
                    "mcp_image": "jason-mcp:test",
                    "mcp_artifact_digest": "sha256:mcp",
                },
                "owner_approval": {"approved": False},
                "history": [],
            }
            with (
                patch.object(runner, "load_record", return_value=record),
                patch.object(runner, "verify_candidate_on_main"),
                patch.object(
                    runner,
                    "image_id",
                    side_effect=lambda image: {
                        "jason-runtime:test": "sha256:runtime",
                        "jason-mcp:test": "sha256:mcp",
                    }[image],
                ),
                patch.object(runner, "save_record") as save_record,
            ):
                approved = runner.approve_release(
                    ROOT,
                    state_root,
                    release_id="release-test",
                    candidate_sha=SHA_A,
                )
            self.assertTrue(approved["owner_approval"]["approved"])
            self.assertEqual(approved["owner_approval"]["candidate_sha"], SHA_A)
            self.assertEqual(
                approved["owner_approval"]["source"],
                "explicit_owner_instruction",
            )
            self.assertEqual(
                approved["history"][-1]["gate"],
                "owner_approval_recorded",
            )
            save_record.assert_called_once_with(state_root, record)

    def test_approve_release_is_idempotent_for_same_exact_sha(self):
        record = {
            "state": "production_eligible",
            "release_candidate": {
                "candidate_sha": SHA_A,
                "image": "jason-runtime:test",
                "artifact_digest": "sha256:runtime",
                "mcp_image": "jason-mcp:test",
                "mcp_artifact_digest": "sha256:mcp",
            },
            "owner_approval": {
                "approved": True,
                "candidate_sha": SHA_A,
                "source": "explicit_owner_instruction",
                "recorded_at": "2026-10-07T18:56:58+00:00",
            },
            "history": [],
        }
        with (
            patch.object(runner, "load_record", return_value=record),
            patch.object(runner, "verify_candidate_on_main"),
            patch.object(
                runner,
                "image_id",
                side_effect=lambda image: {
                    "jason-runtime:test": "sha256:runtime",
                    "jason-mcp:test": "sha256:mcp",
                }[image],
            ),
            patch.object(runner, "save_record") as save_record,
        ):
            approved = runner.approve_release(
                ROOT,
                Path("/tmp"),
                release_id="release-test",
                candidate_sha=SHA_A,
            )
        self.assertIs(approved, record)
        save_record.assert_not_called()

    def test_approve_release_rejects_sha_mismatch(self):
        record = {
            "state": "production_eligible",
            "release_candidate": {"candidate_sha": SHA_A},
            "owner_approval": {"approved": False},
        }
        with patch.object(runner, "load_record", return_value=record):
            with self.assertRaisesRegex(
                runner.ReleaseManagerError,
                "candidate SHA does not match",
            ):
                runner.approve_release(
                    ROOT,
                    Path("/tmp"),
                    release_id="release-test",
                    candidate_sha=SHA_B,
                )

    def test_approve_release_rejects_noneligible_state(self):
        record = {
            "state": "release_candidate",
            "release_candidate": {"candidate_sha": SHA_A},
        }
        with patch.object(runner, "load_record", return_value=record):
            with self.assertRaisesRegex(
                runner.ReleaseManagerError,
                "production_eligible",
            ):
                runner.approve_release(
                    ROOT,
                    Path("/tmp"),
                    release_id="release-test",
                    candidate_sha=SHA_A,
                )

    def test_production_transaction_lock_blocks_second_promoter(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            first_record = {
                "release_id": "release-first",
                "release_candidate": {"candidate_sha": SHA_A},
            }
            second_record = {
                "release_id": "release-second",
                "release_candidate": {"candidate_sha": SHA_B},
            }
            first = runner.acquire_production_transaction_lock(ROOT, root, first_record)
            try:
                with self.assertRaisesRegex(
                    runner.ReleaseManagerBusy,
                    "another production release transaction is already active",
                ):
                    runner.acquire_production_transaction_lock(ROOT, root, second_record)
                metadata = (root / "production-transaction.lock").read_text(encoding="utf-8")
                self.assertIn("release-first", metadata)
                self.assertIn(SHA_A, metadata)
            finally:
                runner.release_production_transaction_lock(first)

            second = runner.acquire_production_transaction_lock(ROOT, root, second_record)
            runner.release_production_transaction_lock(second)

    def test_deploy_releases_transaction_lock_after_failure(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            release = {
                "release_id": "release-failing",
                "release_candidate": {"candidate_sha": SHA_A},
            }
            with patch.object(
                runner,
                "_deploy_production_locked",
                side_effect=runner.ReleaseManagerError("forced failure"),
            ):
                with self.assertRaisesRegex(runner.ReleaseManagerError, "forced failure"):
                    runner.deploy_production(ROOT, root, release)

            followup = runner.acquire_production_transaction_lock(
                ROOT,
                root,
                {
                    "release_id": "release-followup",
                    "release_candidate": {"candidate_sha": SHA_B},
                },
            )
            runner.release_production_transaction_lock(followup)

    def test_promote_eligible_treats_busy_transaction_as_queued(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            records = root / "records"
            records.mkdir()
            payload = {
                "release_id": runner.record_id(SHA_A),
                "state": "production_eligible",
                "created_at": "2026-10-07T17:00:00+00:00",
            }
            runner.atomic_json(records / f"{payload['release_id']}.json", payload)
            with (
                patch.object(runner, "production_window_open", return_value=True),
                patch.object(
                    runner,
                    "production_gate_result",
                    return_value={"allowed": True, "protected_core": False, "reasons": []},
                ),
                patch.object(
                    runner,
                    "deploy_production",
                    side_effect=runner.ReleaseManagerBusy("busy"),
                ),
            ):
                self.assertFalse(runner.promote_eligible(ROOT, root))

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

            with (
                patch.object(runner, "production_window_open", return_value=True),
                patch.object(
                    runner,
                    "production_gate_result",
                    return_value={"allowed": True, "protected_core": False, "reasons": []},
                ),
                patch.object(runner, "deploy_production", side_effect=fake_deploy),
            ):
                self.assertTrue(runner.promote_eligible(ROOT, root))
            self.assertEqual(len(promoted), 1)

    def test_promote_eligible_skips_unapproved_protected_core_and_continues(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            records = root / "records"
            records.mkdir()
            first_sha = SHA_A
            second_sha = "c" * 40
            for index, sha in enumerate((first_sha, second_sha), start=1):
                payload = {
                    "release_id": runner.record_id(sha),
                    "state": "production_eligible",
                    "created_at": f"2026-10-02T0{index}:00:00+00:00",
                }
                runner.atomic_json(records / f"{payload['release_id']}.json", payload)

            def gate_result(repo, record):
                if record["release_id"] == runner.record_id(first_sha):
                    return {
                        "allowed": False,
                        "protected_core": True,
                        "reasons": [
                            "protected-core release requires explicit owner approval",
                            "owner approval is not bound to the exact candidate SHA",
                        ],
                    }
                return {"allowed": True, "protected_core": False, "reasons": []}

            promoted = []
            with (
                patch.object(runner, "production_window_open", return_value=True),
                patch.object(runner, "production_gate_result", side_effect=gate_result),
                patch.object(
                    runner,
                    "deploy_production",
                    side_effect=lambda repo, state_root, record: promoted.append(
                        record["release_id"]
                    ),
                ),
            ):
                self.assertTrue(runner.promote_eligible(ROOT, root))

            self.assertEqual(promoted, [runner.record_id(second_sha)])


    def test_worktree_failure_does_not_strand_false_production_state(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            record = {
                "release_id": runner.record_id(SHA_A),
                "state": "production_eligible",
                "rollback_sha": SHA_B,
                "release_candidate": {
                    "candidate_sha": SHA_A,
                    "image": "jason-runtime:test",
                    "artifact_digest": "sha256:runtime",
                    "mcp_image": "jason-mcp:test",
                    "mcp_artifact_digest": "sha256:mcp",
                },
            }
            def image(value):
                return "sha256:runtime" if value == "jason-runtime:test" else "sha256:mcp"
            with (
                patch.object(runner, "image_id", side_effect=image),
                patch.object(runner, "require_host_reconciler_ready"),
                patch.object(runner, "live_production_alignment", return_value={}),
                patch.object(runner, "worktree", side_effect=runner.ReleaseManagerError("repo unavailable")),
                patch.object(runner, "save_record") as save_record,
            ):
                with self.assertRaisesRegex(runner.ReleaseManagerError, "repo unavailable"):
                    runner.deploy_production(ROOT, root, record)
            self.assertEqual(record["state"], "production_eligible")
            save_record.assert_not_called()

    def test_production_preflight_uses_exact_candidate_worktree_for_runtime_and_mcp(self):
        with tempfile.TemporaryDirectory() as td:
            state_root = Path(td)
            candidate_tree = state_root / "candidate-tree"
            runtime_script = (
                candidate_tree
                / "infrastructure"
                / "jason-runtime"
                / "production-deploy.sh"
            )
            mcp_script = (
                candidate_tree
                / "infrastructure"
                / "jason-mcp"
                / "production-deploy.sh"
            )
            runtime_script.parent.mkdir(parents=True)
            mcp_script.parent.mkdir(parents=True)
            runtime_script.write_text("#!/bin/sh\n", encoding="utf-8")
            mcp_script.write_text("#!/bin/sh\n", encoding="utf-8")
            with (
                patch.object(runner, "require_host_reconciler_ready") as host_ready,
                patch.object(runner, "worktree", return_value=candidate_tree) as make_tree,
                patch.object(runner, "remove_worktree") as remove_tree,
                patch.object(runner, "run", return_value="PREFLIGHT=PASS") as run_command,
            ):
                runner.production_preflight(
                    ROOT,
                    state_root,
                    "jason-runtime:test",
                    "jason-mcp:test",
                    SHA_A,
                )
            host_ready.assert_called_once_with(state_root)
            make_tree.assert_called_once_with(ROOT, state_root, SHA_A)
            self.assertEqual(run_command.call_count, 2)
            self.assertEqual(
                run_command.call_args_list[0].args[0][0],
                str(runtime_script),
            )
            self.assertEqual(
                run_command.call_args_list[1].args[0][0],
                str(mcp_script),
            )
            self.assertEqual(
                run_command.call_args_list[0].kwargs["env"][
                    "JASON_RUNTIME_PRODUCTION_IMAGE"
                ],
                "jason-runtime:test",
            )
            self.assertEqual(
                run_command.call_args_list[1].kwargs["env"][
                    "JASON_MCP_PRODUCTION_IMAGE"
                ],
                "jason-mcp:test",
            )
            remove_tree.assert_called_once_with(ROOT, candidate_tree)

    def test_installer_source_contains_non_login_user_bus_binding(self):
        installer = (ROOT / "tools" / "install_release_manager.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("XDG_RUNTIME_DIR", installer)
        self.assertIn("DBUS_SESSION_BUS_ADDRESS", installer)
        self.assertIn("unix:path=/run/user/{uid}/bus", installer)

    def test_service_uses_managed_git_source_for_candidate_evidence(self):
        service = (
            ROOT
            / "infrastructure"
            / "openclaw-operations"
            / "systemd"
            / "user"
            / "jason-release-manager.service"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "--repo /home/al/.local/lib/jason/engineering-worker-source",
            service,
        )
        self.assertIn(
            "WorkingDirectory=/home/al/.local/lib/jason/engineering-worker-source",
            service,
        )
        self.assertIn(
            "/home/al/.local/lib/jason/release_manager_host_runner.py",
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

    def test_live_production_alignment_requires_runtime_mcp_and_host_same_sha(self):
        mcp = {
            "Config": {"Labels": {"com.teamaot.jason.source_revision": SHA_A}},
            "State": {"Status": "running"},
            "Image": "sha256:mcp",
        }
        with (
            patch.object(runner, "live_runtime", return_value={"revision": SHA_A}),
            patch.object(runner, "output", return_value=__import__("json").dumps([mcp])),
            patch.object(runner.Path, "resolve", return_value=Path("/opt/jason/releases") / SHA_A),
        ):
            result = runner.live_production_alignment(SHA_A)
        self.assertEqual(result["runtime_revision"], SHA_A)
        self.assertEqual(result["mcp_revision"], SHA_A)
        self.assertEqual(result["host_revision"], SHA_A)

    def test_live_production_alignment_fails_closed_on_mcp_or_host_drift(self):
        mcp = {
            "Config": {"Labels": {"com.teamaot.jason.source_revision": SHA_B}},
            "State": {"Status": "running"},
            "Image": "sha256:mcp",
        }
        with (
            patch.object(runner, "live_runtime", return_value={"revision": SHA_A}),
            patch.object(runner, "output", return_value=__import__("json").dumps([mcp])),
            patch.object(runner.Path, "resolve", return_value=Path("/opt/jason/releases") / SHA_A),
        ):
            with self.assertRaisesRegex(runner.ReleaseManagerError, "production alignment mismatch"):
                runner.live_production_alignment(SHA_A)

    def test_preprod_scratch_is_outside_live_openclaw_tree(self):
        state_root = Path("/var/lib/jason/openclaw/release-manager")
        scratch = runner.preprod_scratch_path(state_root, "release-test")
        self.assertEqual(scratch, Path("/var/lib/jason/release-manager-preprod/release-test"))
        self.assertFalse(str(scratch).startswith("/var/lib/jason/openclaw/"))

    def test_preprod_clone_rejects_destination_nested_under_live_source(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td)
            state_root = source / "openclaw" / "release-manager"
            state_root.mkdir(parents=True)
            live = {
                "inspect": {
                    "Config": {"Env": [], "Labels": {}},
                    "HostConfig": {"NetworkMode": "bridge", "Tmpfs": {}},
                    "Mounts": [
                        {
                            "Type": "bind",
                            "Source": str(source),
                            "Destination": "/var/lib/jason/openclaw",
                            "RW": True,
                        }
                    ],
                    "NetworkSettings": {"Networks": {}},
                }
            }
            with self.assertRaisesRegex(runner.ReleaseManagerError, "nested under live state source"):
                runner.create_preprod_container(
                    live=live,
                    candidate_image="jason-runtime:test",
                    candidate_sha=SHA_A,
                    state_root=state_root,
                    release_id="release-test",
                )

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

    def test_prepare_release_discovers_live_rollback_and_runs_preprod(self):
        with tempfile.TemporaryDirectory() as td:
            state_root = Path(td)
            created = {
                "release_id": runner.record_id(SHA_A),
                "state": "release_candidate",
                "release_candidate": {
                    "candidate_sha": SHA_A,
                    "artifact_digest": "sha256:test",
                    "image": "jason-runtime:test",
                    "immutable": True,
                },
            }
            with (
                patch.object(runner, "live_runtime", return_value={"revision": SHA_B}),
                patch.object(runner, "create_record", return_value=created) as create_record,
                patch.object(runner, "run_preproduction", return_value={**created, "state": "production_eligible"}) as preprod,
            ):
                result = runner.prepare_release(
                    ROOT,
                    state_root,
                    SHA_A,
                    "todo",
                )
            self.assertEqual(result["state"], "production_eligible")
            self.assertEqual(create_record.call_args.kwargs["rollback_sha"], SHA_B)
            self.assertFalse(create_record.call_args.kwargs["owner_approved"])
            preprod.assert_called_once()

    def test_prepare_release_is_idempotent_after_production_eligible(self):
        with tempfile.TemporaryDirectory() as td:
            state_root = Path(td)
            release_id = runner.record_id(SHA_A)
            runner.atomic_json(
                state_root / "records" / f"{release_id}.json",
                {
                    "release_id": release_id,
                    "state": "production_eligible",
                    "release_candidate": {"candidate_sha": SHA_A},
                },
            )
            with patch.object(runner, "live_runtime") as live:
                result = runner.prepare_release(
                    ROOT,
                    state_root,
                    SHA_A,
                    "todo",
                )
            self.assertEqual(result["state"], "production_eligible")
            live.assert_not_called()

    def test_exact_sha_rejects_symbolic_ref(self):
        with self.assertRaises(runner.ReleaseManagerError):
            runner.exact_sha("main", "candidate_sha")


    def test_publish_production_closeout_requires_documentation_and_board_success(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            script = repo / "tools" / "publish_documentation_reconciliation.sh"
            script.parent.mkdir(parents=True)
            script.write_text("#!/bin/sh\n", encoding="utf-8")
            with patch.object(
                runner,
                "run",
                return_value=(
                    "DOCUMENTATION_SUCCESS_RECONCILIATION=PASS mode=production\n"
                    "CONTROL_BOARD_PUBLICATION=PASS"
                ),
            ) as execute:
                result = runner.publish_production_closeout(repo, SHA_A)
            self.assertEqual(result, {"documentation": "pass", "control_board": "pass"})
            self.assertEqual(execute.call_args.args[0][1:], ["production", SHA_A])

    def test_publish_production_closeout_fails_closed_without_board_publication(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            script = repo / "tools" / "publish_documentation_reconciliation.sh"
            script.parent.mkdir(parents=True)
            script.write_text("#!/bin/sh\n", encoding="utf-8")
            with patch.object(
                runner,
                "run",
                return_value="DOCUMENTATION_SUCCESS_RECONCILIATION=PASS mode=production",
            ):
                with self.assertRaisesRegex(runner.ReleaseManagerError, "control-board publication"):
                    runner.publish_production_closeout(repo, SHA_A)


if __name__ == "__main__":
    unittest.main()


def test_release_manager_preflights_managed_host_reconciliation_contract():
    text = (ROOT / "tools" / "release_manager_host_runner.py").read_text(encoding="utf-8")
    assert "verify_candidate_host_reconciliation_contract" in text
    assert "verify_host_reconciliation_evidence" in text
    assert "host_reconciliation_candidate_script_verified" in text
    assert "managed_engineering_source_verified" in text
    assert "managed_documentation_source_verified" in text
    assert "developer_checkout_dependency_absent" in text
    assert "host_reconciliation_preflight_passed" in text
