#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
from typing import Any

REPO = "al-teamaot-com/jason"
REQUIRED_WORKFLOWS = {
    "Validate Jason",
    "SEC-007 Security Regressions",
    "Validate Jason Teams Gateway",
    "Validate Conversation Experience Foundation",
}
STATE_PATH = "docs/control/AUTOMATED-CHANGE-STATE.json"
REPO_ROOT = Path(os.environ.get("JASON_DOCUMENTATION_REPO_ROOT", "/home/al/projects/jason"))


def run(*args: str, check: bool = True) -> str:
    result = subprocess.run(args, text=True, capture_output=True, check=check)
    return result.stdout.strip()


def gh_json(*args: str) -> Any:
    text = run("gh", *args)
    return json.loads(text or "null")


def changed_paths(revision: str) -> tuple[str, ...]:
    run("git", "-C", str(REPO_ROOT), "fetch", "origin", revision, "--depth=2")
    parent = f"{revision}^1"
    output = run("git", "-C", str(REPO_ROOT), "diff", "--name-only", parent, revision)
    return tuple(line.strip() for line in output.splitlines() if line.strip())


def is_material(paths: tuple[str, ...]) -> bool:
    return any(not (path.startswith("docs/") or path.startswith(".github/")) for path in paths)


def recorded_revision() -> str:
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "show", f"origin/main:{STATE_PATH}"],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return ""
    try:
        state = json.loads(result.stdout)
    except json.JSONDecodeError:
        return ""
    return str((state.get("validated_source") or {}).get("revision") or "")


def successful_main_runs() -> list[dict[str, Any]]:
    data = gh_json(
        "run", "list",
        "--repo", REPO,
        "--workflow", "Validate Jason",
        "--branch", "main",
        "--event", "push",
        "--status", "success",
        "--limit", "20",
        "--json", "databaseId,headSha,url,createdAt",
    )
    return list(data or [])


def latest_material_success() -> dict[str, Any] | None:
    for item in successful_main_runs():
        revision = str(item.get("headSha") or "")
        if revision and is_material(changed_paths(revision)):
            return item
    return None


def publish_source_if_needed() -> None:
    run("git", "-C", str(REPO_ROOT), "fetch", "origin", "main")
    latest = latest_material_success()
    if latest is None:
        print("SOURCE_DOCUMENTATION_RECONCILIATION=NO_MATERIAL_SUCCESS")
        return
    revision = str(latest["headSha"])
    if revision == recorded_revision():
        print("SOURCE_DOCUMENTATION_RECONCILIATION=UP_TO_DATE")
        return
    script = Path(__file__).resolve().with_name("publish_documentation_reconciliation.sh")
    run(
        "bash", str(script),
        "source", revision,
        str(latest.get("databaseId") or ""),
        str(latest.get("url") or ""),
    )
    print(f"SOURCE_DOCUMENTATION_RECONCILIATION=PUBLISHED revision={revision}")


def automation_prs() -> list[dict[str, Any]]:
    items = gh_json(
        "pr", "list",
        "--repo", REPO,
        "--state", "open",
        "--limit", "100",
        "--json", "number,headRefName,headRefOid,url,mergeable,mergeStateStatus",
    )
    return [
        item for item in (items or [])
        if str(item.get("headRefName") or "").startswith("automation/documentation-reconcile-")
    ]


def workflows_green(head_sha: str) -> bool:
    runs = gh_json(
        "run", "list",
        "--repo", REPO,
        "--commit", head_sha,
        "--event", "pull_request",
        "--limit", "30",
        "--json", "name,status,conclusion",
    )
    latest: dict[str, dict[str, Any]] = {}
    for item in runs or []:
        name = str(item.get("name") or "")
        if name in REQUIRED_WORKFLOWS and name not in latest:
            latest[name] = item
    if set(latest) != REQUIRED_WORKFLOWS:
        return False
    return all(
        str(item.get("status")) == "completed" and str(item.get("conclusion")) == "success"
        for item in latest.values()
    )


def merge_ready_automation_prs() -> str:
    items = automation_prs()
    if not items:
        return "none"
    for item in items:
        number = str(item["number"])
        mergeable = str(item.get("mergeable") or "")
        merge_state = str(item.get("mergeStateStatus") or "")
        if mergeable == "CONFLICTING" or merge_state == "DIRTY":
            print(f"DOCUMENTATION_PR_REFRESH_REQUIRED={number}")
            return "refresh"
        sha = str(item.get("headRefOid") or "")
        if not sha or not workflows_green(sha):
            print(f"DOCUMENTATION_PR_WAITING={number}")
            return "waiting"
        run("gh", "pr", "merge", number, "--repo", REPO, "--merge")
        print(f"DOCUMENTATION_PR_MERGED={number}")
        return "merged"
    return "none"


def main() -> int:
    pr_state = merge_ready_automation_prs()
    if pr_state == "refresh":
        publish_source_if_needed()
        return 0
    if pr_state in {"waiting", "merged"}:
        return 0
    publish_source_if_needed()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
