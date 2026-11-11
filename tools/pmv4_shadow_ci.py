#!/usr/bin/env python3
"""Read-only independent GitHub protected-source / check verifier for PMv4.

No reliance on PMV3 release runtime, release queue, Teams, or local CI claims.
Live GitHub API is authoritative; failure is a denial, not a fallback.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import re
import subprocess
from typing import Any, Callable, Mapping

REPO = "al-teamaot-com/jason"
HEAD = re.compile(r"\A[0-9a-f]{40}\Z")
REQUIRED_WORKFLOWS = frozenset((
    "Validate Jason",
    "SEC-007 Security Regressions",
    "Validate Jason Teams Gateway",
    "Validate Conversation Experience Foundation",
))
# Actual protected-main required checks verified against GitHub on Nov 11.
# Changes may ADD checks, but removing the baseline requires reviewed source.
BASELINE_REQUIRED_CHECKS = frozenset((
    "cap-001", "cap-003", "cap-007", "system-registry",
    "runtime-service", "repository-hygiene",
    "conversation-experience", "teams-gateway",
))
GITHUB_ACTIONS_APP_ID = 15368
MAX_RESPONSE = 2 * 1024 * 1024


def github_json(endpoint: str, *, runner: Callable[..., Any] = subprocess.run) -> Mapping[str, Any]:
    # Endpoints are assembled internally from an exact SHA or fixed URI.
    if not endpoint.startswith(f"/repos/{REPO}/"):
        raise ValueError("untrusted GitHub endpoint")
    args = ["/usr/bin/gh", "api", "-H", "Accept: application/vnd.github+json", endpoint]
    try:
        proc = runner(args, shell=False, capture_output=True, text=True,
                      check=False, timeout=20)
    except (OSError, subprocess.TimeoutExpired, TypeError, ValueError) as exc:
        raise RuntimeError("GITHUB_SOURCE_UNAVAILABLE") from exc
    if proc.returncode != 0 or not isinstance(proc.stdout, str):
        raise RuntimeError("GITHUB_SOURCE_UNAVAILABLE")
    if len(proc.stdout.encode("utf-8")) > MAX_RESPONSE:
        raise RuntimeError("GITHUB_RESPONSE_OVERSIZE")
    try:
        result = json.loads(proc.stdout)
    except (ValueError, TypeError) as exc:
        raise RuntimeError("GITHUB_RESPONSE_INVALID") from exc
    if not isinstance(result, dict):
        raise RuntimeError("GITHUB_RESPONSE_INVALID")
    return result


def protected_main_ci_verified(candidate_sha: str, *,
                               runner: Callable[..., Any] = subprocess.run,
                               at: datetime | None = None) -> bool:
    """Require the exact *current protected main* SHA and fresh green workflows."""
    if not isinstance(candidate_sha, str) or not HEAD.fullmatch(candidate_sha):
        return False
    now = at or datetime.now(timezone.utc)
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        return False
    try:
        main = github_json(f"/repos/{REPO}/branches/main", runner=runner)
        main_sha = (main.get("commit") or {}).get("sha")
        if (main_sha != candidate_sha or main.get("name") != "main"
            or main.get("protected") is not True):
            return False
        runs = github_json(
            f"/repos/{REPO}/actions/runs?head_sha={candidate_sha}&per_page=100",
            runner=runner,
        )
        if not isinstance(runs.get("workflow_runs"), list) or len(runs["workflow_runs"]) > 100:
            return False
        latest: dict[str, tuple[datetime, bool]] = {}
        for workflow in runs["workflow_runs"]:
            if not isinstance(workflow, dict):
                continue
            name = workflow.get("name")
            if name not in REQUIRED_WORKFLOWS:
                continue
            if (workflow.get("head_sha") != candidate_sha
                or workflow.get("head_branch") != "main"
                or workflow.get("event") != "push"):
                continue
            finished = workflow.get("updated_at")
            if not isinstance(finished, str):
                return False
            timestamp = datetime.fromisoformat(finished.replace("Z", "+00:00"))
            if timestamp.tzinfo is None or not now - timedelta(hours=24) <= timestamp <= now:
                return False
            ok = (workflow.get("status") == "completed"
                  and workflow.get("conclusion") == "success")
            if name in latest and timestamp == latest[name][0]:
                # Ambiguous duplicate source evidence must not accidentally
                # promote an older success over a simultaneous failure.
                latest[name] = (timestamp, latest[name][1] and ok)
            elif name not in latest or timestamp > latest[name][0]:
                latest[name] = (timestamp, ok)
        if not (set(latest) == REQUIRED_WORKFLOWS
                and all(ok for _, ok in latest.values())):
            return False
        # Workflow-success summaries alone do NOT satisfy the real required
        # check run contexts on protected main. Inspect the native branch
        # policy and each exact-SHA GitHub Actions check run independently.
        protection = github_json(
            f"/repos/{REPO}/branches/main/protection/required_status_checks",
            runner=runner,
        )
        required = protection.get("checks")
        if (protection.get("strict") is not True
            or not isinstance(required, list)
            or len(required) < len(BASELINE_REQUIRED_CHECKS)
            or len(required) > 60):
            return False
        expected: dict[str, int] = {}
        for requirement in required:
            if (not isinstance(requirement, dict)
                or not isinstance(requirement.get("context"), str)
                or not isinstance(requirement.get("app_id"), int)
                or isinstance(requirement.get("app_id"), bool)
                or requirement["app_id"] <= 0
                or requirement["context"] in expected):
                return False
            expected[requirement["context"]] = requirement["app_id"]
        if (not BASELINE_REQUIRED_CHECKS.issubset(expected)
            or any(expected[name] != GITHUB_ACTIONS_APP_ID
                   for name in BASELINE_REQUIRED_CHECKS)):
            return False
        checks = github_json(
            f"/repos/{REPO}/commits/{candidate_sha}/check-runs?per_page=100",
            runner=runner,
        )
        all_runs = checks.get("check_runs")
        total = checks.get("total_count")
        if (not isinstance(all_runs, list)
            or not isinstance(total, int) or isinstance(total, bool)
            or total > 100 or total != len(all_runs)):
            return False
        observed: dict[str, tuple[datetime, bool]] = {}
        for check in all_runs:
            if not isinstance(check, dict) or check.get("name") not in expected:
                continue
            name = check["name"]
            app = check.get("app")
            if (check.get("head_sha") != candidate_sha
                or not isinstance(app, dict)
                or app.get("id") != expected[name]):
                continue
            finished = check.get("completed_at")
            if not isinstance(finished, str):
                return False
            timestamp = datetime.fromisoformat(finished.replace("Z", "+00:00"))
            if timestamp.tzinfo is None or not now - timedelta(hours=24) <= timestamp <= now:
                return False
            ok = check.get("status") == "completed" and check.get("conclusion") == "success"
            if name in observed and timestamp == observed[name][0]:
                observed[name] = (timestamp, observed[name][1] and ok)
            elif name not in observed or timestamp > observed[name][0]:
                observed[name] = (timestamp, ok)
        return set(observed) == set(expected) and all(
            ok for _, ok in observed.values()
        )
    except (RuntimeError, AttributeError, TypeError, ValueError, OverflowError):
        return False


if __name__ == "__main__":
    raise SystemExit("Library only: require independent protected-main verification.")
