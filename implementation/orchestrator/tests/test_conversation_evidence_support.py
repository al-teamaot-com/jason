from __future__ import annotations

import pytest

from orchestrator.conversation_evidence_support import (
    ConversationEvidenceSupportExtractor,
)
from orchestrator.conversation_kernel import InformationNeed, InformationTarget
from orchestrator.contracts import (
    ExecutionStage,
    OrchestrationResult,
    OrchestrationStatus,
)
from orchestrator.dynamic_resource_response import DynamicEvidenceSelection


class FakeReasoner:
    def __init__(self, *selections):
        self.selections = list(selections)
        self.calls = []

    def select(self, *, question, sanitized_data):
        self.calls.append((question, sanitized_data))
        return self.selections.pop(0)


def need():
    return InformationNeed(
        target=InformationTarget(
            kind="endpoint",
            source="literal",
            reference="NODE-77",
        ),
        need="identity associated with the most recent session",
        authority="observe",
        temporal_scope="most_recent",
    )


def result(*, status=OrchestrationStatus.SUCCEEDED, provider_id="provider-one", data=None):
    output = {}
    if status is OrchestrationStatus.SUCCEEDED:
        output = {
            "provider": provider_id,
            "data": data if data is not None else {
                "device": {
                    "sessionUser": "Example User",
                    "otherValue": "Adjacent Value",
                }
            },
        }
    return OrchestrationResult(
        execution_id="exec-1",
        correlation_id="corr-1",
        capability_name="endpoint.device.search",
        status=status,
        stage=(
            ExecutionStage.COMPLETED
            if status is OrchestrationStatus.SUCCEEDED
            else ExecutionStage.FAILED
        ),
        reason_codes=("test",),
        resolution=None,
        output=output,
        attempts=1,
        provider_id=provider_id,
    )


def test_supported_path_is_deterministically_dereferenced_into_conversation_support():
    reasoner = FakeReasoner(
        DynamicEvidenceSelection(
            answer_type="direct",
            evidence_paths=("/device/sessionUser",),
        )
    )
    extractor = ConversationEvidenceSupportExtractor(reasoner=reasoner)

    assessment = extractor.assess(
        need=need(),
        result=result(),
        support_prefix="need-1",
    )

    assert assessment.status == "supported"
    assert assessment.selected_paths == ("/device/sessionUser",)
    assert len(assessment.supports) == 1
    support = assessment.supports[0]
    assert support.value == "Example User"
    assert support.information_need == need().need
    assert support.evidence_reference == "exec-1:/device/sessionUser"


def test_unavailable_selection_stays_unsupported_instead_of_using_adjacent_value():
    reasoner = FakeReasoner(
        DynamicEvidenceSelection(answer_type="unavailable")
    )
    extractor = ConversationEvidenceSupportExtractor(reasoner=reasoner)

    assessment = extractor.assess(
        need=need(),
        result=result(),
        support_prefix="need-1",
    )

    assert assessment.status == "unsupported"
    assert assessment.supports == ()
    assert "did not establish" in assessment.reason


def test_failed_governed_read_never_reaches_evidence_reasoner():
    reasoner = FakeReasoner()
    extractor = ConversationEvidenceSupportExtractor(reasoner=reasoner)

    assessment = extractor.assess(
        need=need(),
        result=result(status=OrchestrationStatus.FAILED),
        support_prefix="need-1",
    )

    assert assessment.status == "failed"
    assert reasoner.calls == []


def test_provider_provenance_must_remain_consistent_before_evidence_reasoning():
    reasoner = FakeReasoner(
        DynamicEvidenceSelection(answer_type="unavailable")
    )
    extractor = ConversationEvidenceSupportExtractor(reasoner=reasoner)
    bad = OrchestrationResult(
        execution_id="exec-1",
        correlation_id="corr-1",
        capability_name="endpoint.device.search",
        status=OrchestrationStatus.SUCCEEDED,
        stage=ExecutionStage.COMPLETED,
        reason_codes=("test",),
        resolution=None,
        output={"provider": "different-provider", "data": {"x": 1}},
        attempts=1,
        provider_id="provider-one",
    )

    with pytest.raises(RuntimeError, match="provenance"):
        extractor.assess(
            need=need(),
            result=bad,
            support_prefix="need-1",
        )

    assert reasoner.calls == []


def test_sanitized_secret_value_cannot_become_conversation_support():
    reasoner = FakeReasoner(
        DynamicEvidenceSelection(
            answer_type="direct",
            evidence_paths=("/password",),
        )
    )
    extractor = ConversationEvidenceSupportExtractor(reasoner=reasoner)
    raw = {"password": "DoNotExposeThis"}

    with pytest.raises(PermissionError, match="redacted evidence"):
        extractor.assess(
            need=need(),
            result=result(data=raw),
            support_prefix="need-1",
        )

    assert raw == {"password": "DoNotExposeThis"}
    assert reasoner.calls[0][1]["password"] == "[REDACTED]"
