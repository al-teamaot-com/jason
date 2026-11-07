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

    def test_outstanding_work_is_visible_even_if_intake_has_no_candidate(self):
        with tempfile.TemporaryDirectory() as td:
            spool = Path(td)
            (spool / "todo-release-state.json").write_text(json.dumps({
                "items": {
                    "TODO-OPS-001": {"phase": "waiting_operational_acceptance", "reason": "live proof required"},
                    "TODO-OPS-002": {"phase": "development_blocked", "reason": "API prerequisite"},
                    "TODO-COMM-001": {"phase": "complete"},
                }
            }), encoding="utf-8")
            snapshot = module.outstanding_commitment_snapshot(spool)
            self.assertEqual(snapshot["status"], "known")
            self.assertEqual(snapshot["outstanding_count"], 2)
            self.assertEqual(snapshot["items"][0]["next_gate"], "production_outcome_verification")
            self.assertEqual(snapshot["items"][1]["next_gate"], "resolve_documented_development_blocker")
            self.assertEqual([item["id"] for item in snapshot["items"]], ["TODO-OPS-001", "TODO-OPS-002"])

    def test_missing_downstream_report_is_not_treated_as_empty_backlog(self):
        with tempfile.TemporaryDirectory() as td:
            snapshot = module.outstanding_commitment_snapshot(Path(td))
            self.assertEqual(snapshot["status"], "unknown")
            self.assertIsNone(snapshot["outstanding_count"])

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


class FullRepositoryTodoIntakeInventoryTests(unittest.TestCase):
    def _item(self, number, body='- TODO item: TODO-OPS-002', title='BackupIQ'):
        return {'number':number,'body':body,'title':title,'url':f'https://github.com/test/issues/{number}'}

    def test_older_canonical_issue_is_included_beyond_default_window(self):
        from unittest.mock import patch
        issues=[self._item(2021),self._item(952)]+[self._item(n,'', 'unrelated') for n in range(2000,2300)]
        with patch.object(module,'gh_json',return_value=issues) as gh:
            result=module.open_todo_issue_map(Path('/tmp/repo'))
        self.assertEqual(result['TODO-OPS-002']['number'],952)
        self.assertIn('5000',gh.call_args.args[0])

    def test_changed_duplicate_source_fails_closed(self):
        from unittest.mock import patch
        issues=[self._item(952),self._item(2021,'- TODO item: TODO-OPS-002\nOther instruction')]
        with patch.object(module,'gh_json',return_value=issues):
            with self.assertRaisesRegex(RuntimeError,'Conflicting GitHub TODO identities'):
                module.open_todo_issue_map(Path('/tmp/repo'))

    def test_saturated_inventory_never_authorizes_new_issue(self):
        from unittest.mock import patch
        with patch.object(module,'gh_json',return_value=[{} for _ in range(5000)]):
            with self.assertRaisesRegex(RuntimeError,'safe limit'):
                module.open_todo_issue_map(Path('/tmp/repo'))



class ConflictedIdentityIsolationTests(unittest.TestCase):
    def _issue(self, number, item_id="TODO-OPS-013", title=None, extra=""):
        return {
            "number": number,
            "title": title or f"Approved TODO {number}",
            "body": f"- TODO item: {item_id}\n{extra}",
            "url": f"https://github.com/al-teamaot-com/jason/issues/{number}",
        }

    def test_disjoint_approved_work_can_progress_while_identity_is_quarantined(self):
        from unittest.mock import patch
        issues = [self._issue(1500), self._issue(1459)]
        conflicts = {}
        with patch.object(module, "gh_json", return_value=issues):
            inventory = module.open_todo_issue_map(
                Path("/tmp/repo"), identity_conflicts=conflicts,
            )
        self.assertEqual(inventory["TODO-OPS-013"]["number"], 1459)
        self.assertEqual(conflicts["TODO-OPS-013"]["issue_numbers"], [1459, 1500])
        self.assertFalse(conflicts["TODO-OPS-013"]["new_work_authorized"])
        self.assertEqual(module.additional_conflict_capacity(conflicts), 1)
        candidate, reason = module.select_candidate(
            todos=module.parse_todo_sections(TODO_TEXT),
            support_text="", support_state={"items": {}},
            max_support_repairs=2, existing_issues=inventory,
        )
        self.assertEqual(reason, "eligible")
        self.assertEqual(candidate.item_id, "TODO-OPS-010")

    def test_quarantine_preserves_all_conflicting_identities_in_any_order(self):
        from unittest.mock import patch
        issues = [self._issue(1500), self._issue(1459), self._issue(1510)]
        with patch.object(module, "gh_json", return_value=issues):
            conflicts = {}
            result = module.open_todo_issue_map(
                Path("/tmp/repo"), identity_conflicts=conflicts,
            )
        self.assertEqual(result["TODO-OPS-013"]["number"], 1459)
        self.assertEqual(
            conflicts["TODO-OPS-013"]["issue_numbers"], [1459, 1500, 1510],
        )
        self.assertEqual(module.additional_conflict_capacity(conflicts), 2)

    def test_scheduled_dry_run_records_conflict_and_does_not_abort(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo, spool = root / "repo", root / "spool"
            (repo / "config").mkdir(parents=True)
            (repo / "config/development-release-coordinator.json").write_text(
                json.dumps({
                    "todo_autonomy": {"enabled": True, "max_active_items": 3,
                                     "max_open_todo_issues": 10},
                    "support_autonomy": {"max_active_items": 2},
                }), encoding="utf-8",
            )
            def git_read(args, *, cwd, check=True):
                self.assertEqual(args[0], "git")
                if args[1] == "fetch":
                    return ""
                if args[1] == "show" and "Project-Jason-TODO" in args[2]:
                    return TODO_TEXT
                if args[1] == "show" and args[2].endswith("SUPPORT.md"):
                    return ""
                raise AssertionError(f"unexpected command: {args!r}")
            with patch.object(module, "run", side_effect=git_read), \
                    patch.object(module, "gh_json", return_value=[
                        self._issue(1500), self._issue(1459)
                    ]), \
                    patch.object(module.support_worker, "open_support_issue_ids", return_value=set()), \
                    patch.object(module, "create_issue", side_effect=AssertionError("must not mutate")), \
                    patch.object(sys, "argv", [
                        "todo_engineering_intake.py", "--repo", str(repo),
                        "--spool", str(spool), "--dry-run",
                    ]):
                self.assertEqual(module.main(), 0)
            state = json.loads((spool / "todo-intake-state.json").read_text())
            self.assertEqual(state["status"], "dry_run")
            self.assertEqual(state["candidate"]["id"], "TODO-OPS-010")
            self.assertEqual(state["identity_conflict_count"], 1)
            self.assertEqual(
                state["identity_conflicts"]["TODO-OPS-013"]["issue_numbers"],
                [1459, 1500],
            )

    def test_new_conflict_at_creation_recheck_fails_closed_without_issue(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo, spool = root / "repo", root / "spool"
            (repo / "config").mkdir(parents=True)
            (repo / "config/development-release-coordinator.json").write_text(
                json.dumps({
                    "todo_autonomy": {"enabled": True, "max_active_items": 3,
                                     "max_open_todo_issues": 10},
                    "support_autonomy": {"max_active_items": 2},
                }), encoding="utf-8",
            )
            def git_read(args, *, cwd, check=True):
                if args[:2] == ["git", "fetch"]:
                    return ""
                if args[:2] == ["git", "show"]:
                    return TODO_TEXT if "Project-Jason-TODO" in args[2] else ""
                raise AssertionError(args)
            with patch.object(module, "run", side_effect=git_read), \
                    patch.object(module, "gh_json", side_effect=[
                        [], [
                            self._issue(1901, "TODO-OPS-010"),
                            self._issue(1902, "TODO-OPS-010"),
                        ],
                    ]), \
                    patch.object(module.support_worker, "open_support_issue_ids", return_value=set()), \
                    patch.object(module, "create_issue", side_effect=AssertionError("must not create")), \
                    patch.object(sys, "argv", [
                        "todo_engineering_intake.py", "--repo", str(repo),
                        "--spool", str(spool),
                    ]):
                self.assertEqual(module.main(), 0)
            state = json.loads((spool / "todo-intake-state.json").read_text())
            self.assertEqual(state["status"], "identity_conflict_quarantined")
            self.assertEqual(
                state["identity_conflicts"]["TODO-OPS-010"]["issue_numbers"],
                [1901, 1902],
            )
