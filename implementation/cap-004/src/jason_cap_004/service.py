from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from .models import AttentionItem, OperationalBriefing, OperationalSignal


_SEVERITY_SCORE = {
    "info": 0,
    "low": 10,
    "medium": 30,
    "high": 60,
    "critical": 100,
}


class OperationalBriefingService:
    """Aggregate provider-neutral signals into a bounded attention briefing."""

    capability_name = "operations.attention.briefing"

    def build(
        self,
        *,
        organization_id: str,
        signals: Iterable[OperationalSignal],
        item_limit: int = 10,
    ) -> OperationalBriefing:
        organization_id = organization_id.strip()
        if not organization_id:
            raise ValueError("organization_id must be non-empty")
        if not 1 <= item_limit <= 50:
            raise ValueError("item_limit must be between 1 and 50")

        accepted: list[OperationalSignal] = []
        for signal in signals:
            if signal.organization_id != organization_id:
                raise ValueError("signal organization boundary mismatch")
            accepted.append(signal)

        groups: dict[tuple[str, str], list[OperationalSignal]] = defaultdict(list)
        for signal in accepted:
            groups[(signal.subject_type, signal.subject_id)].append(signal)

        ranked: list[tuple[int, str, str, list[OperationalSignal]]] = []
        for (subject_type, subject_id), group in groups.items():
            severity_points = max(_SEVERITY_SCORE[s.severity] for s in group)
            corroboration_points = min(20, max(0, len({s.source_provider for s in group}) - 1) * 10)
            volume_points = min(15, max(0, len(group) - 1) * 3)
            score = severity_points + corroboration_points + volume_points
            ranked.append((score, subject_type, subject_id, group))

        ranked.sort(key=lambda row: (-row[0], row[1], row[2]))

        items: list[AttentionItem] = []
        for rank, (score, subject_type, subject_id, group) in enumerate(
            ranked[:item_limit], start=1
        ):
            highest = max(group, key=lambda s: _SEVERITY_SCORE[s.severity]).severity
            name = sorted({s.subject_name for s in group})[0]
            providers = tuple(sorted({s.source_provider for s in group}))
            categories = tuple(sorted({s.category for s in group}))
            summaries = tuple(dict.fromkeys(s.summary for s in group))[:5]
            actions = tuple(
                dict.fromkeys(
                    s.recommended_action
                    for s in group
                    if s.recommended_action
                )
            )[:5]
            evidence = tuple(
                dict.fromkeys(
                    s.evidence_reference
                    for s in group
                    if s.evidence_reference
                )
            )[:10]
            items.append(
                AttentionItem(
                    rank=rank,
                    priority_score=score,
                    subject_type=subject_type,
                    subject_id=subject_id,
                    subject_name=name,
                    highest_severity=highest,
                    signal_count=len(group),
                    providers=providers,
                    categories=categories,
                    summaries=summaries,
                    recommended_actions=actions,
                    evidence_references=evidence,
                )
            )

        return OperationalBriefing(
            organization_id=organization_id,
            generated_from_signal_count=len(accepted),
            attention_items=tuple(items),
        )
