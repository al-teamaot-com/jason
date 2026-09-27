from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import math
import re
from typing import Iterable, Mapping

from .resolution_memory import (
    ResolutionCase,
    ResolutionCaseStatus,
    ResolutionMemoryMatcher,
    ResolutionOutcome,
    ResolutionSignature,
)

_SAFE_ATTRIBUTE_KEYS = frozenset(
    {
        "architecture",
        "component",
        "device_class",
        "edition",
        "feature",
        "hardware_class",
        "join_type",
        "os_build",
        "role",
        "service",
    }
)
_FORBIDDEN_FIELD_FRAGMENTS = (
    "client",
    "company",
    "customer",
    "ticket",
    "hostname",
    "host_name",
    "computer",
    "device_id",
    "asset",
    "serial",
    "ip",
    "email",
    "user",
    "domain",
    "tenant",
    "provider_id",
    "record_id",
    "configuration_item",
    "ci_id",
)
_EMAIL_RE = re.compile(r"\b[^\s@]+@[^\s@]+\.[a-z]{2,}\b", re.I)
_IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_TICKET_RE = re.compile(r"\b(?:t\d{8}\.\d+|ticket[-_ ]?\d+|inc[-_ ]?\d+)\b", re.I)
_DOMAIN_RE = re.compile(r"\b[a-z0-9-]+\.(?:com|net|org|local|lan|internal|co|io)\b", re.I)
_HOSTISH_RE = re.compile(r"\b(?=[a-z0-9-]{5,}\b)(?=[a-z0-9-]*[a-z])(?=[a-z0-9-]*\d)[a-z0-9]+(?:-[a-z0-9]+)+\b", re.I)


@dataclass(frozen=True, slots=True)
class PatternStepEvidence:
    action_key: str
    attempts: int
    successes: int
    failures: int
    inconclusive: int
    confidence: float
    read_only: bool
    approval_required: bool
    disruptive: bool
    disposition: str
    grants_authority: bool = False


@dataclass(frozen=True, slots=True)
class AOTResolutionPattern:
    pattern_id: str
    organization_id: str
    signature: ResolutionSignature
    root_cause_class: str
    support_count: int
    supporting_client_count: int
    contradiction_count: int
    contradiction_rate: float
    outcome_quality: float
    recency_factor: float
    confidence: float
    latest_support_at: datetime
    promotion_mode: str
    steps: tuple[PatternStepEvidence, ...]
    evidence_only: bool = True
    grants_authority: bool = False

    def project(self) -> dict[str, object]:
        return {
            "pattern_id": self.pattern_id,
            "signature": {
                "category": self.signature.category,
                "product": self.signature.product,
                "device_role": self.signature.device_role,
                "platform": self.signature.platform,
                "product_version": self.signature.product_version,
                "symptoms": list(self.signature.symptoms),
                "attributes": dict(self.signature.attributes),
            },
            "root_cause_class": self.root_cause_class,
            "support_count": self.support_count,
            "supporting_client_count": self.supporting_client_count,
            "contradiction_count": self.contradiction_count,
            "contradiction_rate": self.contradiction_rate,
            "outcome_quality": self.outcome_quality,
            "recency_factor": self.recency_factor,
            "confidence": self.confidence,
            "latest_support_at": self.latest_support_at.isoformat(),
            "promotion_mode": self.promotion_mode,
            "steps": [
                {
                    "action_key": step.action_key,
                    "attempts": step.attempts,
                    "successes": step.successes,
                    "failures": step.failures,
                    "inconclusive": step.inconclusive,
                    "confidence": step.confidence,
                    "read_only": step.read_only,
                    "approval_required": step.approval_required,
                    "disruptive": step.disruptive,
                    "disposition": step.disposition,
                    "grants_authority": False,
                }
                for step in self.steps
            ],
            "raw_source_cases_exposed": False,
            "evidence_only": True,
            "grants_authority": False,
            "execution_authority_source": "current_jason_governance_only",
        }


class PatternSanitizationError(ValueError):
    pass


class AOTPatternMemoryBuilder:
    """Derive irreversible AOT-wide troubleshooting patterns from raw client cases.

    Raw cases are accepted only inside this internal derivation boundary. Pattern
    payloads contain no source case IDs, source references, client IDs, owner
    names, provider-native IDs, or free-form evidence text.
    """

    def __init__(self, *, minimum_independent_clients: int = 2) -> None:
        if minimum_independent_clients < 2:
            raise ValueError("minimum_independent_clients must be at least two")
        self.minimum_independent_clients = minimum_independent_clients

    def derive(
        self,
        *,
        organization_id: str,
        cases: Iterable[ResolutionCase],
        now: datetime | None = None,
        technician_approved_case_ids: frozenset[str] = frozenset(),
    ) -> tuple[AOTResolutionPattern, ...]:
        if not organization_id.strip():
            raise ValueError("organization_id must be non-empty")
        now = now or datetime.now(timezone.utc)
        groups: dict[tuple[object, ...], list[ResolutionCase]] = {}

        for case in cases:
            case.validate()
            if case.organization_id != organization_id:
                continue
            if case.status is ResolutionCaseStatus.DEPRECATED:
                continue
            if not case.technician_confirmed:
                continue
            try:
                signature = self._sanitize_signature(case.signature)
                root_cause_class = self._derive_root_cause_class(case, signature)
            except PatternSanitizationError:
                # Ambiguous/identifying material fails closed for promotion. The
                # client-scoped raw case remains valid and retrievable in its own scope.
                continue
            key = (
                signature.category,
                signature.product,
                signature.device_role,
                signature.platform,
                signature.product_version,
                signature.symptoms,
                tuple(sorted(signature.attributes.items())),
                root_cause_class,
            )
            groups.setdefault(key, []).append(case)

        patterns: list[AOTResolutionPattern] = []
        for key, supporting in groups.items():
            clients = {case.client_id for case in supporting}
            explicitly_approved = any(
                case.case_id in technician_approved_case_ids for case in supporting
            )
            if len(clients) < self.minimum_independent_clients and not explicitly_approved:
                continue

            signature = ResolutionSignature(
                category=str(key[0]),
                product=str(key[1]),
                device_role=str(key[2]),
                platform=str(key[3]),
                product_version=str(key[4]),
                symptoms=tuple(key[5]),  # type: ignore[arg-type]
                attributes=dict(key[6]),  # type: ignore[arg-type]
            )
            root_cause_class = str(key[7])
            latest = max(case.resolved_at or case.recorded_at for case in supporting)
            ages = [
                max(0.0, (now - (case.resolved_at or case.recorded_at)).total_seconds() / 86400.0)
                for case in supporting
            ]
            recency = sum(max(0.25, math.exp(-age / 240.0)) for age in ages) / len(ages)
            quality_values = [self._outcome_quality(case.outcome) for case in supporting]
            outcome_quality = sum(quality_values) / len(quality_values)
            contradictions = sum(
                1
                for case in supporting
                if case.outcome in {ResolutionOutcome.FAILED, ResolutionOutcome.INCONCLUSIVE}
                or any(step.outcome is ResolutionOutcome.FAILED for step in case.steps)
            )
            contradiction_rate = contradictions / len(supporting)
            support_factor = min(1.0, len(clients) / 3.0)
            confidence = (
                0.35 * support_factor
                + 0.25 * recency
                + 0.30 * outcome_quality
                + 0.10 * (1.0 - contradiction_rate)
            )
            if explicitly_approved and len(clients) < self.minimum_independent_clients:
                confidence *= 0.75

            digest_input = "|".join(
                [
                    organization_id,
                    signature.category,
                    signature.product,
                    signature.device_role,
                    signature.platform,
                    signature.product_version,
                    ",".join(signature.symptoms),
                    ",".join(f"{k}={v}" for k, v in sorted(signature.attributes.items())),
                    root_cause_class,
                ]
            )
            pattern_id = "aot-pattern-" + hashlib.sha256(
                digest_input.encode("utf-8")
            ).hexdigest()[:20]
            patterns.append(
                AOTResolutionPattern(
                    pattern_id=pattern_id,
                    organization_id=organization_id,
                    signature=signature,
                    root_cause_class=root_cause_class,
                    support_count=len(supporting),
                    supporting_client_count=len(clients),
                    contradiction_count=contradictions,
                    contradiction_rate=round(contradiction_rate, 6),
                    outcome_quality=round(outcome_quality, 6),
                    recency_factor=round(recency, 6),
                    confidence=round(max(0.0, min(confidence, 1.0)), 6),
                    latest_support_at=latest,
                    promotion_mode=(
                        "repeated_independent_cases"
                        if len(clients) >= self.minimum_independent_clients
                        else "technician_approved_early_promotion"
                    ),
                    steps=self._aggregate_steps(supporting),
                )
            )

        patterns.sort(key=lambda item: (-item.confidence, -item.support_count, item.pattern_id))
        return tuple(patterns)

    def search(
        self,
        *,
        signature: ResolutionSignature,
        patterns: Iterable[AOTResolutionPattern],
        limit: int = 10,
    ) -> tuple[dict[str, object], ...]:
        if limit < 1 or limit > 100:
            raise ValueError("limit must be between 1 and 100")
        query = self._sanitize_signature(signature)
        ranked: list[tuple[float, dict[str, object]]] = []
        for pattern in patterns:
            similarity, reasons = ResolutionMemoryMatcher._similarity(
                query.normalized(), pattern.signature.normalized()
            )
            if similarity < 0.45:
                continue
            ranking_score = similarity * pattern.confidence
            projected = pattern.project()
            projected.update(
                {
                    "similarity": round(similarity, 6),
                    "ranking_score": round(ranking_score, 6),
                    "reasons": reasons,
                }
            )
            ranked.append((ranking_score, projected))
        ranked.sort(key=lambda item: item[0], reverse=True)
        return tuple(item[1] for item in ranked[:limit])

    @classmethod
    def _sanitize_signature(cls, signature: ResolutionSignature) -> ResolutionSignature:
        normalized = signature.normalized()
        safe_attributes: dict[str, str] = {}
        for key, value in normalized.attributes.items():
            if any(fragment in key for fragment in _FORBIDDEN_FIELD_FRAGMENTS):
                continue
            if key not in _SAFE_ATTRIBUTE_KEYS:
                continue
            safe_attributes[key] = cls._sanitize_text(value, f"attribute:{key}")
        return ResolutionSignature(
            category=cls._sanitize_text(normalized.category, "category"),
            product=cls._sanitize_text(normalized.product, "product"),
            device_role=cls._sanitize_text(normalized.device_role, "device_role"),
            platform=cls._sanitize_text(normalized.platform, "platform"),
            product_version=cls._sanitize_version(normalized.product_version),
            symptoms=tuple(
                cls._sanitize_text(value, "symptom") for value in normalized.symptoms
            ),
            attributes=safe_attributes,
        )

    @staticmethod
    def _sanitize_version(value: str) -> str:
        normalized = value.strip().casefold()
        if not normalized:
            return ""
        if len(normalized) > 64 or not re.fullmatch(r"[a-z0-9._+:-]+", normalized):
            raise PatternSanitizationError("product_version is not a bounded technical version")
        return normalized

    @staticmethod
    def _sanitize_text(value: str, field_name: str, *, allow_empty: bool = False) -> str:
        normalized = " ".join(value.strip().casefold().split())
        if not normalized:
            if allow_empty:
                return ""
            raise PatternSanitizationError(f"{field_name} is empty")
        if (
            _EMAIL_RE.search(normalized)
            or _IPV4_RE.search(normalized)
            or _TICKET_RE.search(normalized)
            or _DOMAIN_RE.search(normalized)
            or _HOSTISH_RE.search(normalized)
        ):
            raise PatternSanitizationError(
                f"{field_name} contains client-identifying or provider-native material"
            )
        return normalized

    @classmethod
    def _derive_root_cause_class(
        cls, case: ResolutionCase, signature: ResolutionSignature
    ) -> str:
        # Never copy free-form root_cause into cross-client pattern memory.
        # Derive a technical class from already-sanitized context plus canonical
        # successful remediation action keys. This makes client-name leakage
        # structurally impossible through the root-cause field.
        remediation_keys = sorted(
            {
                cls._sanitize_action_key(step.action_key)
                for step in case.steps
                if step.kind.value == "remediation"
                and step.outcome in {ResolutionOutcome.RESOLVED, ResolutionOutcome.IMPROVED}
            }
        )
        suffix = "+".join(remediation_keys) if remediation_keys else "no_verified_remediation"
        return f"{signature.category}:{signature.product}:{suffix}"

    @staticmethod
    def _sanitize_action_key(value: str) -> str:
        normalized = value.strip().casefold()
        if not normalized or len(normalized) > 128:
            raise PatternSanitizationError("action_key is empty or too long")
        if not re.fullmatch(r"[a-z][a-z0-9._:-]*", normalized):
            raise PatternSanitizationError("action_key is not canonical")
        if _EMAIL_RE.search(normalized) or _IPV4_RE.search(normalized) or _TICKET_RE.search(normalized):
            raise PatternSanitizationError("action_key contains identifying material")
        return normalized

    @staticmethod
    def _outcome_quality(outcome: ResolutionOutcome) -> float:
        return {
            ResolutionOutcome.RESOLVED: 1.0,
            ResolutionOutcome.IMPROVED: 0.8,
            ResolutionOutcome.INCONCLUSIVE: 0.45,
            ResolutionOutcome.FAILED: 0.2,
        }[outcome]

    @staticmethod
    def _aggregate_steps(cases: list[ResolutionCase]) -> tuple[PatternStepEvidence, ...]:
        buckets: dict[str, dict[str, object]] = {}
        for case in cases:
            for step in case.steps:
                try:
                    action_key = AOTPatternMemoryBuilder._sanitize_action_key(step.action_key)
                except PatternSanitizationError:
                    continue
                bucket = buckets.setdefault(
                    action_key,
                    {
                        "attempts": 0,
                        "successes": 0,
                        "failures": 0,
                        "inconclusive": 0,
                        "read_only": True,
                        "approval_required": False,
                        "disruptive": False,
                    },
                )
                bucket["attempts"] = int(bucket["attempts"]) + 1
                bucket["read_only"] = bool(bucket["read_only"]) and step.read_only
                bucket["approval_required"] = bool(bucket["approval_required"]) or step.approval_required
                bucket["disruptive"] = bool(bucket["disruptive"]) or step.disruptive
                if step.outcome in {ResolutionOutcome.RESOLVED, ResolutionOutcome.IMPROVED}:
                    bucket["successes"] = int(bucket["successes"]) + 1
                elif step.outcome is ResolutionOutcome.FAILED:
                    bucket["failures"] = int(bucket["failures"]) + 1
                else:
                    bucket["inconclusive"] = int(bucket["inconclusive"]) + 1

        results: list[PatternStepEvidence] = []
        for action_key, bucket in buckets.items():
            successes = int(bucket["successes"])
            failures = int(bucket["failures"])
            inconclusive = int(bucket["inconclusive"])
            attempts = int(bucket["attempts"])
            confidence = (successes + 1.0) / (successes + failures + inconclusive + 2.0)
            if successes and failures:
                disposition = "historically_conflicted"
            elif failures > successes:
                disposition = "historically_unreliable"
            elif successes >= 2 and confidence >= 0.6:
                disposition = "historically_supported"
            else:
                disposition = "insufficient_history"
            results.append(
                PatternStepEvidence(
                    action_key=action_key,
                    attempts=attempts,
                    successes=successes,
                    failures=failures,
                    inconclusive=inconclusive,
                    confidence=round(confidence, 6),
                    read_only=bool(bucket["read_only"]),
                    approval_required=bool(bucket["approval_required"]),
                    disruptive=bool(bucket["disruptive"]),
                    disposition=disposition,
                )
            )
        rank = {
            "historically_supported": 0,
            "insufficient_history": 1,
            "historically_conflicted": 2,
            "historically_unreliable": 3,
        }
        results.sort(
            key=lambda item: (
                rank[item.disposition],
                not item.read_only,
                -item.confidence,
                item.action_key,
            )
        )
        return tuple(results)
