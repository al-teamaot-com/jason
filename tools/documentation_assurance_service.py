#!/usr/bin/env python3
"""Independent documentation assurance scanner.

Read-only against source. Writes only its own service-state JSON. It deliberately
has no PMV3 imports and cannot merge, deploy, or mutate provider state.
"""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path
from typing import Any

try:
    from isolated_service_common import atomic_json, load_json, now_iso
except ModuleNotFoundError:
    from tools.isolated_service_common import atomic_json, load_json, now_iso

DOC_PREFIXES = ("docs/",)
DOC_FILES = {"README.md", "mkdocs.yml", "SUPPORT.md"}
MATERIAL_PREFIXES = ("implementation/", "tools/", "config/", ".github/")


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, timeout=20, check=False)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "git command failed")
    return result.stdout.strip()


def changed_paths(repo: Path, base: str, head: str) -> list[str]:
    text = git(repo, "diff", "--name-only", f"{base}..{head}")
    return [line for line in text.splitlines() if line]


def classify(paths: list[str]) -> dict[str, Any]:
    docs = sorted(p for p in paths if p.startswith(DOC_PREFIXES) or p in DOC_FILES)
    material = sorted(p for p in paths if p.startswith(MATERIAL_PREFIXES))
    requires_docs = bool(material)
    if not paths:
        status = "current"
        reason = "no_changes"
    elif requires_docs and not docs:
        status = "attention"
        reason = "material_change_without_documentation_change"
    elif requires_docs:
        # A changed documentation file is not proof that it accurately
        # documents the changed behavior. Require source-to-docs review.
        status = "review_required"
        reason = "material_change_with_unverified_documentation"
    else:
        status = "current"
        reason = "no_material_source_change"
    return {
        "status": status,
        "reason": reason,
        "requires_documentation_review": requires_docs,
        "material_paths": material,
        "documentation_paths": docs,
    }


def scan(repo: Path, state_path: Path, base: str | None = None, head: str = "HEAD") -> dict[str, Any]:
    head_sha = git(repo, "rev-parse", head)
    previous = load_json(state_path)
    if base:
        base_sha = git(repo, "rev-parse", base)
    elif previous.get("last_scanned_sha"):
        base_sha = str(previous["last_scanned_sha"])
        try:
            git(repo, "merge-base", "--is-ancestor", base_sha, head_sha)
        except RuntimeError:
            base_sha = git(repo, "rev-parse", f"{head_sha}^1")
    else:
        base_sha = git(repo, "rev-parse", f"{head_sha}^1")
    paths = changed_paths(repo, base_sha, head_sha)
    result = {
        "schema_version": "1.0",
        "service": "documentation_assurance",
        "observed_at": now_iso(),
        "base_sha": base_sha,
        "head_sha": head_sha,
        "last_scanned_sha": head_sha,
        "changed_paths": paths,
        **classify(paths),
    }
    atomic_json(state_path, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--base")
    parser.add_argument("--head", default="HEAD")
    args = parser.parse_args()
    result = scan(args.repo.resolve(), args.state, args.base, args.head)
    print(result["status"], result["reason"])
    return 0 if result["status"] == "current" else 2


if __name__ == "__main__":
    raise SystemExit(main())
