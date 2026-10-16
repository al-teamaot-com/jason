#!/usr/bin/env python3
"""Project Jason change-integration gate.

Fail closed when a material PR is not reconciled with current main or when it
silently overlaps recently active implementation-sensitive work.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

SENSITIVE_PREFIXES = (
    ".github/workflows/",
    "implementation/",
    "infrastructure/",
    "deploy/",
    "config/",
    "scripts/",
    "tools/",
)
SENSITIVE_ROOTS = {
    "CONTRIBUTING.md",
    ".github/pull_request_template.md",
}
ACK_PATTERN = re.compile(
    r"(?im)^\s*(?:-\s*)?Integration coordination\s*:\s*(?P<value>.+?)\s*$"
)
PR_NUMBER_PATTERN = re.compile(r"#(\d+)")


def run(*args: str) -> str:
    completed = subprocess.run(
        args,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return completed.stdout.strip()


def sensitive(path: str) -> bool:
    return path in SENSITIVE_ROOTS or path.startswith(SENSITIVE_PREFIXES)


def api_json(url: str, token: str) -> object:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "project-jason-change-integration-gate",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def paged(url: str, token: str) -> list[dict]:
    results: list[dict] = []
    page = 1
    while True:
        sep = "&" if "?" in url else "?"
        payload = api_json(f"{url}{sep}per_page=100&page={page}", token)
        if not isinstance(payload, list):
            raise RuntimeError(f"Expected list response from {url}")
        results.extend(payload)
        if len(payload) < 100:
            return results
        page += 1


def parse_acknowledged(body: str) -> set[int]:
    match = ACK_PATTERN.search(body or "")
    if not match:
        return set()
    value = match.group("value").strip()
    if value.lower() in {"none", "n/a", "not applicable"}:
        return set()
    return {int(item) for item in PR_NUMBER_PATTERN.findall(value)}


def changed_files(base_ref: str) -> set[str]:
    output = run("git", "diff", "--name-only", f"origin/{base_ref}...HEAD")
    return {line.strip() for line in output.splitlines() if line.strip()}


def ensure_current_base(base_ref: str) -> None:
    subprocess.run(
        ["git", "fetch", "--no-tags", "origin", f"{base_ref}:refs/remotes/origin/{base_ref}"],
        check=True,
    )
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", f"origin/{base_ref}", "HEAD"],
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"PR head is not reconciled with current origin/{base_ref}. "
            f"Update the branch from current {base_ref}, resolve conflicts, and re-run validation."
        )


def active_overlap_check(
    repository: str,
    current_pr: int,
    base_ref: str,
    current_files: set[str],
    body: str,
    token: str,
    active_days: int,
) -> list[str]:
    current_sensitive = {path for path in current_files if sensitive(path)}
    if not current_sensitive:
        return []

    pulls_url = (
        f"https://api.github.com/repos/{repository}/pulls"
        f"?state=open&base={urllib.parse.quote(base_ref)}&sort=updated&direction=desc"
    )
    open_pulls = paged(pulls_url, token)
    cutoff = datetime.now(timezone.utc) - timedelta(days=active_days)
    acknowledged = parse_acknowledged(body)
    errors: list[str] = []

    for pr in open_pulls:
        number = int(pr["number"])
        if number == current_pr:
            continue

        updated = datetime.fromisoformat(str(pr["updated_at"]).replace("Z", "+00:00"))
        if updated < cutoff:
            continue

        files = paged(
            f"https://api.github.com/repos/{repository}/pulls/{number}/files",
            token,
        )
        other_sensitive = {
            str(item["filename"])
            for item in files
            if sensitive(str(item["filename"]))
        }
        overlap = sorted(current_sensitive & other_sensitive)
        if overlap and number not in acknowledged:
            preview = ", ".join(overlap[:8])
            if len(overlap) > 8:
                preview += f", ... (+{len(overlap) - 8} more)"
            errors.append(
                f"Active implementation overlap with PR #{number}: {preview}. "
                f"Review/reconcile it, then add '#{number}' to the PR body's "
                f"'Integration coordination:' line."
            )

    return errors


def load_event(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", type=Path, required=True)
    parser.add_argument("--active-days", type=int, default=7)
    args = parser.parse_args()

    event = load_event(args.event)
    pr = event.get("pull_request")
    if not pr:
        print("change-integration: non-PR event; no PR overlap gate required")
        return 0

    repository = event["repository"]["full_name"]
    current_pr = int(pr["number"])
    base_ref = str(pr["base"]["ref"])
    body = str(pr.get("body") or "")
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        print("change-integration: GITHUB_TOKEN is required for PR overlap checks", file=sys.stderr)
        return 2

    try:
        ensure_current_base(base_ref)
        files = changed_files(base_ref)
        print(f"change-integration: PR #{current_pr} changes {len(files)} file(s)")
        errors = active_overlap_check(
            repository=repository,
            current_pr=current_pr,
            base_ref=base_ref,
            current_files=files,
            body=body,
            token=token,
            active_days=args.active_days,
        )
    except Exception as exc:
        print(f"change-integration: FAIL: {exc}", file=sys.stderr)
        return 1

    if errors:
        print("change-integration: FAIL", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print("change-integration: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
