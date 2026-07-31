from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Iterable

from .contracts import (
    DecisionMemoryRecord,
    MatchDisposition,
    MemoryClass,
    MemoryMatch,
    MemoryStatus,
    NormalizedFacts,
)


def stable_fingerprint(facts: NormalizedFacts) -> str:
    canonical = json.dumps(
        dict(sorted(facts.fingerprint_fields().items())),
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class DecisionMemoryStore:
    """In-memory reference implementation; replace with an append-audited database adapter."""

    def __init__(self) -> None:
        self._records: dict[str, DecisionMemoryRecord] = {}

    def add(self, record: DecisionMemoryRecord) -> None:
        if record.memory_id in self._records:
            raise ValueError(f"memory record already exists: {record.memory_id}")
        self._records[record.memory_id] = record

    def get(self, memory_id: str) -> DecisionMemoryRecord:
        return self._records[memory_id]

    def records(self) -> Iterable[DecisionMemoryRecord]:
        return tuple(self._records.values())

    def record_outcome(self, memory_id: str, succeeded: bool, ticket_id: str) -> None:
        record = self.get(memory_id)
        if ticket_id not in record.source_ticket_ids:
            record.source_ticket_ids.append(ticket_id)
        if succeeded:
            record.success_count += 1
            record.consecutive_failures = 0
            record.last_verified_at = datetime.now(timezone.utc)
        else:
            record.failure_count += 1
            record.consecutive_failures += 1
            if record.consecutive_failures >= 2:
                record.status = MemoryStatus.SUSPENDED
                record.invalidation_reason = "automatically suspended after consecutive failures"


class DecisionMemoryMatcher:
    def __init__(
        self,
        minimum_reuse_successes: int = 3,
        minimum_reuse_rate: float = 0.90,
        review_threshold: float = 0.75,
    ) -> None:
        self.minimum_reuse_successes = minimum_reuse_successes
        self.minimum_reuse_rate = minimum_reuse_rate
        self.review_threshold = review_threshold

    def match(
        self,
        facts: NormalizedFacts,
        records: Iterable[DecisionMemoryRecord],
        now: datetime | None = None,
    ) -> list[MemoryMatch]:
        now = now or datetime.now(timezone.utc)
        fingerprint = stable_fingerprint(facts)
        results: list[MemoryMatch] = []

        for record in records:
            reasons: list[str] = []
            if record.organization_scope != facts.organization_id:
                continue
            if record.client_scope is not None and record.client_scope != facts.client_id:
                continue
            if not record.is_current(now):
                continue

            fields = facts.fingerprint_fields()
            if self._is_excluded(fields, record):
                continue
            if not self._required_match(fields, record):
                continue
            if not self._allowed_match(fields, record):
                continue

            score = self._score(fields, fingerprint, record, reasons)
            disposition = MatchDisposition.REJECT

            trusted = (
                record.success_count >= self.minimum_reuse_successes
                and record.success_rate >= self.minimum_reuse_rate
            )
            if record.memory_class is MemoryClass.SIMILAR_CASE:
                disposition = MatchDisposition.REVIEW
                reasons.append("similar cases are evidence only")
            elif score == 1.0 and trusted:
                disposition = MatchDisposition.REUSE
                reasons.append("current verified record meets reuse threshold")
            elif score >= self.review_threshold:
                disposition = MatchDisposition.REVIEW
                reasons.append("partial or insufficiently proven match requires review")
            else:
                reasons.append("match score below review threshold")

            results.append(
                MemoryMatch(
                    memory_id=record.memory_id,
                    disposition=disposition,
                    score=score,
                    reasons=tuple(reasons),
                    decision=record.decision if disposition is not MatchDisposition.REJECT else None,
                    approved_capability=(
                        record.approved_capability
                        if disposition is MatchDisposition.REUSE
                        else None
                    ),
                )
            )

        return sorted(results, key=lambda item: item.score, reverse=True)

    @staticmethod
    def _required_match(fields: dict[str, str], record: DecisionMemoryRecord) -> bool:
        return all(fields.get(key) == value for key, value in record.applicability.required.items())

    @staticmethod
    def _allowed_match(fields: dict[str, str], record: DecisionMemoryRecord) -> bool:
        return all(
            key not in fields or fields[key] in allowed
            for key, allowed in record.applicability.allowed_values.items()
        )

    @staticmethod
    def _is_excluded(fields: dict[str, str], record: DecisionMemoryRecord) -> bool:
        return any(fields.get(key) in values for key, values in record.applicability.excluded.items())

    @staticmethod
    def _score(
        fields: dict[str, str],
        fingerprint: str,
        record: DecisionMemoryRecord,
        reasons: list[str],
    ) -> float:
        if record.memory_class is MemoryClass.EXACT:
            if record.fingerprint == fingerprint:
                reasons.append("exact normalized fingerprint matched")
                return 1.0
            reasons.append("exact fingerprint did not match")
            return 0.0

        required = record.applicability.required
        allowed = record.applicability.allowed_values
        total = len(required) + len(allowed)
        if total == 0:
            return 0.0
        matched = sum(fields.get(k) == v for k, v in required.items())
        matched += sum(fields.get(k) in values for k, values in allowed.items())
        return matched / total
