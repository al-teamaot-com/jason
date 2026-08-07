from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


Severity = Literal["info", "low", "medium", "high", "critical"]


@dataclass(frozen=True, slots=True)
class OperationalSignal:
    """Provider-neutral fact or concern that may deserve operator attention."""

    source_provider: str
    organization_id: str
    subject_type: str
    subject_id: str
    subject_name: str
    category: str
    severity: Severity
    summary: str
    recommended_action: str | None = None
    evidence_reference: str | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "source_provider",
            "organization_id",
            "subject_type",
            "subject_id",
            "subject_name",
            "category",
            "summary",
        ):
            if not str(getattr(self, field_name)).strip():
                raise ValueError(f"{field_name} must be non-empty")
        if self.severity not in {"info", "low", "medium", "high", "critical"}:
            raise ValueError(f"Unsupported severity: {self.severity}")


@dataclass(frozen=True, slots=True)
class AttentionItem:
    rank: int
    priority_score: int
    subject_type: str
    subject_id: str
    subject_name: str
    highest_severity: Severity
    signal_count: int
    providers: tuple[str, ...]
    categories: tuple[str, ...]
    summaries: tuple[str, ...]
    recommended_actions: tuple[str, ...]
    evidence_references: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class OperationalBriefing:
    organization_id: str
    generated_from_signal_count: int
    attention_items: tuple[AttentionItem, ...]
