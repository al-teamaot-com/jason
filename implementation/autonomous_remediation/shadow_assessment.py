"""Read-only shadow assessment for autonomous queue readiness.

This deliberately does not claim tickets, create notes, execute components, or
perform any provider mutation. It lets production queue data exercise discovery,
priority normalization and playbook matching before unattended activation.
"""

from __future__ import annotations

from dataclasses import dataclass

from .autonomous_queue_worker import PlaybookClassificationPort, QueueCandidate, QueueSourcePort
from .attention_scheduler import AutonomyConfig


@dataclass(frozen=True)
class ShadowAssessmentItem:
    resource_id: str
    source_queue: str
    priority_score: int
    owned_by_jason: bool
    playbook_id: str
    match_state: str
    standing_authority_active: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class ShadowAssessment:
    candidate_count: int
    configured_active_limit: int
    selected_for_attention: tuple[ShadowAssessmentItem, ...]
    all_items: tuple[ShadowAssessmentItem, ...]


class ShadowQueueAssessor:
    def __init__(
        self,
        *,
        config: AutonomyConfig,
        queue_source: QueueSourcePort,
        classifier: PlaybookClassificationPort,
    ) -> None:
        self.config = config
        self.queue_source = queue_source
        self.classifier = classifier

    def assess(self) -> ShadowAssessment:
        candidates = tuple(self.queue_source.reconcile_candidates())
        ordered = sorted(
            candidates,
            key=lambda item: (
                -int(item.urgent),
                -int(item.owned_by_jason),
                -item.priority,
                item.resource_id,
            ),
        )
        assessed = tuple(self._assess_item(candidate) for candidate in ordered)
        return ShadowAssessment(
            candidate_count=len(assessed),
            configured_active_limit=self.config.max_active_work_items,
            selected_for_attention=assessed[: self.config.max_active_work_items],
            all_items=assessed,
        )

    def _assess_item(self, candidate: QueueCandidate) -> ShadowAssessmentItem:
        match = self.classifier.classify(candidate)
        return ShadowAssessmentItem(
            resource_id=candidate.resource_id,
            source_queue=candidate.source_queue,
            priority_score=candidate.priority,
            owned_by_jason=candidate.owned_by_jason,
            playbook_id=match.playbook_id,
            match_state=match.state.value,
            standing_authority_active=match.standing_authority_active,
            reasons=match.reasons,
        )
