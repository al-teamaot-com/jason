from pathlib import Path
import unittest
from unittest.mock import patch

import owner_approved_development_worker as worker


def _issue(number, *, pm_v2=False):
    body = "- **Autonomous development:** owner-approved\n"
    if pm_v2:
        body += "- Development controller: PM-V2\n"
    return {
        "number": number,
        "title": f"Issue {number}",
        "body": body,
        "url": f"https://example.invalid/{number}",
        "labels": [],
        "updatedAt": "2026-10-31T12:00:00Z",
    }


class PMV2WorkerSelectionTests(unittest.TestCase):
    def _fake_gh(self, args, cwd=None):
        if args[:2] == ["repo", "view"]:
            return {"nameWithOwner": "al-teamaot-com/jason"}
        if args[:2] == ["issue", "list"]:
            return [_issue(101, pm_v2=True), _issue(102, pm_v2=False)]
        if args and args[0] == "api":
            number = int(str(args[1]).rsplit("/", 1)[-1])
            return {
                "author_association": "OWNER",
                "user": {"login": "owner"},
                "number": number,
            }
        raise AssertionError(args)

    def test_v1_global_scan_skips_pm_v2_owned_issue(self):
        with patch.object(worker.support, "gh_json", side_effect=self._fake_gh):
            items = worker.owner_approved_issues(Path("/tmp/repo"))
        self.assertEqual([x["issue_number"] for x in items], [102])

    def test_exact_selector_can_claim_pm_v2_owned_issue(self):
        with patch.object(worker.support, "gh_json", side_effect=self._fake_gh):
            items = worker.owner_approved_issues(
                Path("/tmp/repo"), exact_issue_number=101
            )
        self.assertEqual([x["issue_number"] for x in items], [101])
