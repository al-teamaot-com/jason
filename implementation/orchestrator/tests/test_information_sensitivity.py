from __future__ import annotations

from orchestrator.information_sensitivity import (
    SensitivityFindingKind,
    assess_sensitive_evidence,
)


def test_plain_operational_evidence_is_not_marked_sensitive() -> None:
    assessment = assess_sensitive_evidence(
        {
            "hostname": "AOT-50282",
            "address": "192.168.1.50",
            "notes": "Printer is configured by IP.",
        }
    )

    assert assessment.sensitive is False
    assert assessment.findings == ()


def test_secret_named_field_marks_evidence_sensitive_without_returning_value() -> None:
    assessment = assess_sensitive_evidence(
        {"connection": {"password": "example-sensitive-value"}}
    )

    assert assessment.sensitive is True
    assert assessment.findings[0].kind is SensitivityFindingKind.SECRET_FIELD
    assert "example-sensitive-value" not in repr(assessment)


def test_credential_assignment_inside_document_text_is_sensitive() -> None:
    assessment = assess_sensitive_evidence(
        {"content": "For the appliance, password: example-sensitive-value"}
    )

    kinds = {finding.kind for finding in assessment.findings}
    assert SensitivityFindingKind.CREDENTIAL_ASSIGNMENT in kinds
    assert "example-sensitive-value" not in repr(assessment)


def test_private_key_marker_is_sensitive() -> None:
    assessment = assess_sensitive_evidence(
        {"notes": "-----BEGIN PRIVATE KEY-----\nexample\n-----END PRIVATE KEY-----"}
    )

    assert assessment.sensitive is True
    assert any(
        finding.kind is SensitivityFindingKind.PRIVATE_KEY
        for finding in assessment.findings
    )


def test_common_token_shape_is_sensitive() -> None:
    assessment = assess_sensitive_evidence(
        {"notes": "token sk-abcdefghijklmnop1234567890"}
    )

    assert assessment.sensitive is True
    assert any(
        finding.kind is SensitivityFindingKind.TOKEN_SHAPE
        for finding in assessment.findings
    )
