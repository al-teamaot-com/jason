#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
from typing import Any

REPO = "al-teamaot-com/jason"
STATE_PATH = "docs/control/AUTOMATED-CHANGE-STATE.json"
REPO_ROOT = Path(os.environ.get("JASON_DOCUMENTATION_REPO_ROOT", "/home/al/projects/jason"))


def run(*args: str, check: bool = True) -> str:
    result = subprocess.run(args, text=True, capture_output=True, check=check)
    return result.stdout.strip()


def gh_json(*args: str) -> Any:
    text = run("gh", *args)
    return json.loads(text or "null")


def ensure_complete_main_history() -> None:
    """Refresh main without allowing ancestry checks to run on shallow history."""

    shallow = run(
        "git",
        "-C",
        str(REPO_ROOT),
        "rev-parse",
        "--is-shallow-repository",
    ).strip().casefold()
    if shallow == "true":
        run(
            "git",
            "-C",
            str(REPO_ROOT),
            "fetch",
            "--unshallow",
            "origin",
            "main",
        )
    else:
        run("git", "-C", str(REPO_ROOT), "fetch", "origin", "main")


def ensure_revision(revision: str) -> None:
    """Fetch a missing revision without changing repository depth."""

    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "cat-file", "-e", f"{revision}^{{commit}}"],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        run("git", "-C", str(REPO_ROOT), "fetch", "origin", revision)


def changed_paths(revision: str) -> tuple[str, ...]:
    ensure_revision(revision)
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
        "api",
        (
            f"repos/{REPO}/actions/workflows/validate.yml/runs"
            "?branch=main&event=push&status=success&per_page=100"
        ),
    )
    runs = data.get("workflow_runs", []) if isinstance(data, dict) else []
    return [
        {
            "databaseId": item.get("id"),
            "headSha": item.get("head_sha"),
            "url": item.get("html_url"),
            "createdAt": item.get("created_at"),
        }
        for item in runs
        if isinstance(item, dict)
    ]


def first_parent_history(limit: int = 200) -> tuple[str, ...]:
    output = run(
        "git",
        "-C",
        str(REPO_ROOT),
        "rev-list",
        "--first-parent",
        f"--max-count={limit}",
        "origin/main",
    )
    return tuple(line.strip() for line in output.splitlines() if line.strip())


def latest_material_success() -> dict[str, Any] | None:
    by_revision = {
        str(item.get("headSha") or ""): item
        for item in successful_main_runs()
        if str(item.get("headSha") or "")
    }
    for revision in first_parent_history():
        item = by_revision.get(revision)
        if item is not None and is_material(changed_paths(revision)):
            return item
    return None


def is_ancestor(ancestor: str, descendant: str) -> bool:
    if not ancestor or not descendant:
        return False
    result = subprocess.run(
        [
            "git",
            "-C",
            str(REPO_ROOT),
            "merge-base",
            "--is-ancestor",
            ancestor,
            descendant,
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def validated_convergence_success(
    recorded: str,
    candidate: str,
) -> dict[str, Any] | None:
    """Return validated current main when two valid histories converge there.

    Normal source documentation follows the latest material successful commit.
    If the recorded source and latest material candidate are on different
    histories that have since been merged, moving directly to the candidate
    would look like a backward move. In that narrow case, current main is an
    acceptable convergence revision only when:

    - both revisions are ancestors of current main; and
    - current main itself has a successful Validate Jason push run.

    Otherwise reconciliation continues to fail closed.
    """

    history = first_parent_history()
    if not history:
        return None
    current_main = history[0]
    if not (
        is_ancestor(recorded, current_main)
        and is_ancestor(candidate, current_main)
    ):
        return None

    for item in successful_main_runs():
        if str(item.get("headSha") or "") == current_main:
            return item
    return None


def publish_source_if_needed() -> None:
    ensure_complete_main_history()
    latest = latest_material_success()
    if latest is None:
        print("SOURCE_DOCUMENTATION_RECONCILIATION=NO_MATERIAL_SUCCESS")
        return

    revision = str(latest["headSha"])
    recorded = recorded_revision()
    if revision == recorded:
        print("SOURCE_DOCUMENTATION_RECONCILIATION=UP_TO_DATE")
        return
    if recorded and not is_ancestor(recorded, revision):
        convergence = validated_convergence_success(recorded, revision)
        if convergence is None:
            print(
                "SOURCE_DOCUMENTATION_RECONCILIATION=REFUSED_BACKWARD "
                f"recorded={recorded} candidate={revision}"
            )
            return
        latest = convergence
        revision = str(latest["headSha"])
        print(
            "SOURCE_DOCUMENTATION_RECONCILIATION=CONVERGED "
            f"recorded={recorded} candidate={revision}"
        )

    script = Path(__file__).resolve().with_name("publish_documentation_reconciliation.sh")
    run(
        "bash",
        str(script),
        "source",
        revision,
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


def required_checks_green(pr_number: str) -> bool:
    result = subprocess.run(
        [
            "gh", "pr", "checks", pr_number,
            "--repo", REPO,
            "--required",
            "--json", "name,state,bucket",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if not result.stdout.strip():
        return False
    try:
        checks = json.loads(result.stdout)
    except json.JSONDecodeError:
        return False
    if not checks:
        return False
    return all(str(item.get("bucket") or "") == "pass" for item in checks)


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
        if merge_state == "BEHIND":
            run("gh", "pr", "update-branch", number, "--repo", REPO)
            print(f"DOCUMENTATION_PR_UPDATED_TO_MAIN={number}")
            return "waiting"
        if not required_checks_green(number):
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
