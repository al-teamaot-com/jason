#!/usr/bin/env python3
"""Native Project Jason support intake worker.

Runs on the Jason host. Reads canonical SUPPORT.md from protected GitHub main,
derives the open break/fix queue, detects existing repair PRs, and persists a
durable local queue for Jason's engineering executor. It performs no provider
mutation and sends no notifications.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

SUPPORT_ROW = re.compile(
    r"^\|\s*(SUPPORT-[^|]+?)\s*\|\s*(P\d)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|"
)
SUPPORT_ID = re.compile(r"\bSUPPORT-[A-Z]+-[0-9]+\b")
CLOSED_TERMS = ("resolved", "closed", "reclassified")
DEFAULT_REPOSITORY = "al-teamaot-com/jason"
DEFAULT_STATE_DIR = Path("/var/lib/jason/openclaw/support-intake")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run_gh(args: list[str]) -> Any:
    completed = subprocess.run(
        ["gh", "api", *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        env=os.environ.copy(),
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "GitHub read failed: " + (completed.stderr.strip() or "unknown gh error")[:500]
        )
    return json.loads(completed.stdout)


def fetch_support_md(repository: str) -> str:
    payload = run_gh([f"repos/{repository}/contents/SUPPORT.md?ref=main"])
    if not isinstance(payload, Mapping):
        raise RuntimeError("GitHub SUPPORT.md response was not an object")
    content = str(payload.get("content") or "").replace("\n", "")
    encoding = str(payload.get("encoding") or "")
    if encoding != "base64" or not content:
        raise RuntimeError("GitHub SUPPORT.md content was not base64 encoded")
    return base64.b64decode(content).decode("utf-8")


def fetch_open_prs(repository: str) -> list[dict[str, Any]]:
    payload = run_gh([f"repos/{repository}/pulls?state=open&per_page=100"])
    if not isinstance(payload, list):
        raise RuntimeError("GitHub open PR response was not a list")
    return [dict(item) for item in payload if isinstance(item, Mapping)]


def parse_open_support(text: str) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for raw in text.splitlines():
        match = SUPPORT_ROW.match(raw)
        if not match:
            continue
        item_id, priority, status, title = (part.strip() for part in match.groups())
        low = status.casefold()
        if any(term in low for term in CLOSED_TERMS):
            continue
        items.append(
            {
                "id": item_id,
                "priority": priority,
                "status": status,
                "title": title,
            }
        )
    return items


def pr_support_ids(pr: Mapping[str, Any]) -> set[str]:
    haystack = " ".join(
        [
            str(pr.get("title") or ""),
            str(pr.get("body") or ""),
            str((pr.get("head") or {}).get("ref") or "")
            if isinstance(pr.get("head"), Mapping)
            else "",
        ]
    )
    return set(SUPPORT_ID.findall(haystack.upper()))


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": "1.0", "items": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise RuntimeError("support intake state is unreadable") from error
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), dict):
        raise RuntimeError("support intake state has invalid shape")
    return payload


def atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("x", encoding="utf-8") as handle:
        os.chmod(temp, 0o600)
        handle.write(json.dumps(dict(payload), indent=2, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)


def priority_rank(value: str) -> int:
    try:
        return int(value.upper().removeprefix("P"))
    except ValueError:
        return 99


def derive_queue(
    *,
    support_items: list[dict[str, str]],
    prs: list[dict[str, Any]],
    previous: dict[str, Any],
    observed_at: str,
) -> dict[str, Any]:
    pr_map: dict[str, list[dict[str, Any]]] = {}
    for pr in prs:
        for support_id in pr_support_ids(pr):
            pr_map.setdefault(support_id, []).append(
                {
                    "number": int(pr.get("number") or 0),
                    "title": str(pr.get("title") or ""),
                    "url": str(pr.get("html_url") or ""),
                    "head": str((pr.get("head") or {}).get("ref") or "")
                    if isinstance(pr.get("head"), Mapping)
                    else "",
                }
            )

    previous_items = previous.get("items") or {}
    records: dict[str, dict[str, Any]] = {}
    for item in support_items:
        old = previous_items.get(item["id"]) if isinstance(previous_items, Mapping) else None
        first_seen = (
            str(old.get("first_seen_at"))
            if isinstance(old, Mapping) and old.get("first_seen_at")
            else observed_at
        )
        active_prs = pr_map.get(item["id"], [])
        records[item["id"]] = {
            **item,
            "first_seen_at": first_seen,
            "last_seen_at": observed_at,
            "work_state": "active_engineering" if active_prs else "queued_for_engineering",
            "active_prs": active_prs,
        }

    ordered = sorted(
        records.values(),
        key=lambda row: (
            priority_rank(str(row["priority"])),
            0 if row["work_state"] == "active_engineering" else 1,
            str(row["first_seen_at"]),
            str(row["id"]),
        ),
    )

    selected = ordered[0] if ordered else None
    return {
        "schema_version": "1.0",
        "observed_at": observed_at,
        "source": "protected-main:SUPPORT.md",
        "mode": "native_host_intake",
        "browser_dependency": False,
        "engineering_executor": "not_configured",
        "selected_support_id": selected["id"] if selected else None,
        "items": records,
        "ordered_ids": [row["id"] for row in ordered],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", default=DEFAULT_REPOSITORY)
    parser.add_argument("--state-dir", type=Path, default=DEFAULT_STATE_DIR)
    args = parser.parse_args()

    state_dir = args.state_dir.expanduser().resolve()
    state_path = state_dir / "support-work-queue.json"
    next_path = state_dir / "next-support-work.json"

    observed_at = now_iso()
    support = parse_open_support(fetch_support_md(args.repository))
    prs = fetch_open_prs(args.repository)
    previous = load_state(state_path)
    queue = derive_queue(
        support_items=support,
        prs=prs,
        previous=previous,
        observed_at=observed_at,
    )
    atomic_json(state_path, queue)

    selected = queue.get("selected_support_id")
    selected_record = (queue.get("items") or {}).get(selected) if selected else None
    atomic_json(
        next_path,
        {
            "schema_version": "1.0",
            "observed_at": observed_at,
            "support_id": selected,
            "work": selected_record,
            "engineering_executor": "not_configured",
        },
    )

    print(f"OPEN_SUPPORT_ITEMS={len(queue['ordered_ids'])}")
    print(f"SELECTED_SUPPORT_ID={selected or 'NONE'}")
    if selected_record:
        print(f"SELECTED_WORK_STATE={selected_record['work_state']}")
    print("ENGINEERING_EXECUTOR=NOT_CONFIGURED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
