from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class QualityFinding:
    code: str
    severity: str
    message: str


@dataclass(frozen=True, slots=True)
class QualityGateResult:
    passed: bool
    findings: tuple[QualityFinding, ...]


def evaluate_reasoning_result(result: dict[str, Any], available_evidence_ids: set[str]) -> QualityGateResult:
    """Apply deterministic safety and evidence checks to a validated reasoning result."""

    findings: list[QualityFinding] = []
    cited = set(result.get("evidence_ids", []))
    missing = sorted(cited - available_evidence_ids)
    if missing:
        findings.append(QualityFinding("QG001", "error", f"Unknown evidence references: {', '.join(missing)}"))

    if not cited:
        findings.append(QualityFinding("QG002", "error", "At least one evidence reference is required."))

    confidence = float(result.get("confidence", 0))
    unresolved = result.get("unresolved_uncertainty", [])
    if confidence > 0.85 and unresolved:
        findings.append(QualityFinding("QG003", "error", "High confidence is inconsistent with unresolved uncertainty."))

    hypotheses = result.get("hypotheses", [])
    for hypothesis in hypotheses:
        support = set(hypothesis.get("supporting_evidence_ids", []))
        contradiction = set(hypothesis.get("contradicting_evidence_ids", []))
        unknown = sorted((support | contradiction) - available_evidence_ids)
        if unknown:
            findings.append(QualityFinding("QG004", "error", f"Hypothesis {hypothesis.get('hypothesis_id', '?')} cites unknown evidence: {', '.join(unknown)}"))
        if hypothesis.get("status") == "leading" and not support:
            findings.append(QualityFinding("QG005", "error", f"Leading hypothesis {hypothesis.get('hypothesis_id', '?')} has no supporting evidence."))

    risk = result.get("risk")
    if risk in {"high", "critical"} and not result.get("approval_required"):
        findings.append(QualityFinding("QG006", "error", "High or critical risk recommendations require approval."))

    if result.get("approval_required") and not result.get("approval_class"):
        findings.append(QualityFinding("QG007", "error", "An approval class is required when approval is required."))

    if confidence < 0.5 and not result.get("next_evidence_step"):
        findings.append(QualityFinding("QG008", "error", "Low-confidence results must identify the next evidence-gathering step."))

    return QualityGateResult(passed=not any(item.severity == "error" for item in findings), findings=tuple(findings))
