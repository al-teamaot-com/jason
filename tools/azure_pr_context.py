#!/usr/bin/env python3
"""Resolve Azure PR context without trusting undefined pipeline expressions."""
from __future__ import annotations
import argparse
import re

ID = re.compile(r"[1-9][0-9]*")
MERGE_REF = re.compile(r"refs/pull/([1-9][0-9]*)/merge")


def resolve_pr_id(explicit: str, source_branch: str) -> int:
    explicit = (explicit or "").strip()
    source_branch = (source_branch or "").strip()
    explicit_id = int(explicit) if ID.fullmatch(explicit) else None
    match = MERGE_REF.fullmatch(source_branch)
    branch_id = int(match.group(1)) if match else None
    if explicit_id is not None and branch_id is not None and explicit_id != branch_id:
        raise ValueError("PR identity disagrees with source branch")
    if branch_id is not None:
        return branch_id
    if explicit_id is not None and not source_branch:
        return explicit_id
    raise ValueError("No trustworthy Azure PR identity")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--explicit", default="")
    parser.add_argument("--source-branch", default="")
    args = parser.parse_args()
    try:
        value = resolve_pr_id(args.explicit, args.source_branch)
    except ValueError:
        print("AZURE_PR_CONTEXT=BLOCKED", file=__import__("sys").stderr)
        return 2
    print(value)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
