#!/usr/bin/env python3
"""Evidence-only Project Jason development and release coordinator.

The coordinator derives a control-board view from authoritative repository,
roadmap, support, and production-alignment evidence. It recommends work but
never grants deployment or provider authority.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "development-release-coordinator.json"
ROADMAP_STATUS = ROOT / "docs" / "roadmaps" / "Jason-Roadmap-Status.json"
TODO_BACKLOG = ROOT / "docs" / "roadmaps" / "Project-Jason-TODO-and-Future-Ideas.md"
SUPPORT = ROOT / "SUPPORT.md"
AUTOMATED_CHANGE_STATE = ROOT / "docs" / "control" / "AUTOMATED-CHANGE-STATE.json"

SENSITIVE_PREFIXES = (
    ".github/workflows/",
    "implementation/",
    "infrastructure/",
    "deploy/",
    "config/",
    "scripts/",
    "tools/",
)
SENSITIVE_ROOTS = {"CONTRIBUTING.md", ".github/pull_request_template.md"}

SUPPORT_ROW = re.compile(
    r"^\|\s*(SUPPORT-[^|]+?)\s*\|\s*(P\d)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|"
)
TODO_HEADING = re.compile(r"^###\s+(TODO-[A-Z]+-\d+)\s+—\s+(.+?)\s*$")
FIELD = re.compile(r"^- \*\*(Priority|Status):\*\*\s*(.+?)\s*$")


@dataclass
class Api:
    repository: str
    token: str

    def request(self, path: str, method: str = "GET", payload: dict[str, Any] | None = None) -> Any:
        url = f"https://api.github.com/repos/{self.repository}{path}"
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "project-jason-development-release-coordinator",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))

    def paged(self, path: str) -> list[dict[str, Any]]:
        page = 1
        results: list[dict[str, Any]] = []
        while True:
            sep = "&" if "?" in path else "?"
            payload = self.request(f"{path}{sep}per_page=100&page={page}")
            if not isinstance(payload, list):
                raise RuntimeError(f"Expected list response from {path}")
            results.extend(payload)
            if len(payload) < 100:
                return results
            page += 1


def sensitive(path: str) -> bool:
    return path in SENSITIVE_ROOTS or path.startswith(SENSITIVE_PREFIXES)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def latest_checks(check_runs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for check in check_runs:
        name = str(check.get("name", ""))
        if not name:
            continue
        if name not in latest or int(check.get("id", 0)) > int(latest[name].get("id", 0)):
            latest[name] = check
    return latest


def summarize_required_checks(
    required: list[str], check_runs: list[dict[str, Any]]
) -> tuple[str, str, list[str]]:
    latest = latest_checks(check_runs)
    failures: list[str] = []
    pending: list[str] = []
    missing: list[str] = []
    passed = 0

    for name in required:
        check = latest.get(name)
        if check is None:
            missing.append(name)
            continue
        if check.get("status") != "completed":
            pending.append(name)
            continue
        if check.get("conclusion") == "success":
            passed += 1
        else:
            failures.append(name)

    if failures:
        state = "failing"
    elif missing:
        state = "missing"
    elif pending:
        state = "pending"
    else:
        state = "passed"

    detail = failures or missing or pending
    return state, f"{passed}/{len(required)}", detail


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
    return items


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
            field = FIELD.match(raw)
            if field:
                current[field.group(1).lower()] = field.group(2).strip()
    if current:
        items.append(current)

    excluded = ("blocked", "implemented", "retired", "rejected", "complete")
    return [
        item
        for item in items
        if not any(word in item.get("status", "").lower() for word in excluded)
    ]


def release_attention(pr_states: list[dict[str, Any]]) -> str:
    candidates = [
        pr
        for pr in pr_states
        if pr.get("recent") and pr["state"] in {"Blocked", "Needs revalidation"}
    ]
    if candidates:
        pr = candidates[0]
        return (
            f"Reconcile PR #{pr['number']} ({pr['title']}) before considering it for promotion. "
            "Independent development may continue in separate workstreams."
        )
    return "No recently active PR currently requires release-lane reconciliation."


def development_recommendation(
    support: list[dict[str, str]],
    todos: list[dict[str, str]],
) -> str:
    for priority in ("P0", "P1", "P2", "P3"):
        candidates = [item for item in support if item["priority"] == priority]
        if candidates:
            item = candidates[0]
            return f"Address {item['id']} ({item['title']}) — open {priority} support defect."

    for priority in ("P0", "P1", "P2", "P3"):
        candidates = [item for item in todos if item.get("priority") == priority]
        if candidates:
            item = candidates[0]
            return (
                f"Consider {item['id']} ({item['title']}) next. "
                "This is advisory; roadmap authority remains human."
            )

    return "No unblocked roadmap recommendation was derived from the current governed sources."


def classify_pr(
    pr: dict[str, Any],
    compare: dict[str, Any],
    check_state: str,
    preprod_configured: bool,
) -> str:
    if pr.get("draft"):
        return "In development"
    if int(compare.get("behind_by", 0) or 0) > 0:
        return "Needs revalidation"
    if check_state in {"failing", "missing"}:
        return "Blocked"
    if check_state == "pending":
        return "Validating"
    if check_state == "passed":
        return "Pre-prod ready" if preprod_configured else "CI-ready"
    return "In development"


def collect(api: Api, config: dict[str, Any]) -> dict[str, Any]:
    base = str(config["base_branch"])
    main = api.request(f"/branches/{urllib.parse.quote(base, safe='')}")
    main_sha = str(main["commit"]["sha"])
    pulls = api.paged(
        f"/pulls?state=open&base={urllib.parse.quote(base, safe='')}&sort=updated&direction=desc"
    )
    required = list(config["required_checks"])
    now = datetime.now(timezone.utc)
    active_cutoff = now - timedelta(days=int(config.get("active_overlap_days", 7)))
    display_cutoff = now - timedelta(days=int(config.get("active_display_days", 3)))

    pr_states: list[dict[str, Any]] = []
    active_files: dict[int, set[str]] = {}

    for pr in pulls:
        number = int(pr["number"])
        head_sha = str(pr["head"]["sha"])
        compare = api.request(f"/compare/{main_sha}...{head_sha}")
        checks_payload = api.request(f"/commits/{head_sha}/check-runs")
        check_state, check_count, check_detail = summarize_required_checks(
            required, list(checks_payload.get("check_runs", []))
        )
        state = classify_pr(
            pr,
            compare,
            check_state,
            bool(config.get("preproduction", {}).get("configured", False)),
        )
        updated = datetime.fromisoformat(str(pr["updated_at"]).replace("Z", "+00:00"))
        recent = updated >= display_cutoff
        if updated >= active_cutoff:
            files = api.paged(f"/pulls/{number}/files")
            active_files[number] = {
                str(item["filename"])
                for item in files
                if sensitive(str(item["filename"]))
            }

        pr_states.append(
            {
                "number": number,
                "title": str(pr["title"]),
                "url": str(pr["html_url"]),
                "updated_at": str(pr["updated_at"]),
                "head_sha": head_sha,
                "behind_by": int(compare.get("behind_by", 0) or 0),
                "check_state": check_state,
                "check_count": check_count,
                "check_detail": check_detail,
                "state": state,
                "recent": recent,
            }
        )

    overlaps: list[dict[str, Any]] = []
    numbers = sorted(active_files)
    for index, left in enumerate(numbers):
        for right in numbers[index + 1 :]:
            shared = sorted(active_files[left] & active_files[right])
            if shared:
                overlaps.append({"left": left, "right": right, "files": shared})

    production = load_json(AUTOMATED_CHANGE_STATE)
    roadmap = load_json(ROADMAP_STATUS)
    support = parse_support(SUPPORT.read_text(encoding="utf-8"))
    todos = parse_todos(TODO_BACKLOG.read_text(encoding="utf-8"))

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "main_sha": main_sha,
        "production": production.get("production", {}),
        "validated_source": production.get("validated_source", {}),
        "pr_states": pr_states,
        "overlaps": overlaps,
        "support": support,
        "todos": todos,
        "roadmap": roadmap,
        "release_attention": release_attention(pr_states),
        "development_recommendation": development_recommendation(support, todos),
        "older_open_pr_count": sum(1 for pr in pr_states if not pr.get("recent")),
        "preproduction": config.get("preproduction", {}),
        "production_policy": config.get("production", {}),
        "autonomous_repair_policy": config.get("production", {}).get("autonomous_repair", {}),
    }


def render(board: dict[str, Any]) -> str:
    prod = board["production"]
    preprod = board["preproduction"]
    lines = [
        "# Jason Development & Release Control Board",
        "",
        "> Derived evidence only. This board recommends and coordinates; it does not grant deployment, provider, or roadmap authority.",
        "",
        f"**Generated:** {board['generated_at']}  ",
        f"**Current main:** `{board['main_sha']}`  ",
        f"**Production revision:** `{prod.get('revision', 'unknown')}`  ",
        f"**Production health:** {prod.get('status', 'unknown')}  ",
        f"**Production evidence observed:** {prod.get('observed_at', 'unknown')}  ",
        f"**Pre-production environment:** {'configured' if preprod.get('configured') else 'not configured'}  ",
        "",
        "## Release attention",
        "",
        board["release_attention"],
        "",
        "## Recommended next development",
        "",
        board["development_recommendation"],
        "",
        "## Recently active development",
        "",
        "| PR | State | Main drift | Required checks | Updated |",
        "| --- | --- | ---: | --- | --- |",
    ]
    recent_prs = [pr for pr in board["pr_states"] if pr.get("recent")]
    for pr in recent_prs:
        title = pr["title"].replace("|", "\\|")
        lines.append(
            f"| [#{pr['number']}]({pr['url']}) {title} | {pr['state']} | "
            f"{pr['behind_by']} behind | {pr['check_count']} ({pr['check_state']}) | "
            f"{pr['updated_at']} |"
        )
    if not recent_prs:
        lines.append("| — | No recently active PRs | — | — | — |")
    if board["older_open_pr_count"]:
        lines.append(
            f"\nOlder open PRs not shown: **{board['older_open_pr_count']}**. "
            "If resumed, they must reconcile with current main before merge."
        )

    lines.extend(["", "## Active implementation overlaps", ""])
    if board["overlaps"]:
        for overlap in board["overlaps"]:
            preview = ", ".join(f"`{path}`" for path in overlap["files"][:8])
            if len(overlap["files"]) > 8:
                preview += f", … (+{len(overlap['files']) - 8} more)"
            lines.append(
                f"- PR #{overlap['left']} and PR #{overlap['right']}: {preview}"
            )
    else:
        lines.append("- No active implementation-sensitive file overlaps detected.")

    lines.extend(["", "## Open support defects", ""])
    if board["support"]:
        for item in board["support"][:12]:
            lines.append(
                f"- **{item['priority']} {item['id']}** — {item['title']} "
                f"_(status: {item['status']})_"
            )
    else:
        lines.append("- No open support defects were parsed from SUPPORT.md.")

    lines.extend(["", "## Unblocked roadmap candidates", ""])
    if board["todos"]:
        for item in board["todos"][:12]:
            lines.append(
                f"- **{item.get('priority', '?')} {item['id']}** — {item['title']} "
                f"_(status: {item.get('status', 'unknown')})_"
            )
    else:
        lines.append("- No unblocked TODO candidates were parsed.")

    lines.extend(
        [
            "",
            "## Release lane",
            "",
            f"- Parallel development allowed: **yes**.",
            f"- Production promotion serialized: **{'yes' if board['production_policy'].get('serialized_promotion') else 'no'}**.",
            f"- Human production approval required for normal releases: **{'yes' if board['production_policy'].get('human_approval_required') else 'no'}**.",
            f"- Autonomous repair classification enabled: **{'yes' if board['autonomous_repair_policy'].get('classification_enabled') else 'no'}**.",
            f"- Human approval required for an eligible autonomous repair: **{'yes' if board['autonomous_repair_policy'].get('human_approval_required_when_eligible') else 'no'}**.",
            f"- Autonomous repair production execution enabled: **{'yes' if board['autonomous_repair_policy'].get('automatic_execution_enabled') else 'no'}**.",
            f"- Autonomous repair execution blocker: {board['autonomous_repair_policy'].get('execution_blocker', 'none')}.",
            "- A CI-ready PR is not production-ready when pre-production is not configured.",
            "- Production promotion must use an exact merged main SHA and the governed release preflight.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def publish(api: Api, issue_number: int, body: str) -> None:
    if not api.token:
        raise RuntimeError("GITHUB_TOKEN is required to publish the control board")
    api.request(f"/issues/{issue_number}", method="PATCH", payload={"body": body})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--token", default=os.environ.get("GITHUB_TOKEN", ""))
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    if not args.repository:
        raise SystemExit("ERROR: repository is required via --repository or GITHUB_REPOSITORY")

    config = load_json(args.config)
    api = Api(args.repository, args.token)
    board = collect(api, config)
    body = render(board)

    if args.output:
        args.output.write_text(body, encoding="utf-8")
    else:
        print(body)

    if args.publish:
        publish(api, int(config["control_board_issue"]), body)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
