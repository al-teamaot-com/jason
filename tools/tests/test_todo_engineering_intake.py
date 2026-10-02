import importlib.util
import sys
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


def test_parse_todo_sections_preserves_exact_section():
    items = module.parse_todo_sections(TODO_TEXT)
    assert [item.item_id for item in items] == [
        "TODO-OPS-010",
        "TODO-OPS-011",
        "TODO-OPS-012",
    ]
    assert items[0].priority == "P1"
    assert items[0].status == "Planned"
    assert "Build the thing." in items[0].section


def test_only_planned_and_in_progress_are_executable():
    items = module.parse_todo_sections(TODO_TEXT)
    status = {item.item_id: item.executable for item in items}
    assert status["TODO-OPS-010"] is True
    assert status["TODO-OPS-012"] is True
    assert status["TODO-OPS-011"] is False


def test_support_first_blocks_todo_when_repair_capacity_exists():
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
    assert candidate is None
    assert "Support-first" in reason


def test_todo_selected_by_priority_after_support_is_satisfied():
    todos = module.parse_todo_sections(TODO_TEXT)
    support = (
        "| ID | Priority | Status | Title | Evidence | Acceptance |\n"
        "| --- | --- | --- | --- | --- | --- |\n"
    )
    candidate, reason = module.select_candidate(
        todos=todos,
        support_text=support,
        support_state={"items": {}},
        max_support_repairs=2,
        existing_issues={},
    )
    assert reason == "eligible"
    assert candidate is not None
    assert candidate.item_id == "TODO-OPS-010"


def test_existing_todo_issue_is_not_duplicated():
    todos = module.parse_todo_sections(TODO_TEXT)
    candidate, _ = module.select_candidate(
        todos=todos,
        support_text="",
        support_state={"items": {}},
        max_support_repairs=2,
        existing_issues={"TODO-OPS-010": {"number": 5}},
    )
    assert candidate is not None
    assert candidate.item_id == "TODO-OPS-012"


def test_issue_body_binds_development_to_release_manager_completion():
    item = module.parse_todo_sections(TODO_TEXT)[0]
    body = module.issue_body(item)
    assert "- TODO item: TODO-OPS-010" in body
    assert "- **Autonomous development:** owner-approved" in body
    assert "Release path: Jason Release Manager required" in body
    assert "production_verified" in body
    assert "Protected-core production approval: not granted by this intake" in body
