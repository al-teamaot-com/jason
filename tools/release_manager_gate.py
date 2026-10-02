#!/usr/bin/env python3
"""Non-production Jason Release Manager gate.

This module is deliberately incapable of authorizing production. It enforces
release-state transitions, immutable candidate evidence, pre-production
verification, Support List impact checks, and Support-first development
priority. Production execution remains outside this pilot and is denied by
policy.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = ROOT / "config" / "release-manager-policy.json"
DEFAULT_SUPPORT = ROOT / "SUPPORT.md"
DEFAULT_TODO = ROOT / "docs" / "roadmaps" / "Project-Jason-TODO-and-Future-Ideas.md"

SUPPORT_ROW = re.compile(
    r"^\|\s*(SUPPORT-[^|]+?)\s*\|\s*(P\d)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|"
)
TODO_HEADING = re.compile(r"^###\s+(TODO-[A-Z]+-\d+)\s+—\s+(.+?)\s*$")
TODO_FIELD = re.compile(r"^- \*\*(Priority|Status):\*\*\s*(.+?)\s*$")
PRIORITY_ORDER = ("P0", "P1", "P2", "P3")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_support(text: str) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for raw in text.splitlines():
        match = SUPPORT_ROW.match(raw)
        if not match:
            continue
        item_id, priority, status, title = (part.strip() for part in match.groups())
        low = status.lower()
        if any(word in low for word in ("resolved", "closed", "reclassified")):
            continue
        items.append(
            {"id": item_id, "priority": priority, "status": status, "title": title}
        )
    return sorted(
        items,
        key=lambda item: (
            PRIORITY_ORDER.index(item["priority"])
            if item["priority"] in PRIORITY_ORDER
            else len(PRIORITY_ORDER),
            item["id"],
        ),
    )


def parse_todos(text: str) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for raw in text.splitlines():
        heading = TODO_HEADING.match(raw)
        if heading:
            if current:
                items.append(current)
            current = {"id": heading.group(1), "title": heading.group(2)}
            continue
        if current:
            field = TODO_FIELD.match(raw)
            if field:
                current[field.group(1).lower()] = field.group(2).strip()
    if current:
        items.append(current)

    excluded = ("blocked", "implemented", "retired", "rejected", "complete")
    active = [
        item
        for item in items
        if not any(word in item.get("status", "").lower() for word in excluded)
    ]
    return sorted(
        active,
        key=lambda item: (
            PRIORITY_ORDER.index(item.get("priority", ""))
            if item.get("priority", "") in PRIORITY_ORDER
            else len(PRIORITY_ORDER),
            item["id"],
        ),
    )


def work_priority_plan(
    support: list[dict[str, str]],
    todos: list[dict[str, str]],
    *,
    active_support_ids: list[str] | None = None,
    max_active_support_repairs: int = 2,
) -> dict[str, Any]:
    active = set(active_support_ids or [])
    open_support = [item for item in support if item["id"] not in active]
    available_support_slots = max(0, max_active_support_repairs - len(active))
    support_to_start = open_support[:available_support_slots]
    support_capacity_full = available_support_slots == 0
    todo_start_allowed = not open_support or support_capacity_full
    return {
        "active_support_repairs": sorted(active),
        "available_support_slots": available_support_slots,
        "support_to_start": [item["id"] for item in support_to_start],
        "next_support_item": open_support[0]["id"] if open_support else None,
        "next_todo_item": todos[0]["id"] if todos else None,
        "todo_start_allowed": todo_start_allowed,
        "reason": (
            "Support List has priority and unused repair capacity exists."
            if open_support and not support_capacity_full
            else "Support capacity is full or no open Support item remains."
        ),
    }


def _present(mapping: dict[str, Any], fields: list[str]) -> list[str]:
    missing: list[str] = []
    for field in fields:
        value = mapping.get(field)
        if value is None or value is False or value == "":
            missing.append(field)
    return missing


def evaluate_transition(
    record: dict[str, Any],
    target_state: str,
    policy: dict[str, Any],
    *,
    support_items: list[dict[str, str]],
    todos: list[dict[str, str]],
) -> dict[str, Any]:
    current = str(record.get("state") or "requested")
    reasons: list[str] = []
    warnings: list[str] = []

    if not policy.get("enabled", False):
        reasons.append("release manager policy is disabled")

    states = set(policy.get("states", []))
    if current not in states:
        reasons.append(f"unknown current state: {current}")
    if target_state not in states:
        reasons.append(f"unknown target state: {target_state}")

    allowed = set((policy.get("transitions") or {}).get(current, []))
    if target_state not in allowed:
        reasons.append(f"transition {current} -> {target_state} is not allowed")

    if (
        policy.get("mode") == "non_production_only"
        and target_state in {"production", "production_verified", "closed"}
        and not policy.get("production_transition_enabled", False)
    ):
        reasons.append(
            "production transition is disabled in the non-production Release Manager pilot"
        )

    change_class = str(record.get("change_class") or "")
    support_id = str(record.get("support_item") or "")

    if target_state == "development":
        if change_class == "support":
            open_ids = {item["id"] for item in support_items}
            if not support_id:
                reasons.append("support change requires support_item")
            elif support_id not in open_ids:
                reasons.append(f"support item {support_id} is not currently open")
        elif change_class in {"todo", "feature", "enhancement"}:
            active_support = list(record.get("active_support_repairs") or [])
            max_active = int(
                (policy.get("priority") or {}).get("max_active_support_repairs", 2)
            )
            plan = work_priority_plan(
                support_items,
                todos,
                active_support_ids=active_support,
                max_active_support_repairs=max_active,
            )
            if not plan["todo_start_allowed"]:
                reasons.append(
                    "Support-first scheduling blocks new TODO/feature work while "
                    "an open Support item can occupy available repair capacity"
                )
                warnings.append(
                    f"next support item: {plan['next_support_item']}"
                )

    if target_state == "dev_verified":
        dev = dict(record.get("development") or {})
        missing = _present(
            dev, list(policy.get("required_development_evidence", []))
        )
        if missing:
            reasons.append(
                "development verification evidence missing: " + ", ".join(missing)
            )

    if target_state == "release_candidate":
        candidate = dict(record.get("release_candidate") or {})
        missing = _present(
            candidate, list(policy.get("required_release_candidate_evidence", []))
        )
        if missing:
            reasons.append(
                "release candidate evidence missing: " + ", ".join(missing)
            )
        source_sha = str((record.get("development") or {}).get("source_sha") or "")
        candidate_sha = str(candidate.get("candidate_sha") or "")
        if source_sha and candidate_sha and source_sha != candidate_sha:
            reasons.append("release candidate SHA does not equal dev-verified source SHA")
        if candidate.get("immutable") is not True:
            reasons.append("release candidate must be marked immutable")

    if target_state == "preproduction":
        preprod_policy = dict(policy.get("preproduction") or {})
        if not preprod_policy.get("configured", False):
            reasons.append(
                f"pre-production environment {preprod_policy.get('environment_name', 'unknown')} "
                "is not configured"
            )
        candidate = dict(record.get("release_candidate") or {})
        if not candidate.get("candidate_sha") or not candidate.get("artifact_digest"):
            reasons.append("exact immutable release candidate evidence is required")

    if target_state == "preprod_verified":
        candidate = dict(record.get("release_candidate") or {})
        preprod = dict(record.get("preproduction") or {})
        missing = _present(
            preprod, list(policy.get("required_preproduction_evidence", []))
        )
        if missing:
            reasons.append(
                "pre-production verification evidence missing: " + ", ".join(missing)
            )
        if (
            preprod.get("deployed_sha")
            and candidate.get("candidate_sha")
            and preprod["deployed_sha"] != candidate["candidate_sha"]
        ):
            reasons.append("pre-production deployed SHA differs from release candidate")
        if (
            preprod.get("artifact_digest")
            and candidate.get("artifact_digest")
            and preprod["artifact_digest"] != candidate["artifact_digest"]
        ):
            reasons.append(
                "pre-production artifact digest differs from release candidate"
            )

    if target_state == "production_eligible":
        impact = dict(record.get("support_impact") or {})
        if not impact.get("checked", False):
            reasons.append("Support List impact check has not been completed")
        blocking = list(impact.get("blocking_items") or [])
        if blocking:
            reasons.append(
                "blocking Support List items remain: " + ", ".join(blocking)
            )
        candidate = dict(record.get("release_candidate") or {})
        preprod = dict(record.get("preproduction") or {})
        if candidate.get("candidate_sha") != preprod.get("deployed_sha"):
            reasons.append("production eligibility requires exact pre-production candidate SHA")
        if candidate.get("artifact_digest") != preprod.get("artifact_digest"):
            reasons.append(
                "production eligibility requires the exact pre-production artifact digest"
            )
        if preprod.get("acceptance_passed") is not True:
            reasons.append("pre-production acceptance has not passed")

    return {
        "schema_version": "1.0",
        "current_state": current,
        "target_state": target_state,
        "allowed": not reasons,
        "reasons": reasons,
        "warnings": warnings,
        "production_execution_permitted": bool(
            policy.get("production_transition_enabled", False)
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--target-state", required=True)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--support", type=Path, default=DEFAULT_SUPPORT)
    parser.add_argument("--todo", type=Path, default=DEFAULT_TODO)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    policy = load_json(args.policy)
    record = load_json(args.record)
    result = evaluate_transition(
        record,
        args.target_state,
        policy,
        support_items=parse_support(args.support.read_text(encoding="utf-8")),
        todos=parse_todos(args.todo.read_text(encoding="utf-8")),
    )
    payload = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    return 0 if result["allowed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
