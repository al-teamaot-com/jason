from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from pmv4_shadow_ci import (
    protected_main_ci_verified, REQUIRED_WORKFLOWS,
    BASELINE_REQUIRED_CHECKS, GITHUB_ACTIONS_APP_ID,
)

SHA = "a" * 40
NOW = datetime(2026, 11, 11, 18, 0, tzinfo=timezone.utc)


def fake_runner(*, sha=SHA, workflows=None, branch="main", event="push", rc=0,
                required_contexts=None, check_runs=None, strict=True, total=None):
    if workflows is None:
        workflows = [
            {
                "name": name, "head_sha": sha, "head_branch": branch,
                "status": "completed", "conclusion": "success",
                "event": event, "updated_at": NOW.isoformat(),
            } for name in REQUIRED_WORKFLOWS
        ]

    if required_contexts is None:
        required_contexts = sorted(BASELINE_REQUIRED_CHECKS)
    if check_runs is None:
        check_runs = [dict(
            name=name, head_sha=sha, status="completed", conclusion="success",
            completed_at=NOW.isoformat(), app={"id": GITHUB_ACTIONS_APP_ID},
        ) for name in required_contexts]

    def run(argv, **kw):
        assert argv[:2] == ["/usr/bin/gh", "api"]
        assert kw["shell"] is False
        assert kw["timeout"] == 20
        if argv[-1].endswith("/branches/main"):
            payload = {"name": "main", "protected": True, "commit": {"sha": sha}}
        elif argv[-1].endswith("/protection/required_status_checks"):
            payload = {"strict": strict, "checks": [
                {"context": name, "app_id": GITHUB_ACTIONS_APP_ID}
                for name in required_contexts
            ]}
        elif "/check-runs?" in argv[-1]:
            assert SHA in argv[-1]
            payload = {"total_count": len(check_runs) if total is None else total,
                       "check_runs": check_runs}
        else:
            assert "head_sha=" + SHA in argv[-1]
            payload = {"workflow_runs": workflows}
        return subprocess.CompletedProcess(argv, rc, json.dumps(payload), "")
    return run


class GitHubVerifierTests(unittest.TestCase):
    def test_genuine_protected_source_requires_all_green(self):
        self.assertTrue(protected_main_ci_verified(SHA, runner=fake_runner(), at=NOW))

    def test_non_main_candidate_rejected(self):
        self.assertFalse(protected_main_ci_verified("b"*40, runner=fake_runner(), at=NOW))

    def test_missing_workflow_rejected(self):
        missing = [dict(name=name, head_sha=SHA, head_branch="main", event="push",
                        status="completed", conclusion="success",
                        updated_at=NOW.isoformat())
                   for name in list(REQUIRED_WORKFLOWS)[:-1]]
        self.assertFalse(protected_main_ci_verified(SHA, runner=fake_runner(workflows=missing), at=NOW))

    def test_green_pr_only_is_not_protected_main_push(self):
        self.assertFalse(protected_main_ci_verified(SHA, runner=fake_runner(event="pull_request"), at=NOW))

    def test_stale_check_results_rejected(self):
        stale = [dict(name=name, head_sha=SHA, head_branch="main", event="push",
                      status="completed", conclusion="success",
                      updated_at=(NOW - timedelta(days=2)).isoformat())
                 for name in REQUIRED_WORKFLOWS]
        self.assertFalse(protected_main_ci_verified(SHA, runner=fake_runner(workflows=stale), at=NOW))

    def test_partial_red_incomplete_rejected(self):
        base = [dict(name=name, head_sha=SHA, head_branch="main", event="push",
                     status="completed", conclusion="success",
                     updated_at=NOW.isoformat()) for name in REQUIRED_WORKFLOWS]
        base[0]["conclusion"] = "failure"
        self.assertFalse(protected_main_ci_verified(SHA, runner=fake_runner(workflows=base), at=NOW))
        base[0]["conclusion"] = "success"
        base[1]["status"] = "queued"
        self.assertFalse(protected_main_ci_verified(SHA, runner=fake_runner(workflows=base), at=NOW))

    def test_provider_failure_fails_closed(self):
        self.assertFalse(protected_main_ci_verified(SHA, runner=fake_runner(rc=1), at=NOW))
        self.assertFalse(protected_main_ci_verified("--danger", runner=fake_runner(), at=NOW))

    def test_malformed_response_fails_closed(self):
        def runner(argv, **kwargs):
            return subprocess.CompletedProcess(argv, 0, "not-json", "")
        self.assertFalse(protected_main_ci_verified(SHA, runner=runner, at=NOW))

    def test_later_failure_overrides_earlier_success(self):
        green = [dict(name=name, head_sha=SHA, head_branch="main", event="push",
                      status="completed", conclusion="success", updated_at=(NOW - timedelta(minutes=10)).isoformat())
                 for name in REQUIRED_WORKFLOWS]
        bad = dict(green[0])
        bad["status"] = "completed"
        bad["conclusion"] = "failure"
        bad["updated_at"] = NOW.isoformat()
        self.assertFalse(protected_main_ci_verified(SHA, runner=fake_runner(workflows=green + [bad]), at=NOW))

    def test_all_branch_protection_required_jobs_must_pass(self):
        green = [dict(name=name, head_sha=SHA, status="completed",
                      conclusion="success", completed_at=NOW.isoformat(),
                      app={"id": GITHUB_ACTIONS_APP_ID})
                 for name in sorted(BASELINE_REQUIRED_CHECKS)]
        red = [dict(x) for x in green]
        red[0]["conclusion"] = "failure"
        self.assertFalse(protected_main_ci_verified(SHA, runner=fake_runner(check_runs=red), at=NOW))
        self.assertFalse(protected_main_ci_verified(SHA, runner=fake_runner(check_runs=green[:-1]), at=NOW))
        self.assertFalse(protected_main_ci_verified(SHA, runner=fake_runner(
            check_runs=green, total=101,
        ), at=NOW))

    def test_branch_protection_drift_fails_closed(self):
        self.assertFalse(protected_main_ci_verified(
            SHA, runner=fake_runner(required_contexts=["runtime-service"]), at=NOW))
        self.assertFalse(protected_main_ci_verified(
            SHA, runner=fake_runner(strict=False), at=NOW))

    def test_untrusted_check_app_or_stale_check_rejected(self):
        check_runs = [dict(name=name, head_sha=SHA, status="completed",
                           conclusion="success", completed_at=NOW.isoformat(),
                           app={"id": GITHUB_ACTIONS_APP_ID})
                      for name in sorted(BASELINE_REQUIRED_CHECKS)]
        check_runs[0]["app"] = {"id": 8888}
        self.assertFalse(protected_main_ci_verified(
            SHA, runner=fake_runner(check_runs=check_runs), at=NOW))
        check_runs[0]["app"] = {"id": GITHUB_ACTIONS_APP_ID}
        check_runs[1]["completed_at"] = (NOW - timedelta(days=2)).isoformat()
        self.assertFalse(protected_main_ci_verified(
            SHA, runner=fake_runner(check_runs=check_runs), at=NOW))

    def test_timestamp_in_future_rejected(self):
        rows = [dict(name=name, head_sha=SHA, head_branch="main", event="push",
                     status="completed", conclusion="success",
                     updated_at=(NOW + timedelta(hours=2)).isoformat())
                for name in REQUIRED_WORKFLOWS]
        self.assertFalse(protected_main_ci_verified(SHA, runner=fake_runner(workflows=rows), at=NOW))


if __name__ == "__main__":
    unittest.main()
