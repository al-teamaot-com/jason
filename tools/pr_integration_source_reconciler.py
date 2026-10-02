#!/usr/bin/env python3
"""Host-side governed reconciliation for opted-in Project Jason pull requests.

This process intentionally runs outside GitHub Actions under Jason's existing
authenticated host GitHub identity. That allows a native PR branch update to
emit the normal pull_request/synchronize event, so protected required checks
are evaluated in their authoritative PR context.

The process updates or merges source only. It never deploys production.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

REPO = os.environ.get("JASON_REPOSITORY", "").strip()
ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = Path(
    os.environ.get(
        "JASON_DEVELOPMENT_RELEASE_CONFIG",
        str(ROOT / "config" / "development-release-coordinator.json"),
    )
)

ELIGIBILITY_PATTERN = re.compile(
    r"(?im)^\s*(?:-\s*)?Integration automation\s*:\s*enabled\s*$"
)
TRUSTED_ASSOCIATIONS = frozenset({"OWNER", "MEMBER", "COLLABORATOR"})


class IntegrationHostError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class IntegrationPolicy:
    base_branch: str
    required_checks: tuple[str, ...]
    additional_required_checks: tuple[str, ...]
    max_prs_per_run: int


def run(*args: str, check: bool = True) -> str:
    result = subprocess.run(
        args,
        text=True,
        capture_output=True,
        check=False,
    )
    if check and result.returncode != 0:
        stderr = result.stderr.strip()
        stdout = result.stdout.strip()
        raise IntegrationHostError(
            f"command failed rc={result.returncode}: {' '.join(args)}; "
            f"stderr={stderr[:500]}; stdout={stdout[:500]}"
        )
    return result.stdout.strip()


def gh_json(*args: str) -> Any:
    payload = run("gh", *args)
    return json.loads(payload or "null")


def load_policy(path: Path = CONFIG_PATH) -> IntegrationPolicy:
    payload = json.loads(path.read_text(encoding="utf-8"))
    integration = payload.get("integration_automation") or {}
    return IntegrationPolicy(
        base_branch=str(payload["base_branch"]),
        required_checks=tuple(str(item) for item in payload["required_checks"]),
        additional_required_checks=tuple(
            str(item)
            for item in integration.get("additional_required_checks", [])
        ),
        max_prs_per_run=max(
            1,
            int(integration.get("max_prs_per_run", 3)),
        ),
    )


def automation_enabled(body: str) -> bool:
    return ELIGIBILITY_PATTERN.search(body or "") is not None


def eligible_pr(pr: Mapping[str, Any], policy: IntegrationPolicy) -> bool:
    if str(pr.get("state") or "").lower() != "open":
        return False
    if bool(pr.get("draft")):
        return False
    if str(pr.get("author_association") or "").upper() not in TRUSTED_ASSOCIATIONS:
        return False
    base = pr.get("base")
    head = pr.get("head")
    if not isinstance(base, Mapping) or not isinstance(head, Mapping):
        return False
    if str(base.get("ref") or "") != policy.base_branch:
        return False
    head_repo = head.get("repo")
    if not isinstance(head_repo, Mapping):
        return False
    if str(head_repo.get("full_name") or "") != REPO:
        return False
    return automation_enabled(str(pr.get("body") or ""))


def open_pull_requests(policy: IntegrationPolicy) -> list[dict[str, Any]]:
    payload = gh_json(
        "api",
        f"repos/{REPO}/pulls"
        f"?state=open&base={policy.base_branch}&sort=updated&direction=asc&per_page=100",
    )
    if not isinstance(payload, list):
        raise IntegrationHostError("open pull-request query returned invalid payload")
    return [item for item in payload if isinstance(item, dict)]


def read_pr(number: int) -> dict[str, Any]:
    payload = gh_json("api", f"repos/{REPO}/pulls/{int(number)}")
    if not isinstance(payload, dict):
        raise IntegrationHostError(f"PR #{number} lookup returned invalid payload")
    return payload


def compare_to_base(pr: Mapping[str, Any], policy: IntegrationPolicy) -> dict[str, Any]:
    head = pr.get("head") or {}
    head_sha = str(head.get("sha") or "")
    if not head_sha:
        raise IntegrationHostError("PR is missing head SHA")
    payload = gh_json(
        "api",
        f"repos/{REPO}/compare/{policy.base_branch}...{head_sha}",
    )
    if not isinstance(payload, dict):
        raise IntegrationHostError("compare query returned invalid payload")
    return payload


def native_update_branch(number: int) -> None:
    """Use the authenticated host identity so normal PR synchronize CI runs."""
    run(
        "gh",
        "pr",
        "update-branch",
        str(int(number)),
        "--repo",
        REPO,
    )


def pr_required_checks(number: int) -> list[dict[str, Any]]:
    result = subprocess.run(
        [
            "gh",
            "pr",
            "checks",
            str(int(number)),
            "--repo",
            REPO,
            "--required",
            "--json",
            "name,state,bucket",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode not in (0, 8):
        raise IntegrationHostError(
            f"required-check query failed for PR #{number}: "
            f"{result.stderr.strip()[:500]}"
        )
    if not result.stdout.strip():
        return []
    payload = json.loads(result.stdout)
    return [item for item in payload if isinstance(item, dict)]


def required_check_state(number: int) -> tuple[str, tuple[str, ...]]:
    checks = pr_required_checks(number)
    if not checks:
        return "missing", ()
    failing = tuple(
        str(item.get("name") or "")
        for item in checks
        if str(item.get("bucket") or "").lower() == "fail"
    )
    if failing:
        return "failed", failing
    pending = tuple(
        str(item.get("name") or "")
        for item in checks
        if str(item.get("bucket") or "").lower() != "pass"
    )
    if pending:
        return "pending", pending
    return "passed", ()


def latest_check_runs(head_sha: str) -> dict[str, dict[str, Any]]:
    payload = gh_json(
        "api",
        f"repos/{REPO}/commits/{head_sha}/check-runs?per_page=100",
    )
    raw = payload.get("check_runs", []) if isinstance(payload, Mapping) else []
    latest: dict[str, dict[str, Any]] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "")
        if not name:
            continue
        current = latest.get(name)
        if current is None or int(item.get("id") or 0) > int(current.get("id") or 0):
            latest[name] = item
    return latest


def additional_check_state(
    pr: Mapping[str, Any],
    policy: IntegrationPolicy,
) -> tuple[str, tuple[str, ...]]:
    if not policy.additional_required_checks:
        return "passed", ()
    head = pr.get("head") or {}
    head_sha = str(head.get("sha") or "")
    latest = latest_check_runs(head_sha)
    missing: list[str] = []
    pending: list[str] = []
    failed: list[str] = []
    for name in policy.additional_required_checks:
        item = latest.get(name)
        if item is None:
            missing.append(name)
            continue
        if str(item.get("status") or "") != "completed":
            pending.append(name)
            continue
        if str(item.get("conclusion") or "") != "success":
            failed.append(name)
    if failed:
        return "failed", tuple(failed)
    if missing:
        return "missing", tuple(missing)
    if pending:
        return "pending", tuple(pending)
    return "passed", ()


def merge_pr(number: int) -> None:
    run(
        "gh",
        "pr",
        "merge",
        str(int(number)),
        "--repo",
        REPO,
        "--merge",
    )


def outcome_for_pr(
    pr: Mapping[str, Any],
    policy: IntegrationPolicy,
) -> str:
    number = int(pr["number"])
    current = read_pr(number)
    if not eligible_pr(current, policy):
        return "ineligible"

    comparison = compare_to_base(current, policy)
    if int(comparison.get("behind_by", 0) or 0) > 0:
        native_update_branch(number)
        return "updated_to_main"

    if bool(current.get("mergeable")) is False:
        mergeable_state = str(current.get("mergeable_state") or "").lower()
        if mergeable_state in {"dirty", "conflicting"}:
            return "conflict"

    required_state, required_detail = required_check_state(number)
    if required_state != "passed":
        detail = ",".join(item for item in required_detail if item)
        return f"required_{required_state}" + (f":{detail}" if detail else "")

    additional_state, additional_detail = additional_check_state(current, policy)
    if additional_state != "passed":
        detail = ",".join(item for item in additional_detail if item)
        return f"additional_{additional_state}" + (f":{detail}" if detail else "")

    # Re-read immediately before merge. If main moved while checks completed,
    # update the PR and wait for the next native PR-context validation cycle.
    current = read_pr(number)
    comparison = compare_to_base(current, policy)
    if int(comparison.get("behind_by", 0) or 0) > 0:
        native_update_branch(number)
        return "updated_to_newer_main"

    required_state, required_detail = required_check_state(number)
    if required_state != "passed":
        detail = ",".join(item for item in required_detail if item)
        return f"required_{required_state}" + (f":{detail}" if detail else "")

    merge_pr(number)
    return "merged"


def reconcile(policy: IntegrationPolicy) -> dict[int, str]:
    candidates = [
        item
        for item in open_pull_requests(policy)
        if eligible_pr(item, policy)
    ]
    outcomes: dict[int, str] = {}
    for item in candidates[: policy.max_prs_per_run]:
        number = int(item["number"])
        try:
            outcomes[number] = outcome_for_pr(item, policy)
        except Exception as exc:
            outcomes[number] = (
                f"error:{type(exc).__name__}:{str(exc)[:300]}"
            )
    return outcomes


def main() -> int:
    if "/" not in REPO:
        raise IntegrationHostError(
            "JASON_REPOSITORY must identify the configured Jason source repository"
        )
    policy = load_policy()
    outcomes = reconcile(policy)
    print(json.dumps({"outcomes": outcomes}, sort_keys=True))

    # Waiting, failed CI, and conflicts are fail-closed operational states, not
    # service failures. The timer continues so independent PRs can progress.
    infrastructure_errors = [
        value
        for value in outcomes.values()
        if value.startswith("error:")
    ]
    return 1 if infrastructure_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
