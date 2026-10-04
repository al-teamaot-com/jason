import importlib.util
import sys
import unittest
import tempfile
import json
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

MODULE_PATH = TOOLS / "todo_engineering_intake.py"
SPEC = importlib.util.spec_from_file_location("todo_engineering_intake", MODULE_PATH)
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


TODO_TEXT = """# Backlog

### TODO-OPS-010 — Approved high priority item

- **Priority:** P1
- **Status:** Approved for Autonomous Engineering — owner-approved 2026-10-03
- **Autonomous engineering readiness:** Approved
- **Risk level:** Moderate
- **Idea:** Build the thing.

### TODO-OPS-011 — Proposed item

- **Priority:** P0
- **Status:** Proposed
- **Autonomous engineering readiness:** Not reviewed
- **Idea:** Save this idea only.

### TODO-OPS-012 — Planned but not approved item

- **Priority:** P2
- **Status:** Planned
- **Autonomous engineering readiness:** Not reviewed
- **Idea:** Do not start this automatically.

### TODO-OPS-013 — Status approved but readiness missing

- **Priority:** P1
- **Status:** Approved for Autonomous Engineering
- **Idea:** Fail closed without readiness evidence.
"""


class TodoEngineeringIntakeTests(unittest.TestCase):
    def test_parse_todo_sections_preserves_exact_section(self):
        items = module.parse_todo_sections(TODO_TEXT)
        self.assertEqual(
            [item.item_id for item in items],
            ["TODO-OPS-010", "TODO-OPS-011", "TODO-OPS-012", "TODO-OPS-013"],
        )
        self.assertEqual(items[0].priority, "P1")
        self.assertTrue(items[0].status.startswith("Approved for Autonomous Engineering"))
        self.assertEqual(items[0].readiness, "Approved")
        self.assertIn("Build the thing.", items[0].section)

    def test_only_owner_approved_ready_items_are_executable(self):
        items = module.parse_todo_sections(TODO_TEXT)
        status = {item.item_id: item.executable for item in items}
        self.assertTrue(status["TODO-OPS-010"])
        self.assertFalse(status["TODO-OPS-011"])
        self.assertFalse(status["TODO-OPS-012"])
        self.assertFalse(status["TODO-OPS-013"])

    def test_identified_support_is_queued_not_active_capacity(self):
        state = {
            "items": {
                "SUPPORT-OPS-001": {"phase": "identified"},
                "SUPPORT-OPS-002": {"phase": "diagnosing"},
                "SUPPORT-OPS-003": {"phase": "blocked"},
            }
        }
        self.assertEqual(module.active_support_ids(state), ["SUPPORT-OPS-002"])
        self.assertEqual(module.blocked_support_ids(state), ["SUPPORT-OPS-003"])

    def test_support_first_blocks_todo_when_repair_capacity_exists(self):
        todos = module.parse_todo_sections(TODO_TEXT)
        support = (
            "| ID | Priority | Status | Title | Evidence | Acceptance |\n"
            "| --- | --- | --- | --- | --- | --- |\n"
            "| SUPPORT-OPS-099 | P1 | Open | Broken thing | evidence | fix |\n"
        )
        candidate, reason = module.select_candidate(
            todos=todos,
            support_text=support,
            support_state={"items": {}},
            max_support_repairs=2,
            existing_issues={},
        )
        self.assertIsNone(candidate)
        self.assertIn("Support-first", reason)

    def test_support_row_without_repair_issue_does_not_create_phantom_pressure(self):
        todos = module.parse_todo_sections(TODO_TEXT)
        support = (
            "| ID | Priority | Status | Title | Evidence | Acceptance |\n"
            "| --- | --- | --- | --- | --- | --- |\n"
            "| SUPPORT-OPS-099 | P1 | Open | Broken thing | evidence | fix |\n"
        )
        candidate, reason = module.select_candidate(
            todos=todos,
            support_text=support,
            support_state={"items": {}},
            max_support_repairs=2,
            existing_issues={},
            eligible_support_ids=set(),
        )
        self.assertEqual(reason, "eligible")
        self.assertIsNotNone(candidate)
        self.assertEqual(candidate.item_id, "TODO-OPS-010")

    def test_blocked_support_does_not_starve_todo_forever(self):
        todos = module.parse_todo_sections(TODO_TEXT)
        support = (
            "| ID | Priority | Status | Title | Evidence | Acceptance |\n"
            "| --- | --- | --- | --- | --- | --- |\n"
            "| SUPPORT-OPS-099 | P1 | Open | Broken thing | evidence | fix |\n"
        )
        candidate, reason = module.select_candidate(
            todos=todos,
            support_text=support,
            support_state={
                "items": {
                    "SUPPORT-OPS-099": {
                        "phase": "blocked",
                        "reason": "requires human input",
                    }
                }
            },
            max_support_repairs=2,
            existing_issues={},
        )
        self.assertEqual(reason, "eligible")
        self.assertIsNotNone(candidate)
        self.assertEqual(candidate.item_id, "TODO-OPS-010")

    def test_todo_selected_by_priority_after_support_is_satisfied(self):
        todos = module.parse_todo_sections(TODO_TEXT)
        candidate, reason = module.select_candidate(
            todos=todos,
            support_text="",
            support_state={"items": {}},
            max_support_repairs=2,
            existing_issues={},
        )
        self.assertEqual(reason, "eligible")
        self.assertIsNotNone(candidate)
        self.assertEqual(candidate.item_id, "TODO-OPS-010")

    def test_existing_todo_issue_is_not_duplicated(self):
        todos = module.parse_todo_sections(TODO_TEXT)
        candidate, _ = module.select_candidate(
            todos=todos,
            support_text="",
            support_state={"items": {}},
            max_support_repairs=2,
            existing_issues={"TODO-OPS-010": {"number": 5}},
        )
        self.assertIsNone(candidate)

    def test_blocked_todo_issue_does_not_consume_open_issue_capacity(self):
        issues = {
            "TODO-GOV-002": {"number": 866},
            "TODO-COMM-001": {"number": 947},
            "TODO-COMM-004": {"number": 948},
        }
        with tempfile.TemporaryDirectory() as td:
            spool = Path(td)
            (spool / "development-state.json").write_text(
                json.dumps({
                    "items": {
                        "DEV-866": {"issue_number": 866, "phase": "blocked"},
                        "DEV-947": {"issue_number": 947, "phase": "diagnosing"},
                        "DEV-948": {"issue_number": 948, "phase": "diagnosing"},
                    }
                }),
                encoding="utf-8",
            )
            self.assertEqual(module.capacity_consuming_todo_issue_count(issues, spool), 2)

    def test_blocked_issue_still_suppresses_duplicate_todo_intake(self):
        todos = module.parse_todo_sections(TODO_TEXT)
        candidate, _ = module.select_candidate(
            todos=todos,
            support_text="",
            support_state={"items": {}},
            max_support_repairs=2,
            existing_issues={"TODO-OPS-010": {"number": 5}},
        )
        self.assertIsNone(candidate)

    def test_issue_body_binds_development_to_release_manager_completion(self):
        item = module.parse_todo_sections(TODO_TEXT)[0]
        body = module.issue_body(item)
        self.assertIn("- TODO item: TODO-OPS-010", body)
        self.assertIn("- TODO readiness: Approved", body)
        self.assertIn("- **Autonomous development:** owner-approved", body)
        self.assertIn("Release path: Jason Release Manager required", body)
        self.assertIn("production_verified", body)
        self.assertIn("Protected-core production approval: not granted by this intake", body)


if __name__ == "__main__":
    unittest.main()
