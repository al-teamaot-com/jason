import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).resolve().parents[1] / "autonomous_repair_host_runner.py"
SPEC = importlib.util.spec_from_file_location("autonomous_repair_host_runner", MODULE_PATH)
runner = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = runner
SPEC.loader.exec_module(runner)


CANDIDATE = "a" * 40
ROLLBACK = "b" * 40


def request_payload():
    material = {
        "schema_version": "1.0",
        "capability": "deployment.repair.apply",
        "provider": "jason_host_repair_runner",
        "principal_id": "jason-autonomy-worker",
        "organization_id": "aot",
        "execution_id": "exec-1",
        "correlation_id": "corr-1",
        "candidate_sha": CANDIDATE,
        "rollback_sha": ROLLBACK,
        "support_item": "SUPPORT-OPS-023",
        "pr_number": 123,
        "post_deploy_verification": "Verify repaired behavior.",
    }
    authority = {
        key: material[key]
        for key in (
            "capability",
            "provider",
            "principal_id",
            "organization_id",
            "candidate_sha",
            "rollback_sha",
            "support_item",
            "pr_number",
            "post_deploy_verification",
        )
    }
    import hashlib
    fingerprint = hashlib.sha256(
        json.dumps(authority, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        **material,
        "request_id": fingerprint,
        "request_fingerprint": fingerprint,
        "requested_at": "2026-09-28T14:00:00+00:00",
        "state": "queued",
    }


class FakeApi:
    def __init__(self, *args, **kwargs):
        pass

    def request(self, path):
        if path == "/pulls/123":
            return {
                "number": 123,
                "merged_at": "2026-09-28T14:00:00Z",
                "merge_commit_sha": CANDIDATE,
                "body": """
- Release class: autonomous-repair-candidate
- Support item: SUPPORT-OPS-023
- Previously approved behavior: Existing behavior.
- New capability: no
- Security impact: none
- New authority or permission: no
- Provider/API contract change: no
- Schema or migration: no
- New dependency: no
- Infrastructure or topology change: no
- Client scope expansion: no
- Disruptive operational behavior: no
- Regression test: implementation/runtime_service/tests/test_fix.py
- Post-deploy verification: Verify repaired behavior.
""",
                "head": {"sha": "c" * 40},
            }
        if path == f"/commits/{CANDIDATE}":
            return {"parents": [{"sha": ROLLBACK}, {"sha": "d" * 40}]}
        if path == f"/commits/{CANDIDATE}/check-runs":
            return {"check_runs": []}
        if path == "/branches/main":
            return {"commit": {"sha": CANDIDATE}}
        if path == f"/compare/{CANDIDATE}...{CANDIDATE}":
            return {"status": "identical"}
        raise AssertionError(path)

    def paged(self, path):
        if path == "/pulls/123/files":
            return [
                {
                    "filename": "implementation/runtime_service/src/jason_runtime/fix.py",
                    "additions": 4,
                    "deletions": 2,
                },
                {
                    "filename": "implementation/runtime_service/tests/test_fix.py",
                    "additions": 10,
                    "deletions": 0,
                },
            ]
        raise AssertionError(path)


class HostRepairRunnerTests(unittest.TestCase):
    def test_request_fingerprint_rejects_tampering(self):
        payload = request_payload()
        payload["candidate_sha"] = "e" * 40
        with self.assertRaises(runner.RepairRunnerError) as caught:
            runner._canonical_request(payload)
        self.assertEqual(caught.exception.code, "REQUEST_FINGERPRINT_MISMATCH")

    def test_wait_live_health_tolerates_startup_transition(self):
        with patch.object(
            runner,
            "_live_health",
            side_effect=["starting", "starting", "healthy"],
        ), patch.object(runner.time, "sleep") as sleep:
            health = runner._wait_live_health(attempts=3, interval_seconds=0.1)
        self.assertEqual(health, "healthy")
        self.assertEqual(sleep.call_count, 2)

    def test_wait_live_health_fails_closed_after_bound(self):
        with patch.object(runner, "_live_health", return_value="starting"), patch.object(
            runner.time, "sleep"
        ):
            with self.assertRaises(runner.RepairRunnerError) as caught:
                runner._wait_live_health(attempts=2, interval_seconds=0)
        self.assertEqual(caught.exception.code, "PRODUCTION_NOT_HEALTHY")

    def test_wait_live_revision_health_tolerates_candidate_startup(self):
        with patch.object(
            runner,
            "_live_revision",
            return_value=CANDIDATE,
        ), patch.object(
            runner,
            "_live_health",
            side_effect=["starting", "healthy"],
        ), patch.object(runner.time, "sleep") as sleep:
            revision, health = runner._wait_live_revision_health(
                CANDIDATE, attempts=2, interval_seconds=0.1
            )
        self.assertEqual(revision, CANDIDATE)
        self.assertEqual(health, "healthy")
        self.assertEqual(sleep.call_count, 1)

    def test_wait_live_revision_health_fails_on_revision_change(self):
        with patch.object(
            runner,
            "_live_revision",
            return_value=ROLLBACK,
        ), patch.object(runner, "_live_health", return_value="healthy"):
            with self.assertRaises(runner.RepairRunnerError) as caught:
                runner._wait_live_revision_health(CANDIDATE, attempts=2)
        self.assertEqual(caught.exception.code, "POST_DEPLOY_VERIFICATION_FAILED")

    def test_wait_live_revision_health_supports_verified_rollback(self):
        with patch.object(
            runner,
            "_live_revision",
            return_value=ROLLBACK,
        ), patch.object(
            runner,
            "_live_health",
            side_effect=["starting", "healthy"],
        ), patch.object(runner.time, "sleep"):
            revision, health = runner._wait_live_revision_health(
                ROLLBACK, attempts=2, interval_seconds=0
            )
        self.assertEqual(revision, ROLLBACK)
        self.assertEqual(health, "healthy")

    def test_live_rollback_mismatch_fails_before_git_or_build(self):
        with tempfile.TemporaryDirectory() as td:
            request_path = Path(td) / "request.json"
            request_path.write_text(json.dumps(request_payload()), encoding="utf-8")
            with patch.object(runner, "_live_revision", return_value="e" * 40),                  patch.object(runner, "_live_health", return_value="healthy"),                  patch.object(runner, "_verify_git") as verify_git:
                with self.assertRaises(runner.RepairRunnerError) as caught:
                    runner._process(
                        repo=Path(td),
                        spool=Path(td),
                        request_path=request_path,
                    )
            self.assertEqual(caught.exception.code, "ROLLBACK_REVISION_MISMATCH")
            verify_git.assert_not_called()

    def test_unrelated_main_changes_rejected_by_first_parent(self):
        class WrongParentApi(FakeApi):
            def request(self, path):
                if path == f"/commits/{CANDIDATE}":
                    return {"parents": [{"sha": "e" * 40}, {"sha": "d" * 40}]}
                return super().request(path)

        fake_gate = type(
            "Gate",
            (),
            {
                "load_json": staticmethod(lambda path: {"automatic_production_execution_enabled": True}),
                "Api": WrongParentApi,
            },
        )
        with patch.object(runner, "_load_gate", return_value=fake_gate):
            with self.assertRaises(runner.RepairRunnerError) as caught:
                runner._independent_classification(
                    repo=Path("/tmp"),
                    request=request_payload(),
                    live_revision=ROLLBACK,
                )
        self.assertEqual(caught.exception.code, "UNRELATED_MAIN_CHANGES_PRESENT")

    def test_policy_disabled_blocks_before_classification(self):
        fake_gate = type(
            "Gate",
            (),
            {
                "load_json": staticmethod(
                    lambda path: {"automatic_production_execution_enabled": False}
                ),
            },
        )
        with patch.object(runner, "_load_gate", return_value=fake_gate):
            with self.assertRaises(runner.RepairRunnerError) as caught:
                runner._independent_classification(
                    repo=Path("/tmp"),
                    request=request_payload(),
                    live_revision=ROLLBACK,
                )
        self.assertEqual(caught.exception.code, "AUTONOMOUS_EXECUTION_DISABLED")

    def test_process_one_persists_rejection_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "requests").mkdir()
            payload = request_payload()
            request_id = payload["request_id"]
            (root / "requests" / f"{request_id}.json").write_text(
                json.dumps(payload),
                encoding="utf-8",
            )
            with patch.object(
                runner,
                "_process",
                side_effect=runner.RepairRunnerError("TEST_REJECT", "bounded rejection"),
            ):
                processed = runner.process_one(
                    repo=root,
                    spool=root,
                    preflight_only=True,
                )
            self.assertTrue(processed)
            result = json.loads(
                (root / "results" / f"{request_id}.json").read_text(encoding="utf-8")
            )
            self.assertEqual(result["state"], "rejected")
            self.assertEqual(result["error_code"], "TEST_REJECT")


if __name__ == "__main__":
    unittest.main()
