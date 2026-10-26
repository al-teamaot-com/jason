#!/usr/bin/env python3
"""Strict ref reconciliation planner. Never performs provider writes."""
from __future__ import annotations
import json
import re
import sys

SHA = re.compile(r"^[a-f0-9]{40}$")
PREFIXES = ("refs/heads/", "refs/tags/")


def validate(refs):
    if not isinstance(refs, dict):
        raise ValueError("ref inventory must be an object")
    for name, sha in refs.items():
        if not isinstance(name, str) or not name.startswith(PREFIXES) or not isinstance(sha, str) or not SHA.fullmatch(sha):
            raise ValueError("invalid ref inventory")
    if "refs/heads/main" not in refs:
        raise ValueError("main is missing")


def plan(github, azure, ancestor):
    """ancestor(old_sha,new_sha) MUST be based on complete, verified Git objects."""
    validate(github)
    validate(azure)
    additions, advances, holds = [], [], []
    for ref in sorted(github):
        new = github[ref]
        old = azure.get(ref)
        if old is None:
            additions.append({"ref": ref, "new": new, "expected_old": None})
        elif new != old:
            if ref.startswith("refs/tags/"):
                holds.append({"ref": ref, "reason": "tag_conflict", "azure": old, "github": new})
            elif ancestor(old, new):
                advances.append({"ref": ref, "new": new, "expected_old": old})
            else:
                holds.append({"ref": ref, "reason": "non_fast_forward", "azure": old, "github": new})
    preserved = sorted(set(azure) - set(github))
    return {"add_only": additions, "fast_forward_only": advances, "hold": holds,
            "preserve_azure_only": preserved, "ready": not holds,
            "execution_authorized": False, "writes_performed": False}


if __name__ == "__main__":
    print("Library only: inventories must be authenticated and ancestry independently checked", file=sys.stderr)
    raise SystemExit(2)
