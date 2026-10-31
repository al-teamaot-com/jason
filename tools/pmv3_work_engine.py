#!/usr/bin/env python3
"""PMV3 durable autonomous work engine.

This module is intentionally isolated from PMV2 production state. It owns only
PMV3 state and provides the scheduler/recovery semantics required by the PMV3
agreement:

SCAN -> SELECT RUNNABLE -> EXECUTE -> VERIFY -> RETRY/RECOVER
     -> RECHECK WAITING/BLOCKED -> CONTINUE

Execution is injected through a handler so tests and preproduction can prove the
engine before any production worker is connected.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping


SCHEMA_VERSION = "3.0"
TERMINAL = {"complete", "failed_external"}
ACTIVE = {"running", "verifying"}
WAITING = {"waiting", "retry_wait"}
RETRYABLE = {
    "http_transport_failed",
    "connector_transport_error",
    "provider_timeout",
    "connection_reset",
    "temporary_unavailable",
    "rate_limited",
}
EXTERNAL = {
    "credentials_required",
    "provider_license_required",
    "billing_exhausted",
    "owner_approval_required",
    "tenant_permission_required",
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds")


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def atomic_write(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temp = tempfile.mkstemp(prefix=".pmv3-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump(data, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def empty_state() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "updated_at": iso(utcnow()),
        "cycle": 0,
        "items": {},
        "receipts": {},
        "metrics": {
            "completed": 0,
            "active": 0,
            "waiting": 0,
            "blocked": 0,
            "retrying": 0,
            "runnable": 0,
        },
    }


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return empty_state()
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("invalid PMV3 state")
    if not isinstance(value.get("items"), dict) or not isinstance(value.get("receipts"), dict):
        raise ValueError("invalid PMV3 work inventory")
    return value


def action_key(item_id: str, action: str, generation: int) -> str:
    raw = f"{item_id}|{action}|{generation}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class Outcome:
    status: str
    reason: str = ""
    retry_class: str = ""
    dependency: str = ""
    receipt: str = ""


def make_item(
    item_id: str,
    action: str,
    *,
    priority: int = 100,
    approved: bool = True,
    dependency: str = "",
    approval_required: bool = False,
    approval_request_id: str = "",
) -> dict[str, Any]:
    now = iso(utcnow())
    return {
        "id": item_id,
        "action": action,
        "priority": int(priority),
        "approved": bool(approved),
        "approval_required": bool(approval_required),
        "approval_request_id": approval_request_id,
        "approval": None,
        "phase": "waiting" if dependency else "runnable",
        "reason": "dependency_wait" if dependency else "",
        "dependency": dependency,
        "generation": 1,
        "attempts": 0,
        "max_attempts": 3,
        "next_attempt_at": None,
        "claimed_at": None,
        "updated_at": now,
        "last_progress_at": now,
        "last_outcome": None,
    }


def admit(state: dict[str, Any], item: Mapping[str, Any]) -> bool:
    item_id = str(item.get("id") or "")
    if not item_id:
        raise ValueError("work item id required")
    if item_id in state["items"]:
        return False
    state["items"][item_id] = dict(item)
    return True


def record_teams_approval(
    state: dict[str, Any],
    item_id: str,
    *,
    request_id: str,
    decision: str,
    actor_id: str,
    tenant_id: str,
    receipt_id: str,
    verified: bool,
    channel: str = "teams",
) -> None:
    """Record only authenticated Teams approval evidence.

    PMV3 has no SSH/shell/local-file/GitHub/chat-text approval path.
    """
    if channel != "teams":
        raise ValueError("PMV3 approvals must come from Teams")
    if not verified:
        raise ValueError("unverified Teams approval")
    item = state["items"].get(item_id)
    if not isinstance(item, dict):
        raise KeyError(item_id)
    expected = str(item.get("approval_request_id") or "")
    if not expected or request_id != expected:
        raise ValueError("approval request mismatch")
    normalized = decision.casefold().strip()
    if normalized not in {"approve", "deny"}:
        raise ValueError("invalid Teams approval decision")
    item["approval"] = {
        "channel": "teams",
        "request_id": request_id,
        "decision": normalized,
        "actor_id": actor_id,
        "tenant_id": tenant_id,
        "receipt_id": receipt_id,
        "verified": True,
    }


def approval_satisfied(item: Mapping[str, Any]) -> bool:
    if not bool(item.get("approval_required")):
        return True
    approval = item.get("approval")
    if not isinstance(approval, Mapping):
        return False
    return (
        approval.get("channel") == "teams"
        and approval.get("verified") is True
        and approval.get("decision") == "approve"
        and approval.get("request_id") == item.get("approval_request_id")
        and bool(approval.get("actor_id"))
        and bool(approval.get("tenant_id"))
        and bool(approval.get("receipt_id"))
    )


def classify_reason(reason: str) -> str:
    text = reason.casefold()
    if any(term in text for term in ("http transport", "connectortransporterror", "provider timeout", "connection reset")):
        return "http_transport_failed"
    if "rate limit" in text or "429" in text:
        if "insufficient_quota" in text or "credit_balance_exhausted" in text:
            return "billing_exhausted"
        return "rate_limited"
    if any(term in text for term in ("credential", "api details", "tenant permission", "license required")):
        return "credentials_required"
    if any(term in text for term in ("owner approval", "explicit approval", "authorization required")):
        return "owner_approval_required"
    return "unknown"


def dependency_satisfied(item: Mapping[str, Any], facts: Mapping[str, bool]) -> bool:
    dependency = str(item.get("dependency") or "")
    return not dependency or bool(facts.get(dependency, False))


def recheck(state: dict[str, Any], facts: Mapping[str, bool], *, now: datetime) -> None:
    for item in state["items"].values():
        phase = str(item.get("phase") or "")
        if phase in TERMINAL or phase in ACTIVE:
            continue
        if phase == "waiting" and dependency_satisfied(item, facts):
            item["phase"] = "runnable"
            item["reason"] = ""
            item["dependency"] = ""
            item["updated_at"] = iso(now)
            item["last_progress_at"] = iso(now)
        elif phase == "retry_wait":
            due = parse_time(item.get("next_attempt_at"))
            if due is not None and due <= now:
                item["phase"] = "runnable"
                item["reason"] = ""
                item["next_attempt_at"] = None
                item["updated_at"] = iso(now)
        elif phase == "blocked":
            retry_class = classify_reason(str(item.get("reason") or ""))
            if retry_class in RETRYABLE:
                item["phase"] = "runnable"
                item["reason"] = ""
                item["updated_at"] = iso(now)


def runnable_items(state: Mapping[str, Any], *, capacity: int) -> list[dict[str, Any]]:
    active = sum(1 for item in state["items"].values() if item.get("phase") in ACTIVE)
    slots = max(0, int(capacity) - active)
    candidates = [
        dict(item)
        for item in state["items"].values()
        if item.get("phase") == "runnable" and bool(item.get("approved")) and approval_satisfied(item)
    ]
    candidates.sort(key=lambda x: (int(x.get("priority") or 100), str(x.get("updated_at") or ""), str(x.get("id") or "")))
    return candidates[:slots]


def backoff_seconds(attempts: int) -> int:
    # 30s, 60s, 120s; intentionally bounded.
    return min(120, 30 * (2 ** max(0, attempts - 1)))


def apply_outcome(
    state: dict[str, Any],
    item: dict[str, Any],
    outcome: Outcome,
    *,
    now: datetime,
) -> None:
    stored = state["items"][item["id"]]
    stored["last_outcome"] = {
        "status": outcome.status,
        "reason": outcome.reason,
        "retry_class": outcome.retry_class,
        "receipt": outcome.receipt,
        "at": iso(now),
    }

    if outcome.status == "complete":
        stored["phase"] = "complete"
        stored["reason"] = ""
        stored["updated_at"] = iso(now)
        stored["last_progress_at"] = iso(now)
        return

    if outcome.status == "waiting":
        stored["phase"] = "waiting"
        stored["reason"] = outcome.reason or "dependency_wait"
        stored["dependency"] = outcome.dependency
        stored["updated_at"] = iso(now)
        return

    retry_class = outcome.retry_class or classify_reason(outcome.reason)
    if outcome.status == "retry" or retry_class in RETRYABLE:
        attempts = int(stored.get("attempts") or 0)
        if attempts < int(stored.get("max_attempts") or 3):
            stored["phase"] = "retry_wait"
            stored["reason"] = outcome.reason or retry_class
            stored["next_attempt_at"] = iso(now + timedelta(seconds=backoff_seconds(attempts)))
            stored["updated_at"] = iso(now)
            return
        stored["phase"] = "blocked"
        stored["reason"] = "retry_exhausted: " + (outcome.reason or retry_class)
        stored["updated_at"] = iso(now)
        return

    if retry_class in EXTERNAL or outcome.status == "external":
        stored["phase"] = "failed_external"
        stored["reason"] = outcome.reason or retry_class
        stored["updated_at"] = iso(now)
        return

    stored["phase"] = "blocked"
    stored["reason"] = outcome.reason or "unclassified_failure"
    stored["updated_at"] = iso(now)


def execute_cycle(
    state: dict[str, Any],
    *,
    facts: Mapping[str, bool],
    handler: Callable[[Mapping[str, Any], str], Outcome],
    capacity: int = 3,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or utcnow()
    state["cycle"] = int(state.get("cycle") or 0) + 1

    # Recovery rule: a process crash may leave an item running without a receipt.
    # Re-admit it safely; the action key prevents duplicate execution if a prior
    # durable receipt already exists.
    for item in state["items"].values():
        if item.get("phase") in ACTIVE:
            key = action_key(str(item["id"]), str(item["action"]), int(item.get("generation") or 1))
            if key in state["receipts"]:
                item["phase"] = "complete"
                item["reason"] = ""
            else:
                item["phase"] = "runnable"
                item["reason"] = "recovered_after_interrupted_execution"
            item["claimed_at"] = None
            item["updated_at"] = iso(now)

    recheck(state, facts, now=now)

    for item in runnable_items(state, capacity=capacity):
        stored = state["items"][item["id"]]
        key = action_key(str(item["id"]), str(item["action"]), int(item.get("generation") or 1))
        if key in state["receipts"]:
            stored["phase"] = "complete"
            stored["reason"] = ""
            stored["updated_at"] = iso(now)
            continue

        stored["phase"] = "running"
        stored["attempts"] = int(stored.get("attempts") or 0) + 1
        stored["claimed_at"] = iso(now)
        stored["updated_at"] = iso(now)

        outcome = handler(dict(stored), key)
        if outcome.receipt:
            state["receipts"][key] = {
                "item_id": item["id"],
                "receipt": outcome.receipt,
                "recorded_at": iso(now),
            }
        apply_outcome(state, item, outcome, now=now)

    refresh_metrics(state)
    state["updated_at"] = iso(now)
    return state


def refresh_metrics(state: dict[str, Any]) -> None:
    items = list(state["items"].values())
    state["metrics"] = {
        "completed": sum(1 for i in items if i.get("phase") == "complete"),
        "active": sum(1 for i in items if i.get("phase") in ACTIVE),
        "waiting": sum(1 for i in items if i.get("phase") == "waiting"),
        "blocked": sum(1 for i in items if i.get("phase") in {"blocked", "failed_external"}),
        "retrying": sum(1 for i in items if i.get("phase") == "retry_wait"),
        "runnable": sum(1 for i in items if i.get("phase") == "runnable" and i.get("approved") and approval_satisfied(i)),
    }


def progress_percent(state: Mapping[str, Any]) -> int:
    items = list((state.get("items") or {}).values())
    if not items:
        return 0
    complete = sum(1 for i in items if i.get("phase") == "complete")
    return int((complete * 100) / len(items))
