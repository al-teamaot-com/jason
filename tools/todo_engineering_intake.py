#!/usr/bin/env python3
"""Project Jason governed TODO engineering intake.

Turns actionable TODO backlog entries into bounded owner-approved development
issues consumed by the existing owner-approved development worker. This module
does not implement code, merge pull requests, deploy production, or grant
provider authority.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import release_manager_gate as release_gate
import support_repair_host_worker as support_worker

DEFAULT_REPO = Path("/home/al/projects/jason")
DEFAULT_SPOOL = Path("/var/lib/jason/openclaw/support-repair")
DEFAULT_CONFIG = Path("config/development-release-coordinator.json")
TODO_PATH = Path("docs/roadmaps/Project-Jason-TODO-and-Future-Ideas.md")
SUPPORT_PATH = Path("SUPPORT.md")

TODO_HEADING = re.compile(r"^###\s+(TODO-[A-Z]+-\d+)\s+—\s+(.+?)\s*$")
FIELD = re.compile(r"^- \*\*(Priority|Status|Autonomous engineering readiness):\*\*\s*(.+?)\s*$")
ISSUE_TODO = re.compile(r"(?im)^\s*-\s*TODO item\s*:\s*(TODO-[A-Z]+-[0-9]+)\s*$")
EXECUTABLE_STATUS = "approved for autonomous engineering"
PRIORITY = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}


class TodoIntakeError(RuntimeError):
    pass


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run(args: list[str], *, cwd: Path, check: bool = True) -> str:
    completed = subprocess.run(
        args,
        cwd=cwd,
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return completed.stdout.strip()


def gh_json(args: list[str], *, cwd: Path) -> Any:
    raw = run(["gh", *args], cwd=cwd)
    return json.loads(raw) if raw else None


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


@dataclass(frozen=True, slots=True)
class TodoItem:
    item_id: str
    title: str
    priority: str
    status: str
    readiness: str
    section: str

    @property
    def executable(self) -> bool:
        status = self.status.casefold().strip()
        readiness = self.readiness.casefold().strip()
        return (
            status.startswith(EXECUTABLE_STATUS)
            and readiness.startswith("approved")
        )


def parse_todo_sections(text: str) -> list[TodoItem]:
    lines = text.splitlines()
    headings: list[tuple[int, re.Match[str]]] = []
    for index, line in enumerate(lines):
        match = TODO_HEADING.match(line)
        if match:
            headings.append((index, match))

    items: list[TodoItem] = []
    for pos, (start, match) in enumerate(headings):
        end = headings[pos + 1][0] if pos + 1 < len(headings) else len(lines)
        section_lines = lines[start:end]
        fields: dict[str, str] = {}
        for line in section_lines[1:]:
            field = FIELD.match(line)
            if field:
                fields[field.group(1).casefold()] = field.group(2).strip()
        items.append(
            TodoItem(
                item_id=match.group(1),
                title=match.group(2).strip(),
                priority=fields.get("priority", ""),
                status=fields.get("status", ""),
                readiness=fields.get("autonomous engineering readiness", ""),
                section="\n".join(section_lines).strip(),
            )
        )
    return items


def open_todo_issue_map(repo: Path) -> dict[str, dict[str, Any]]:
    issues = gh_json(
        [
            "issue",
            "list",
            "--state",
            "open",
            "--limit",
            "200",
            "--json",
            "number,title,body,url,updatedAt",
        ],
        cwd=repo,
    ) or []
    result: dict[str, dict[str, Any]] = {}
    for issue in issues:
        body = str(issue.get("body") or "")
        match = ISSUE_TODO.search(body)
        if match:
            result[match.group(1).upper()] = dict(issue)
    return result


def load_support_state(spool: Path) -> dict[str, Any]:
    path = spool / "state.json"
    if not path.exists():
        return {"items": {}}
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {"items": {}}


def blocked_support_ids(state: Mapping[str, Any]) -> list[str]:
    items = state.get("items") if isinstance(state.get("items"), Mapping) else {}
    return sorted(
        str(item_id)
        for item_id, record in items.items()
        if isinstance(record, Mapping)
        and str(record.get("phase") or "") == "blocked"
    )


def active_support_ids(state: Mapping[str, Any]) -> list[str]:
    active_phases = {
        "diagnosing",
        "implementing",
        "ci_repair_needed",
        "ci_repairing",
        "pr_validating",
        "merged_waiting_deployment",
        "production_verifying",
        "closure_validating",
        "closure_merging",
    }
    items = state.get("items") if isinstance(state.get("items"), Mapping) else {}
    return sorted(
        str(item_id)
        for item_id, record in items.items()
        if isinstance(record, Mapping)
        and str(record.get("phase") or "") in active_phases
    )


def capacity_consuming_todo_issue_count(
    issues: Mapping[str, Mapping[str, Any]],
    spool: Path,
) -> int:
    """Count open TODO issues that still consume admission capacity.

    Blocked development remains durably bound to its existing TODO issue for
    duplicate suppression, but it must not permanently consume a new-work slot.
    """
    path = spool / "development-state.json"
    if not path.exists():
        return len(issues)
    value = json.loads(path.read_text(encoding="utf-8"))
    records = value.get("items") if isinstance(value, Mapping) else {}
    records = records if isinstance(records, Mapping) else {}
    blocked_issue_numbers = {
        int(record.get("issue_number"))
        for record in records.values()
        if isinstance(record, Mapping)
        and str(record.get("phase") or "") == "blocked"
        and str(record.get("issue_number") or "").isdigit()
    }
    return sum(
        1
        for issue in issues.values()
        if int(issue.get("number", 0) or 0) not in blocked_issue_numbers
    )


def outstanding_commitment_snapshot(spool: Path) -> dict[str, Any]:
    """Report stalled downstream work without granting additional admission authority.

    The release bridge remains authoritative for item phases. An absent or
    malformed report is unknown, never evidence that all work is complete.
    """
    path = spool / "todo-release-state.json"
    if not path.is_file():
        return {"status": "unknown", "outstanding_count": None, "items": []}
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"status": "unknown", "outstanding_count": None, "items": []}
    records = state.get("items") if isinstance(state, dict) else None
    if not isinstance(records, dict):
        return {"status": "unknown", "outstanding_count": None, "items": []}
    pending = [
        {"id": item_id, "phase": str(record.get("phase") or "unknown"),
         "reason": str(record.get("reason") or "")[:350]}
        for item_id, record in sorted(records.items())
        if isinstance(record, dict) and record.get("phase") != "complete"
    ]
    return {"status": "known", "outstanding_count": len(pending), "items": pending}


def active_development_count(spool: Path) -> int:
    path = spool / "development-state.json"
    if not path.exists():
        return 0
    value = json.loads(path.read_text(encoding="utf-8"))
    items = value.get("items") if isinstance(value, Mapping) else {}
    items = items if isinstance(items, Mapping) else {}
    active = {
        "identified",
        "diagnosing",
        "implementing",
        "ci_repair_needed",
        "ci_repairing",
        "pr_validating",
        "merged_waiting_release",
        "release_preparing",
        "release_waiting",
    }
    return sum(
        1
        for record in items.values()
        if isinstance(record, Mapping)
        and str(record.get("phase") or "") in active
    )


def select_candidate(
    *,
    todos: list[TodoItem],
    support_text: str,
    support_state: Mapping[str, Any],
    max_support_repairs: int,
    existing_issues: Mapping[str, Any],
    eligible_support_ids: set[str] | None = None,
) -> tuple[TodoItem | None, str]:
    support = release_gate.parse_support(support_text)
    if eligible_support_ids is not None:
        support = [
            item for item in support
            if item["id"] in eligible_support_ids
        ]
    todo_summary = [
        {
            "id": item.item_id,
            "title": item.title,
            "priority": item.priority,
            "status": item.status,
        }
        for item in todos
        if item.executable
    ]
    plan = release_gate.work_priority_plan(
        support,
        todo_summary,
        active_support_ids=active_support_ids(support_state),
        blocked_support_ids=blocked_support_ids(support_state),
        max_active_support_repairs=max_support_repairs,
    )
    if not plan["todo_start_allowed"]:
        return (
            None,
            "Support-first scheduling: an open Support item can occupy an available repair slot",
        )

    candidates = [
        item
        for item in todos
        if item.executable
        and item.priority in PRIORITY
        and item.item_id not in existing_issues
    ]
    candidates.sort(key=lambda item: (PRIORITY[item.priority], item.item_id))
    if not candidates:
        return None, "No actionable TODO item without an existing engineering issue"
    return candidates[0], "eligible"


def issue_body(item: TodoItem) -> str:
    return f"""## Governed TODO engineering intake

- TODO item: {item.item_id}
- TODO priority: {item.priority}
- TODO source status: {item.status}
- TODO readiness: {item.readiness}
- **Autonomous development:** owner-approved
- Approval source: governed Project Jason TODO readiness record
- Development worker: jason-owner-approved-development-worker
- Release path: Jason Release Manager required
- Production deployment authority: none
- Protected-core production approval: not granted by this intake

## Organizational outcome

Implement the exact bounded TODO scope below. Do not silently broaden the request.
If the work discovers that Jason is failing behavior it is already expected to
provide, create/update a Support List item and let Support-first priority take over.

## Source TODO section

{item.section}

## Release and completion rule

The development issue and source PR are not completion evidence.

This TODO may be considered implemented only after:
1. the exact merged main SHA is admitted by Jason Release Manager;
2. isolated pre-production passes;
3. the exact tested artifact reaches production;
4. production reaches `production_verified` / `closed`;
5. the TODO backlog is updated to `Implemented` with the release ID and production SHA.

If the change touches protected-core paths, exact owner approval remains required
at the Release Manager production gate.
"""


def create_issue(repo: Path, item: TodoItem) -> dict[str, Any]:
    title = f"{item.item_id}: {item.title}"
    body = issue_body(item)
    import tempfile

    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
        handle.write(body)
        path = Path(handle.name)
    try:
        raw = run(
            [
                "gh",
                "issue",
                "create",
                "--title",
                title[:250],
                "--body-file",
                str(path),
            ],
            cwd=repo,
        )
    finally:
        path.unlink(missing_ok=True)
    match = re.search(r"/issues/(\d+)", raw)
    if not match:
        raise TodoIntakeError("could not determine created TODO engineering issue number")
    number = int(match.group(1))
    detail = gh_json(
        ["issue", "view", str(number), "--json", "number,title,body,url,author"],
        cwd=repo,
    )
    if not isinstance(detail, Mapping):
        raise TodoIntakeError("created TODO issue could not be read back")
    if item.item_id not in str(detail.get("body") or ""):
        raise TodoIntakeError("created TODO issue failed readback binding")
    return dict(detail)


def atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.chmod(0o600)
    temp.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=DEFAULT_REPO)
    parser.add_argument("--spool", type=Path, default=DEFAULT_SPOOL)
    parser.add_argument("--max-support-repairs", type=int, default=2)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    repo = args.repo.resolve()
    spool = args.spool.resolve()
    config = load_json(repo / DEFAULT_CONFIG)
    policy = dict(config.get("todo_autonomy") or {})
    state_path = spool / "todo-intake-state.json"

    if not policy.get("enabled", False):
        atomic_json(
            state_path,
            {
                "schema_version": "1.0",
                "observed_at": now(),
                "status": "disabled",
            },
        )
        return 0

    run(["git", "fetch", "--no-tags", "origin", "main"], cwd=repo)
    todo_text = run(["git", "show", f"origin/main:{TODO_PATH.as_posix()}"], cwd=repo)
    support_text = run(["git", "show", f"origin/main:{SUPPORT_PATH.as_posix()}"], cwd=repo)

    todos = parse_todo_sections(todo_text)
    issues = open_todo_issue_map(repo)
    support_state = load_support_state(spool)
    support_limit = int(
        config.get("support_autonomy", {}).get("max_active_items", args.max_support_repairs)
    )
    active_support = len(active_support_ids(support_state))
    blocked_support = len(blocked_support_ids(support_state))
    active_development = active_development_count(spool)
    engineering_limit = max(
        1,
        int(policy.get("max_active_items", 1)) + support_limit,
    )
    if active_support + active_development >= engineering_limit:
        candidate, reason = None, "Engineering capacity is already fully occupied"
    elif capacity_consuming_todo_issue_count(issues, spool) >= int(
        policy.get("max_open_todo_issues", 1)
    ):
        candidate, reason = None, "Maximum capacity-consuming TODO engineering issues already reached"
    else:
        candidate, reason = select_candidate(
            todos=todos,
            support_text=support_text,
            support_state=support_state,
            max_support_repairs=support_limit,
            existing_issues=issues,
            eligible_support_ids=support_worker.open_support_issue_ids(repo),
        )

    state: dict[str, Any] = {
        "schema_version": "1.0",
        "observed_at": now(),
        "status": "idle" if candidate is None else "candidate_selected",
        "reason": reason,
        "active_support_repairs": active_support,
        "blocked_support_repairs": blocked_support,
        "active_development_items": active_development,
        "engineering_capacity": engineering_limit,
        "existing_todo_issues": {
            item_id: int(issue["number"]) for item_id, issue in sorted(issues.items())
        },
        "capacity_consuming_todo_issues": capacity_consuming_todo_issue_count(issues, spool),
    }

    downstream = outstanding_commitment_snapshot(spool)
    state["downstream_commitments"] = downstream
    if candidate is None and downstream["outstanding_count"]:
        state["status"] = "stalled_upstream_or_downstream"
        state["reason"] = (
            f"No new candidate; {downstream['outstanding_count']} approved commitments "
            f"remain in existing engineering/release workflows. Intake alone cannot advance them."
        )

    if candidate is None:
        atomic_json(state_path, state)
        return 0

    state["candidate"] = {
        "id": candidate.item_id,
        "priority": candidate.priority,
        "status": candidate.status,
        "title": candidate.title,
    }

    if args.dry_run:
        state["status"] = "dry_run"
        atomic_json(state_path, state)
        print(json.dumps(state, indent=2))
        return 0

    created = create_issue(repo, candidate)
    state["status"] = "issue_created"
    state["issue"] = {
        "number": int(created["number"]),
        "url": str(created.get("url") or ""),
        "todo_id": candidate.item_id,
    }
    atomic_json(state_path, state)
    print(json.dumps(state, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
