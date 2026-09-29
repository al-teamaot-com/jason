#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import urllib.request


class DocumentationImpactError(RuntimeError):
    pass


def validate_pull_request_body(body: str) -> None:
    text = body or ""
    if "## Documentation impact" not in text:
        raise DocumentationImpactError(
            "PR body is missing required '## Documentation impact' section"
        )
    updated = re.search(
        r"^- \[[xX]\] Documentation updated\s*$",
        text,
        re.MULTILINE,
    )
    none = re.search(
        r"^- \[[xX]\] No documentation impact\s*$",
        text,
        re.MULTILINE,
    )
    if bool(updated) == bool(none):
        raise DocumentationImpactError(
            "Select exactly one documentation-impact outcome: "
            "Documentation updated OR No documentation impact"
        )
    if none:
        match = re.search(
            r"^No-documentation-impact reason:\s*(.+?)\s*$",
            text,
            re.MULTILINE,
        )
        if match is None or len(match.group(1).strip()) < 12:
            raise DocumentationImpactError(
                "No documentation impact requires a concrete reason "
                "of at least 12 characters"
            )


def fetch_pull_request(repository: str, pr_number: int, token: str) -> dict:
    if not repository or not token:
        raise DocumentationImpactError(
            "repository and GITHUB_TOKEN are required for dispatched PR validation"
        )
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repository}/pulls/{int(pr_number)}",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "project-jason-documentation-impact-gate",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise DocumentationImpactError("pull request lookup returned invalid payload")
    return payload


def resolve_pull_request(
    *,
    event: dict,
    repository: str,
    pr_number: int | None,
    token: str,
) -> dict | None:
    pr = event.get("pull_request")
    if isinstance(pr, dict):
        return pr
    if pr_number is None:
        return None
    return fetch_pull_request(repository, pr_number, token)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", type=Path)
    parser.add_argument(
        "--repository",
        default=os.environ.get("GITHUB_REPOSITORY", ""),
    )
    parser.add_argument("--pr-number", type=int)
    args = parser.parse_args()

    event = {}
    if args.event and args.event.exists():
        event = json.loads(args.event.read_text(encoding="utf-8"))

    repository = args.repository
    if not repository and isinstance(event.get("repository"), dict):
        repository = str(event["repository"].get("full_name") or "")

    pr = resolve_pull_request(
        event=event,
        repository=repository,
        pr_number=args.pr_number,
        token=os.environ.get("GITHUB_TOKEN", ""),
    )
    if not isinstance(pr, dict):
        print("DOCUMENTATION_IMPACT_GATE=SKIP non-pull-request event")
        return 0

    validate_pull_request_body(str(pr.get("body") or ""))
    print("DOCUMENTATION_IMPACT_GATE=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
