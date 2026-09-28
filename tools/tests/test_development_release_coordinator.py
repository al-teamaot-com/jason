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

    def test_sensitive_overlap_paths(self):
        self.assertTrue(coordinator.sensitive("implementation/runtime/app.py"))
        self.assertTrue(coordinator.sensitive("tools/example.py"))
        self.assertFalse(coordinator.sensitive("docs/sessions/example.md"))


if __name__ == "__main__":
    unittest.main()
