#!/usr/bin/env python3
"""Source-only proposed replacement for the existing J-Man status_report.py.

This intentionally reuses the existing J-Man TASKS.md register and OpenClaw
message delivery, not a new service, scheduler, state store or approval flow.
It never converts a task-record assertion into independently verified completion.
NO deployment/activation is performed by this module.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from zoneinfo import ZoneInfo


def _latest_pmv4_section(text: str) -> str:
    matches = list(re.finditer(r"^## PMv4\.x\b[^\n]*", text, flags=re.M | re.I))
    if not matches:
        return ""
    start = matches[-1]
    remainder = text[start.end():]
    next_heading = re.search(r"^##\s", remainder, flags=re.M)
    return remainder[:next_heading.start()] if next_heading else remainder


def _line_after(section: str, prefix: str) -> str:
    match = re.search(r"^[-*]\s*" + re.escape(prefix) + r"\s*:\s*(.*?)\s*$",
                      section, flags=re.I | re.M)
    return match.group(1)[:250] if match else ""


def _status_from_record(section: str) -> str:
    for prefix in ("Current status", "Status"):
        value = _line_after(section, prefix)
        if value:
            return value
    return "unavailable"


def _whole_percent(section: str) -> str:
    match = re.search(r"Whole PMv4 program completion\s*:\s*(?:estimated\s*)?(\d{1,3})%",
                      section, flags=re.I)
    if not match:
        return "Unknown — percentage not present in current task record"
    value = int(match.group(1))
    if value > 100:
        return "Unknown — invalid percentage in task record"
    return f"{value}% (J-Man task-record estimate; independent whole-objective acceptance pending)"


def build_report(task_file: Path, *, when: dt.datetime) -> str:
    when = when.astimezone(ZoneInfo("America/New_York"))
    if not task_file.is_file():
        return (f"J-Man status | {when:%Y-%m-%d %H:%M} ET\n"
                "Overall Status: UNKNOWN — existing TASKS.md unavailable; no success claim.\n"
                "Verified: Nothing about active objective execution can be established.\n"
                "Problems/Blockers: Task record missing; gateway and production state not independently probed.\n"
                "Next Action: Restore read-only access to the existing work record and verify current runtime.\n"
                "Needed From Me: Nothing for initial investigation.\n"
                "Whole-Task Completion: Unknown — no authoritative current objective evidence.\n")
    data = task_file.read_bytes()
    section = _latest_pmv4_section(data.decode("utf-8", errors="replace"))
    if not section:
        return (f"J-Man status | {when:%Y-%m-%d %H:%M} ET\n"
                "Overall Status: UNKNOWN — PMv4 objective absent from current task register.\n"
                f"Verified: Existing task record is readable (SHA256 {hashlib.sha256(data).hexdigest()[:16]}).\n"
                "Problems/Blockers: No PMv4 status evidence; no runtime/provider health readback.\n"
                "Next Action: Reconcile the accepted PMv4 objective with the existing task register.\n"
                "Needed From Me: Nothing for initial read-only reconciliation.\n"
                "Whole-Task Completion: Unknown — no PMv4 progress evidence.\n")
    record_status = _status_from_record(section)
    upper = record_status.upper()
    blocked = any(word in upper for word in ("BLOCKED", "FAILED", "STALLED", "DEGRADED"))
    claimed = (bool(re.search(r"\bCOMPLETE\b", upper))
               and not any(term in upper for term in ("NOT VERIFIED", "INCOMPLETE", "NOT COMPLETE", "UNVERIFIED")))
    msg = ("BLOCKED / DEGRADED (TASK RECORD, LIVE STATE UNVERIFIED)" if blocked
           else "UNVERIFIED COMPLETION CLAIM" if claimed
           else "IN PROGRESS / OPERATIONAL ACCEPTANCE UNVERIFIED")
    needed = _line_after(section, "Needed From Owner") or _line_after(section, "Needed From Me")
    if needed.casefold().startswith("nothing"):
        needed_text = "Nothing (per task record; independent authority check not performed)"
    elif needed:
        needed_text = "Action indicated in the task record; confirm the exact current requirement"
    else:
        needed_text = "Unknown — task record does not establish the required Owner action"
    stamp = dt.datetime.fromtimestamp(task_file.stat().st_mtime, tz=dt.timezone.utc)
    days = (when.astimezone(dt.timezone.utc) - stamp).total_seconds() / 86400
    age = "STALE" if days > 2 else "RECENT"
    # A file's content is evidence of what was recorded, NOT independent
    # evidence that the objective actually succeeded or production is healthy.
    return (f"J-Man status | {when:%Y-%m-%d %H:%M} ET\n"
            f"Overall Status: {msg}. Task-register assertion is not operational proof.\n"
            f"Verified: Existing PMv4 record read, SHA256 {hashlib.sha256(data).hexdigest()[:16]}; "
            f"record freshness {age}; status category: {msg}.\n"
            "Problems/Blockers: Live outcome, deployment, ticket processing and unattended recovery "
            "have not been independently verified by this report.\n"
            "Next Action: Verify current execution/acceptance through the governed source and runtime "
            "before declaring completion.\n"
            f"Needed From Me: {needed_text}.\n"
            f"Whole-Task Completion: {_whole_percent(section)}.\n")


def send_meaningful_event(
    event: dict,
    *, trusted_evidence_check,
    task_file: Path | None = None,
    sender=None,
) -> str:
    """PMv4 J-Man event hook: source-only until trusted native dispatch is bound.

    Called by the existing approved J-Man/work-engine controller after fresh
    independent source observation. No user/chat-supplied verification callback
    may be installed; the trusted runtime must own that dependency.
    """
    import importlib.util
    source = Path(__file__).resolve().with_name("meaningful_events.py")
    spec = importlib.util.spec_from_file_location("pmv4_meaningful_events", source)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    target = os.environ.get("JMAN_TEAMS_TARGET", "").strip()
    if not module.OWNER_TARGET.fullmatch(target):
        raise module.EventRejected("licensed_owner_teams_route_unverified")
    if sender is None:
        sender = lambda msg: module.existing_teams_sender(msg, target=target)
    return module.publish_once(
        event,
        task_register=task_file or Path.home() / ".openclaw/workspaces/j-man/TASKS.md",
        independent_evidence_check=trusted_evidence_check,
        sender=sender,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--send", action="store_true", help="use existing OpenClaw Teams channel; requires configured target")
    parser.add_argument("--task-file", type=Path, default=Path.home() / ".openclaw/workspaces/j-man/TASKS.md")
    args = parser.parse_args(argv)
    text = build_report(args.task_file, when=dt.datetime.now(dt.timezone.utc))
    if not args.send:
        print(text, end="")
        return 0
    # PMv4 Owner preference: no routine scheduled status spam.
    # Native task/work-engine terminal events call send_meaningful_event with
    # fresh independent evidence; the legacy scheduled --send remains harmless.
    print("ROUTINE_STATUS_SUPPRESSED: meaningful events only", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
