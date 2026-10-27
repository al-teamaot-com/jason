#!/usr/bin/env python3
"""Fetch a *public documentation* candidate index, never a provider permission list.

Only operator-invoked snapshot refresh uses the public Internet. This module
neither imports provider credentials nor executes any Autotask API operation.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import html
import json
from pathlib import Path
import re
from urllib.request import Request, urlopen

SOURCE = "https://autotask.net/help/developerhelp/content/apis/rest/Entities/_EntitiesOverview.htm"
_IDENTIFIER = re.compile(r"[A-Za-z][A-Za-z0-9_]+\Z")
_ROWS = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.I | re.S)
_CELLS = re.compile(r"<td\b[^>]*>(.*?)</td>", re.I | re.S)
_TAG = re.compile(r"<[^>]*>", re.S)


def parse_documented_entity_names(document: str) -> list[str]:
    if not isinstance(document, str):
        raise TypeError("public vendor document must be text")
    names = []
    for row in _ROWS.findall(document):
        cells = _CELLS.findall(row)
        if len(cells) != 3:
            continue
        name = html.unescape(_TAG.sub("", cells[0])).strip()
        if _IDENTIFIER.fullmatch(name):
            names.append(name)
    # Detect a truncated/altered public document rather than publishing a bad
    # partial "complete" index. This is a candidate-name gate, not API proof.
    if len(names) < 150:
        raise ValueError("Autotask published index incomplete or changed")
    if not {"Tickets", "TimeEntries", "Projects", "Contacts"}.issubset(names):
        raise ValueError("required Autotask index anchors missing")
    return sorted(set(names))


def main() -> int:
    argp = argparse.ArgumentParser()
    argp.add_argument("--output", type=Path, required=True)
    args = argp.parse_args()
    req = Request(SOURCE, headers={"User-Agent": "Jason-Documentation-Inventory/1.0"})
    with urlopen(req, timeout=20) as response:
        raw = response.read(2_500_001)
        if len(raw) > 2_500_000:
            raise ValueError("public index larger than review bound")
        page = raw.decode("utf-8")
    names = parse_documented_entity_names(page)
    result = {
        "schema_version": "1.0",
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_url": SOURCE,
        "entity_count": len(names),
        "entity_names": names,
        "note": "Public documentation candidate names only; NOT proof of provider queryability, AOT API-user authorization, or Jason read/release permissions.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"PUBLIC_AUTOTASK_ENTITY_CANDIDATES={len(names)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
