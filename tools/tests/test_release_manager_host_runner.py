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
    def test_root_host_reconciliation_is_always_production_control_core(self):
        for path in (
            "tools/reconcile_production_host_services.sh",
            "tools/reconcile_managed_unit_delta.py",
        ):
            for change_class in ("support", "release_blocker", "todo", "feature"):
                self.assertEqual(
                    runner.classify_change_risk(change_class, [path]),
                    "production_control_core",
                )

    def test_owner_release_approval_code_is_protected_control_core(self):
        import json
        policy = json.loads((ROOT / "config/release-manager-policy.json").read_text())
        import fnmatch
        names = (
            "implementation/runtime_service/src/jason_runtime/mobile_release_approval.py",
            "implementation/runtime_service/src/jason_runtime/universal_teams_approval.py",
            "tools/release_mobile_approval_consumer.py",
            "implementation/runtime_service/src/jason_runtime/playbook_autonomy_review.py",
            "implementation/connectors/microsoft_graph/teams_approval_channel.py",
        )
        for name in names:
            self.assertEqual(runner.classify_change_risk("feature", [name]), "production_control_core")
            self.assertTrue(any(fnmatch.fnmatch(name, pat) for pat in policy["protected_core_globs"]))

    def test_owner_approval_status_notice_does_not_imply_teams_card_or_release(self):
        import inspect
        source = inspect.getsource(runner.promote_eligible)
        self.assertIn("STATUS ONLY - NOT AN APPROVAL CARD", source)
        self.assertIn("BLOCKED: no actionable Teams approval is enabled", source)
        self.assertIn("Only a separate", source)
        self.assertIn("authenticated owner Approve click", source)
        self.assertIn("this notice", source.casefold())
        self.assertIn("owner_action=owner_instruction", source)
        self.assertIn("if owner_teams_eligible:", source)

    def test_live_owner_release_mode_does_not_trust_policy_file_alone(self):
        expected = {"inspect": {"Config": {"Env": [
            "SAFE_CONSOLE=silent",
            "JASON_RELEASE_MOBILE_APPROVAL_MODE=owner_reviewed",
        ]}}}
        self.assertEqual(runner.live_release_mobile_approval_mode(expected), "owner_reviewed")
        expected["inspect"]["Config"]["Env"][-1] = "JASON_RELEASE_MOBILE_APPROVAL_MODE=owner_only_pilot"
        self.assertEqual(runner.live_release_mobile_approval_mode(expected), "owner_only_pilot")
        for values in (
            [], ["JASON_RELEASE_MOBILE_APPROVAL_MODE=off"],
            ["JASON_RELEASE_MOBILE_APPROVAL_MODE=unexpected"],
            ["JASON_RELEASE_MOBILE_APPROVAL_MODE=owner_reviewed"] * 2,
        ):
            self.assertEqual(
                runner.live_release_mobile_approval_mode({"inspect": {"Config": {"Env": values}}}),
                "off",
            )

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
        self.assertEqual(runner.MUTATION_ENV_OVERRIDES["JASON_UNIVERSAL_APPROVAL_MODE"], "off")
        self.assertEqual(runner.MUTATION_ENV_OVERRIDES["JASON_UNIVERSAL_APPROVAL_WORKER_ENABLED"], "false")
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
        responses = [json.dumps(first_page), json.dumps(second_page)]
        with patch.object(runner, "output", side_effect=responses) as gh_output:
            result = runner.github_checks(SHA_A, ["runtime-service"])
        self.assertTrue(result["passed"])
        self.assertEqual(result["failures"], [])
        self.assertEqual(gh_output.call_count, 2)
        self.assertEqual(gh_output.call_args_list[1].args[0][:2], ["gh", "api"])
        self.assertIn("per_page=100&page=2", gh_output.call_args_list[1].args[0][-1])

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
            self.assertEqual(record["risk_profile"], "production_repair")
            self.assertEqual(record["release_manifest"]["candidate_sha"], SHA_A)
            self.assertEqual(record["release_manifest"]["rollback_sha"], SHA_B)
            self.assertEqual(record["release_candidate"]["provenance"]["source_sha"], SHA_A)

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

    def test_consume_owner_approval_request_calls_exact_release_approval_and_archives(self):
        import json

        with tempfile.TemporaryDirectory() as td:
            state_root = Path(td)
            release_id = runner.record_id(SHA_A)
            request_root = state_root / "owner-approval-requests"
            request_root.mkdir(parents=True)
            request = {
                "schema_version": "1.0",
                "release_id": release_id,
                "candidate_sha": SHA_A,
                "approved_by": "owner-al",
                "organization_id": "aot",
                "reason": "approved in chat",
                "recorded_at": "2026-10-07T19:00:00+00:00",
                "source": "authenticated_jason_mcp_owner",
            }
            request_path = request_root / f"{release_id}.json"
            request_path.write_text(json.dumps(request), encoding="utf-8")
            with patch.object(runner, "approve_release") as approve:
                count = runner.consume_owner_approval_requests(ROOT, state_root)
            self.assertEqual(count, 1)
            approve.assert_called_once_with(
                ROOT,
                state_root,
                release_id=release_id,
                candidate_sha=SHA_A,
                source="governed_mcp_owner:owner-al",
            )
            self.assertFalse(request_path.exists())
            archived = (
                state_root
                / "owner-approval-requests-processed"
                / f"{release_id}.json"
            )
            self.assertEqual(json.loads(archived.read_text(encoding="utf-8")), request)

    def test_consume_owner_approval_request_rejects_release_sha_mismatch(self):
        import json

        with tempfile.TemporaryDirectory() as td:
            state_root = Path(td)
            release_id = runner.record_id(SHA_A)
            request_root = state_root / "owner-approval-requests"
            request_root.mkdir(parents=True)
            (request_root / f"{release_id}.json").write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "release_id": release_id,
                        "candidate_sha": SHA_B,
                        "approved_by": "owner-al",
                        "organization_id": "aot",
                    }
                ),
                encoding="utf-8",
            )
            with (
                patch.object(runner, "approve_release") as approve,
                self.assertRaisesRegex(
                    runner.ReleaseManagerError,
                    "release ID does not match candidate SHA",
                ),
            ):
                runner.consume_owner_approval_requests(ROOT, state_root)
            approve.assert_not_called()

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

    def test_repository_policy_owner_approved_automatic_release_mode(self):
        policy = runner.gate.load_json(ROOT / "config" / "release-manager-policy.json")
        self.assertTrue(policy["schedule"]["automatic_promotion_enabled"])
        self.assertTrue(policy["production"]["normal_release_auto_promote_when_eligible"])
        self.assertTrue(policy["production"]["require_owner_approval_for_all"])

    def test_production_drift_timer_is_faster_than_release_evaluation(self):
        timer = (ROOT / "infrastructure/openclaw-operations/systemd/jason-production-drift-watchdog.timer").read_text(encoding="utf-8")
        policy = runner.gate.load_json(ROOT / "config/release-manager-policy.json")
        self.assertIn("OnUnitActiveSec=1min", timer)
        self.assertIn("AccuracySec=10s", timer)
        self.assertEqual(policy["schedule"]["reconcile_interval_minutes"], 5)
        self.assertTrue(policy["production"]["fresh_pre_mutation_health_required"])

    def test_unattended_promotion_is_inert_when_manual_mode_enabled(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with (
                patch.object(
                    runner.gate,
                    "load_json",
                    return_value={"schedule": {"automatic_promotion_enabled": False}},
                ),
                patch.object(runner, "consume_owner_approval_requests") as approvals,
                patch.object(runner, "production_window_open") as window,
                patch.object(runner, "deploy_production") as deploy,
            ):
                self.assertFalse(runner.promote_eligible(ROOT, root))
            approvals.assert_not_called()
            window.assert_not_called()
            deploy.assert_not_called()

    def test_promote_eligible_treats_busy_transaction_as_queued(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            records = root / "records"
            records.mkdir()
            payload = {
                "release_id": runner.record_id(SHA_A),
                "state": "production_eligible",
                "created_at": "2026-10-07T17:00:00+00:00",
                "rollback_sha": SHA_B,
                "release_candidate": {"candidate_sha": SHA_A},
            }
            runner.atomic_json(records / f"{payload['release_id']}.json", payload)
            with (
                patch.object(runner.gate, "load_json", return_value={"schedule": {"automatic_promotion_enabled": True}}),
                patch.object(runner, "production_window_open", return_value=True),
                patch.object(runner, "authoritative_auto_promotion_head", return_value=SHA_A),
                patch.object(runner, "live_runtime", return_value={"revision": SHA_B}),
                patch.object(runner, "live_production_alignment", return_value={}),
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
                    "rollback_sha": SHA_B,
                    "release_candidate": {"candidate_sha": sha},
                }
                runner.atomic_json(records / f"{payload['release_id']}.json", payload)

            promoted = []
            def fake_deploy(repo, state_root, record):
                promoted.append(record["release_id"])
                return record

            with (
                patch.object(runner.gate, "load_json", return_value={"schedule": {"automatic_promotion_enabled": True}}),
                patch.object(runner, "production_window_open", return_value=True),
                patch.object(runner, "authoritative_auto_promotion_head", return_value=SHA_A),
                patch.object(runner, "live_runtime", return_value={"revision": SHA_B}),
                patch.object(runner, "live_production_alignment", return_value={}),
                patch.object(
                    runner,
                    "production_gate_result",
                    return_value={"allowed": True, "protected_core": False, "reasons": []},
                ),
                patch.object(runner, "deploy_production", side_effect=fake_deploy),
            ):
                self.assertTrue(runner.promote_eligible(ROOT, root))
            self.assertEqual(len(promoted), 1)

    def test_promote_eligible_demotes_stale_baseline_without_deploying(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            records = root / "records"
            records.mkdir()
            release_id = runner.record_id(SHA_A)
            runner.atomic_json(
                records / f"{release_id}.json",
                {
                    "release_id": release_id,
                    "state": "production_eligible",
                    "rollback_sha": SHA_B,
                    "release_candidate": {"candidate_sha": SHA_A},
                    "history": [],
                },
            )
            with (
                patch.object(runner.gate, "load_json", return_value={"schedule": {"automatic_promotion_enabled": True}}),
                patch.object(runner, "production_window_open", return_value=True),
                patch.object(runner, "authoritative_auto_promotion_head", return_value=SHA_A),
                patch.object(runner, "live_runtime", return_value={"revision": "c" * 40}),
                patch.object(runner, "live_production_alignment", return_value={}),
                patch.object(runner, "deploy_production") as deploy,
            ):
                result = runner.promote_eligible(ROOT, root)
            self.assertFalse(result)
            deploy.assert_not_called()
            record = runner.load_record(root, release_id)
            self.assertEqual(record["state"], "development")
            self.assertEqual(
                record["revalidation_required"]["reason"],
                "production_baseline_advanced",
            )
            self.assertEqual(
                record["revalidation_required"]["previous_rollback_sha"],
                SHA_B,
            )
            self.assertEqual(
                record["revalidation_required"]["current_production_sha"],
                "c" * 40,
            )

    def test_prepare_release_rebuilds_stale_demoted_candidate(self):
        with tempfile.TemporaryDirectory() as td:
            state_root = Path(td)
            release_id = runner.record_id(SHA_A)
            runner.atomic_json(
                state_root / "records" / f"{release_id}.json",
                {
                    "release_id": release_id,
                    "state": "development",
                    "change_class": "release_blocker",
                    "rollback_sha": SHA_B,
                    "owner_approval": {"approved": True},
                    "release_candidate": {"candidate_sha": SHA_A},
                    "revalidation_required": {
                        "reason": "production_baseline_advanced",
                    },
                    "history": [],
                },
            )
            rebuilt = {
                "release_id": release_id,
                "state": "release_candidate",
                "release_candidate": {"candidate_sha": SHA_A},
            }
            with (
                patch.object(runner, "revalidate_circuit_breaker"),
                patch.object(runner, "live_runtime", return_value={"revision": "c" * 40}),
                patch.object(runner, "create_record", return_value=rebuilt) as create,
                patch.object(
                    runner,
                    "run_preproduction",
                    return_value={**rebuilt, "state": "production_eligible"},
                ) as preprod,
            ):
                result = runner.prepare_release(
                    ROOT,
                    state_root,
                    SHA_A,
                    "release_blocker",
                    owner_approved=True,
                )
            self.assertEqual(result["state"], "production_eligible")
            self.assertEqual(create.call_args.kwargs["rollback_sha"], "c" * 40)
            self.assertTrue(create.call_args.kwargs["owner_approved"])
            preprod.assert_called_once()

    def test_promote_eligible_skips_superseded_and_selects_only_main(self):
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
                    "rollback_sha": SHA_B,
                    "release_candidate": {"candidate_sha": sha},
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
                patch.object(runner.gate, "load_json", return_value={"schedule": {"automatic_promotion_enabled": True}}),
                patch.object(runner, "production_window_open", return_value=True),
                patch.object(runner, "authoritative_auto_promotion_head", return_value=second_sha),
                patch.object(runner, "live_runtime", return_value={"revision": SHA_B}),
                patch.object(runner, "live_production_alignment", return_value={}),
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
                "risk_profile": {"change_risk": "low"},
                "release_manifest": {
                    "candidate_sha": SHA_A, "rollback_sha": SHA_B,
                    "risk_profile": {"change_risk": "low"},
                },
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

    def test_bounded_preprod_filters_only_event_history(self):
        names = (
            "orchestration-events.sqlite3\n"
            "orchestration-events.sqlite3-wal\n"
            "orchestration-events.sqlite3-shm\n"
            "authority.sqlite3\n"
            "governed-execution.sqlite3\n"
            "support-repair\n"
        )
        self.assertEqual(
            runner.bounded_preprod_openclaw_entries(names),
            ["authority.sqlite3", "governed-execution.sqlite3", "support-repair"],
        )

    def test_bounded_preprod_refuses_unsafe_or_oversized_listing(self):
        for value in ("", "../escape\n", "a/b\n", "dup\ndup\n", "entry\n" * 257):
            with self.subTest(value=value[:25]):
                with self.assertRaises(runner.ReleaseManagerError):
                    runner.bounded_preprod_openclaw_entries(value)

    def test_bounded_preprod_rejects_low_disk_before_provider_io(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "clone"
            from unittest.mock import Mock
            with (
                patch.object(runner.shutil, "disk_usage", return_value=Mock(free=5 * 1024**3)),
                patch.object(runner, "run") as command,
            ):
                with self.assertRaisesRegex(runner.ReleaseManagerError, "disk headroom"):
                    runner.copy_state_from_live_container(
                        "/var/lib/jason/openclaw", target,
                    )
            command.assert_not_called()

    def test_bounded_preprod_copies_authority_but_not_large_event_journal(self):
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "clone"
            commands = []
            def record(command):
                commands.append(command)
                if command[:3] == ["docker", "exec", "jason-runtime"]:
                    return "orchestration-events.sqlite3\nauthority.sqlite3\nsupport-repair"
                return ""
            with (
                patch.object(runner.shutil, "disk_usage", return_value=Mock(free=12 * 1024**3)),
                patch.object(runner, "run", side_effect=record),
            ):
                runner.copy_state_from_live_container(
                    "/var/lib/jason/openclaw", target,
                )
            copied = [str(v[2]) for v in commands if v[:2] == ["docker", "cp"]]
            self.assertEqual(len(copied), 2)
            self.assertTrue(any(name.endswith("/authority.sqlite3") for name in copied))
            self.assertTrue(any(name.endswith("/support-repair") for name in copied))
            self.assertFalse(any("orchestration-events" in name for name in copied))

    def test_bounded_preprod_refuses_growth_past_reserve_after_copy(self):
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "clone"
            seen = []
            def record(command):
                seen.append(command)
                if command[:3] == ["docker", "exec", "jason-runtime"]:
                    return "governed-execution.sqlite3"
                return ""
            with (
                patch.object(runner.shutil, "disk_usage",
                             side_effect=[Mock(free=8 * 1024**3), Mock(free=2 * 1024**3)]),
                patch.object(runner, "run", side_effect=record),
            ):
                with self.assertRaisesRegex(runner.ReleaseManagerError, "bounded disk capacity"):
                    runner.copy_state_from_live_container(
                        "/var/lib/jason/openclaw", target,
                    )
            self.assertEqual(len([c for c in seen if c[:2] == ["docker", "cp"]]), 1)

    def test_release_manager_defaults_to_managed_source_not_developer_checkout(self):
        self.assertEqual(
            runner.DEFAULT_REPO,
            Path("/home/al/.local/lib/jason/engineering-worker-source"),
        )

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

    def test_preprod_partial_clone_failure_cleans_only_isolated_scratch(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state_root = root / "openclaw" / "release-manager"
            state_root.mkdir(parents=True)
            live_source = root / "live-openclaw"
            live_source.mkdir()
            release_id = "release-" + "a" * 16
            live = {
                "inspect": {
                    "Config": {"Env": [], "Labels": {}},
                    "HostConfig": {"NetworkMode": "bridge", "Tmpfs": {}},
                    "Mounts": [{
                        "Type": "bind",
                        "Source": str(live_source),
                        "Destination": "/var/lib/jason/openclaw",
                        "RW": True,
                    }],
                    "NetworkSettings": {"Networks": {}},
                },
            }
            with (
                patch.object(runner.subprocess, "run"),
                patch.object(
                    runner, "copy_state_from_live_container",
                    side_effect=OSError("simulated test copy failure"),
                ),
            ):
                with self.assertRaisesRegex(OSError, "simulated test copy failure"):
                    runner.create_preprod_container(
                        live=live, candidate_image="jason-runtime:test",
                        candidate_sha=SHA_A, state_root=state_root,
                        release_id=release_id,
                    )
            scratch = runner.preprod_scratch_path(state_root, release_id)
            self.assertFalse(scratch.exists())
            self.assertTrue(live_source.is_dir())

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

    def test_control_state_circuit_breaker_revalidates_only_against_last_known_good(self):
        with tempfile.TemporaryDirectory() as td:
            state_root = Path(td)
            manifest = {"revision": SHA_B, "complete": True, "observed_at": "2026-10-07T19:00:00+00:00"}
            runner.set_last_known_good(state_root, manifest, release_id="release-baseline")
            record = {
                "release_id": runner.record_id(SHA_A),
                "release_candidate": {"candidate_sha": SHA_A},
            }
            runner.open_circuit_breaker(
                state_root,
                record,
                reason="synthetic failure",
                rollback_verified=True,
            )
            self.assertEqual(
                runner.load_control_state(state_root)["circuit_breaker"]["state"],
                "open",
            )
            with patch.object(runner, "capture_production_manifest", return_value=manifest) as capture:
                state = runner.revalidate_circuit_breaker(state_root)
            capture.assert_called_once_with(SHA_B)
            self.assertEqual(state["circuit_breaker"]["state"], "closed")
            self.assertEqual(
                state["circuit_breaker"]["reason"],
                "authoritative_health_revalidated",
            )

    def test_open_circuit_breaker_fails_closed_without_valid_lkg(self):
        with tempfile.TemporaryDirectory() as td:
            state_root = Path(td)
            runner.save_control_state(
                state_root,
                {
                    "circuit_breaker": {"state": "open", "reason": "test"},
                    "last_known_good": None,
                },
            )
            with self.assertRaisesRegex(runner.ReleaseManagerError, "no valid last-known-good"):
                runner.revalidate_circuit_breaker(state_root)

    def test_controller_identity_pin_rejects_policy_change(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            policy = repo / "config" / "release-manager-policy.json"
            policy.parent.mkdir(parents=True)
            policy.write_text('{"version":1}\n', encoding="utf-8")
            candidate = repo / "tools" / "release_manager_host_runner.py"
            candidate.parent.mkdir(parents=True)
            candidate.write_bytes(b"candidate")
            pin = runner.controller_identity(repo)
            policy.write_text('{"version":2}\n', encoding="utf-8")
            with self.assertRaisesRegex(runner.ReleaseManagerError, "changed mid-transaction: policy_digest"):
                runner.verify_controller_identity(pin, repo)

    def test_operator_recovery_requires_owner_review_backup_and_git_main(self):
        import json

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            old_root = root / SHA_B
            new_root = root / SHA_A
            old = old_root / "tools" / "release_manager_host_runner.py"
            old.parent.mkdir(parents=True)
            old.write_bytes(b"root-owned-original-runner")
            new = new_root / "tools" / "release_manager_host_runner.py"
            new.parent.mkdir(parents=True)
            new.write_bytes(b"reviewed-fixed-runner")
            policy = new_root / "config" / "release-manager-policy.json"
            policy.parent.mkdir(parents=True)
            policy.write_text("{}", encoding="utf-8")
            installed = root / ".local" / "lib" / "jason" / "release_manager_host_runner.py"
            installed.parent.mkdir(parents=True)
            installed.write_bytes(new.read_bytes())
            installed.chmod(0o755)
            source_link = installed.parent / "release-manager-source"
            source_link.symlink_to(old_root, target_is_directory=True)
            backup = installed.with_name(
                installed.name + ".recovery-backup-"
                + runner.file_digest(old)[len("sha256:"):][:16]
            )
            backup.write_bytes(old.read_bytes())
            backup.chmod(0o600)
            review_path = root / "material-review.json"
            review = {
                "schema_version": "1.0", "status": "approved",
                "source_revision": SHA_A, "recorded_by": "person-al",
            }
            review_path.write_text(json.dumps(review), encoding="utf-8")

            def git_result(args, **kwargs):
                if "show" in args:
                    return new.read_bytes()
                if "refs/remotes/origin/main" in args:
                    return SHA_A
                if "rev-parse" in args:
                    return SHA_A
                raise AssertionError("unreviewed git operation: " + str(args))

            with (
                patch.object(runner, "CONTROLLER_SOURCE", installed),
                patch.object(runner.Path, "home", return_value=root),
                patch.object(runner, "CONTROLLER_RECOVERY_MANAGED_REPO", root / "managed"),
                patch.object(runner, "CONTROLLER_RECOVERY_OWNER_REVIEW", review_path),
                patch.object(runner, "_controller_recovery_old_source_verified", return_value=True),
                patch.object(runner.subprocess, "check_output", side_effect=git_result),
            ):
                pin = runner.controller_identity(new_root)
                self.assertEqual(pin["controller_recovery_mode"], "canonical_owner_recovery")
                self.assertEqual(pin["executing_controller_revision"], SHA_A)
                self.assertEqual(pin["controller_recovery_old_source"], str(old))
                # The privileged host reconciliation changes the source link
                # from old N to new N+1. Immutable old provenance is pinned.
                source_link.unlink()
                source_link.symlink_to(new_root, target_is_directory=True)
                attested = runner.verify_controller_identity(
                    pin, new_root, installed_candidate=True,
                    installed_runner=installed,
                )
                self.assertEqual(attested["controller_handoff"], "staged_for_next_transaction")
                self.assertEqual(attested["executing_controller_digest"], pin["executing_controller_digest"])

                review["status"] = "denied"
                review_path.write_text(json.dumps(review), encoding="utf-8")
                with self.assertRaisesRegex(
                    runner.ReleaseManagerError, "owner review does not match"
                ):
                    runner.verify_controller_identity(
                        pin, new_root, installed_candidate=True,
                        installed_runner=installed,
                    )
                review["status"] = "approved"
                review["source_revision"] = SHA_B
                review_path.write_text(json.dumps(review), encoding="utf-8")
                with self.assertRaisesRegex(
                    runner.ReleaseManagerError, "owner review does not match"
                ):
                    runner.verify_controller_identity(
                        pin, new_root, installed_candidate=True,
                        installed_runner=installed,
                    )
                review["source_revision"] = SHA_A
                review_path.write_text(json.dumps(review), encoding="utf-8")
                backup.write_bytes(b"altered-backup")
                with self.assertRaisesRegex(
                    runner.ReleaseManagerError, "backup missing or altered"
                ):
                    runner.verify_controller_identity(
                        pin, new_root, installed_candidate=True,
                        installed_runner=installed,
                    )
                backup.write_bytes(old.read_bytes())
                new.write_bytes(b"unreviewed-candidate")
                with self.assertRaisesRegex(
                    runner.ReleaseManagerError, "installed candidate differs"
                ):
                    runner.verify_controller_identity(
                        pin, new_root, installed_candidate=True,
                        installed_runner=installed,
                    )

    def test_operator_recovery_missing_review_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo = root / SHA_A
            old = root / SHA_B / "tools" / "release_manager_host_runner.py"
            old.parent.mkdir(parents=True)
            old.write_bytes(b"old")
            installed = root / "release_manager_host_runner.py"
            installed.write_bytes(b"new")
            backup = installed.with_name(
                installed.name + ".recovery-backup-"
                + runner.file_digest(old)[len("sha256:"):][:16]
            )
            backup.write_bytes(b"old")
            backup.chmod(0o600)
            (repo / "tools").mkdir(parents=True)
            (repo / "tools" / "release_manager_host_runner.py").write_bytes(b"new")
            with (
                patch.object(runner, "_controller_recovery_old_source_verified", return_value=True),
                patch.object(runner, "CONTROLLER_RECOVERY_OWNER_REVIEW", root / "missing-review.json"),
                patch.object(runner.subprocess, "check_output", side_effect=[
                    SHA_A, SHA_A, b"new",
                ]),
            ):
                with self.assertRaisesRegex(
                    runner.ReleaseManagerError, "exact owner review missing"
                ):
                    runner._operator_recovery_identity(repo, installed, old)

    def test_controller_self_update_pins_old_runner_and_attests_installed_new_runner(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo = root / "candidate"
            policy = repo / "config" / "release-manager-policy.json"
            policy.parent.mkdir(parents=True)
            policy.write_text("{}", encoding="utf-8")
            candidate = repo / "tools" / "release_manager_host_runner.py"
            candidate.parent.mkdir(parents=True)
            candidate.write_bytes(b"reviewed-new-controller")
            old = root / SHA_B / "tools" / "release_manager_host_runner.py"
            old.parent.mkdir(parents=True)
            old.write_bytes(b"immutable-old-controller")
            installed = root / "installed" / "release_manager_host_runner.py"
            installed.parent.mkdir(parents=True)
            installed.write_bytes(candidate.read_bytes())
            with patch.object(runner, "CONTROLLER_SOURCE", old):
                pin = runner.controller_identity(repo)
                self.assertNotEqual(pin["executing_controller_digest"], pin["candidate_controller_digest"])
                verified = runner.verify_controller_identity(
                    pin, repo, installed_candidate=True, installed_runner=installed
                )
                self.assertEqual(verified["executing_controller_revision"], SHA_B)
                self.assertEqual(verified["executing_controller_digest"], pin["executing_controller_digest"])
                self.assertEqual(verified["installed_controller_digest"], pin["candidate_controller_digest"])
                self.assertEqual(verified["controller_handoff"], "staged_for_next_transaction")

                # Reject a compromised installed N+1, a compromised immutable
                # candidate, a replaced running N, and policy changes.
                installed.write_bytes(b"unexpected-new-controller")
                with self.assertRaisesRegex(runner.ReleaseManagerError, "installed Production Manager controller differs"):
                    runner.verify_controller_identity(pin, repo, installed_candidate=True, installed_runner=installed)
                installed.write_bytes(candidate.read_bytes())
                candidate.write_bytes(b"tampered-candidate")
                with self.assertRaisesRegex(runner.ReleaseManagerError, "candidate_controller_digest"):
                    runner.verify_controller_identity(pin, repo, installed_candidate=True, installed_runner=installed)
                candidate.write_bytes(b"reviewed-new-controller")
                old.write_bytes(b"tampered-active-controller")
                with self.assertRaisesRegex(runner.ReleaseManagerError, "executing_controller_digest"):
                    runner.verify_controller_identity(pin, repo, installed_candidate=True, installed_runner=installed)
                old.write_bytes(b"immutable-old-controller")
                policy.write_text("changed", encoding="utf-8")
                with self.assertRaisesRegex(runner.ReleaseManagerError, "policy_digest"):
                    runner.verify_controller_identity(pin, repo, installed_candidate=True, installed_runner=installed)

    def test_scheduled_installed_controller_copy_changes_only_for_next_transaction(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            old_root = root / SHA_B
            new_root = root / SHA_A
            old = old_root / "tools" / "release_manager_host_runner.py"
            new = new_root / "tools" / "release_manager_host_runner.py"
            old.parent.mkdir(parents=True)
            new.parent.mkdir(parents=True)
            old.write_bytes(b"immutable-old-version")
            new.write_bytes(b"reviewed-new-version")
            (new_root / "config").mkdir()
            (new_root / "config" / "release-manager-policy.json").write_text("{}")
            installed = root / ".local" / "lib" / "jason" / "release_manager_host_runner.py"
            installed.parent.mkdir(parents=True)
            installed.write_bytes(old.read_bytes())
            active_source = installed.parent / "release-manager-source"
            active_source.symlink_to(old_root, target_is_directory=True)

            # Simulate the actual user-systemd ExecStart path, not a command
            # launched directly from /opt/jason/releases/<old SHA>/tools.
            with patch.object(runner, "CONTROLLER_SOURCE", installed), patch.object(
                runner.Path, "home", return_value=root
            ):
                pin = runner.controller_identity(new_root)
                self.assertEqual(pin["executing_controller_revision"], SHA_B)
                self.assertEqual(
                    pin["executing_controller_immutable_path"], str(old)
                )
                installed.write_bytes(new.read_bytes())
                active_source.unlink()
                active_source.symlink_to(new_root, target_is_directory=True)

                verified = runner.verify_controller_identity(
                    pin, new_root, installed_candidate=True
                )
                self.assertEqual(verified["executing_controller_revision"], SHA_B)
                self.assertEqual(
                    verified["executing_controller_digest"], runner.file_digest(old)
                )
                self.assertEqual(
                    verified["installed_controller_digest"], runner.file_digest(new)
                )
                # A fresh future invocation resolves N+1 as active, only
                # AFTER old transaction returns and releases its flock.
                successor = runner.controller_identity(new_root)
                self.assertEqual(successor["executing_controller_revision"], SHA_A)
                self.assertNotEqual(
                    successor["executing_controller_digest"],
                    verified["executing_controller_digest"],
                )
                old.write_bytes(b"modified-immutable-old")
                with self.assertRaisesRegex(
                    runner.ReleaseManagerError, "executing_controller_digest"
                ):
                    runner.verify_controller_identity(
                        pin, new_root, installed_candidate=True
                    )

    def test_scheduled_controller_requires_immutable_source_match_at_entry(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            release = root / SHA_B
            old = release / "tools" / "release_manager_host_runner.py"
            old.parent.mkdir(parents=True)
            old.write_bytes(b"immutable-old")
            new = root / SHA_A
            c = new / "tools" / "release_manager_host_runner.py"
            c.parent.mkdir(parents=True)
            c.write_bytes(b"reviewed-new")
            (new / "config").mkdir()
            (new / "config" / "release-manager-policy.json").write_text("{}")
            installed = root / ".local" / "lib" / "jason" / "release_manager_host_runner.py"
            installed.parent.mkdir(parents=True)
            installed.write_bytes(b"untrusted-installed-runner")
            (installed.parent / "release-manager-source").symlink_to(
                release, target_is_directory=True
            )
            with patch.object(runner, "CONTROLLER_SOURCE", installed), patch.object(
                runner.Path, "home", return_value=root
            ):
                with self.assertRaisesRegex(
                    runner.ReleaseManagerError, "controller recovery old source is not root immutable"
                ):
                    runner.controller_identity(new)

    def test_scheduled_controller_refuses_missing_immutable_source_link(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            candidate = root / SHA_A
            c = candidate / "tools" / "release_manager_host_runner.py"
            c.parent.mkdir(parents=True)
            c.write_bytes(b"reviewed-candidate")
            (candidate / "config").mkdir()
            (candidate / "config" / "release-manager-policy.json").write_text("{}")
            installed = root / ".local" / "lib" / "jason" / "release_manager_host_runner.py"
            installed.parent.mkdir(parents=True)
            installed.write_bytes(b"old-controller")
            with patch.object(runner, "CONTROLLER_SOURCE", installed), patch.object(
                runner.Path, "home", return_value=root
            ):
                with self.assertRaisesRegex(
                    runner.ReleaseManagerError, "immutable source link missing"
                ):
                    runner.controller_identity(candidate)

    def test_closeout_records_both_controller_digests_and_staged_handoff(self):
        source = (ROOT / "tools" / "release_manager_host_runner.py").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            '"executing_controller_digest": controller_verified["executing_controller_digest"]',
            source,
        )
        self.assertIn(
            '"installed_controller_digest": controller_verified["installed_controller_digest"]',
            source,
        )
        self.assertIn(
            '"controller_handoff": controller_verified["controller_handoff"]',
            source,
        )

    def test_controller_self_update_rejects_missing_installed_controller(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo = root / "candidate"
            p = repo / "config" / "release-manager-policy.json"
            p.parent.mkdir(parents=True)
            p.write_text("{}", encoding="utf-8")
            c = repo / "tools" / "release_manager_host_runner.py"
            c.parent.mkdir(parents=True)
            c.write_bytes(b"candidate")
            pin = runner.controller_identity(repo)
            with self.assertRaisesRegex(runner.ReleaseManagerError, "installed Production Manager controller differs"):
                runner.verify_controller_identity(
                    pin, repo, installed_candidate=True,
                    installed_runner=root / "nonexistent" / "runner.py"
                )

    def test_change_risk_classifies_release_manager_as_production_control_core(self):
        self.assertEqual(
            runner.classify_change_risk(
                "release_blocker",
                ["tools/release_manager_host_runner.py"],
            ),
            "production_control_core",
        )
        self.assertEqual(
            runner.classify_change_risk("todo", ["docs/operations/example.md"]),
            "normal",
        )

    def test_functional_smoke_requires_runtime_mcp_host_alignment_and_http_health(self):
        with (
            patch.object(
                runner,
                "live_production_alignment",
                return_value={
                    "runtime_revision": SHA_A,
                    "mcp_revision": SHA_A,
                    "host_revision": SHA_A,
                },
            ),
            patch.object(runner, "live_mcp", return_value={"revision": SHA_A}),
            patch.object(runner, "output", return_value="200\n") as output,
        ):
            result = runner.run_functional_smoke_tests(SHA_A)
        self.assertTrue(result["passed"])
        self.assertEqual(output.call_args.args[0][:3], ["docker", "exec", "jason-runtime"])
        self.assertEqual(result["runtime_healthz_http_status"], 200)
        self.assertTrue(result["runtime_mcp_host_alignment"])

    def test_release_policy_requires_hardening_production_evidence(self):
        import json

        policy = json.loads((ROOT / "config" / "release-manager-policy.json").read_text(encoding="utf-8"))
        production = policy["production"]
        self.assertTrue(production["circuit_breaker_required"])
        self.assertTrue(production["last_known_good_manifest_required"])
        self.assertTrue(production["controller_identity_pinning_required"])
        self.assertTrue(production["functional_smoke_test_required"])
        required = set(policy["required_production_verification_evidence"])
        self.assertTrue(
            {
                "functional_smoke_tests_passed",
                "controller_identity_verified",
                "last_known_good_manifest_captured",
                "pre_mutation_health_passed",
                "production_manifest_complete",
                "desired_state_converged",
            }.issubset(required)
        )

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


def test_missing_lkg_recovery_requires_approval_and_clean_drift(tmp_path):
    import json
    state = tmp_path
    sha = SHA_A
    record = {"state": "closed", "production": {"verified_at": "2026-10-09T13:11:56+00:00", "live_sha": sha}}
    (state / 'records').mkdir()
    (state / 'records' / f'release-{sha[:16]}.json').write_text(json.dumps(record))
    control = {"schema_version": "1.0", "circuit_breaker": {"state": "open"}, "last_known_good": None}
    (state / 'production-control-state.json').write_text(json.dumps(control))
    (state / 'production-drift.json').write_text(json.dumps({"schema_version": "1.0", "status": "drift_detected", "problems": [{"kind": "failed_user_unit"}]}))
    with __import__('pytest').raises(runner.ReleaseManagerError, match='explicit owner'):
        runner.recover_missing_last_known_good(state, sha, owner_approved=False)
    with patch.object(runner, 'capture_production_manifest') as manifest:
        with __import__('pytest').raises(runner.ReleaseManagerError, match='drift remains'):
            runner.recover_missing_last_known_good(state, sha, owner_approved=True)
        manifest.assert_not_called()
    assert json.loads((state / 'production-control-state.json').read_text()) == control
    (state / 'production-drift.json').write_text(json.dumps({"schema_version": "1.0", "status": "pass", "observed_at": datetime.now(timezone.utc).isoformat(), "problems": []}))
    with patch.object(runner, 'capture_production_manifest', return_value={"complete": True, "revision": sha, "observed_at": "now"}):
        result = runner.recover_missing_last_known_good(state, sha, owner_approved=True)
    assert result['recovered'] is True
    assert json.loads((state / 'production-control-state.json').read_text())['last_known_good']['manifest']['revision'] == sha


def test_missing_lkg_recovery_rejects_stale_clean_drift(tmp_path):
    import json
    sha = SHA_A
    (tmp_path / 'records').mkdir()
    (tmp_path / 'records' / f'release-{sha[:16]}.json').write_text(json.dumps({'state': 'closed', 'production': {'verified_at': 'now', 'live_sha': sha}}))
    original = {'schema_version': '1.0', 'circuit_breaker': {'state': 'open'}, 'last_known_good': None}
    (tmp_path / 'production-control-state.json').write_text(json.dumps(original))
    (tmp_path / 'production-drift.json').write_text(json.dumps({'schema_version': '1.0', 'status': 'pass', 'observed_at': '2025-01-01T00:00:00+00:00', 'problems': []}))
    with patch.object(runner, 'capture_production_manifest') as capture:
        with __import__('pytest').raises(runner.ReleaseManagerError, match='not fresh'):
            runner.recover_missing_last_known_good(tmp_path, sha, owner_approved=True)
        capture.assert_not_called()
    selfcheck = json.loads((tmp_path / 'production-control-state.json').read_text())
    assert selfcheck == original

class GovernedReleaseReissueTests(unittest.TestCase):
    def test_verified_rollback_creates_new_attempt_and_preserves_history(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            historical = {'release_id': runner.record_id(SHA_A), 'state': 'rolled_back',
                'failure': {'rollback_verified': True},
                'release_candidate': {'candidate_sha': SHA_A}}
            runner.atomic_json(runner.record_path(root, runner.record_id(SHA_A)), historical)
            def create(**kw):
                return {'release_id': kw['release_id_override'], 'state': 'release_candidate'}
            with patch.object(runner, 'revalidate_circuit_breaker'), \
                 patch.object(runner, 'live_runtime', return_value={'revision': SHA_B}), \
                 patch.object(runner, 'create_record', side_effect=create), \
                 patch.object(runner, 'run_preproduction', side_effect=lambda repo, state_root, record: record):
                result = runner.prepare_release(ROOT, root, SHA_A, 'release_blocker', reissue_rolled_back=True)
            self.assertEqual(result['release_id'], runner.record_id(SHA_A) + '-retry-1')
            self.assertEqual(result['reissued_from'], runner.record_id(SHA_A))
            self.assertEqual(runner.load_record(root, runner.record_id(SHA_A)), historical)

    def test_unverified_rollback_cannot_reissue(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runner.atomic_json(runner.record_path(root, runner.record_id(SHA_A)),
                {'release_id': runner.record_id(SHA_A), 'state': 'rolled_back',
                 'failure': {'rollback_verified': False},
                 'release_candidate': {'candidate_sha': SHA_A}})
            with patch.object(runner, 'revalidate_circuit_breaker'):
                with self.assertRaisesRegex(runner.ReleaseManagerError, 'verified rolled-back'):
                    runner.prepare_release(ROOT, root, SHA_A, 'release_blocker', reissue_rolled_back=True)


def test_governed_reissue_rejects_concurrent_pending_attempt():
    import pytest
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        base = runner.record_id(SHA_A)
        runner.atomic_json(runner.record_path(root, base), {
            'release_id': base, 'state': 'rolled_back', 'failure': {'rollback_verified': True},
            'release_candidate': {'candidate_sha': SHA_A}})
        runner.atomic_json(runner.record_path(root, base + '-retry-1'), {
            'release_id': base + '-retry-1', 'state': 'production_eligible',
            'release_candidate': {'candidate_sha': SHA_A}})
        with patch.object(runner, 'revalidate_circuit_breaker'):
            with pytest.raises(runner.ReleaseManagerError, match='existing retry attempt'):
                runner.prepare_release(ROOT, root, SHA_A, 'release_blocker', reissue_rolled_back=True)


class HostReconciliationTimeoutContractTests(unittest.TestCase):
    def test_bound_covers_observed_service_activation_and_exporter(self):
        import inspect
        default = inspect.signature(runner.request_host_reconcile).parameters['timeout_seconds'].default
        self.assertGreater(default, 202 + 17 + 60)
        self.assertLessEqual(default, 480)

    def test_absent_host_result_still_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / 'host-reconcile' / 'requests').mkdir(parents=True)
            (root / 'host-reconcile' / 'results').mkdir(parents=True)
            with patch.object(runner, 'require_host_reconciler_ready'), patch.object(runner.time, 'monotonic', side_effect=[0.0, 2.0]):
                with self.assertRaisesRegex(runner.ReleaseManagerError, 'host reconciliation result timed out'):
                    runner.request_host_reconcile(root, SHA_A, timeout_seconds=1.0)


def test_rollback_retention_only_removes_old_exited_named_containers():
    from unittest.mock import patch
    names = [f'jason-runtime-rollback-20261011T{i:06d}Z' for i in range(22)]
    rows = '\n'.join(f'2026-10-11 {i:06d}|{name}' for i, name in enumerate(names))
    calls = []
    def fake_run(args, **kwargs):
        calls.append(args)
        return rows if args[1] == 'ps' else ''
    with patch.object(runner, 'run', side_effect=fake_run):
        assert runner.reconcile_stopped_rollback_retention() == 16
    removed = [args[2] for args in calls if args[1] == 'rm']
    assert removed == list(reversed(names[:6]))
    assert not any('prune' in args for args in calls)


def test_explicit_prepare_reconciles_retention_before_breaker_revalidation():
    """Both automatic and owner-triggered releases reserve rollback headroom."""
    from unittest.mock import patch
    order = []
    def cleanup():
        order.append('retention')
        return 16
    def breaker(state_root):
        order.append('breaker')
        raise runner.ReleaseManagerError('controlled stop before release mutation')
    with patch.object(runner, 'reconcile_stopped_rollback_retention', side_effect=cleanup), \
         patch.object(runner, 'revalidate_circuit_breaker', side_effect=breaker):
        with __import__('pytest').raises(runner.ReleaseManagerError,
                                         match='controlled stop before release mutation'):
            runner.prepare_release(Path('/tmp/nonexistent'), Path('/tmp/nonexistent'),
                                   SHA_A, 'release_blocker', owner_approved=True)
    assert order == ['retention', 'breaker']
    # No release record or production mutation was reached.


def test_retention_failure_prevents_breaker_revalidation_and_mutation():
    from unittest.mock import patch
    with patch.object(runner, 'reconcile_stopped_rollback_retention',
                      side_effect=runner.ReleaseManagerError('docker unavailable')), \
         patch.object(runner, 'revalidate_circuit_breaker') as breaker:
        with __import__('pytest').raises(runner.ReleaseManagerError, match='docker unavailable'):
            runner.prepare_release(Path('/tmp/nonexistent'), Path('/tmp/nonexistent'),
                                   SHA_A, 'release_blocker', owner_approved=True)
        breaker.assert_not_called()


def test_release_contract_fails_before_mutation_on_legacy_missing_manifest(tmp_path):
    import pytest
    record = {'state': 'production_eligible', 'rollback_sha': SHA_B,
              'release_candidate': {'candidate_sha': SHA_A}}
    with patch.object(runner, 'require_host_reconciler_ready') as ready:
        with pytest.raises(runner.ReleaseManagerError, match='release_manifest or risk_profile'):
            runner._deploy_production_locked(ROOT, tmp_path, record)
        ready.assert_not_called()
    assert record['state'] == 'production_eligible'
    assert not list(tmp_path.glob('records/*.json'))


def test_release_contract_rejects_mismatched_release_sha_and_risk():
    import pytest
    record = {'state': 'production_eligible', 'rollback_sha': SHA_B,
              'release_candidate': {'candidate_sha': SHA_A},
              'risk_profile': {'score': 1},
              'release_manifest': {'candidate_sha': SHA_B, 'rollback_sha': SHA_B,
                                   'risk_profile': {'score': 1}}}
    with pytest.raises(runner.ReleaseManagerError, match='identities do not match'):
        runner.validate_release_record_contract(record)
    record['release_manifest']['candidate_sha'] = SHA_A
    record['release_manifest']['risk_profile'] = {'score': 9}
    with pytest.raises(runner.ReleaseManagerError, match='risk classification differs'):
        runner.validate_release_record_contract(record)
    record['release_manifest']['risk_profile'] = record['risk_profile']
    runner.validate_release_record_contract(record)


def test_nonprotected_release_waits_for_owner_without_failing_systemd(tmp_path):
    from unittest.mock import patch
    records = tmp_path / 'records';records.mkdir()
    record = {'release_id': runner.record_id(SHA_A), 'state': 'production_eligible',
              'rollback_sha': SHA_B, 'release_candidate': {'candidate_sha': SHA_A}, 'owner_approval': {'approved': False}}
    runner.atomic_json(records / (record['release_id'] + '.json'), record)
    with (patch.object(runner.gate, 'load_json', return_value={'schedule': {'automatic_promotion_enabled': True}}),
          patch.object(runner, 'consume_owner_approval_requests'),
          patch.object(runner, 'production_window_open', return_value=True),
          patch.object(runner, 'authoritative_auto_promotion_head', return_value=SHA_A),
          patch.object(runner, 'live_runtime', return_value={'revision': SHA_B}),
          patch.object(runner, 'live_production_alignment', return_value={}),
          patch.object(runner, 'reconcile_stopped_rollback_retention'),
          patch.object(runner, 'production_gate_result', return_value={
              'allowed': False, 'protected_core': False,
              'reasons': ['production release requires explicit owner approval',
                          'owner approval is not bound to the exact candidate SHA']}),
          patch.object(runner, 'write_owner_notification_event') as notify,
          patch.object(runner, 'deploy_production') as deploy):
        assert runner.promote_eligible(ROOT, tmp_path) is False
        notify.assert_called_once()
        deploy.assert_not_called()
    assert runner.load_record(tmp_path, record['release_id'])['state'] == 'production_eligible'


def test_unapproved_release_with_other_denials_fails_closed(tmp_path):
    import pytest
    records = tmp_path / 'records';records.mkdir()
    record = {'release_id': runner.record_id(SHA_A), 'state': 'production_eligible',
              'rollback_sha': SHA_B, 'release_candidate': {'candidate_sha': SHA_A}}
    runner.atomic_json(records / (record['release_id'] + '.json'), record)
    with (patch.object(runner.gate, 'load_json', return_value={'schedule': {'automatic_promotion_enabled': True}}),
          patch.object(runner, 'consume_owner_approval_requests'),
          patch.object(runner, 'production_window_open', return_value=True),
          patch.object(runner, 'authoritative_auto_promotion_head', return_value=SHA_A),
          patch.object(runner, 'live_runtime', return_value={'revision': SHA_B}),
          patch.object(runner, 'live_production_alignment', return_value={}),
          patch.object(runner, 'reconcile_stopped_rollback_retention'),
          patch.object(runner, 'production_gate_result', return_value={
              'allowed': False, 'protected_core': False,
              'reasons': ['production release requires explicit owner approval',
                          'candidate policy signature missing']}),
          patch.object(runner, 'write_owner_notification_event') as notify,
          patch.object(runner, 'deploy_production') as deploy):
        with pytest.raises(runner.ReleaseManagerError, match='candidate policy signature missing'):
            runner.promote_eligible(ROOT, tmp_path)
        notify.assert_not_called()
        deploy.assert_not_called()


def test_evidence_bundle_is_built_before_reporting_production_verified():
    import inspect
    source = inspect.getsource(runner._deploy_production_locked)
    assert source.index('record["evidence_bundle"] = {') < source.index(
        'gate_transition(repo, state_root, record, "production_verified")'
    )


def test_release_contract_rejects_missing_risk_profile_with_manifest_present():
    import pytest
    record = {'state': 'production_eligible', 'rollback_sha': SHA_B,
              'release_candidate': {'candidate_sha': SHA_A},
              'release_manifest': {'candidate_sha': SHA_A, 'rollback_sha': SHA_B}}
    with pytest.raises(runner.ReleaseManagerError, match='release_manifest or risk_profile'):
        runner.validate_release_record_contract(record)


def _ccc_test_report(candidate=SHA_A, runtime=SHA_B, *, mode='transition'):
    ids = sorted(runner.CCC_REQUIRED_CHECKS | {'material-change-owner-review'})
    checks = [
        {'check_id': key, 'status': 'NOT_PROVEN' if key == 'runtime-source-alignment' and mode == 'transition' else 'PASS'}
        for key in ids
    ]
    return {
        'schema_version': '1.0', 'source_revision': candidate,
        'runtime_revision': runtime, 'status': 'NOT_PROVEN' if mode == 'transition' else 'PASS',
        'trigger': 'material_change', 'run_id': 'ccc-test-123',
        'finished_at': datetime.now(timezone.utc).isoformat(),
        'material_changes': ['implementation/runtime_service/src/jason_runtime/autonomy_worker_runtime.py'],
        'checks': checks,
    }


def test_ccc_preflight_permits_exactly_one_expected_runtime_alignment_gap():
    report = _ccc_test_report()
    evidence = runner.verify_release_ccc_report(
        report, candidate_sha=SHA_A, runtime_sha=SHA_B, before_mutation=True,
    )
    assert evidence['status'] == 'NOT_PROVEN'
    assert evidence['mode'] == 'candidate_transition'
    assert evidence['source_revision'] == SHA_A
    report['runtime_revision'] = SHA_A
    report['status'] = 'PASS'
    for item in report['checks']:
        item['status'] = 'PASS'
    assert runner.verify_release_ccc_report(
        report, candidate_sha=SHA_A, runtime_sha=SHA_A, before_mutation=True,
    )['mode'] == 'aligned'


def test_ccc_preflight_rejects_any_other_not_proven_or_failure():
    import pytest
    for check, status in [
        ('checker-currentness', 'NOT_PROVEN'),
        ('material-change-owner-review', 'NOT_PROVEN'),
        ('j900-release-validation', 'FAIL'),
        ('systemd-failed-units', 'FAIL'),
        ('governed-provider-boundary-canaries', 'NOT_PROVEN'),
    ]:
        report = _ccc_test_report()
        for item in report['checks']:
            if item['check_id'] == check:
                item['status'] = status
        with pytest.raises(runner.ReleaseManagerError, match='pre-mutation CCC denied'):
            runner.verify_release_ccc_report(
                report, candidate_sha=SHA_A, runtime_sha=SHA_B, before_mutation=True,
            )


def test_ccc_preflight_rejects_unsafe_evidence_shapes():
    import pytest
    base = _ccc_test_report()
    for mutation in ['wrong_source', 'wrong_runtime', 'missing', 'duplicate', 'unknown', 'wrong_status', 'unreviewed_material']:
        import copy
        report = copy.deepcopy(base)
        if mutation == 'wrong_source':
            report['source_revision'] = SHA_B
        elif mutation == 'wrong_runtime':
            report['runtime_revision'] = SHA_A
        elif mutation == 'missing':
            report['checks'] = report['checks'][1:]
        elif mutation == 'duplicate':
            report['checks'].append(report['checks'][0])
        elif mutation == 'unknown':
            report['checks'].append({'check_id': 'unanticipated-required-gate', 'status': 'NOT_PROVEN'})
        elif mutation == 'wrong_status':
            report['status'] = 'PASS'
        elif mutation == 'unreviewed_material':
            report['checks'] = [v for v in report['checks'] if v['check_id'] != 'material-change-owner-review']
        with pytest.raises(runner.ReleaseManagerError):
            runner.verify_release_ccc_report(
                report, candidate_sha=SHA_A, runtime_sha=SHA_B, before_mutation=True,
            )


def test_ccc_post_deploy_requires_exact_live_revision_and_unanimous_pass():
    import pytest
    report = _ccc_test_report(runtime=SHA_A, mode='pass')
    assert runner.verify_release_ccc_report(
        report, candidate_sha=SHA_A, runtime_sha=SHA_A, before_mutation=False,
    )['mode'] == 'live_certified'
    for field, value in [('status', 'NOT_PROVEN'), ('source_revision', SHA_B), ('runtime_revision', SHA_B)]:
        altered = dict(report)
        altered[field] = value
        with pytest.raises(runner.ReleaseManagerError):
            runner.verify_release_ccc_report(
                altered, candidate_sha=SHA_A, runtime_sha=SHA_A, before_mutation=False,
            )
    report['checks'][0]['status'] = 'FAIL'
    with pytest.raises(runner.ReleaseManagerError, match='post-mutation CCC'):
        runner.verify_release_ccc_report(
            report, candidate_sha=SHA_A, runtime_sha=SHA_A, before_mutation=False,
        )


def test_ccc_gate_execution_requires_fresh_report_and_matching_process_result(tmp_path):
    import json
    import pytest
    from types import SimpleNamespace
    ccc = tmp_path / 'run_ccc.py';ccc.write_text('')
    config = tmp_path / 'ccc.json';config.write_text('{}')
    latest = tmp_path / 'latest.json'
    fresh = _ccc_test_report(runtime=SHA_A, mode='pass')
    with patch.object(runner.subprocess, 'run', return_value=SimpleNamespace(returncode=0)):
        with pytest.raises(runner.ReleaseManagerError, match='did not persist'):
            runner.run_release_ccc_gate(SHA_A, SHA_A, before_mutation=False, ccc_runner=ccc, ccc_config=config, latest=latest)
        latest.write_text(json.dumps(fresh))
        assert runner.run_release_ccc_gate(SHA_A, SHA_A, before_mutation=False, ccc_runner=ccc, ccc_config=config, latest=latest)['mode'] == 'live_certified'
        fresh['finished_at'] = '2020-01-01T00:00:00+00:00'
        latest.write_text(json.dumps(fresh))
        with pytest.raises(runner.ReleaseManagerError, match='stale'):
            runner.run_release_ccc_gate(SHA_A, SHA_A, before_mutation=False, ccc_runner=ccc, ccc_config=config, latest=latest)
        fresh['finished_at'] = '2031-01-01T00:00:00+00:00'
        latest.write_text(json.dumps(fresh))
        with pytest.raises(runner.ReleaseManagerError, match='future-dated'):
            runner.run_release_ccc_gate(SHA_A, SHA_A, before_mutation=False, ccc_runner=ccc, ccc_config=config, latest=latest)
    fresh['finished_at'] = datetime.now(timezone.utc).isoformat()
    latest.write_text(json.dumps(fresh))
    with patch.object(runner.subprocess, 'run', return_value=SimpleNamespace(returncode=2)):
        with pytest.raises(runner.ReleaseManagerError, match='process failed'):
            runner.run_release_ccc_gate(SHA_A, SHA_A, before_mutation=False, ccc_runner=ccc, ccc_config=config, latest=latest)


def test_ccc_precedes_mutation_and_postflight_precedes_closed_release():
    import inspect
    source = inspect.getsource(runner._deploy_production_locked)
    assert source.index('ccc_preflight = run_release_ccc_gate(') < source.index('gate_transition(repo, state_root, record, "production")')
    assert source.index('ccc_postflight = run_release_ccc_gate(') > source.index('runtime_deployed = True')
    assert source.index('ccc_postflight = run_release_ccc_gate(') < source.index('gate_transition(repo, state_root, record, "production_verified")')
    assert source.index('ccc_postflight = run_release_ccc_gate(') < source.index('set_last_known_good(\n            state_root,\n            production_manifest')


def test_production_complete_notification_follows_root_last_known_good_commit():
    import inspect
    source = inspect.getsource(runner._deploy_production_locked)
    commit = source.index('set_last_known_good(\n            state_root,\n            production_manifest')
    verified = source.index('gate_transition(repo, state_root, record, "production_verified")')
    closed = source.index('gate_transition(repo, state_root, record, "closed")')
    persisted = source.index('save_record(state_root, record)', closed)
    complete_notification = source.index('"production_queue_completed"')
    assert commit < verified < closed < persisted < complete_notification


def test_release_contract_accepts_emitted_string_risk_enum_with_exact_manifest():
    for classification in ('normal', 'production_repair', 'production_control_core', 'schema_or_contract'):
        record = {'state': 'production_eligible', 'rollback_sha': SHA_B,
                  'release_candidate': {'candidate_sha': SHA_A},
                  'risk_profile': classification,
                  'release_manifest': {'candidate_sha': SHA_A, 'rollback_sha': SHA_B,
                                       'risk_profile': classification}}
        runner.validate_release_record_contract(record)


def test_release_contract_rejects_missing_unknown_or_mismatched_risk():
    import pytest
    record = {'rollback_sha': SHA_B, 'release_candidate': {'candidate_sha': SHA_A},
              'risk_profile': 'production_control_core',
              'release_manifest': {'candidate_sha': SHA_A, 'rollback_sha': SHA_B,
                                   'risk_profile': 'production_control_core'}}
    for invalid in ('', 'unknown', None, {}, []):
        record['risk_profile'] = invalid
        with pytest.raises(runner.ReleaseManagerError, match='risk_profile'):
            runner.validate_release_record_contract(record)
    record['risk_profile'] = 'production_control_core'
    record['release_manifest']['risk_profile'] = 'normal'
    with pytest.raises(runner.ReleaseManagerError, match='risk classification differs'):
        runner.validate_release_record_contract(record)


def test_ccc_postflight_transient_prometheus_rechecks_fresh_report_and_audits_runs(tmp_path):
    from types import SimpleNamespace
    import json

    ccc = tmp_path / "run_ccc.py"
    ccc.write_text("")
    config = tmp_path / "ccc.json"
    config.write_text("{}")
    latest = tmp_path / "latest.json"
    calls = []

    def ccc_check(*args, **kwargs):
        calls.append(len(calls) + 1)
        report = _ccc_test_report(runtime=SHA_A, mode="pass")
        report["run_id"] = f"independent-check-{calls[-1]}"
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        failed = calls[-1] <= 2
        if failed:
            report["status"] = "FAIL"
            next(x for x in report["checks"] if x["check_id"] == "prometheus-targets")["status"] = "FAIL"
        latest.write_text(json.dumps(report))
        return SimpleNamespace(returncode=1 if failed else 0)

    with patch.object(runner.subprocess, "run", side_effect=ccc_check), patch.object(runner.time, "sleep") as sleep:
        evidence = runner.run_release_ccc_gate(
            SHA_A, SHA_A, before_mutation=False,
            ccc_runner=ccc, ccc_config=config, latest=latest,
        )
    assert evidence["mode"] == "live_certified"
    assert evidence["checks"]["prometheus-targets"] == "PASS"
    assert evidence["transient_monitoring_retries"] == 2
    assert evidence["failed_monitoring_run_ids"] == [
        "independent-check-1", "independent-check-2",
    ]
    assert len(calls) == 3
    assert [x.args for x in sleep.call_args_list] == [(15,), (20,)]


def test_ccc_postflight_persistent_monitoring_failure_remains_fatal(tmp_path):
    from types import SimpleNamespace
    import json
    import pytest

    ccc = tmp_path / "run_ccc.py"
    ccc.write_text("")
    config = tmp_path / "ccc.json"
    config.write_text("{}")
    latest = tmp_path / "latest.json"
    runs = []

    def ccc_check(*args, **kwargs):
        runs.append(len(runs) + 1)
        report = _ccc_test_report(runtime=SHA_A, mode="pass")
        report["status"] = "FAIL"
        report["run_id"] = f"independent-check-{runs[-1]}"
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        next(x for x in report["checks"] if x["check_id"] == "prometheus-targets")["status"] = "FAIL"
        latest.write_text(json.dumps(report))
        return SimpleNamespace(returncode=1)

    with patch.object(runner.subprocess, "run", side_effect=ccc_check), patch.object(runner.time, "sleep") as sleep:
        with pytest.raises(runner.ReleaseManagerError, match="post-mutation CCC did not certify"):
            runner.run_release_ccc_gate(
                SHA_A, SHA_A, before_mutation=False,
                ccc_runner=ccc, ccc_config=config, latest=latest,
            )
    assert len(runs) == 4
    assert [x.args for x in sleep.call_args_list] == [(15,), (20,), (25,)]


def test_ccc_postflight_other_failures_and_wrong_identity_do_not_retry(tmp_path):
    from types import SimpleNamespace
    import json
    import pytest

    ccc = tmp_path / "run_ccc.py"
    ccc.write_text("")
    config = tmp_path / "ccc.json"
    config.write_text("{}")
    latest = tmp_path / "latest.json"

    for check, source in [
        ("systemd-failed-units", SHA_A),
        ("openclaw-authority-health", SHA_A),
        ("prometheus-targets", SHA_B),
    ]:
        report = _ccc_test_report(runtime=SHA_A, mode="pass")
        report["status"] = "FAIL"
        report["source_revision"] = source
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        next(x for x in report["checks"] if x["check_id"] == check)["status"] = "FAIL"
        latest.write_text(json.dumps(report))
        with patch.object(runner.subprocess, "run", return_value=SimpleNamespace(returncode=1)) as proc, patch.object(runner.time, "sleep") as sleep:
            with pytest.raises(runner.ReleaseManagerError):
                runner.run_release_ccc_gate(
                    SHA_A, SHA_A, before_mutation=False,
                    ccc_runner=ccc, ccc_config=config, latest=latest,
                )
        assert proc.call_count == 1
        sleep.assert_not_called()


def test_ccc_postflight_reused_failed_run_id_fails_closed(tmp_path):
    from types import SimpleNamespace
    import json
    import pytest

    ccc = tmp_path / "run_ccc.py"
    ccc.write_text("")
    config = tmp_path / "ccc.json"
    config.write_text("{}")
    latest = tmp_path / "latest.json"
    report = _ccc_test_report(runtime=SHA_A, mode="pass")
    report["status"] = "FAIL"
    report["run_id"] = "reused-ccc-run"
    next(x for x in report["checks"] if x["check_id"] == "prometheus-targets")["status"] = "FAIL"

    def ccc_check(*args, **kwargs):
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        latest.write_text(json.dumps(report))
        return SimpleNamespace(returncode=1)

    with patch.object(runner.subprocess, "run", side_effect=ccc_check) as proc, patch.object(runner.time, "sleep") as sleep:
        with pytest.raises(runner.ReleaseManagerError, match="repeated a prior monitoring report"):
            runner.run_release_ccc_gate(
                SHA_A, SHA_A, before_mutation=False,
                ccc_runner=ccc, ccc_config=config, latest=latest,
            )
    assert proc.call_count == 2
    assert sleep.call_count == 1
