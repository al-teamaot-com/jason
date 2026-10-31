from __future__ import annotations

import hashlib
from collections import defaultdict
from typing import Any

from .store import PMV2Store, canonical_json


def _proposal_id(kind: str, key: str) -> str:
    digest = hashlib.sha256(f"{kind}:{key}".encode("utf-8")).hexdigest()[:16]
    return f"SELF-{kind.upper()}-{digest}"


def reconcile_improvement_proposals(
    *,
    store: PMV2Store,
    minimum_recurrences: int,
) -> dict[str, int]:
    """Create evidence-backed proposal-only records; never execution authority."""
    if minimum_recurrences < 2:
        raise ValueError("self-improvement recurrence threshold must be at least 2")

    proposals = 0
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in store.list_assignments():
        if row.source == "self_improvement":
            continue
        reason = str(row.blocked_reason or "").strip()
        if not reason:
            continue
        if row.attempt_count >= minimum_recurrences or row.state in {
            "blocked", "validation_pending"
        }:
            grouped[reason].append({
                "assignment_id": row.assignment_id,
                "state": row.state,
                "attempt_count": row.attempt_count,
                "completion_percent": row.completion_percent,
            })

    for reason, evidence in sorted(grouped.items()):
        recurrence = max(
            len(evidence),
            max((int(item["attempt_count"]) for item in evidence), default=0),
        )
        if recurrence < minimum_recurrences:
            continue
        proposal_id = _proposal_id("work", reason)
        metadata = {
            "proposal_only": True,
            "reason": reason,
            "recurrence_count": recurrence,
            "evidence": evidence[:25],
            "authority": "proposal_requires_owner_approved_todo",
        }
        store.upsert_assignment(
            assignment_id=f"self:{proposal_id}",
            source="self_improvement",
            source_ref=proposal_id,
            title=f"Investigate recurring PM V2 work blocker: {reason[:100]}",
            priority=2,
            work_type="development",
            runnable=False,
            scope_hash="sha256:" + hashlib.sha256(
                canonical_json(metadata).encode("utf-8")
            ).hexdigest(),
            metadata=metadata,
            blocked_reason="proposal_requires_owner_approved_todo",
        )
        proposals += 1

    for component in store.component_snapshot():
        failures = int(component.get("consecutive_failures") or 0)
        if failures < minimum_recurrences:
            continue
        name = str(component.get("component") or "")
        if not name:
            continue
        proposal_id = _proposal_id("component", name)
        metadata = {
            "proposal_only": True,
            "component": name,
            "consecutive_failures": failures,
            "last_return_code": component.get("last_return_code"),
            "state": component.get("state"),
            "authority": "proposal_requires_owner_approved_todo",
        }
        store.upsert_assignment(
            assignment_id=f"self:{proposal_id}",
            source="self_improvement",
            source_ref=proposal_id,
            title=f"Investigate recurring PM V2 component failure: {name}",
            priority=1,
            work_type="development",
            runnable=False,
            scope_hash="sha256:" + hashlib.sha256(
                canonical_json(metadata).encode("utf-8")
            ).hexdigest(),
            metadata=metadata,
            blocked_reason="proposal_requires_owner_approved_todo",
        )
        proposals += 1

    return {"proposal_count": proposals}
