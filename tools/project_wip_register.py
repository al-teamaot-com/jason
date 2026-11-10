#!/usr/bin/env python3
"""Jason-owned, evidence-first WIP reconciliation for GitHub issue #2396.

Advisory register maintenance only; no authority grants, releases, or provider writes.
Execution is by Jason's existing scheduled development control-board workflow.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import os
import re

from development_release_coordinator import Api

REPO = "al-teamaot-com/jason"
REGISTER = 2396
BEGIN = "<!-- JASON-WIP-SYNC-BEGIN -->"
END = "<!-- JASON-WIP-SYNC-END -->"
REF = re.compile(r"(?:issues|pull)/(\d+)|(?<![\w])#(\d+)")
AUTO_ID = re.compile(r"GH-(?:ISSUE|PR)-(\d+)")
VERIFIED = re.compile(
    r"<!--\s*jason-wip-verified:\s*(https://[^\s>]+)\s*-->",
    re.IGNORECASE,
)
RETENTION_DAYS = 21


def references(text: str) -> set[int]:
    return {int(a or b) for a, b in REF.findall(text or "")}


def normal_title(title: str) -> str:
    return " ".join((title or "").replace("|", "/").split())[:145]


def is_done(issue: dict) -> tuple[bool, str]:
    """Only independent recorded outcome evidence permits closure on the register."""
    match = VERIFIED.search(issue.get("body") or "")
    return (
        issue.get("state") == "closed"
        and (issue.get("state_reason") == "completed"
             or bool((issue.get("pull_request") or {}).get("merged_at")))
        and match is not None,
        match.group(1) if match else "",
    )


def candidate(issue: dict, cutoff: datetime) -> bool:
    if issue.get("state") != "open":
        return False
    title = (issue.get("title") or "").lower().strip()
    if title.startswith(("idea", "design hold", "backlog", "deferred", "project jason — master work")):
        return False
    if "pull_request" in issue:
        return True  # An open PR is an uncompleted engineering assignment.
    labels = {
        (x.get("name") or "").lower()
        for x in issue.get("labels", []) if isinstance(x, dict)
    }
    if labels & {"in progress", "in-progress", "work-in-progress", "wip", "active"}:
        return True
    created = parse_date(issue.get("created_at"))
    return bool(created and created >= cutoff)  # New assigned work, not old backlog.


def parse_date(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def fetch_recent(api: Api, now: datetime) -> list[dict]:
    """Page newest updates; do not trust an arbitrary single-page result."""
    result: list[dict] = []
    for page in range(1, 51):
        batch = api.request(
            f"/issues?state=open&sort=updated&direction=desc&per_page=100&page={page}"
        )
        if not isinstance(batch, list):
            raise ValueError("GitHub issue pagination returned non-list")
        if not batch:
            break
        result.extend(batch)
        # Fully paginate *open* work, including older stalled work, in bounded
        # pages instead of one expensive API call per retained stale issue.
        if len(batch) < 100:
            break
    else:
        raise ValueError("GitHub issue pagination exceeded safe bound")
    # Every open PR is unfinished engineering work, including older PRs.
    # GitHub's /issues endpoint is not a substitute for complete PR pagination.
    for page in range(1, 11):
        batch = api.request(f"/pulls?state=open&per_page=100&page={page}")
        if not isinstance(batch, list):
            raise ValueError("GitHub PR pagination returned non-list")
        for item in batch:
            copy = dict(item)
            copy["pull_request"] = {"url": copy.get("html_url", "")}
            result.append(copy)
        if len(batch) < 100:
            break
    else:
        raise ValueError("GitHub PR pagination exceeded safe bound")
    return result


def parse_existing(block: str) -> dict[int, str]:
    rows: dict[int, str] = {}
    for line in block.splitlines():
        first = line.split("|")[1] if line.startswith("|") else ""
        if AUTO_ID.search(first):
            # Retain every member of a consolidated incident group across runs.
            for number in references(line):
                rows[number] = line
    return rows


def get_source(api: Api, number: int) -> dict:
    return api.request(f"/issues/{number}")


def format_line(issue: dict, done: bool, evidence: str = "") -> str:
    number = int(issue["number"])
    kind = "PR" if issue.get("pull_request") else "ISSUE"
    label = f"[{kind} #{number}](https://github.com/{REPO}/{'pull' if kind == 'PR' else 'issues'}/{number})"
    title = normal_title(issue.get("title", ""))
    if done:
        status = f"**100% verified** — [evidence]({evidence})"
    elif issue.get("state") == "closed":
        status = "Verification pending — closed in GitHub, no operational proof"
    else:
        status = "Active — not 100% verified"
    return f"| GH-{kind}-{number} | {label}: {title} | {status} |"


def incident_key(issue: dict) -> str:
    number = int(issue["number"])
    if issue.get("pull_request"):
        return f"pr:{number}"
    title = normal_title(issue.get("title", "")).lower()
    title = re.sub(r"support-auto-[0-9a-f]{6,}", "support-auto", title)
    return f"issue:{title}"


def grouped_lines(selected: list[dict]) -> tuple[list[str], list[str]]:
    groups: dict[str, list[dict]] = {}
    for issue in selected:
        groups.setdefault(incident_key(issue), []).append(issue)
    active: list[str] = []
    complete: list[str] = []
    for _, group in sorted(groups.items(), reverse=True):
        group.sort(key=lambda i: int(i["number"]), reverse=True)
        if len(group) == 1:
            done, evidence = is_done(group[0])
            (complete if done else active).append(format_line(group[0], done, evidence))
            continue
        proofs = [is_done(i) for i in group]
        all_done = all(done for done, _ in proofs)
        refs = ", ".join(
            f"[#{int(i['number'])}](https://github.com/{REPO}/issues/{int(i['number'])})"
            for i in group
        )
        title = normal_title(group[0].get("title", ""))
        title = re.sub(r"SUPPORT-AUTO-[0-9A-Fa-f]{6,}", "SUPPORT-AUTO", title)
        if all_done:
            status = f"**100% verified** ({len(group)} linked issues); " + ", ".join(
                f"[evidence]({url})" for _, url in proofs
            )
        else:
            verified_count = sum(1 for done, _ in proofs if done)
            status = f"Active — {verified_count}/{len(group)} independently verified"
        line = f"| GH-ISSUE-{int(group[0]['number'])} ({len(group)} related) | {title}: {refs} | {status} |"
        (complete if all_done else active).append(line)
    return active, complete


def active_table(active: list[str]) -> str:
    return "\n".join([
        "### Auto-discovered active WIP",
        "| ID | Source / objective | Status |",
        "| --- | --- | --- |",
        *(active or ["| — | No untracked active work found | — |"]),
    ])


def complete_table(complete: list[str]) -> str:
    return "\n".join([
        "### Auto-discovered completed (verified)",
        "| ID | Source / objective | Status |",
        "| --- | --- | --- |",
        *(complete or ["| — | No 100%-verified work recorded | — |"]),
    ])


def archive_curated_verified(human: str, api: Api) -> str:
    """Move whole objectives only if EVERY linked source has verified acceptance."""
    before, after = human.split("## COMPLETED", 1)
    kept: list[str] = []
    archived: list[str] = []
    for line in before.splitlines():
        if not re.match(r"^\| W\d+ \|", line):
            kept.append(line)
            continue
        refs = references(line)
        if not refs or REGISTER in refs:
            kept.append(line)
            continue
        sources = [get_source(api, ref) for ref in sorted(refs)]
        statuses = [is_done(src) for src in sources]
        if not statuses or not all(done for done, _ in statuses):
            kept.append(line)
            continue
        archived.append(line + " **100% independently verified:** " +
                        ", ".join(f"[evidence]({url})" for _, url in statuses))
    if not archived:
        return human
    completed_header = "## COMPLETED (100% independently verified)"
    assert human.count(completed_header) == 1
    parts = after.split("\n", 1)
    rest = parts[1] if len(parts) > 1 else ""
    archived_text = "\n".join(archived)
    return "\n".join(kept) + "\n" + completed_header + "\n" + archived_text + "\n" + rest


def reconcile(api: Api, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    reg = get_source(api, REGISTER)
    body = str(reg.get("body") or "")
    if not body.startswith("# Project Jason") or "## ACTIVE WIP" not in body:
        raise ValueError("WIP register structure mismatch; refusing to overwrite")
    prior = ""
    if BEGIN in body or END in body:
        if body.count(BEGIN) != 1 or body.count(END) != 1:
            raise ValueError("WIP register automation markers inconsistent")
        before, later = body.split(BEGIN, 1)
        prior, after = later.split(END, 1)
        human = before + after
    else:
        human = body.rstrip() + "\n\n"
    human = archive_curated_verified(human, api)
    # Only the explicitly active human-curated section provides dedupe anchors.
    curated_active = human.split("## ACTIVE WIP", 1)[1].split("## COMPLETED", 1)[0]
    curated_refs = references(curated_active)
    seen = parse_existing(prior)
    recent = fetch_recent(api, now)
    by_id = {int(x["number"]): x for x in recent}
    # Preserve previously discovered WIP even after activity ages out.
    for number in sorted(set(seen) - set(by_id)):
        by_id[number] = get_source(api, number)
    selected: dict[int, dict] = {}
    for number, issue in sorted(by_id.items()):
        if number == REGISTER or number in curated_refs:
            continue
        if number in seen or candidate(issue, now - timedelta(days=RETENTION_DAYS)):
            selected[number] = issue

    included: list[dict] = []
    untracked_issue_ids = {
        n for n, i in selected.items() if not i.get("pull_request")
    }
    for number, issue in sorted(selected.items(), reverse=True):
        if number not in seen and references(issue.get("body") or "") & curated_refs:
            continue
        if (number not in seen and issue.get("pull_request")
                and references(issue.get("body") or "") & untracked_issue_ids):
            continue
        included.append(issue)
    active, complete = grouped_lines(included)

    generated = "\n".join([
        BEGIN,
        "## Jason automated discovery (read-only GitHub reconciliation)",
        "",
        "Open PRs and recent new issues not represented by the curated objective rows.",
        "Closed PRs/issues **remain active** until exact operational verification is recorded.",
        "Full completion requires closed/completed source **and** the marker",
        "\u0060<!-- jason-wip-verified: https://evidence.example/path -->\u0060",
        "containing an actual verifiable acceptance-evidence URL. The marker is not self-validating.",
        "This automation never grants production authority or approves releases.",
        "",
        active_table(active),
        "",
        complete_table(complete),
        END,
    ])
    new_body = human.rstrip() + "\n\n" + generated + "\n"
    if new_body == body:
        return {"changed": False, "active": len(active), "completed": len(complete)}
    # Refresh once immediately before write; fail closed on concurrent human edits.
    if (get_source(api, REGISTER).get("body") or "") != body:
        raise RuntimeError("register changed concurrently; retry next scheduled run")
    api.request(f"/issues/{REGISTER}", method="PATCH", payload={"body": new_body})
    return {"changed": True, "active": len(active), "completed": len(complete)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", default=REPO)
    parser.add_argument("--token", default=os.environ.get("GITHUB_TOKEN", ""))
    args = parser.parse_args()
    if args.repository != REPO or not args.token:
        raise SystemExit("refusing to mutate without exact repository and GitHub token")
    result = reconcile(Api(repository=args.repository, token=args.token))
    print(f"wip_reconciled changed={result['changed']} active={result['active']} completed={result['completed']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
