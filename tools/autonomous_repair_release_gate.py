#!/usr/bin/env python3
"""Classify merged Project Jason support fixes for autonomous repair release.

This gate never performs deployment. It decides whether a merged support fix
belongs to the pre-authorized repair class and whether all execution
preconditions are satisfied. Production execution must still occur through the
named governed deployment capability defined by Jason's deployment system.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = ROOT / "config" / "autonomous-repair-release-policy.json"
SUPPORT = ROOT / "SUPPORT.md"
PRODUCTION_STATE = ROOT / "docs" / "control" / "AUTOMATED-CHANGE-STATE.json"

SUPPORT_ROW = re.compile(
    r"^\|\s*(SUPPORT-[^|]+?)\s*\|\s*(P\d)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|"
)
META_LINE = re.compile(r"^\s*-\s*([^:]+?)\s*:\s*(.*?)\s*$")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


class Api:
    def __init__(self, repository: str, token: str) -> None:
        self.repository = repository
        self.token = token

    def request(self, path: str, method: str = "GET", payload: dict[str, Any] | None = None) -> Any:
        url = f"https://api.github.com/repos/{self.repository}{path}"
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "project-jason-autonomous-repair-release",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else None

    def paged(self, path: str) -> list[dict[str, Any]]:
        page = 1
        results: list[dict[str, Any]] = []
        while True:
            sep = "&" if "?" in path else "?"
            payload = self.request(f"{path}{sep}per_page=100&page={page}")
            if not isinstance(payload, list):
                raise RuntimeError(f"Expected list response from {path}")
            results.extend(payload)
            if len(payload) < 100:
                return results
            page += 1


def normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def parse_metadata(body: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in (body or "").splitlines():
        match = META_LINE.match(raw)
        if not match:
            continue
        result[normalize_key(match.group(1))] = match.group(2).strip()
    return result


def parse_open_support(text: str) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for raw in text.splitlines():
        match = SUPPORT_ROW.match(raw)
        if not match:
            continue
        item_id, priority, status, title = (part.strip() for part in match.groups())
        low = status.lower()
        if any(word in low for word in ("resolved", "closed", "reclassified")):
            continue
        result[item_id] = {
            "id": item_id,
            "priority": priority,
            "status": status,
            "title": title,
        }
    return result


def latest_checks(check_runs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for check in check_runs:
        name = str(check.get("name") or "")
        if not name:
            continue
        if name not in latest or int(check.get("id", 0)) > int(latest[name].get("id", 0)):
            latest[name] = check
    return latest


def check_summary(required: list[str], check_runs: list[dict[str, Any]]) -> tuple[bool, list[str]]:
    latest = latest_checks(check_runs)
    problems: list[str] = []
    for name in required:
        check = latest.get(name)
        if check is None:
            problems.append(f"missing required check: {name}")
            continue
        if check.get("status") != "completed":
            problems.append(f"required check still pending: {name}")
            continue
        if check.get("conclusion") != "success":
            problems.append(f"required check failed: {name}")
    return not problems, problems


def is_test_path(path: str, policy: dict[str, Any]) -> bool:
    if Path(path).name.startswith("test_"):
        return True
    if any(path.startswith(prefix) for prefix in policy.get("test_path_prefixes", [])):
        return True
    return any(fragment in path for fragment in policy.get("test_path_fragments", []))


def path_denial_reason(path: str, policy: dict[str, Any]) -> str | None:
    if path in set(policy.get("denied_exact_paths", [])):
        return f"denied exact path: {path}"
    for prefix in policy.get("denied_path_prefixes", []):
        if path.startswith(prefix):
            return f"denied path prefix {prefix}: {path}"
    low = path.lower()
    for fragment in policy.get("denied_path_fragments", []):
        if fragment.lower() in low:
            return f"denied path fragment {fragment}: {path}"
    for term in policy.get("denied_path_terms", []):
        if term.lower() in low:
            return f"security/authority-sensitive path term {term}: {path}"
    if Path(path).name in set(policy.get("denied_filenames", [])):
        return f"dependency/deployment-sensitive filename: {path}"
    return None


def production_freshness(
    production_state: dict[str, Any],
    *,
    max_age_minutes: int,
    now: datetime | None = None,
) -> tuple[bool, str]:
    now = now or datetime.now(timezone.utc)
    production = production_state.get("production") or {}
    observed = str(production.get("observed_at") or "")
    status = str(production.get("status") or "")
    if status != "aligned_and_healthy":
        return False, f"production status is {status or 'unknown'}"
    if not observed:
        return False, "production observation timestamp is missing"
    try:
        observed_at = datetime.fromisoformat(observed.replace("Z", "+00:00"))
    except ValueError:
        return False, "production observation timestamp is invalid"
    age_minutes = max(0.0, (now - observed_at).total_seconds() / 60.0)
    if age_minutes > max_age_minutes:
        return False, f"production evidence is stale ({age_minutes:.1f} minutes old)"
    return True, f"production evidence fresh ({age_minutes:.1f} minutes old)"


MERGE_PR_NUMBER = re.compile(
    r"(?im)^Merge (?:PR|pull request) #(\d+)\b"
)


def _resolve_pr_from_merge_commit(api: Api, merged_sha: str) -> dict[str, Any]:
    commit = api.request(f"/commits/{urllib.parse.quote(merged_sha, safe='')}")
    message = str(((commit or {}).get("commit") or {}).get("message") or "")
    match = MERGE_PR_NUMBER.search(message)
    if not match:
        raise RuntimeError(
            f"Unable to derive merged PR number from commit {merged_sha}"
        )
    pr = api.request(f"/pulls/{int(match.group(1))}")
    if not pr.get("merged_at") or pr.get("merge_commit_sha") != merged_sha:
        raise RuntimeError(
            f"Merge-title PR does not match commit {merged_sha}"
        )
    return pr


def resolve_pr(api: Api, *, pr_number: int | None, merged_sha: str | None) -> dict[str, Any]:
    if pr_number is not None:
        return api.request(f"/pulls/{pr_number}")
    if not merged_sha:
        raise RuntimeError("Either --pr-number or --merged-sha is required")

    pulls: list[dict[str, Any]] = []
    try:
        pulls = api.paged(f"/commits/{urllib.parse.quote(merged_sha, safe='')}/pulls")
    except urllib.error.HTTPError as exc:
        if exc.code < 500:
            raise

    merged = [pr for pr in pulls if pr.get("merged_at") and pr.get("merge_commit_sha") == merged_sha]
    if len(merged) == 1:
        return merged[0]
    if len(merged) > 1:
        raise RuntimeError(
            f"Expected exactly one merged PR for commit {merged_sha}; found {len(merged)}"
        )
    return _resolve_pr_from_merge_commit(api, merged_sha)


def classify(
    *,
    pr: dict[str, Any],
    files: list[dict[str, Any]],
    check_runs: list[dict[str, Any]],
    support_items: dict[str, dict[str, str]],
    production_state: dict[str, Any],
    policy: dict[str, Any],
    main_sha: str,
    merge_is_on_main: bool,
) -> dict[str, Any]:
    source_reasons: list[str] = []
    execution_reasons: list[str] = []

    if not policy.get("enabled", False):
        source_reasons.append("autonomous repair policy is disabled")

    if not pr.get("merged_at"):
        source_reasons.append("PR is not merged")
    merge_sha = str(pr.get("merge_commit_sha") or "")
    if not merge_sha:
        source_reasons.append("merged PR has no merge commit SHA")
    if not merge_is_on_main:
        source_reasons.append("merge commit is not reachable from protected main")

    metadata = parse_metadata(str(pr.get("body") or ""))
    for key, expected in (policy.get("required_metadata") or {}).items():
        actual = metadata.get(key, "")
        if actual.lower() != str(expected).lower():
            source_reasons.append(
                f"metadata {key} must be {expected!r}; got {actual or '<missing>'!r}"
            )
    for key in policy.get("required_nonempty_metadata", []):
        if not metadata.get(key, "").strip():
            source_reasons.append(f"metadata {key} is required")

    support_item = metadata.get("support_item", "").strip()
    required_prefix = str(policy.get("required_support_prefix", "SUPPORT-"))
    if support_item and not support_item.startswith(required_prefix):
        source_reasons.append(f"support item must begin with {required_prefix}")
    if support_item and support_item not in support_items:
        source_reasons.append(f"support item {support_item} is not currently open in SUPPORT.md")

    file_paths = [str(item.get("filename") or "") for item in files]
    if len(file_paths) > int(policy.get("max_changed_files", 25)):
        source_reasons.append(
            f"changed file count {len(file_paths)} exceeds autonomous limit"
        )
    changed_lines = sum(
        int(item.get("additions", 0) or 0) + int(item.get("deletions", 0) or 0)
        for item in files
    )
    if changed_lines > int(policy.get("max_changed_lines", 800)):
        source_reasons.append(
            f"changed line count {changed_lines} exceeds autonomous limit"
        )

    for path in file_paths:
        reason = path_denial_reason(path, policy)
        if reason:
            source_reasons.append(reason)

    changed_tests = [path for path in file_paths if is_test_path(path, policy)]
    regression_test = metadata.get("regression_test", "").strip()
    if not changed_tests:
        source_reasons.append("no regression test file changed")
    if regression_test and regression_test not in file_paths:
        source_reasons.append(
            f"declared regression test was not changed by PR: {regression_test}"
        )
    if regression_test and not is_test_path(regression_test, policy):
        source_reasons.append(
            f"declared regression test is not in an approved test path: {regression_test}"
        )

    checks_ok, check_problems = check_summary(
        list(policy.get("required_checks", [])),
        check_runs,
    )
    if not checks_ok:
        execution_reasons.extend(check_problems)

    fresh, freshness_reason = production_freshness(
        production_state,
        max_age_minutes=int(policy.get("production_evidence_max_age_minutes", 30)),
    )
    if not fresh:
        execution_reasons.append(freshness_reason)

    production = production_state.get("production") or {}
    rollback_sha = str(production.get("revision") or "")
    if not rollback_sha:
        execution_reasons.append("known-good production rollback revision is missing")
    elif rollback_sha == merge_sha:
        execution_reasons.append("rollback revision equals candidate revision")

    if not policy.get("automatic_authorization_enabled", False):
        execution_reasons.append("automatic repair authorization is disabled")

    execution_path_available = bool(policy.get("automatic_production_execution_enabled", False))
    if not execution_path_available:
        execution_reasons.append(
            "named governed deployment capability is not yet enabled for autonomous execution"
        )

    source_eligible = not source_reasons
    human_approval_required = not source_eligible
    execution_ready = source_eligible and not execution_reasons

    if not source_eligible:
        classification = "approval_required"
    elif execution_ready:
        classification = "autonomous_repair_ready"
    else:
        classification = "autonomous_repair_authorized_blocked"

    return {
        "schema_version": "1.0",
        "classification": classification,
        "source_repair_eligible": source_eligible,
        "human_approval_required": human_approval_required,
        "execution_ready": execution_ready,
        "automatic_production_execution_enabled": execution_path_available,
        "support_item": support_item,
        "pr_number": int(pr.get("number") or 0),
        "head_sha": str((pr.get("head") or {}).get("sha") or ""),
        "merge_sha": merge_sha,
        "current_main_sha": main_sha,
        "rollback_sha": rollback_sha,
        "changed_file_count": len(file_paths),
        "changed_line_count": changed_lines,
        "changed_tests": changed_tests,
        "source_reasons": source_reasons,
        "execution_reasons": execution_reasons,
        "post_deploy_verification": metadata.get("post_deploy_verification", ""),
        "previously_approved_behavior": metadata.get("previously_approved_behavior", ""),
        "grants_provider_authority": False,
        "requires_governed_deployment_runner": True,
    }


COMMENT_MARKER = "<!-- jason-autonomous-repair-release -->"


def render_comment(result: dict[str, Any]) -> str:
    source = "PASS" if result["source_repair_eligible"] else "FAIL"
    execution = "READY" if result["execution_ready"] else "BLOCKED"
    lines = [
        COMMENT_MARKER,
        "## Autonomous Repair Release Classification",
        "",
        f"- Classification: **{result['classification']}**",
        f"- Repair eligibility: **{source}**",
        f"- Human production approval required: **{'yes' if result['human_approval_required'] else 'no'}**",
        f"- Autonomous execution: **{execution}**",
        f"- Support item: `{result['support_item'] or 'missing'}`",
        f"- Candidate SHA: `{result['merge_sha'] or 'missing'}`",
        f"- Rollback SHA: `{result['rollback_sha'] or 'missing'}`",
    ]
    if result["source_reasons"]:
        lines.extend(["", "### Eligibility blockers"])
        lines.extend(f"- {reason}" for reason in result["source_reasons"])
    if result["execution_reasons"]:
        lines.extend(["", "### Execution blockers"])
        lines.extend(f"- {reason}" for reason in result["execution_reasons"])
    lines.extend(
        [
            "",
            "This classification does not grant provider authority. Any autonomous production execution must use Jason's named governed deployment capability, exact immutable release SHA, rollback target, and post-deploy verification.",
        ]
    )
    return "\n".join(lines)


def upsert_comment(api: Api, pr_number: int, body: str) -> None:
    comments = api.paged(f"/issues/{pr_number}/comments")
    existing = next(
        (
            comment
            for comment in comments
            if COMMENT_MARKER in str(comment.get("body") or "")
        ),
        None,
    )
    if existing:
        api.request(
            f"/issues/comments/{int(existing['id'])}",
            method="PATCH",
            payload={"body": body},
        )
    else:
        api.request(
            f"/issues/{pr_number}/comments",
            method="POST",
            payload={"body": body},
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--token", default=os.environ.get("GITHUB_TOKEN", ""))
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--pr-number", type=int)
    parser.add_argument("--merged-sha")
    parser.add_argument("--output", type=Path, default=Path("autonomous-repair-release.json"))
    parser.add_argument("--comment", action="store_true")
    parser.add_argument("--candidate-only", action="store_true")
    args = parser.parse_args()

    if not args.repository:
        raise SystemExit("ERROR: repository is required")
    policy = load_json(args.policy)
    api = Api(args.repository, args.token)
    pr = resolve_pr(api, pr_number=args.pr_number, merged_sha=args.merged_sha)
    number = int(pr["number"])
    metadata = parse_metadata(str(pr.get("body") or ""))
    expected_class = str(
        (policy.get("required_metadata") or {}).get(
            "release_class", "autonomous-repair-candidate"
        )
    )
    if args.candidate_only and metadata.get("release_class", "").lower() != expected_class.lower():
        print(
            json.dumps(
                {
                    "classification": "not_candidate",
                    "pr_number": number,
                    "reason": "PR did not request autonomous repair classification",
                },
                indent=2,
            )
        )
        return 0

    files = api.paged(f"/pulls/{number}/files")
    merge_sha = str(pr.get("merge_commit_sha") or "")
    checks_payload = api.request(f"/commits/{urllib.parse.quote(merge_sha, safe='')}/check-runs")
    main = api.request("/branches/main")
    main_sha = str(main["commit"]["sha"])
    compare = api.request(
        f"/compare/{urllib.parse.quote(merge_sha, safe='')}...{urllib.parse.quote(main_sha, safe='')}"
    )
    merge_is_on_main = compare.get("status") in {"ahead", "identical"} or merge_sha == main_sha

    result = classify(
        pr=pr,
        files=files,
        check_runs=list(checks_payload.get("check_runs", [])),
        support_items=parse_open_support(SUPPORT.read_text(encoding="utf-8")),
        production_state=load_json(PRODUCTION_STATE),
        policy=policy,
        main_sha=main_sha,
        merge_is_on_main=merge_is_on_main,
    )

    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))

    if args.comment:
        if not args.token:
            raise SystemExit("ERROR: --comment requires GITHUB_TOKEN")
        upsert_comment(api, number, render_comment(result))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
