"""Autonomous Support/TODO tracking for Project Jason conversations."""
from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path


def _norm(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(text).casefold()))


def _next_id(text: str, prefix: str) -> str:
    nums = [int(x) for x in re.findall(rf"{re.escape(prefix)}-(?:CAP|REQ)-(\d+)", text)]
    return f"{prefix}-{'CAP' if prefix == 'SUPPORT' else 'REQ'}-{(max(nums) + 1 if nums else 1):03d}"


def _titles(text: str) -> list[tuple[str, str]]:
    out = []
    for line in text.splitlines():
        m = re.match(r"^###\s+((?:SUPPORT|TODO)-[^\s]+)\s+—\s+(.+)$", line.strip())
        if m:
            out.append((m.group(1), m.group(2)))
            continue
        if line.startswith("| SUPPORT-"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) >= 4:
                out.append((cells[0], cells[3]))
    return out


@dataclass(frozen=True, slots=True)
class WorkItemResult:
    item_id: str
    list_name: str
    created: bool
    title: str

    @property
    def user_notice(self) -> str:
        if self.created:
            return f"I added {self.item_id} to the {self.list_name} list."
        return f"This is already tracked as {self.item_id} on the {self.list_name} list."


@dataclass(slots=True)
class AutomaticWorkItemTracker:
    support_path: Path
    todo_path: Path
    similarity_threshold: float = 0.78

    def record_support(self, *, title: str, summary: str, evidence: str = "", acceptance: str = "") -> WorkItemResult:
        return self._record(
            path=self.support_path,
            list_name="Support",
            prefix="SUPPORT",
            title=title,
            body=(
                f"\n| {{id}} | P1 | Open — automatically recorded | {title.strip()} | "
                f"{(evidence or summary).strip().replace('|', '/')} | "
                f"{(acceptance or 'Restore the expected governed workflow and verify it with authoritative readback.').strip().replace('|', '/')} |\n"
            ),
        )

    def record_todo(self, *, title: str, summary: str, why_it_matters: str = "") -> WorkItemResult:
        return self._record(
            path=self.todo_path,
            list_name="To Do",
            prefix="TODO",
            title=title,
            body=(
                "\n### {id} — " + title.strip() + "\n\n"
                "- **Priority:** P2\n"
                "- **Status:** Proposed\n"
                "- **Risk level:** Moderate\n"
                "- **Idea:** " + summary.strip() + "\n"
                "- **Why it matters:** " + (why_it_matters or summary).strip() + "\n"
                "- **Why not now:** Jason does not currently expose or implement this governed capability.\n"
                "- **Prerequisites:** Define the provider-neutral capability, governance, evidence, tests, and acceptance criteria.\n"
                "- **Decision owner:** Jason Governance Authority\n"
                "- **Review trigger:** Reconsider when requested again or when adjacent capabilities are being implemented.\n"
            ),
        )

    def _record(self, *, path: Path, list_name: str, prefix: str, title: str, body: str) -> WorkItemResult:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            if prefix == "SUPPORT":
                path.write_text("# Project Jason Support List\n\n| ID | Priority | Status | Item | Current blocker / evidence | Acceptance criteria |\n| --- | --- | --- | --- | --- | --- |\n", encoding="utf-8")
            else:
                path.write_text("# Project Jason TODO and Future Ideas\n", encoding="utf-8")
        text = path.read_text(encoding="utf-8")
        normalized = _norm(title)
        best: tuple[float, str, str, str] | None = None
        sources = (
            (Path(self.support_path), "Support"),
            (Path(self.todo_path), "To Do"),
        )
        for candidate_path, candidate_list_name in sources:
            if not candidate_path.exists():
                continue
            candidate_text = candidate_path.read_text(encoding="utf-8")
            for item_id, existing_title in _titles(candidate_text):
                score = SequenceMatcher(None, normalized, _norm(existing_title)).ratio()
                if best is None or score > best[0]:
                    best = (score, item_id, existing_title, candidate_list_name)
        if best is not None and best[0] >= self.similarity_threshold:
            return WorkItemResult(best[1], best[3], False, best[2])

        item_id = _next_id(text, prefix)
        rendered = body.format(id=item_id)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(rendered)
        return WorkItemResult(item_id, list_name, True, title.strip())
