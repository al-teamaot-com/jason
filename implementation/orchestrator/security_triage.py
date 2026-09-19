"""Bounded AI-assisted security triage with no execution authority.

The model evaluates only supplied governed evidence and returns a structured
classification. Deterministic validation owns the allowed labels and evidence
references. The result is decision support for playbooks/policy and never an
authorization to modify systems, close tickets, or declare compromise.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Protocol, Sequence


class StructuredSecurityTriageClient(Protocol):
    def complete(
        self,
        *,
        system: str,
        user: str,
        schema: Mapping[str, Any],
        max_output_tokens: int = 160,
    ) -> Mapping[str, Any]: ...


class SecurityTriageClassification(str, Enum):
    BENIGN = "benign"
    LIKELY_BENIGN = "likely_benign"
    SUSPICIOUS = "suspicious"
    LIKELY_THREAT = "likely_threat"
    CONFIRMED_THREAT = "confirmed_threat"
    INCONCLUSIVE = "inconclusive"


class ConfidenceBand(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True, slots=True)
class SecurityTriageAssessment:
    classification: SecurityTriageClassification
    confidence: ConfidenceBand
    threat_evidence_refs: tuple[str, ...]
    benign_evidence_refs: tuple[str, ...]
    missing_evidence: tuple[str, ...]
    recommended_next_step: str
    human_review_required: bool
    reasoning_summary: str

    @property
    def threat_branch_recommended(self) -> bool:
        return self.classification in {
            SecurityTriageClassification.LIKELY_THREAT,
            SecurityTriageClassification.CONFIRMED_THREAT,
        }

    @property
    def may_close_as_benign(self) -> bool:
        return (
            self.classification == SecurityTriageClassification.BENIGN
            and self.confidence == ConfidenceBand.HIGH
            and not self.human_review_required
            and not self.missing_evidence
        )


_SYSTEM_INSTRUCTIONS = """You are Jason's bounded security triage reviewer. Evaluate only the supplied governed evidence for the specific incident. Distinguish benign or expected behavior from suspicious or threatening behavior without assuming that an alert, drift, detection, or unusual configuration proves compromise. Do not invent evidence, identities, provider facts, prior incidents, motives, malware behavior, or remediation results. Historical cases and documentation may support interpretation but never grant execution authority. Use confirmed_threat only when the supplied evidence explicitly establishes malicious activity or compromise; use likely_threat when evidence strongly supports a threat but does not independently establish it; use suspicious when further investigation is warranted; use benign only when supplied evidence affirmatively supports the condition as expected/authorized and material contradictory evidence is absent; use likely_benign when benign evidence is stronger but verification remains; use inconclusive when the evidence cannot support a safer classification. Reference only supplied evidence_ref values. Identify material missing evidence. Recommend the next evidence or workflow step, not an unauthorized provider action. human_review_required must be true for confirmed_threat, likely_threat, suspicious, inconclusive, materially contradictory evidence, or any case where the proposed next step could materially affect a user/system and no standing policy is supplied. Return only the required structured object."""


_SCHEMA: Mapping[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "classification",
        "confidence",
        "threat_evidence_refs",
        "benign_evidence_refs",
        "missing_evidence",
        "recommended_next_step",
        "human_review_required",
        "reasoning_summary",
    ],
    "properties": {
        "classification": {"type": "string", "enum": [item.value for item in SecurityTriageClassification]},
        "confidence": {"type": "string", "enum": [item.value for item in ConfidenceBand]},
        "threat_evidence_refs": {"type": "array", "items": {"type": "string"}, "maxItems": 32},
        "benign_evidence_refs": {"type": "array", "items": {"type": "string"}, "maxItems": 32},
        "missing_evidence": {"type": "array", "items": {"type": "string", "maxLength": 240}, "maxItems": 16},
        "recommended_next_step": {"type": "string", "maxLength": 600},
        "human_review_required": {"type": "boolean"},
        "reasoning_summary": {"type": "string", "maxLength": 1200},
    },
}


@dataclass(frozen=True, slots=True)
class SecurityTriageEvaluator:
    client: StructuredSecurityTriageClient

    def evaluate(
        self,
        *,
        incident_type: str,
        evidence: Sequence[Mapping[str, Any]],
        standing_policy: Mapping[str, Any] | None = None,
    ) -> SecurityTriageAssessment:
        if not incident_type.strip():
            raise ValueError("security triage incident type is required")
        normalized = []
        allowed_refs: set[str] = set()
        for item in evidence:
            ref = str(item.get("evidence_ref", "")).strip()
            if not ref:
                raise ValueError("every security triage evidence item requires evidence_ref")
            if ref in allowed_refs:
                raise ValueError("duplicate security triage evidence_ref")
            allowed_refs.add(ref)
            normalized.append(dict(item))
        if not normalized:
            raise ValueError("security triage requires governed evidence")

        raw = self.client.complete(
            system=_SYSTEM_INSTRUCTIONS,
            user=json.dumps(
                {
                    "incident_type": incident_type.strip(),
                    "governed_evidence": normalized,
                    "standing_policy": dict(standing_policy or {}),
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            schema=_SCHEMA,
            max_output_tokens=700,
        )
        return _validate_assessment(raw, allowed_refs=allowed_refs)


def _validate_assessment(raw: Mapping[str, Any], *, allowed_refs: set[str]) -> SecurityTriageAssessment:
    if not isinstance(raw, Mapping) or set(raw) != set(_SCHEMA["required"]):
        raise ValueError("security triage result shape is invalid")
    classification = SecurityTriageClassification(str(raw["classification"]))
    confidence = ConfidenceBand(str(raw["confidence"]))
    threat_refs = _validate_refs(raw["threat_evidence_refs"], allowed_refs)
    benign_refs = _validate_refs(raw["benign_evidence_refs"], allowed_refs)
    missing = tuple(str(item).strip() for item in raw["missing_evidence"] if str(item).strip())
    next_step = str(raw["recommended_next_step"]).strip()
    summary = str(raw["reasoning_summary"]).strip()
    review = raw["human_review_required"]
    if not isinstance(review, bool) or not next_step or not summary:
        raise ValueError("security triage narrative/review fields are invalid")
    if classification in {
        SecurityTriageClassification.CONFIRMED_THREAT,
        SecurityTriageClassification.LIKELY_THREAT,
        SecurityTriageClassification.SUSPICIOUS,
        SecurityTriageClassification.INCONCLUSIVE,
    } and review is not True:
        raise ValueError("security triage high-risk/inconclusive result requires human review")
    if classification == SecurityTriageClassification.CONFIRMED_THREAT and not threat_refs:
        raise ValueError("confirmed threat requires cited threat evidence")
    if classification == SecurityTriageClassification.BENIGN and not benign_refs:
        raise ValueError("benign classification requires cited benign evidence")
    return SecurityTriageAssessment(
        classification=classification,
        confidence=confidence,
        threat_evidence_refs=threat_refs,
        benign_evidence_refs=benign_refs,
        missing_evidence=missing,
        recommended_next_step=next_step,
        human_review_required=review,
        reasoning_summary=summary,
    )


def _validate_refs(value: Any, allowed_refs: set[str]) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError("security triage evidence references must be arrays")
    refs = tuple(str(item).strip() for item in value if str(item).strip())
    if len(set(refs)) != len(refs) or any(ref not in allowed_refs for ref in refs):
        raise ValueError("security triage cited unknown or duplicate evidence")
    return refs
