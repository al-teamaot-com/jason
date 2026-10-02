#!/usr/bin/env python3
"""Ratchet gate for Jason canonical-capability reuse.

The gate deliberately checks changed caller files rather than failing the
repository for historical implementation debt. Provider adapters/invokers may
contain provider-specific imports. Workflow/process callers may not add direct
provider/HTTP plumbing and must instead request canonical capabilities through
Jason's governed runtime.
"""

from __future__ import annotations

import argparse
import ast
import fnmatch
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = ROOT / "config" / "canonical-capability-boundary.json"


@dataclass(frozen=True, slots=True)
class Violation:
    path: str
    line: int
    rule: str
    detail: str


def load_policy(path: Path = DEFAULT_POLICY) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def matches_any(path: str, globs: Iterable[str]) -> bool:
    normalized = path.replace("\\", "/")
    return any(fnmatch.fnmatch(normalized, pattern) for pattern in globs)


def is_caller(path: str, policy: dict[str, Any]) -> bool:
    return matches_any(path, policy.get("caller_path_globs", []))


def is_provider_boundary(path: str, policy: dict[str, Any]) -> bool:
    return matches_any(path, policy.get("provider_boundary_path_globs", []))


def dotted_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        left = dotted_name(node.value)
        return f"{left}.{node.attr}" if left else node.attr
    return None


def inspect_python(path: str, source: str, policy: dict[str, Any]) -> list[Violation]:
    if not is_caller(path, policy) or is_provider_boundary(path, policy):
        return []

    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as exc:
        return [
            Violation(
                path=path,
                line=int(exc.lineno or 1),
                rule="python_parse",
                detail=f"cannot inspect caller boundary because Python parsing failed: {exc.msg}",
            )
        ]

    forbidden_imports = tuple(policy.get("forbidden_import_prefixes_for_callers", []))
    forbidden_calls = set(policy.get("forbidden_call_names_for_callers", []))
    violations: list[Violation] = []

    def import_forbidden(module: str) -> bool:
        return any(
            module == prefix.rstrip(".")
            or module.startswith(prefix)
            for prefix in forbidden_imports
        )

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if import_forbidden(alias.name):
                    violations.append(
                        Violation(
                            path=path,
                            line=node.lineno,
                            rule="direct_provider_import",
                            detail=(
                                f"caller imports {alias.name}; request a canonical "
                                "capability through the governed runtime instead"
                            ),
                        )
                    )
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if import_forbidden(module):
                violations.append(
                    Violation(
                        path=path,
                        line=node.lineno,
                        rule="direct_provider_import",
                        detail=(
                            f"caller imports from {module}; provider plumbing belongs "
                            "behind a canonical capability boundary"
                        ),
                    )
                )
        elif isinstance(node, ast.Call):
            name = dotted_name(node.func)
            if name in forbidden_calls:
                violations.append(
                    Violation(
                        path=path,
                        line=node.lineno,
                        rule="direct_provider_call",
                        detail=(
                            f"caller invokes {name}; direct transport calls are not "
                            "permitted in workflow/process callers"
                        ),
                    )
                )

    return violations


def changed_files(base: str, head: str = "HEAD") -> list[str]:
    completed = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...{head}"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [
        line.strip()
        for line in completed.stdout.splitlines()
        if line.strip().endswith(".py")
    ]


def inspect_paths(paths: Iterable[str], policy: dict[str, Any]) -> list[Violation]:
    violations: list[Violation] = []
    for raw in paths:
        path = raw.replace("\\", "/")
        candidate = ROOT / path
        if not candidate.is_file() or candidate.suffix != ".py":
            continue
        violations.extend(
            inspect_python(
                path,
                candidate.read_text(encoding="utf-8"),
                policy,
            )
        )
    return violations


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--base")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--path", action="append", default=[])
    args = parser.parse_args()

    policy = load_policy(args.policy)
    paths = list(args.path)
    if args.base:
        paths.extend(changed_files(args.base, args.head))
    if not paths:
        raise SystemExit("ERROR: provide --base or at least one --path")

    violations = inspect_paths(dict.fromkeys(paths), policy)
    result = {
        "schema_version": "1.0",
        "checked_files": sorted(set(paths)),
        "violation_count": len(violations),
        "violations": [
            {
                "path": item.path,
                "line": item.line,
                "rule": item.rule,
                "detail": item.detail,
            }
            for item in violations
        ],
        "status": "pass" if not violations else "fail",
    }
    print(json.dumps(result, indent=2))
    return 0 if not violations else 2


if __name__ == "__main__":
    raise SystemExit(main())
