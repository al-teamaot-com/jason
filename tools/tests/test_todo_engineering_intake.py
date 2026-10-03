import importlib.util
import sys
import unittest
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

### TODO-OPS-010 — Planned high priority item

- **Priority:** P1
- **Status:** Planned
- **Risk level:** Moderate
- **Idea:** Build the thing.

### TODO-OPS-011 — Proposed item

- **Priority:** P0
- **Status:** Proposed
- **Idea:** Save this idea only.

### TODO-OPS-012 — In progress item

- **Priority:** P2
- **Status:** In progress — initial design exists
- **Idea:** Finish the thing.
"""


class TodoEngineeringIntakeTests(unittest.TestCase):
    def test_parse_todo_sections_preserves_exact_section(self):
        items = module.parse_todo_sections(TODO_TEXT)
        self.assertEqual(
            [item.item_id for item in items],
            ["TODO-OPS-010", "TODO-OPS-011", "TODO-OPS-012"],
        )
        self.assertEqual(items[0].priority, "P1")
        self.assertEqual(items[0].status, "Planned")
        self.assertIn("Build the thing.", items[0].section)

    def test_only_planned_and_in_progress_are_executable(self):
        items = module.parse_todo_sections(TODO_TEXT)
        status = {item.item_id: item.executable for item in items}
        self.assertTrue(status["TODO-OPS-010"])
        self.assertTrue(status["TODO-OPS-012"])
        self.assertFalse(status["TODO-OPS-011"])

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
        self.assertIsNotNone(candidate)
        self.assertEqual(candidate.item_id, "TODO-OPS-012")

    def test_issue_body_binds_development_to_release_manager_completion(self):
        item = module.parse_todo_sections(TODO_TEXT)[0]
        body = module.issue_body(item)
        self.assertIn("- TODO item: TODO-OPS-010", body)
        self.assertIn("- **Autonomous development:** owner-approved", body)
        self.assertIn("Release path: Jason Release Manager required", body)
        self.assertIn("production_verified", body)
        self.assertIn("Protected-core production approval: not granted by this intake", body)


if __name__ == "__main__":
    unittest.main()
