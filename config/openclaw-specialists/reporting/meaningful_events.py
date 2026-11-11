"""PMv4 source-only event gate using J-Man's existing register and Teams transport.

The trusted orchestrator must supply independently observed evidence and call
publish_once after an accepted native task/work-engine event. No scheduler,
second approval channel, owner grant or gateway configuration is created here.
"""
from __future__ import annotations

from datetime import datetime, timezone
import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Any, Callable, Mapping

KINDS = {
    "milestone_verified": "Verified milestone",
    "material_problem": "Material problem",
    "owner_decision_required": "Owner decision required",
}
ALLOWED_STAGES = frozenset({
    "in_progress", "implemented", "tested", "merged", "deployed",
    "operationally_verified", "blocked", "degraded",
})
RECEIPT_MARKER = "- PMV4_TEAMS_EVENT_RECEIPT: "
OWNER_TARGET = re.compile(r"\Auser:[a-zA-Z0-9-]{8,128}\Z")
EVENT_ID = re.compile(r"\A[a-zA-Z0-9][a-zA-Z0-9:._-]{3,119}\Z")


class EventRejected(ValueError):
    """Invalid/unverified event or unsafe transport."""


def _limited(value: Any, field: str, limit: int) -> str:
    if not isinstance(value, str):
        raise EventRejected(field + "_invalid")
    value = value.strip()
    if not value or len(value) > limit or any(ord(ch) < 32 and ch != "\n" for ch in value):
        raise EventRejected(field + "_invalid")
    return value


def format_meaningful_event(event: Mapping[str, Any]) -> tuple[str, str] | None:
    """Classify and render only material PMv4 milestones, problems and decisions.

    Self-described completion NEVER qualifies: a trusted observer must verify it
    separately before any send. The event data cannot authorize production.
    """
    if not isinstance(event, Mapping):
        raise EventRejected("event_invalid")
    kind = event.get("kind")
    if kind not in KINDS:
        return None  # Routine tests, task starts, progress chatter are suppressed.
    if event.get("material") is not True:
        return None
    allowed = {
        "event_id", "objective_id", "kind", "material", "headline", "summary",
        "stage", "evidence_ref", "next_action", "owner_action", "whole_percent",
    }
    if set(event) - allowed:
        raise EventRejected("event_fields_unsupported")
    ident = _limited(event.get("event_id"), "event_id", 120)
    if not EVENT_ID.fullmatch(ident):
        raise EventRejected("event_id_unsafe")
    objective = _limited(event.get("objective_id"), "objective_id", 100)
    if objective != "PMv4.11112026.1":
        raise EventRejected("objective_mismatch")
    headline = _limited(event.get("headline"), "headline", 150)
    summary = _limited(event.get("summary"), "summary", 400)
    stage = _limited(event.get("stage"), "stage", 32)
    if stage not in ALLOWED_STAGES:
        raise EventRejected("stage_unsupported")
    evidence = _limited(event.get("evidence_ref"), "evidence_ref", 230)
    next_action = _limited(event.get("next_action"), "next_action", 280)
    pct = event.get("whole_percent")
    if pct is not None and (type(pct) is not int or not 0 <= pct <= 100):
        raise EventRejected("whole_percent_invalid")
    if kind == "milestone_verified" and stage not in {
        "implemented", "tested", "merged", "deployed", "operationally_verified"
    }:
        raise EventRejected("milestone_stage_unverified")
    if kind == "material_problem" and stage not in {"blocked", "degraded"}:
        raise EventRejected("problem_stage_invalid")
    owner_action = event.get("owner_action")
    if kind == "owner_decision_required":
        owner_action = _limited(owner_action, "owner_action", 280)
    elif owner_action not in (None, "", "Nothing"):
        raise EventRejected("owner_action_only_for_decision_event")
    owner_action = owner_action if kind == "owner_decision_required" else "Nothing"
    # Event is a *milestone*, not evidence that the entire PMv4 objective is done.
    msg = (
        f"Jason PMv4 | {KINDS[kind]}\n"
        f"{headline}\n"
        f"Status: {stage.replace('_', ' ')} (PMv4 overall acceptance not implied)\n"
        f"Outcome/problem: {summary}\n"
        f"Independent evidence: {evidence}\n"
        f"Next action: {next_action}\n"
        f"Needed from Owner: {owner_action}\n"
        f"Whole PMv4: {str(pct) + '% (estimate)' if pct is not None else 'not measured'}"
    )
    return ident, msg


def _receipt_rows(text: str) -> list[dict[str, Any]]:
    rows = []
    for line in text.splitlines():
        if line.startswith(RECEIPT_MARKER):
            try:
                row = json.loads(line[len(RECEIPT_MARKER):])
                if isinstance(row, dict):
                    rows.append(row)
            except ValueError:
                raise EventRejected("register_receipt_corrupt") from None
    return rows


def _record(handle: Any, record: Mapping[str, Any]) -> None:
    handle.seek(0, os.SEEK_END)
    size = handle.tell()
    if size:
        handle.seek(-1, os.SEEK_END)
        if handle.read(1) != b"\n":
            handle.write(b"\n")
    handle.seek(0, os.SEEK_END)
    handle.write((RECEIPT_MARKER + json.dumps(dict(record), sort_keys=True, separators=(",", ":"))
                  + "\n").encode("utf-8"))
    handle.flush()
    os.fsync(handle.fileno())


def publish_once(
    event: Mapping[str, Any],
    *,
    task_register: Path,
    independent_evidence_check: Callable[[Mapping[str, Any]], bool],
    sender: Callable[[str], str],
    at: datetime | None = None,
) -> str:
    """At-most-once, evidence-bound delivery via the existing J-Man task register.

    Never automatically re-send an uncertain delivery. The trusted coordinator
    supplies evidence_check and sender, NOT the task payload or an editable JSON
    supplied by an external requester.
    """
    render = format_meaningful_event(event)
    if render is None:
        return "SUPPRESSED_ROUTINE_EVENT"
    if not callable(independent_evidence_check) or not callable(sender):
        raise EventRejected("trusted_adapter_missing")
    if independent_evidence_check(event) is not True:
        raise EventRejected("independent_evidence_unverified")
    now = at or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise EventRejected("time_not_utc_aware")
    key, message = render
    fingerprint = sha256(json.dumps(dict(event), sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    if task_register.is_symlink() or not task_register.is_file():
        raise EventRejected("canonical_task_register_missing")
    with task_register.open("r+b") as fd:
        fcntl.flock(fd.fileno(), fcntl.LOCK_EX)
        fd.seek(0)
        current = fd.read().decode("utf-8")
        rows = _receipt_rows(current)
        prior = [row for row in rows if row.get("event_id") == key]
        if prior:
            if any(row.get("fingerprint") != fingerprint for row in prior):
                raise EventRejected("conflicting_duplicate_event")
            return "ALREADY_HANDLED"
        base = {"event_id": key, "fingerprint": fingerprint,
                "kind": event["kind"], "observed_at": now.isoformat()}
        _record(fd, {**base, "state": "send_reserved"})
        try:
            message_id = sender(message)
            if not isinstance(message_id, str) or not message_id.strip() or len(message_id) > 200:
                raise EventRejected("positive_gateway_receipt_missing")
            if message_id.startswith("accepted:"):
                raise EventRejected("synthetic_receipt_not_delivery")
        except Exception:
            # Reservation is intentional: unknown delivery must be reconciled,
            # not retried into duplicate Teams messages.
            _record(fd, {**base, "state": "delivery_unverified"})
            raise
        _record(fd, {**base, "state": "sent", "message_id": message_id})
        return "SENT_WITH_PROVIDER_RECEIPT"


def existing_teams_sender(message: str, *, target: str, runner: Callable[..., Any] = subprocess.run) -> str:
    """Reuse J-Man's configured OpenClaw msteams sender, not approval cards."""
    if not isinstance(target, str) or not OWNER_TARGET.fullmatch(target):
        raise EventRejected("licensed_owner_teams_route_unverified")
    result = runner(
        ["openclaw", "message", "send", "--channel", "msteams", "--target", target,
         "--message", message, "--json"],
        capture_output=True, text=True, check=False, timeout=45,
    )
    if result.returncode != 0:
        raise EventRejected("existing_teams_sender_failed")
    try:
        parsed = json.loads(result.stdout)
    except (ValueError, TypeError):
        raise EventRejected("provider_receipt_invalid") from None
    if not isinstance(parsed, dict) or not isinstance(parsed.get("payload"), dict):
        raise EventRejected("provider_receipt_invalid")
    if parsed["payload"].get("deliveryStatus") != "sent":
        raise EventRejected("provider_delivery_unverified")
    mid = parsed.get("messageId") or parsed["payload"].get("messageId")
    if type(mid) is int and mid > 0:
        mid = str(mid)
    if not isinstance(mid, str) or not mid.strip() or len(mid) > 200:
        raise EventRejected("provider_message_id_missing")
    return mid
