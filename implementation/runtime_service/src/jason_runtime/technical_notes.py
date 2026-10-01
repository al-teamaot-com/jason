"""Canonical technician-facing note format for Project Jason.

The renderer keeps technician information in the same location across playbooks.
It also provides a compatibility adapter for existing narrative note producers so
legacy evidence is preserved while the runtime migrates to fully structured notes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Sequence

SECTION_ORDER = (
    "STATUS",
    "ISSUE",
    "DEVICE / SCOPE",
    "FINDINGS",
    "EVIDENCE",
    "ACTIONS TAKEN",
    "VERIFICATION",
    "NEXT ACTION",
    "JASON STATE",
)

CANONICAL_TITLES = {
    "technical_review": "Jason - Technical Review",
    "work_update": "Jason - Work Update",
    "remediation_result": "Jason - Remediation Result",
    "waiting": "Jason - Waiting State",
    "human_review": "Jason - Human Review Required",
    "resolution": "Jason - Resolution",
}

@dataclass(frozen=True)
class TechnicalNote:
    kind: str
    status: str
    issue: str
    scope: Sequence[str]
    findings: Sequence[str]
    evidence: Sequence[str]
    actions_taken: Sequence[str]
    verification: Sequence[str]
    next_action: str
    jason_state: Sequence[str]


def _clean(value: object) -> str:
    return " ".join(str(value or "").split()).strip()


def _bullets(values: Iterable[object], *, empty: str) -> list[str]:
    result = [f"- {_clean(value)}" for value in values if _clean(value)]
    return result or [f"- {empty}"]


def canonical_title(kind: str) -> str:
    normalized = _clean(kind).casefold().replace("-", "_").replace(" ", "_")
    return CANONICAL_TITLES.get(normalized, CANONICAL_TITLES["work_update"])


def render_technical_note(note: TechnicalNote) -> str:
    sections: list[tuple[str, list[str]]] = [
        ("STATUS", [_clean(note.status) or "Updated"]),
        ("ISSUE", [_clean(note.issue) or "See ticket title."]),
        ("DEVICE / SCOPE", _bullets(note.scope, empty="No device scope recorded.")),
        ("FINDINGS", _bullets(note.findings, empty="No additional findings recorded.")),
        ("EVIDENCE", _bullets(note.evidence, empty="No additional evidence recorded.")),
        ("ACTIONS TAKEN", _bullets(note.actions_taken, empty="No modifying action recorded.")),
        ("VERIFICATION", _bullets(note.verification, empty="No additional verification recorded.")),
        ("NEXT ACTION", [_clean(note.next_action) or "No next action recorded."]),
        ("JASON STATE", _bullets(note.jason_state, empty="No Jason state recorded.")),
    ]
    lines: list[str] = []
    for heading, content in sections:
        lines.append(f"{heading}:")
        lines.extend(content)
        lines.append("")
    return "\n".join(lines).rstrip()


def infer_kind(title: str) -> str:
    material = _clean(title).casefold()
    if "human review" in material or "escalation" in material:
        return "human_review"
    if "waiting" in material:
        return "waiting"
    if "resolution" in material or "complete" in material:
        return "resolution"
    if "verification" in material or "remediation" in material:
        return "remediation_result"
    if "diagnostic" in material or "review" in material:
        return "technical_review"
    return "work_update"


def infer_status(title: str, body: str) -> str:
    material = f"{_clean(title)} {_clean(body)}".casefold()
    if "human review" in material:
        return "Human Review Required"
    if "waiting" in material:
        return "Waiting"
    if "blocked" in material:
        return "Blocked"
    if "resolution" in material or "verified healthy" in material:
        return "Resolved / Verified"
    if "verification" in material:
        return "Verification Complete"
    if "diagnostic" in material:
        return "Diagnostic Complete"
    return "Updated"


def extract_next_action(body: str, *, kind: str) -> str:
    text = str(body or "")
    match = re.search(
        r"NEXT\s+(?:STEP|ACTION)\s*:\s*(.+?)(?=(?:\s+[A-Z][A-Z /-]{2,}:)|$)",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if match:
        return _clean(match.group(1))
    if kind == "human_review":
        return "Technician review is required before Jason can continue safely."
    if kind == "waiting":
        return "Jason will recheck the documented dependency automatically according to the playbook cadence."
    if kind == "resolution":
        return "None. Resolution is documented and verified."
    return "Continue according to the current Jason lifecycle state documented below."


def extract_evidence(body: str) -> list[str]:
    text = _clean(body)
    evidence: list[str] = []
    summary = re.search(r"Evidence summary:\s*(.+?)(?:\.\s|$)", text, flags=re.IGNORECASE)
    if summary:
        evidence.append(_clean(summary.group(1)))
    verification = re.search(r"Verification:\s*(.+?)(?:\.\s|$)", text, flags=re.IGNORECASE)
    if verification:
        evidence.append(_clean(verification.group(1)))
    for token in re.findall(r"\b[A-Za-z][A-Za-z0-9/_ -]{1,32}=[^;.]+", text):
        item = _clean(token)
        if item and item not in evidence:
            evidence.append(item)
        if len(evidence) >= 8:
            break
    return evidence


def legacy_technical_note(
    *,
    title: str,
    body: str,
    issue: str,
    scope: Sequence[str],
    playbook: str,
    phase: str,
    reason: str,
) -> TechnicalNote:
    kind = infer_kind(title)
    normalized_phase = _clean(phase).casefold()
    normalized_reason = _clean(reason).casefold()
    if normalized_phase == "escalated" or "human review" in normalized_reason or "technician review" in normalized_reason:
        kind = "human_review"
    elif normalized_phase.startswith("waiting_"):
        kind = "waiting"
    elif normalized_phase == "complete":
        kind = "resolution"

    status = infer_status(title, body)
    if kind == "human_review":
        status = "Human Review Required"
    elif kind == "waiting":
        status = "Waiting"
    elif kind == "resolution":
        status = "Resolved / Verified"

    actions: list[str] = []
    for sentence in re.split(r"(?<=[.!?])\s+", _clean(body)):
        lower = sentence.casefold()
        if any(token in lower for token in ("no ", "attempted", "was run", "was used", "resolved")):
            actions.append(sentence)
        if len(actions) >= 6:
            break
    verification = extract_evidence(body)
    findings = [_clean(body)] if _clean(body) else []
    state = [f"Playbook={_clean(playbook) or 'unknown'}", f"Phase={_clean(phase) or 'unknown'}"]
    if _clean(reason):
        state.append(f"Reason={_clean(reason)}")
    return TechnicalNote(
        kind=kind,
        status=status,
        issue=issue,
        scope=scope,
        findings=findings,
        evidence=extract_evidence(body),
        actions_taken=actions,
        verification=verification,
        next_action=extract_next_action(body, kind=kind),
        jason_state=state,
    )
