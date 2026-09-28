import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "jason_support_intake.py"
SPEC = importlib.util.spec_from_file_location("jason_support_intake", MODULE_PATH)
intake = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = intake
SPEC.loader.exec_module(intake)


SUPPORT = """# Project Jason Support List

| ID | Priority | Status | Item | Current blocker / evidence | Acceptance criteria |
| --- | --- | --- | --- | --- | --- |
| SUPPORT-OPS-023 | P1 | Open — fix in validation | SQLite locking | evidence | acceptance |
| SUPPORT-CAP-027 | P1 | Open — discovered 2026-09-28 | Ticket resolution field | evidence | acceptance |
| SUPPORT-OPS-022 | P1 | Closed 2026-09-28 | Old issue | evidence | acceptance |
| SUPPORT-CAP-015 | P1 | Reclassified to TODO | Vendor gap | evidence | acceptance |
"""


class SupportIntakeTests(unittest.TestCase):
    def test_parse_open_support_excludes_closed_and_reclassified(self):
        items = intake.parse_open_support(SUPPORT)
        self.assertEqual(
            [item["id"] for item in items],
            ["SUPPORT-OPS-023", "SUPPORT-CAP-027"],
        )

    def test_pr_support_ids_finds_title_body_and_head(self):
        ids = intake.pr_support_ids(
            {
                "title": "Fix SUPPORT-OPS-023",
                "body": "Also references SUPPORT-CAP-027",
                "head": {"ref": "fix/support-conn-023-retry"},
            }
        )
        self.assertEqual(
            ids,
            {"SUPPORT-OPS-023", "SUPPORT-CAP-027", "SUPPORT-CONN-023"},
        )

    def test_active_engineering_is_prioritized_within_priority(self):
        queue = intake.derive_queue(
            support_items=intake.parse_open_support(SUPPORT),
            prs=[
                {
                    "number": 10,
                    "title": "Fix SUPPORT-CAP-027",
                    "body": "",
                    "head": {"ref": "fix/cap-027"},
                    "html_url": "https://example.invalid/10",
                }
            ],
            previous={"items": {}},
            observed_at="2026-09-28T15:00:00+00:00",
        )
        self.assertEqual(queue["selected_support_id"], "SUPPORT-CAP-027")
        self.assertEqual(
            queue["items"]["SUPPORT-CAP-027"]["work_state"],
            "active_engineering",
        )

    def test_first_seen_is_preserved(self):
        queue = intake.derive_queue(
            support_items=intake.parse_open_support(SUPPORT),
            prs=[],
            previous={
                "items": {
                    "SUPPORT-OPS-023": {
                        "first_seen_at": "2026-09-28T12:00:00+00:00"
                    }
                }
            },
            observed_at="2026-09-28T15:00:00+00:00",
        )
        self.assertEqual(
            queue["items"]["SUPPORT-OPS-023"]["first_seen_at"],
            "2026-09-28T12:00:00+00:00",
        )

    def test_native_mode_has_no_browser_dependency(self):
        queue = intake.derive_queue(
            support_items=[],
            prs=[],
            previous={"items": {}},
            observed_at="2026-09-28T15:00:00+00:00",
        )
        self.assertEqual(queue["mode"], "native_host_intake")
        self.assertFalse(queue["browser_dependency"])
        self.assertEqual(queue["engineering_executor"], "not_configured")


if __name__ == "__main__":
    unittest.main()
