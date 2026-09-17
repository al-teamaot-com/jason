from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import math
import re
from typing import Iterable, Mapping, Sequence


class ResolutionCaseStatus(str, Enum):
    OBSERVED = "observed"
    VERIFIED = "verified"
    DEPRECATED = "deprecated"


class ResolutionOutcome(str, Enum):
    RESOLVED = "resolved"
    IMPROVED = "improved"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"


class ResolutionStepKind(str, Enum):
    DIAGNOSTIC = "diagnostic"
    REMEDIATION = "remediation"
    VERIFICATION = "verification"
    COMMUNICATION = "communication"


@dataclass(frozen=True, slots=True)
class ResolutionSourceReference:
    source_type: str
    source_id: str
    correlation_id: str | None = None

    def validate(self) -> None:
        if not self.source_type.strip() or not self.source_id.strip():
            raise ValueError("resolution source reference must be non-empty")


@dataclass(frozen=True, slots=True)
class ResolutionSignature:
    category: str
    product: str
    device_role: str
    platform: str
    product_version: str = ""
    symptoms: tuple[str, ...] = ()
    attributes: Mapping[str, str] = field(default_factory=dict)

    def normalized(self) -> "ResolutionSignature":
        return ResolutionSignature(
            category=_normalize_atom(self.category),
            product=_normalize_atom(self.product),
            device_role=_normalize_atom(self.device_role),
            platform=_normalize_atom(self.platform),
            product_version=_normalize_atom(self.product_version),
            symptoms=tuple(
                sorted(
                    {
                        _normalize_atom(value)
                        for value in self.symptoms
                        if _normalize_atom(value)
                    }
                )
            ),
            attributes={
                _normalize_atom(str(key)): _normalize_atom(str(value))
                for key, value in sorted(self.attributes.items())
                if _normalize_atom(str(key))
            },
        )


@dataclass(frozen=True, slots=True)
class ResolutionStep:
    step_id: str
    ordinal: int
    kind: ResolutionStepKind
    action_key: str
    action_summary: str
    outcome: ResolutionOutcome
    evidence_summary: str = ""
    read_only: bool = False
    approval_required: bool = False
    disruptive: bool = False

    def validate(self) -> None:
        if not self.step_id.strip():
            raise ValueError("resolution step_id must be non-empty")
        if self.ordinal < 1:
            raise ValueError("resolution step ordinal must be positive")
        if not self.action_key.strip() or not self.action_summary.strip():
            raise ValueError("resolution step action must be non-empty")
        if self.read_only and (self.approval_required or self.disruptive):
            raise ValueError(
                "read-only resolution steps cannot be marked approval-required or disruptive"
            )


@dataclass(frozen=True, slots=True)
class ResolutionCase:
    case_id: str
    organization_id: str
    client_id: str
    signature: ResolutionSignature
    source_references: tuple[ResolutionSourceReference, ...]
    steps: tuple[ResolutionStep, ...]
    root_cause: str
    final_resolution: str
    outcome: ResolutionOutcome
    status: ResolutionCaseStatus
    technician_confirmed: bool
    recorded_at: datetime
    resolved_at: datetime | None = None
    owner: str = ""

    def validate(self) -> None:
        for value, name in (
            (self.case_id, "case_id"),
            (self.organization_id, "organization_id"),
            (self.client_id, "client_id"),
        ):
            if not value.strip():
                raise ValueError(f"resolution {name} must be non-empty")
        if self.recorded_at.tzinfo is None:
            raise ValueError("recorded_at must be timezone-aware")
        if self.resolved_at is not None and self.resolved_at.tzinfo is None:
            raise ValueError("resolved_at must be timezone-aware")
        for reference in self.source_references:
            reference.validate()
        seen: set[str] = set()
        last_ordinal = 0
        for step in sorted(self.steps, key=lambda item: item.ordinal):
            step.validate()
            if step.step_id in seen:
                raise ValueError("duplicate resolution step_id")
            if step.ordinal <= last_ordinal:
                raise ValueError("resolution step ordinals must be unique")
            seen.add(step.step_id)
            last_ordinal = step.ordinal


@dataclass(frozen=True, slots=True)
class SimilarResolutionCase:
    case_id: str
    score: float
    similarity: float
    recency_factor: float
    outcome_factor: float
    reasons: tuple[str, ...]
    root_cause: str
    final_resolution: str
    outcome: ResolutionOutcome
    technician_confirmed: bool
    steps: tuple[ResolutionStep, ...]
    evidence_only: bool = True
    grants_authority: bool = False


@dataclass(frozen=True, slots=True)
class ResolutionStepEvidence:
    action_key: str
    action_summary: str
    kind: ResolutionStepKind
    attempts: int
    successes: int
    failures: int
    weighted_success: float
    weighted_failure: float
    confidence: float
    read_only: bool
    approval_required: bool
    disruptive: bool
    disposition: str
    supporting_case_ids: tuple[str, ...]
    grants_authority: bool = False


@dataclass(frozen=True, slots=True)
class ResolutionSearchResult:
    matches: tuple[SimilarResolutionCase, ...]
    step_evidence: tuple[ResolutionStepEvidence, ...]
    grants_authority: bool = False


class ResolutionMemoryMatcher:
    """Deterministic case similarity and historical step evidence ranking.

    Resolution memory is evidence only. It deliberately contains no execution
    authority and never changes the current approval classification of an action.
    """

    def __init__(
        self,
        *,
        minimum_similarity: float = 0.45,
        maximum_age_days: int = 365,
    ) -> None:
        if not 0.0 <= minimum_similarity <= 1.0:
            raise ValueError("minimum_similarity must be between zero and one")
        if maximum_age_days < 1:
            raise ValueError("maximum_age_days must be positive")
        self.minimum_similarity = minimum_similarity
        self.maximum_age_days = maximum_age_days

    def search(
        self,
        *,
        signature: ResolutionSignature,
        organization_id: str,
        client_id: str,
        cases: Iterable[ResolutionCase],
        now: datetime | None = None,
        limit: int = 10,
    ) -> ResolutionSearchResult:
        if not organization_id.strip() or not client_id.strip():
            raise ValueError("organization_id and client_id must be non-empty")
        if limit < 1 or limit > 100:
            raise ValueError("limit must be between 1 and 100")

        now = now or datetime.now(timezone.utc)
        query = signature.normalized()
        matches: list[SimilarResolutionCase] = []

        for case in cases:
            case.validate()
            if case.organization_id != organization_id:
                continue
            # Similar cases remain client-isolated. Cross-client learning belongs
            # in separately reviewed pattern memory, never raw historical cases.
            if case.client_id != client_id:
                continue
            if case.status is ResolutionCaseStatus.DEPRECATED:
                continue

            age_days = max(
                0.0,
                (now - (case.resolved_at or case.recorded_at)).total_seconds()
                / 86400.0,
            )
            if age_days > self.maximum_age_days:
                continue

            similarity, reasons = self._similarity(query, case.signature.normalized())
            if similarity < self.minimum_similarity:
                continue

            recency_factor = max(0.25, math.exp(-age_days / 240.0))
            outcome_factor = self._outcome_factor(case)
            score = similarity * recency_factor * outcome_factor

            matches.append(
                SimilarResolutionCase(
                    case_id=case.case_id,
                    score=round(score, 6),
                    similarity=round(similarity, 6),
                    recency_factor=round(recency_factor, 6),
                    outcome_factor=round(outcome_factor, 6),
                    reasons=tuple(reasons),
                    root_cause=case.root_cause,
                    final_resolution=case.final_resolution,
                    outcome=case.outcome,
                    technician_confirmed=case.technician_confirmed,
                    steps=tuple(sorted(case.steps, key=lambda item: item.ordinal)),
                )
            )

        matches.sort(key=lambda item: (item.score, item.similarity), reverse=True)
        bounded = tuple(matches[:limit])
        return ResolutionSearchResult(
            matches=bounded,
            step_evidence=self._aggregate_steps(bounded),
        )

    @staticmethod
    def _similarity(
        query: ResolutionSignature,
        candidate: ResolutionSignature,
    ) -> tuple[float, list[str]]:
        score = 0.0
        reasons: list[str] = []

        weighted_exact = (
            ("category", query.category, candidate.category, 0.25),
            ("product", query.product, candidate.product, 0.20),
            ("device_role", query.device_role, candidate.device_role, 0.10),
            ("platform", query.platform, candidate.platform, 0.10),
            (
                "product_version",
                query.product_version,
                candidate.product_version,
                0.05,
            ),
        )
        for name, left, right, weight in weighted_exact:
            if left and right and left == right:
                score += weight
                reasons.append(f"{name} matched")

        query_symptoms = set(query.symptoms)
        candidate_symptoms = set(candidate.symptoms)
        if query_symptoms or candidate_symptoms:
            union = query_symptoms | candidate_symptoms
            overlap = query_symptoms & candidate_symptoms
            symptom_score = len(overlap) / len(union) if union else 0.0
            score += 0.20 * symptom_score
            if overlap:
                reasons.append(
                    "symptom overlap: " + ", ".join(sorted(overlap))
                )

        keys = set(query.attributes) | set(candidate.attributes)
        if keys:
            matched = sum(
                1
                for key in keys
                if key in query.attributes
                and key in candidate.attributes
                and query.attributes[key] == candidate.attributes[key]
            )
            attribute_score = matched / len(keys)
            score += 0.10 * attribute_score
            if matched:
                reasons.append(f"{matched} normalized attributes matched")

        return min(score, 1.0), reasons

    @staticmethod
    def _outcome_factor(case: ResolutionCase) -> float:
        factor = {
            ResolutionOutcome.RESOLVED: 1.0,
            ResolutionOutcome.IMPROVED: 0.80,
            ResolutionOutcome.INCONCLUSIVE: 0.55,
            ResolutionOutcome.FAILED: 0.35,
        }[case.outcome]
        if case.technician_confirmed:
            factor = min(1.0, factor + 0.10)
        if case.status is ResolutionCaseStatus.OBSERVED:
            factor *= 0.85
        return factor

    @staticmethod
    def _aggregate_steps(
        matches: Sequence[SimilarResolutionCase],
    ) -> tuple[ResolutionStepEvidence, ...]:
        buckets: dict[str, dict[str, object]] = {}

        for match in matches:
            case_weight = max(match.score, 0.01)
            for step in match.steps:
                key = _normalize_atom(step.action_key)
                bucket = buckets.setdefault(
                    key,
                    {
                        "summary": step.action_summary,
                        "kind": step.kind,
                        "attempts": 0,
                        "successes": 0,
                        "failures": 0,
                        "weighted_success": 0.0,
                        "weighted_failure": 0.0,
                        "read_only": True,
                        "approval_required": False,
                        "disruptive": False,
                        "case_ids": set(),
                    },
                )
                bucket["attempts"] = int(bucket["attempts"]) + 1
                bucket["read_only"] = bool(bucket["read_only"]) and step.read_only
                bucket["approval_required"] = bool(bucket["approval_required"]) or step.approval_required
                bucket["disruptive"] = bool(bucket["disruptive"]) or step.disruptive
                case_ids = bucket["case_ids"]
                assert isinstance(case_ids, set)
                case_ids.add(match.case_id)

                if step.outcome in {
                    ResolutionOutcome.RESOLVED,
                    ResolutionOutcome.IMPROVED,
                }:
                    bucket["successes"] = int(bucket["successes"]) + 1
                    bucket["weighted_success"] = float(bucket["weighted_success"]) + case_weight
                elif step.outcome is ResolutionOutcome.FAILED:
                    bucket["failures"] = int(bucket["failures"]) + 1
                    bucket["weighted_failure"] = float(bucket["weighted_failure"]) + case_weight

        evidence: list[ResolutionStepEvidence] = []
        for action_key, bucket in buckets.items():
            weighted_success = float(bucket["weighted_success"])
            weighted_failure = float(bucket["weighted_failure"])
            # Beta(1,1) prior prevents a single historical success becoming truth.
            confidence = (weighted_success + 1.0) / (
                weighted_success + weighted_failure + 2.0
            )
            attempts = int(bucket["attempts"])
            failures = int(bucket["failures"])
            successes = int(bucket["successes"])

            if attempts >= 2 and failures > successes:
                disposition = "historically_unreliable"
            elif successes >= 2 and confidence >= 0.60:
                disposition = "historically_supported"
            else:
                disposition = "insufficient_history"

            case_ids = bucket["case_ids"]
            assert isinstance(case_ids, set)
            evidence.append(
                ResolutionStepEvidence(
                    action_key=action_key,
                    action_summary=str(bucket["summary"]),
                    kind=bucket["kind"],  # type: ignore[arg-type]
                    attempts=attempts,
                    successes=successes,
                    failures=failures,
                    weighted_success=round(weighted_success, 6),
                    weighted_failure=round(weighted_failure, 6),
                    confidence=round(confidence, 6),
                    read_only=bool(bucket["read_only"]),
                    approval_required=bool(bucket["approval_required"]),
                    disruptive=bool(bucket["disruptive"]),
                    disposition=disposition,
                    supporting_case_ids=tuple(sorted(case_ids)),
                )
            )

        # Prefer historically supported read-only evidence first, then higher
        # confidence. This is ordering evidence only, not action authorization.
        rank = {
            "historically_supported": 0,
            "insufficient_history": 1,
            "historically_unreliable": 2,
        }
        evidence.sort(
            key=lambda item: (
                rank[item.disposition],
                not item.read_only,
                -item.confidence,
                -item.attempts,
                item.action_key,
            )
        )
        return tuple(evidence)


def _normalize_atom(value: str) -> str:
    return " ".join(
        token
        for token in re.split(r"[^a-z0-9._:+-]+", value.strip().casefold())
        if token
    )
