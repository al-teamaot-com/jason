#!/usr/bin/env python3
"""Governed PR branch reconciliation and green-check merge coordinator.

This is source-integration automation only. It never deploys production and it
never bypasses branch protection, failed checks, merge conflicts, or explicit
PR eligibility.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "development-release-coordinator.json"

ELIGIBILITY_PATTERN = re.compile(
    r"(?im)^\s*(?:-\s*)?Integration automation\s*:\s*enabled\s*$"
)
TRUSTED_ASSOCIATIONS = frozenset({"OWNER", "MEMBER", "COLLABORATOR"})


class ReconciliationError(RuntimeError):
    pass


class MergeConflict(ReconciliationError):
    pass


@dataclass(frozen=True, slots=True)
class IntegrationConfig:
    base_branch: str
    required_checks: tuple[str, ...]
    validation_workflows: tuple[str, ...]
    eligibility_marker: str
    poll_seconds: int
    timeout_seconds: int
    max_prs_per_run: int
    max_reconcile_passes: int


@dataclass
class Api:
    repository: str
    token: str

    def request(
        self,
        path: str,
        *,
        method: str = "GET",
        payload: Mapping[str, Any] | None = None,
    ) -> Any:
        url = f"https://api.github.com/repos/{self.repository}{path}"
        data = None if payload is None else json.dumps(dict(payload)).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "project-jason-pr-reconciler",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read()
                if not raw:
                    return {}
                return json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            if exc.code == 409:
                raise MergeConflict(detail or "GitHub reported a merge conflict") from exc
            raise ReconciliationError(
                f"GitHub API {method} {path} failed with HTTP {exc.code}: {detail}"
            ) from exc

    def paged(self, path: str) -> list[dict[str, Any]]:
        page = 1
        items: list[dict[str, Any]] = []
        while True:
            sep = "&" if "?" in path else "?"
            payload = self.request(f"{path}{sep}per_page=100&page={page}")
            if not isinstance(payload, list):
                raise ReconciliationError(f"Expected list response from {path}")
            items.extend(payload)
            if len(payload) < 100:
                return items
            page += 1


def load_config(path: Path) -> IntegrationConfig:
    payload = json.loads(path.read_text(encoding="utf-8"))
    integration = payload.get("integration_automation", {})
    return IntegrationConfig(
        base_branch=str(payload["base_branch"]),
        required_checks=tuple(
            list(payload["required_checks"])
            + list(integration.get("additional_required_checks", []))
        ),
        validation_workflows=tuple(integration["validation_workflows"]),
        eligibility_marker=str(
            integration.get("eligibility_marker", "Integration automation: enabled")
        ),
        poll_seconds=max(5, int(integration.get("poll_seconds", 15))),
        timeout_seconds=max(60, int(integration.get("timeout_seconds", 1800))),
        max_prs_per_run=max(1, int(integration.get("max_prs_per_run", 3))),
        max_reconcile_passes=max(
            1, int(integration.get("max_reconcile_passes", 3))
        ),
    )


def automation_enabled(body: str) -> bool:
    return ELIGIBILITY_PATTERN.search(body or "") is not None


def eligible_pr(pr: Mapping[str, Any], *, repository: str, base_branch: str) -> bool:
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
    if str(base.get("ref") or "") != base_branch:
        return False
    head_repo = head.get("repo")
    if not isinstance(head_repo, Mapping):
        return False
    if str(head_repo.get("full_name") or "") != repository:
        return False
    return automation_enabled(str(pr.get("body") or ""))


def latest_checks(check_runs: list[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    latest: dict[str, Mapping[str, Any]] = {}
    for check in check_runs:
        name = str(check.get("name") or "")
        if not name:
            continue
        current = latest.get(name)
        if current is None or int(check.get("id") or 0) > int(current.get("id") or 0):
            latest[name] = check
    return latest


def required_check_state(
    required: tuple[str, ...],
    check_runs: list[Mapping[str, Any]],
) -> tuple[str, list[str]]:
    latest = latest_checks(check_runs)
    missing: list[str] = []
    pending: list[str] = []
    failed: list[str] = []
    for name in required:
        check = latest.get(name)
        if check is None:
            missing.append(name)
            continue
        if str(check.get("status") or "") != "completed":
            pending.append(name)
            continue
        if str(check.get("conclusion") or "") != "success":
            failed.append(name)
    if failed:
        return "failed", failed
    if missing:
        return "missing", missing
    if pending:
        return "pending", pending
    return "passed", []


def current_main_sha(api: Api, branch: str) -> str:
    data = api.request(f"/branches/{urllib.parse.quote(branch, safe='')}")
    return str(data["commit"]["sha"])


def compare_with_main(api: Api, *, main_sha: str, head_sha: str) -> Mapping[str, Any]:
    return api.request(
        f"/compare/{urllib.parse.quote(main_sha, safe='')}..."
        f"{urllib.parse.quote(head_sha, safe='')}"
    )


def refresh_pr(api: Api, number: int) -> dict[str, Any]:
    payload = api.request(f"/pulls/{number}")
    if not isinstance(payload, dict):
        raise ReconciliationError(f"PR #{number} did not return an object")
    return payload


def wait_for_reconciled_head(
    api: Api,
    *,
    pr_number: int,
    previous_head_sha: str,
    expected_head_sha: str | None,
    poll_seconds: float = 1.0,
    timeout_seconds: float = 60.0,
) -> dict[str, Any]:
    """Wait until GitHub's PR read model observes the merge-created head.

    The merge endpoint can acknowledge a branch merge before the pull-request
    endpoint reflects the new head SHA. Validation must never run against the
    stale pre-merge head.
    """

    deadline = time.monotonic() + timeout_seconds
    while True:
        current = refresh_pr(api, pr_number)
        current_sha = str(current["head"]["sha"])
        if current_sha != previous_head_sha:
            if expected_head_sha and current_sha != expected_head_sha:
                raise ReconciliationError(
                    f"PR #{pr_number} head changed to unexpected SHA "
                    f"{current_sha}; expected merge head {expected_head_sha}"
                )
            return current
        if time.monotonic() >= deadline:
            raise ReconciliationError(
                f"PR #{pr_number} head did not advance from "
                f"{previous_head_sha} after main reconciliation"
            )
        time.sleep(max(0.0, poll_seconds))


def reconcile_branch(api: Api, pr: Mapping[str, Any], main_sha: str) -> dict[str, Any]:
    number = int(pr["number"])
    head = pr["head"]
    branch = str(head["ref"])
    previous_head_sha = str(head["sha"])
    result = api.request(
        "/merges",
        method="POST",
        payload={
            "base": branch,
            "head": main_sha,
            "commit_message": (
                f"Reconcile PR #{number} with {str(pr['base']['ref'])} {main_sha[:12]}"
            ),
        },
    )
    expected_head_sha = (
        str(result.get("sha"))
        if isinstance(result, Mapping) and result.get("sha")
        else None
    )
    return wait_for_reconciled_head(
        api,
        pr_number=number,
        previous_head_sha=previous_head_sha,
        expected_head_sha=expected_head_sha,
    )


def dispatch_validation(
    api: Api,
    *,
    workflow: str,
    branch: str,
    pr_number: int,
) -> None:
    encoded = urllib.parse.quote(workflow, safe="")
    api.request(
        f"/actions/workflows/{encoded}/dispatches",
        method="POST",
        payload={
            "ref": branch,
            "inputs": {"pr_number": str(pr_number)},
        },
    )


def check_runs(api: Api, sha: str) -> list[Mapping[str, Any]]:
    payload = api.request(f"/commits/{sha}/check-runs?per_page=100")
    runs = payload.get("check_runs", []) if isinstance(payload, Mapping) else []
    return [item for item in runs if isinstance(item, Mapping)]


def wait_for_required_checks(
    api: Api,
    *,
    sha: str,
    required: tuple[str, ...],
    poll_seconds: int,
    timeout_seconds: int,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while True:
        state, detail = required_check_state(required, check_runs(api, sha))
        if state == "passed":
            return
        if state == "failed":
            raise ReconciliationError(
                "required checks failed: " + ", ".join(sorted(detail))
            )
        if time.monotonic() >= deadline:
            raise ReconciliationError(
                f"required checks did not complete before timeout; state={state}; "
                f"detail={','.join(sorted(detail))}"
            )
        time.sleep(poll_seconds)


def merge_pr(api: Api, *, pr_number: int, head_sha: str) -> Mapping[str, Any]:
    result = api.request(
        f"/pulls/{pr_number}/merge",
        method="PUT",
        payload={
            "sha": head_sha,
            "merge_method": "merge",
            "commit_title": f"Merge pull request #{pr_number} after governed reconciliation",
        },
    )
    if not bool(result.get("merged")):
        raise ReconciliationError(
            f"GitHub did not merge PR #{pr_number}: {result.get('message', 'unknown reason')}"
        )
    return result


def add_comment(api: Api, *, pr_number: int, body: str) -> None:
    api.request(
        f"/issues/{pr_number}/comments",
        method="POST",
        payload={"body": body},
    )


def process_pr(api: Api, config: IntegrationConfig, pr: Mapping[str, Any]) -> str:
    number = int(pr["number"])
    for reconcile_pass in range(1, config.max_reconcile_passes + 1):
        pr = refresh_pr(api, number)
        if not eligible_pr(
            pr,
            repository=api.repository,
            base_branch=config.base_branch,
        ):
            return "ineligible"

        main_sha = current_main_sha(api, config.base_branch)
        head_sha = str(pr["head"]["sha"])
        comparison = compare_with_main(api, main_sha=main_sha, head_sha=head_sha)
        if int(comparison.get("behind_by", 0) or 0) > 0:
            try:
                pr = reconcile_branch(api, pr, main_sha)
            except MergeConflict as exc:
                add_comment(
                    api,
                    pr_number=number,
                    body=(
                        "<!-- jason-pr-reconciler-conflict -->\n"
                        f"Automatic reconciliation stopped safely because PR #{number} "
                        f"conflicts with current `{config.base_branch}`. No force merge "
                        f"or conflict override was attempted.\n\nDetails: `{str(exc)[:500]}`"
                    ),
                )
                return "conflict"

        head_sha = str(pr["head"]["sha"])
        state, _ = required_check_state(
            config.required_checks,
            check_runs(api, head_sha),
        )
        if state != "passed":
            for workflow in config.validation_workflows:
                dispatch_validation(
                    api,
                    workflow=workflow,
                    branch=str(pr["head"]["ref"]),
                    pr_number=number,
                )
            try:
                wait_for_required_checks(
                    api,
                    sha=head_sha,
                    required=config.required_checks,
                    poll_seconds=config.poll_seconds,
                    timeout_seconds=config.timeout_seconds,
                )
            except ReconciliationError as exc:
                add_comment(
                    api,
                    pr_number=number,
                    body=(
                        "<!-- jason-pr-reconciler-validation -->\n"
                        f"Automatic integration stopped safely on head `{head_sha[:12]}`: "
                        f"{exc}. The PR was not merged."
                    ),
                )
                return "validation_failed"

        latest_main = current_main_sha(api, config.base_branch)
        latest_pr = refresh_pr(api, number)
        latest_head = str(latest_pr["head"]["sha"])
        comparison = compare_with_main(
            api,
            main_sha=latest_main,
            head_sha=latest_head,
        )
        if int(comparison.get("behind_by", 0) or 0) > 0:
            if reconcile_pass == config.max_reconcile_passes:
                return "main_moved"
            continue

        merge_pr(api, pr_number=number, head_sha=latest_head)
        return "merged"

    return "main_moved"


def open_pull_requests(api: Api, base_branch: str) -> list[dict[str, Any]]:
    pulls = api.paged(
        f"/pulls?state=open&base={urllib.parse.quote(base_branch, safe='')}"
        "&sort=updated&direction=asc"
    )
    return [pr for pr in pulls if isinstance(pr, dict)]


def run(api: Api, config: IntegrationConfig) -> dict[int, str]:
    eligible = [
        pr
        for pr in open_pull_requests(api, config.base_branch)
        if eligible_pr(pr, repository=api.repository, base_branch=config.base_branch)
    ]
    outcomes: dict[int, str] = {}
    for pr in eligible[: config.max_prs_per_run]:
        number = int(pr["number"])
        try:
            outcomes[number] = process_pr(api, config, pr)
        except Exception as exc:
            outcomes[number] = f"error:{type(exc).__name__}:{str(exc)[:300]}"
    return outcomes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--repository",
        default=os.environ.get("GITHUB_REPOSITORY", ""),
    )
    parser.add_argument("--token", default=os.environ.get("GITHUB_TOKEN", ""))
    args = parser.parse_args()

    if not args.repository:
        raise SystemExit("ERROR: repository is required")
    if not args.token:
        raise SystemExit("ERROR: GITHUB_TOKEN is required")

    config = load_config(args.config)
    api = Api(args.repository, args.token)
    outcomes = run(api, config)
    print(json.dumps({"outcomes": outcomes}, sort_keys=True))

    blocking = {
        value
        for value in outcomes.values()
        if value not in {"merged", "ineligible"}
    }
    return 1 if blocking else 0


if __name__ == "__main__":
    raise SystemExit(main())
