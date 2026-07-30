from jason_cap_001.quality import evaluate_reasoning_result


def valid_result() -> dict:
    return {
        "schema_version": "0.1",
        "case_id": "case-1",
        "situation_summary": "The ticket contains a diagnostic warning.",
        "hypotheses": [
            {
                "hypothesis_id": "h1",
                "statement": "The condition requires technician review.",
                "supporting_evidence_ids": ["e1"],
                "contradicting_evidence_ids": [],
                "confidence": 0.7,
                "status": "leading",
            }
        ],
        "recommendation": "Review the cited diagnostic before making changes.",
        "next_evidence_step": None,
        "confidence": 0.7,
        "risk": "medium",
        "evidence_ids": ["e1"],
        "approval_required": False,
        "approval_class": None,
        "unresolved_uncertainty": [],
    }


def test_valid_result_passes() -> None:
    result = evaluate_reasoning_result(valid_result(), {"e1"})
    assert result.passed
    assert result.findings == ()


def test_unknown_evidence_fails() -> None:
    document = valid_result()
    document["evidence_ids"] = ["other-client-evidence"]
    result = evaluate_reasoning_result(document, {"e1"})
    assert not result.passed
    assert "QG001" in {finding.code for finding in result.findings}


def test_high_risk_requires_approval() -> None:
    document = valid_result()
    document["risk"] = "high"
    result = evaluate_reasoning_result(document, {"e1"})
    assert not result.passed
    assert "QG006" in {finding.code for finding in result.findings}


def test_low_confidence_requires_next_evidence_step() -> None:
    document = valid_result()
    document["confidence"] = 0.3
    result = evaluate_reasoning_result(document, {"e1"})
    assert not result.passed
    assert "QG008" in {finding.code for finding in result.findings}
