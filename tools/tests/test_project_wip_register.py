import importlib.util
from datetime import datetime, timezone
from pathlib import Path
import unittest


MODULE = Path(__file__).resolve().parents[1] / "project_wip_register.py"
SPEC = importlib.util.spec_from_file_location("project_wip_register", MODULE)
import sys
sys.path.insert(0, str(MODULE.parent))
wip = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(wip)
NOW = datetime(2026, 11, 10, tzinfo=timezone.utc)


def issue(n, state="open", body="", pull=False, reason=None, title="Work"):
    result = {
        "number": n, "state": state, "state_reason": reason, "title": title,
        "body": body, "created_at": "2026-11-09T12:00:00Z",
        "updated_at": "2026-11-09T13:00:00Z", "labels": []
    }
    if pull:
        result["pull_request"] = {"url": "https://example.invalid/pr"}
    return result


REGISTER_BODY = """# Project Jason — canonical Work in Progress (WIP) register

## ACTIVE WIP — project objectives (consolidated, not duplicate issues)

| # | Objective | Canonical references | Status |
| --- | --- | --- | --- |
| W01 | Teams approval | [#2376](https://github.com/al-teamaot-com/jason/issues/2376), [PR #2395](https://github.com/al-teamaot-com/jason/pull/2395) | Active |

## COMPLETED (100% independently verified)
*None.*
"""


class FakeApi:
    def __init__(self, recent, extra=None):
        self.body = REGISTER_BODY
        self.recent = recent
        self.extra = extra or {}
        self.writes = []

    def request(self, path, method="GET", payload=None):
        if path == "/issues/2396":
            if method == "PATCH":
                self.body = payload["body"]
                self.writes.append(self.body)
                return {}
            return {"body": self.body}
        if path.startswith("/pulls?"):
            return []
        if path.startswith("/issues?"):
            return self.recent if "page=1" in path else []
        if path.startswith("/issues/"):
            n = int(path.split("/")[-1])
            return self.extra.get(n, issue(n))
        raise AssertionError(path)


class WorkInProgressTests(unittest.TestCase):
    def test_references_extract_number_and_url(self):
        self.assertEqual(wip.references("PR #2395 and /issues/2376"), {2395, 2376})

    def test_completion_requires_full_evidence_and_closed_completed_state(self):
        marker = "<!-- jason-wip-verified: https://example.org/acceptance/123 -->"
        self.assertEqual(wip.is_done(issue(9, "open", marker, reason="completed"))[0], False)
        self.assertEqual(wip.is_done(issue(9, "closed", "not verified", reason="completed"))[0], False)
        self.assertEqual(wip.is_done(issue(9, "closed", marker, reason="not_planned"))[0], False)
        done, evidence = wip.is_done(issue(9, "closed", marker, reason="completed"))
        self.assertTrue(done)
        self.assertEqual(evidence, "https://example.org/acceptance/123")

    def test_register_dedupes_linked_work_and_is_idempotent(self):
        api = FakeApi([
            issue(2376, title="Existing tracked issue"),
            issue(2395, title="Existing tracked PR", pull=True),
            issue(2400, body="Fixes #2376", title="Child PR", pull=True),
            issue(2401, title="Independent task", pull=True),
            issue(2402, title="IDEA: later"),
        ])
        first = wip.reconcile(api, NOW)
        self.assertTrue(first["changed"])
        self.assertIn("GH-PR-2401", api.body)
        self.assertNotIn("GH-PR-2400", api.body)
        self.assertNotIn("GH-ISSUE-2376", api.body)
        self.assertNotIn("GH-ISSUE-2402", api.body)
        second = wip.reconcile(api, NOW)
        self.assertFalse(second["changed"])
        self.assertEqual(len(api.writes), 1)

    def test_closed_without_evidence_stays_active_but_verified_moves_to_history(self):
        api = FakeApi([issue(2401, title="Independent task", pull=True)])
        wip.reconcile(api, NOW)
        api.recent = []
        api.extra[2401] = issue(2401, state="closed", reason="completed", title="Independent task", pull=True)
        wip.reconcile(api, NOW)
        self.assertIn("Verification pending", api.body)
        evidence = "<!-- jason-wip-verified: https://example.org/proof/2401 -->"
        api.extra[2401] = issue(2401, state="closed", reason="completed", body=evidence, title="Independent task", pull=True)
        wip.reconcile(api, NOW)
        self.assertIn("**100% verified**", api.body)
        self.assertEqual(api.body.count("GH-PR-2401"), 1)

    def test_duplicate_support_incidents_are_one_group_with_all_sources(self):
        a = issue(2400, title="SUPPORT-AUTO-ABCDEF01 - Jason self-heal degraded")
        b = issue(2399, title="SUPPORT-AUTO-01234567 - Jason self-heal degraded")
        active, complete = wip.grouped_lines([a, b])
        self.assertEqual(len(active), 1)
        self.assertFalse(complete)
        self.assertIn("#2399", active[0])
        self.assertIn("#2400", active[0])
        self.assertEqual(set(wip.parse_existing("\n".join(active))), {2399, 2400})

    def test_curated_objective_requires_all_sources_verified(self):
        marker = "<!-- jason-wip-verified: https://example.org/verified -->"
        api = FakeApi([], {
            2376: issue(2376, "closed", marker, reason="completed"),
            2395: issue(2395, "open", marker, pull=True, reason="completed"),
        })
        self.assertEqual(wip.archive_curated_verified(REGISTER_BODY, api), REGISTER_BODY)
        api.extra[2395] = issue(2395, "closed", marker, pull=True, reason="completed")
        updated = wip.archive_curated_verified(REGISTER_BODY, api)
        self.assertEqual(updated.count("W01"), 1)
        self.assertNotIn("| W01 |", updated.split("## COMPLETED", 1)[0])
        self.assertIn("**100% independently verified:**", updated)

    def test_fail_closed_on_invalid_registry(self):
        api = FakeApi([])
        api.body = "unrelated text"
        with self.assertRaises(ValueError):
            wip.reconcile(api, NOW)


if __name__ == "__main__":
    unittest.main()
