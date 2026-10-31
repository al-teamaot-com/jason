from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from .store import PMV2Store

HEADING = re.compile(r"^###\s+(TODO-[A-Z]+-\d+)\s+—\s+(.+?)\s*$")
FIELD = re.compile(r"^-\s+\*\*(.+?):\*\*\s*(.*?)\s*$")
PRIORITY = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}


@dataclass(frozen=True, slots=True)
class RoadmapItem:
    item_id: str
    title: str
    priority: str
    status: str
    readiness: str
    section: str

    @property
    def autonomous_authority(self) -> bool:
        return (
            self.status.casefold().startswith("approved for autonomous engineering")
            and self.readiness.casefold().startswith("approved")
        )


def parse_roadmap(text: str) -> list[RoadmapItem]:
    lines = text.splitlines()
    heads = [(i, m) for i, line in enumerate(lines) if (m := HEADING.match(line))]
    result: list[RoadmapItem] = []
    for pos, (start, match) in enumerate(heads):
        end = heads[pos + 1][0] if pos + 1 < len(heads) else len(lines)
        section_lines = lines[start:end]
        fields: dict[str, str] = {}
        for line in section_lines[1:]:
            field = FIELD.match(line)
            if field:
                fields[field.group(1).strip().casefold()] = field.group(2).strip()
        result.append(RoadmapItem(
            item_id=match.group(1),
            title=match.group(2).strip(),
            priority=fields.get("priority", "P3"),
            status=fields.get("status", "Proposed"),
            readiness=fields.get("autonomous engineering readiness", ""),
            section="\n".join(section_lines).strip(),
        ))
    return result


def reconcile_roadmap(store: PMV2Store, path: Path) -> dict[str, int]:
    items = parse_roadmap(path.read_text(encoding="utf-8"))
    runnable = proposals = 0
    for item in items:
        allowed = item.autonomous_authority
        runnable += int(allowed)
        proposals += int(not allowed)
        scope_hash = "sha256:" + hashlib.sha256(item.section.encode("utf-8")).hexdigest()
        store.upsert_assignment(
            assignment_id=f"roadmap:{item.item_id}",
            source="roadmap",
            source_ref=item.item_id,
            title=item.title,
            priority=PRIORITY.get(item.priority, 99),
            work_type="development",
            runnable=allowed,
            scope_hash=scope_hash,
            metadata={
                "priority": item.priority,
                "status": item.status,
                "readiness": item.readiness,
                "authority": "owner_approved_todo" if allowed else "idea_only",
            },
            blocked_reason=None if allowed else "not_approved_for_autonomous_engineering",
        )
    return {"items": len(items), "runnable": runnable, "proposal_only": proposals}
