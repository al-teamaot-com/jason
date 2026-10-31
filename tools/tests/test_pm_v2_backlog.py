from pathlib import Path
import tempfile
import unittest

from pm_v2.backlog import parse_roadmap, reconcile_roadmap
from pm_v2.store import PMV2Store


TEXT = """# Project Jason TODO and Future Ideas

### TODO-OPS-001 — Approved thing
- **Priority:** P1
- **Status:** Approved for Autonomous Engineering — owner-approved
- **Autonomous engineering readiness:** Approved
- **Idea:** Do the approved thing.

### TODO-OPS-002 — Idea only
- **Priority:** P2
- **Status:** Proposed
- **Idea:** Maybe later.
"""


class PMV2BacklogTests(unittest.TestCase):
    def test_ideas_do_not_become_execution_authority(self):
        items = parse_roadmap(TEXT)
        self.assertTrue(items[0].autonomous_authority)
        self.assertFalse(items[1].autonomous_authority)

    def test_reconcile_preserves_proposal_only(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            roadmap = root / "roadmap.md"
            roadmap.write_text(TEXT, encoding="utf-8")
            store = PMV2Store(root / "state.sqlite3")
            store.initialize()
            summary = reconcile_roadmap(
                store,
                roadmap,
                owned_todo_ids=("TODO-OPS-001",),
                existing_issue_numbers={"TODO-OPS-001": 101},
            )
            self.assertEqual(summary["runnable"], 1)
            self.assertEqual(summary["proposal_only"], 1)
            rows = {r.source_ref: r for r in store.list_assignments()}
            self.assertEqual(rows["TODO-OPS-001"].state, "queued")
            self.assertEqual(rows["TODO-OPS-002"].state, "proposal_only")
            self.assertFalse(rows["TODO-OPS-002"].runnable)
