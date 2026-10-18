import importlib.util
import sys
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "development_release_coordinator.py"
SPEC = importlib.util.spec_from_file_location("development_release_coordinator", MODULE_PATH)
coordinator = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = coordinator
SPEC.loader.exec_module(coordinator)


class DevelopmentReleaseCoordinatorTests(unittest.TestCase):
    def test_control_board_skips_stale_PR_api_checks_but_preserves_count_and_overlap(self):
        import json
        import tempfile
        from datetime import datetime, timedelta, timezone
        from unittest.mock import patch

        now = datetime.now(timezone.utc)

        def pull(n, sha, age_days):
            return {
                "number": n, "title": f"PR {n}", "html_url": f"https://example.invalid/pr/{n}",
                "head": {"sha": sha}, "updated_at": (
                    now - timedelta(days=age_days)
                ).isoformat(), "draft": False, "body": "",
            }

        recent = pull(101, "a" * 40, 1)
        overlap_only = pull(102, "b" * 40, 5)
        old = pull(103, "c" * 40, 30)

        class FakeApi:
            def __init__(self):
                self.paths = []

            def request(self, path):
                self.paths.append(path)
                if path == "/branches/main":
                    return {"commit": {"sha": "d" * 40}}
                if path == "/compare/" + "d" * 40 + "..." + "a" * 40:
                    return {"behind_by": 0}
                if path == "/commits/" + "a" * 40 + "/check-runs":
                    return {"check_runs": [
                        {"name": "ci", "status": "completed", "conclusion": "success", "id": 1},
                    ]}
                raise AssertionError("Unexpected stale API call: " + path)

            def paged(self, path):
                self.paths.append(path)
                if path.startswith("/pulls?state=open"):
                    return [recent, overlap_only, old]
                if path in ("/pulls/101/files", "/pulls/102/files"):
                    return [{"filename": "tools/important.py"}]
                raise AssertionError("Unexpected stale file lookup: " + path)

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state = root / "state"
            state.mkdir()
            state.joinpath("records").mkdir()
            files = {
                "ROADMAP_STATUS": {"schema_version": "1.0"},
                "AUTOMATED_CHANGE_STATE": {"production": {"status": "unknown"}},
            }
            for name, data in files.items():
                (root / (name + ".json")).write_text(json.dumps(data))
            (root / "support.md").write_text("")
            (root / "todos.md").write_text("")
            api = FakeApi()
            config = {
                "base_branch": "main", "required_checks": ["ci"],
                "active_display_days": 3, "active_overlap_days": 7,
                "preproduction": {"configured": True},
            }
            with (
                patch.object(coordinator, "ROADMAP_STATUS", root / "ROADMAP_STATUS.json"),
                patch.object(coordinator, "AUTOMATED_CHANGE_STATE", root / "AUTOMATED_CHANGE_STATE.json"),
                patch.object(coordinator, "SUPPORT", root / "support.md"),
                patch.object(coordinator, "TODO_BACKLOG", root / "todos.md"),
                patch.object(coordinator, "RELEASE_MANAGER_STATE_ROOT", state),
            ):
                board = coordinator.collect(api, config)

        self.assertEqual(len(board["pr_states"]), 3)
        self.assertEqual(board["older_open_pr_count"], 2)
        self.assertEqual(board["pr_states"][0]["state"], "Pre-prod ready")
        self.assertTrue(board["pr_states"][0]["recent"])
        self.assertEqual(board["pr_states"][1]["state"], "Needs revalidation")
        self.assertEqual(board["pr_states"][2]["check_state"], "not_checked_stale")
        self.assertIsNone(board["pr_states"][2]["behind_by"])
        self.assertEqual(
            board["overlaps"],
            [{"left": 101, "right": 102, "files": ["tools/important.py"]}],
        )
        self.assertEqual(
            len([path for path in api.paths if path.startswith("/compare/")]), 1,
        )
        self.assertEqual(
            len([path for path in api.paths if path.endswith("/check-runs")]), 1,
        )
        self.assertFalse(any("/pulls/103/files" in path for path in api.paths))

    def test_recent_pr_check_error_fails_closed(self):
        from datetime import datetime, timezone
        from unittest.mock import patch

        latest = {
            "number": 12, "title": "Active PR", "html_url": "https://example.invalid/12",
            "head": {"sha": "b" * 40}, "updated_at": datetime.now(timezone.utc).isoformat(),
            "draft": False, "body": "",
        }

        class BrokenApi:
            def request(self, path):
                if path == "/branches/main":
                    return {"commit": {"sha": "a" * 40}}
                raise RuntimeError("live Github check failed")

            def paged(self, path):
                if path.startswith("/pulls?state=open"):
                    return [latest]
                return []

        with self.assertRaisesRegex(RuntimeError, "live Github check failed"):
            coordinator.collect(BrokenApi(), {
                "base_branch": "main", "required_checks": ["ci"],
                "active_display_days": 3, "active_overlap_days": 7,
            })

    def test_required_checks_pass(self):
        required = ["a", "b"]
        checks = [
            {"id": 1, "name": "a", "status": "completed", "conclusion": "success"},
            {"id": 2, "name": "b", "status": "completed", "conclusion": "success"},
        ]
        state, count, detail = coordinator.summarize_required_checks(required, checks)
        self.assertEqual(state, "passed")
        self.assertEqual(count, "2/2")
        self.assertEqual(detail, [])

    def test_required_checks_fail_closed_on_missing(self):
        state, count, detail = coordinator.summarize_required_checks(
            ["a", "b"],
            [{"id": 1, "name": "a", "status": "completed", "conclusion": "success"}],
        )
        self.assertEqual(state, "missing")
        self.assertEqual(count, "1/2")
        self.assertEqual(detail, ["b"])

    def test_stale_pr_needs_revalidation(self):
        state = coordinator.classify_pr(
            {"draft": False},
            {"behind_by": 2},
            "passed",
            preprod_configured=False,
        )
        self.assertEqual(state, "Needs revalidation")

    def test_ci_ready_is_not_production_ready_without_preprod(self):
        state = coordinator.classify_pr(
            {"draft": False},
            {"behind_by": 0},
            "passed",
            preprod_configured=False,
        )
        self.assertEqual(state, "CI-ready")

    def test_support_parser_keeps_open_and_excludes_closed(self):
        text = """| ID | Priority | Status | Item | Current blocker / evidence | Acceptance criteria |
| --- | --- | --- | --- | --- | --- |
| SUPPORT-OPS-023 | P1 | Open — fix in validation | SQLite locking | evidence | acceptance |
| SUPPORT-OPS-022 | P1 | Closed 2026-09-28 | Old defect | evidence | acceptance |
"""
        parsed = coordinator.parse_support(text)
        self.assertEqual([item["id"] for item in parsed], ["SUPPORT-OPS-023"])

    def test_support_repair_prs_recognizes_autonomous_candidate(self):
        pulls = [
            {
                "number": 586,
                "title": "Fix SUPPORT-OPS-027",
                "html_url": "https://example.invalid/586",
                "draft": False,
                "body": """## Autonomous repair release

- Release class: autonomous-repair-candidate
- Support item: SUPPORT-OPS-027
""",
            },
            {
                "number": 100,
                "title": "Unrelated",
                "html_url": "https://example.invalid/100",
                "draft": False,
                "body": "No repair metadata",
            },
        ]
        repairs = coordinator.support_repair_prs(pulls)
        self.assertEqual(repairs["SUPPORT-OPS-027"]["number"], 586)
        self.assertNotIn("SUPPORT-OPS-999", repairs)

    def test_todo_parser_excludes_blocked(self):
        text = """### TODO-OPS-001 — Ready work

- **Priority:** P1
- **Status:** Planned

### TODO-OPS-002 — Waiting work

- **Priority:** P1
- **Status:** Blocked
"""
        parsed = coordinator.parse_todos(text)
        self.assertEqual([item["id"] for item in parsed], ["TODO-OPS-001"])

    def test_release_attention_is_separate_from_development_recommendation(self):
        prs = [
            {
                "number": 10,
                "title": "Stale release candidate",
                "state": "Needs revalidation",
                "recent": True,
            }
        ]
        self.assertIn("PR #10", coordinator.release_attention(prs))

        support = [
            {
                "id": "SUPPORT-OPS-023",
                "priority": "P1",
                "status": "Open",
                "title": "SQLite locking",
            }
        ]
        self.assertIn(
            "SUPPORT-OPS-023",
            coordinator.development_recommendation(support, []),
        )

    def test_render_surfaces_native_support_autonomy(self):
        board = {
            "generated_at": "2026-09-29T00:00:00+00:00",
            "main_sha": "abc",
            "production": {},
            "preproduction": {"configured": False},
            "release_attention": "none",
            "development_recommendation": "none",
            "pr_states": [],
            "older_open_pr_count": 0,
            "overlaps": [],
            "support": [],
            "todos": [],
            "production_policy": {},
            "autonomous_repair_policy": {},
            "support_autonomy_policy": {
                "enabled": True,
                "owner_approved": True,
                "max_active_items": 2,
                "native_repository_implementation_worker": True,
            },
        }
        rendered = coordinator.render(board)
        self.assertIn("Native autonomous support repair enabled: **yes**", rendered)
        self.assertIn("Native repository implementation worker: **yes**", rendered)
        self.assertIn("Maximum active support repairs: **2**", rendered)

    def test_render_surfaces_todo_engineering_autonomy(self):
        board = {
            "generated_at": "2026-10-02T00:00:00+00:00",
            "main_sha": "abc",
            "production": {},
            "preproduction": {"configured": True},
            "release_attention": "none",
            "development_recommendation": "none",
            "pr_states": [],
            "older_open_pr_count": 0,
            "overlaps": [],
            "support": [],
            "todos": [],
            "production_policy": {},
            "autonomous_repair_policy": {},
            "support_autonomy_policy": {},
            "todo_autonomy_policy": {
                "enabled": True,
                "owner_approved": True,
                "eligibility_statuses": ["Planned", "In progress"],
                "max_open_todo_issues": 1,
            },
        }
        rendered = coordinator.render(board)
        self.assertIn("Governed TODO intake enabled: **yes**", rendered)
        self.assertIn("Standing owner approval for actionable TODO intake: **yes**", rendered)
        self.assertIn("Planned, In progress", rendered)
        self.assertIn("Maximum open TODO engineering issues: **1**", rendered)


    def test_repository_todo_open_issue_capacity_matches_engineering_capacity(self):
        import json
        from pathlib import Path

        config = json.loads((Path(__file__).resolve().parents[2] / "config/development-release-coordinator.json").read_text())
        todo = config["todo_autonomy"]
        self.assertEqual(todo["max_open_todo_issues"], 3)
        self.assertEqual(todo["max_active_items"], 1)

    def test_production_health_view_marks_stale_health_for_revalidation(self):
        production = {
            "status": "aligned_and_healthy",
            "observed_at": "2026-10-07T13:00:00+00:00",
            "revision": "abc",
        }
        view = coordinator.production_health_view(
            production,
            max_age_minutes=30,
            now=coordinator.datetime.fromisoformat("2026-10-07T14:00:01+00:00"),
        )
        self.assertEqual(view["status"], "revalidation_required")
        self.assertEqual(view["freshness"], "stale")
        self.assertGreater(view["evidence_age_minutes"], 30)

    def test_production_health_view_keeps_fresh_health(self):
        production = {
            "status": "aligned_and_healthy",
            "observed_at": "2026-10-07T13:50:00+00:00",
            "revision": "abc",
        }
        view = coordinator.production_health_view(
            production,
            max_age_minutes=30,
            now=coordinator.datetime.fromisoformat("2026-10-07T14:00:00+00:00"),
        )
        self.assertEqual(view["status"], "aligned_and_healthy")
        self.assertEqual(view["freshness"], "fresh")

    def test_production_health_view_missing_timestamp_fails_closed(self):
        production = {
            "status": "aligned_and_healthy",
            "revision": "abc",
        }
        view = coordinator.production_health_view(
            production,
            max_age_minutes=30,
            now=coordinator.datetime.fromisoformat("2026-10-07T14:00:00+00:00"),
        )
        self.assertEqual(view["status"], "revalidation_required")
        self.assertEqual(view["freshness"], "missing_timestamp")

    def test_future_or_naive_production_timestamps_cannot_claim_green(self):
        from datetime import datetime, timezone
        now = datetime(2026, 10, 18, 11, 0, tzinfo=timezone.utc)
        for observed, expected_reason in (
            ("2026-10-18T12:00:00+00:00", "future_timestamp"),
            ("2026-10-18T10:59:00", "invalid_timezone"),
        ):
            view = coordinator.production_health_view(
                {"status": "aligned_and_healthy", "observed_at": observed},
                max_age_minutes=30, now=now,
            )
            self.assertEqual(view["status"], "revalidation_required")
            self.assertEqual(view["freshness"], expected_reason)

    def test_release_control_view_surfaces_breaker_lock_queue_and_lkg(self):
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "records").mkdir()
            (root / "production-control-state.json").write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "updated_at": "2026-10-07T20:00:00+00:00",
                        "circuit_breaker": {"state": "open", "reason": "synthetic"},
                        "last_known_good": {
                            "release_id": "release-good",
                            "manifest": {"revision": "a" * 40, "complete": True},
                        },
                    }
                ),
                encoding="utf-8",
            )
            (root / "production-transaction.lock").write_text(
                json.dumps({"release_id": "release-active", "pid": 123}) + "\n",
                encoding="utf-8",
            )
            (root / "production-drift.json").write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "status": "drift_detected",
                        "observed_at": "2026-10-07T20:00:00+00:00",
                        "problems": [{"kind": "forbidden_execution_path"}],
                    }
                ),
                encoding="utf-8",
            )
            (root / "records" / "release-active.json").write_text(
                json.dumps({"release_id": "release-active", "state": "production"}),
                encoding="utf-8",
            )
            (root / "records" / "release-queued.json").write_text(
                json.dumps({"release_id": "release-queued", "state": "production_eligible"}),
                encoding="utf-8",
            )
            view = coordinator.release_control_view(root)
        self.assertEqual(view["circuit_breaker"]["state"], "open")
        self.assertEqual(view["lock_owner"]["release_id"], "release-active")
        self.assertEqual(view["active_transactions"], ["release-active"])
        self.assertEqual(view["queued_candidates"], ["release-queued"])
        self.assertEqual(view["last_known_good_release"], "release-good")
        self.assertEqual(view["last_known_good_revision"], "a" * 40)
        self.assertEqual(view["current_complete_manifest_revision"], "a" * 40)
        self.assertEqual(view["desired_state_drift_status"], "drift_detected")
        self.assertEqual(view["desired_state_drift_problem_count"], 1)

    def test_render_surfaces_production_control_state(self):
        board = {
            "generated_at": "2026-10-07T20:00:00+00:00",
            "main_sha": "abc",
            "production": {},
            "preproduction": {"configured": True},
            "release_control": {
                "circuit_breaker": {"state": "closed"},
                "lock_owner": {"release_id": "release-active"},
                "active_transactions": ["release-active"],
                "queued_candidates": ["release-next"],
                "last_known_good_release": "release-good",
                "last_known_good_revision": "a" * 40,
                "current_complete_manifest_revision": "b" * 40,
                "desired_state_drift_status": "pass",
                "desired_state_drift_problem_count": 0,
            },
            "release_attention": "none",
            "development_recommendation": "none",
            "pr_states": [],
            "older_open_pr_count": 0,
            "overlaps": [],
            "support": [],
            "todos": [],
            "production_policy": {},
            "autonomous_repair_policy": {},
            "support_autonomy_policy": {},
            "todo_autonomy_policy": {},
        }
        rendered = coordinator.render(board)
        self.assertIn("Production circuit breaker:** closed", rendered)
        self.assertIn("Production lock owner:** release-active", rendered)
        self.assertIn("Queued production candidates:** release-next", rendered)
        self.assertIn("Last-known-good release:** release-good", rendered)
        self.assertIn("Current complete production manifest:** " + "b" * 40, rendered)
        self.assertIn("Desired-state drift:** pass (0 problem(s))", rendered)

    def _board_observation(self, revision: str, observed_at: str, *, host: bool = False):
        lines = [
            "# Jason Development & Release Control Board",
            "**Generated:** 2026-10-18T11:02:00+00:00  ",
            "**Current main:** `mainsha`  ",
            f"**Production revision:** `{revision}`  ",
            "**Production health:** aligned_and_healthy  ",
            f"**Production evidence observed:** {observed_at}  ",
            "**Production evidence freshness:** fresh (1.0 minutes old)  ",
            "**Production circuit breaker:** closed  ",
            "**Production lock owner:** none  ",
            "**Active production transaction:** none  ",
            "**Queued production candidates:** none  ",
            "**Last-known-good release:** release-good  ",
            f"**Last-known-good revision:** {revision}  ",
            f"**Current complete production manifest:** {revision}  ",
            "**Desired-state drift:** pass (0 problem(s))  ",
            "## Release attention",
            "Current PRs and blockers",
        ]
        if host:
            lines.append(coordinator.HOST_PRODUCTION_REPORT_MARKER)
        return "\n".join(lines) + "\n"

    def test_scheduled_board_keeps_newer_host_observation(self):
        from datetime import datetime, timezone
        now = datetime(2026, 10, 18, 11, 5, tzinfo=timezone.utc)
        host = self._board_observation("b" * 40, "2026-10-18T11:00:00+00:00", host=True)
        main = self._board_observation("a" * 40, "2026-10-17T11:00:00+00:00")
        merged = coordinator.preserve_newer_host_board_observation(
            main, host, now=now, max_age_minutes=30,
        )
        self.assertIn("Production revision:** `" + "b" * 40 + "`", merged)
        self.assertIn("Production circuit breaker:** closed", merged)
        self.assertIn("Production evidence freshness:** fresh host observation (5.0 minutes old)", merged)
        self.assertIn("## Release attention\nCurrent PRs and blockers", merged)
        self.assertIn(coordinator.HOST_PRODUCTION_REPORT_MARKER, merged)

    def test_previous_host_evidence_expires_even_when_repo_stale(self):
        from datetime import datetime, timezone
        now = datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc)
        host = self._board_observation("b" * 40, "2026-10-18T11:00:00+00:00", host=True)
        main = self._board_observation("a" * 40, "2026-10-17T11:00:00+00:00")
        merged = coordinator.preserve_newer_host_board_observation(
            main, host, now=now, max_age_minutes=30,
        )
        self.assertIn("Production revision:** `" + "b" * 40 + "`", merged)
        self.assertIn("Production health:** revalidation_required", merged)
        self.assertIn("Production circuit breaker:** unknown (host evidence stale)", merged)
        self.assertIn("Desired-state drift:** unknown (host evidence stale)", merged)
        self.assertIn("Production evidence freshness:** stale (60.0 minutes old", merged)

    def test_board_never_trusts_unmarked_or_future_or_invalid_host_data(self):
        from datetime import datetime, timezone
        now = datetime(2026, 10, 18, 11, 5, tzinfo=timezone.utc)
        main = self._board_observation("a" * 40, "2026-10-17T11:00:00+00:00")
        unmarked = self._board_observation("b" * 40, "2026-10-18T11:00:00+00:00")
        future = self._board_observation("b" * 40, "2026-10-18T12:00:00+00:00", host=True)
        invalid = self._board_observation("wrong", "2026-10-18T11:00:00+00:00", host=True)
        for previous in (unmarked, future, invalid):
            self.assertEqual(
                coordinator.preserve_newer_host_board_observation(main, previous, now=now),
                main,
            )

    def test_newer_main_observation_supersedes_host_marker(self):
        from datetime import datetime, timezone
        now = datetime(2026, 10, 18, 11, 15, tzinfo=timezone.utc)
        main = self._board_observation("a" * 40, "2026-10-18T11:12:00+00:00")
        host = self._board_observation("b" * 40, "2026-10-18T11:00:00+00:00", host=True)
        self.assertEqual(
            coordinator.preserve_newer_host_board_observation(main, host, now=now),
            main,
        )

    def test_publish_preserves_newer_host_without_changing_release_authority(self):
        from unittest.mock import patch
        class FakeApi:
            token = "fake-token"
            def __init__(self, previous):
                self.previous = previous
                self.writes = []
            def request(self, path, method="GET", payload=None):
                if method == "GET":
                    return {"body": self.previous}
                self.writes.append((path, payload))
                return {}
        host = self._board_observation("b" * 40, "2026-10-18T11:00:00+00:00", host=True)
        main = self._board_observation("a" * 40, "2026-10-17T11:00:00+00:00")
        api = FakeApi(host)
        from datetime import datetime, timezone
        coordinator.publish(
            api, 526, main,
            now=datetime(2026, 10, 18, 11, 5, tzinfo=timezone.utc),
        )
        self.assertEqual(len(api.writes), 1)
        self.assertEqual(api.writes[0][0], "/issues/526")
        self.assertIn("Production revision:** `" + "b" * 40 + "`", api.writes[0][1]["body"])

    def test_sensitive_overlap_paths(self):
        self.assertTrue(coordinator.sensitive("implementation/runtime/app.py"))
        self.assertTrue(coordinator.sensitive("tools/example.py"))
        self.assertFalse(coordinator.sensitive("docs/sessions/example.md"))


if __name__ == "__main__":
    unittest.main()
