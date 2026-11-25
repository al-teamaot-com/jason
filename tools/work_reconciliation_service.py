#!/usr/bin/env python3
"""Independent work-state reconciler.

Classifies existing commitment state into actionable, recoverable, governed/external,
or waiting buckets. It does not claim work, merge PRs, deploy, or mint authority.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

try:
    from isolated_service_common import atomic_json, load_json, now_iso
except ModuleNotFoundError:
    from tools.isolated_service_common import atomic_json, load_json, now_iso

RECOVERABLE_HINTS = ("stale worktree", "transport", "retry", "clean-source", "validation", "worker record")
EXTERNAL_HINTS = ("credentials", "api details", "owner approval", "human authority", "external dependency")


def classify_item(item: dict[str, Any]) -> tuple[str, str]:
    phase = str(item.get("phase") or "unknown")
    reason = str(item.get("reason") or "")
    text = reason.lower()
    if phase in {"complete", "completed", "production_verified"}:
        return "complete", "none"
    if phase in {"waiting_development_merge", "waiting_development_start", "waiting_operational_acceptance"}:
        return "actionable", phase
    if any(hint in text for hint in EXTERNAL_HINTS):
        return "external", reason
    if any(hint in text for hint in RECOVERABLE_HINTS):
        return "recoverable", reason
    if phase.endswith("blocked"):
        return "governed_or_dependency", reason
    return "waiting", reason or phase


def reconcile(source: dict[str, Any]) -> dict[str, Any]:
    items = source.get("items") if isinstance(source.get("items"), list) else []
    buckets: dict[str, list[dict[str, Any]]] = {name: [] for name in ("actionable", "recoverable", "external", "governed_or_dependency", "waiting", "complete")}
    for item in items:
        if not isinstance(item, dict):
            continue
        category, next_action = classify_item(item)
        buckets[category].append({
            "todo_id": item.get("todo_id"),
            "issue_number": item.get("issue_number"),
            "phase": item.get("phase"),
            "next_action": next_action,
        })
    return {
        "status": "work_available" if buckets["actionable"] or buckets["recoverable"] else "waiting",
        "counts": {key: len(value) for key, value in buckets.items()},
        "buckets": buckets,
    }


def run(input_path: Path, output_path: Path) -> dict[str, Any]:
    source = load_json(input_path)
    result = {
        "schema_version": "1.0",
        "service": "work_reconciliation",
        "observed_at": now_iso(),
        **reconcile(source),
    }
    atomic_json(output_path, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.input, args.output)
    print(result["status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
