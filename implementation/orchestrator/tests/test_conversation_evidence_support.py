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


def test_governed_boolean_semantic_evidence_bypasses_language_selector():
    from orchestrator.conversation_evidence_support import (
        ConversationEvidenceSupportExtractor,
    )
    from orchestrator.conversation_kernel import (
        InformationNeed,
        InformationTarget,
    )
    from orchestrator.contracts import (
        ExecutionStage,
        OrchestrationResult,
        OrchestrationStatus,
    )

    class ExplodingReasoner:
        def select(self, *, question, sanitized_data):
            raise AssertionError(
                "trusted canonical boolean evidence must not require language selection"
            )

    extractor = ConversationEvidenceSupportExtractor(
        reasoner=ExplodingReasoner(),
    )

    need = InformationNeed(
        target=InformationTarget(
            kind="endpoint",
            source="literal",
            reference="AOT-50282",
        ),
        need="restart required",
        authority="observe",
    )

    result = OrchestrationResult(
        execution_id="exec-reboot",
        correlation_id="corr-reboot",
        capability_name="endpoint.device.search",
        status=OrchestrationStatus.SUCCEEDED,
        stage=ExecutionStage.COMPLETED,
        reason_codes=("completed",),
        resolution=None,
        output={
            "provider": "datto_rmm",
            "data": {
                "provider_data": {
                    "semantic_evidence": {
                        "endpoint": {
                            "operating_system": {
                                "maintenance_state": {
                                    "reboot_required": True,
                                }
                            }
                        }
                    }
                }
            },
        },
        attempts=1,
        provider_id="datto_rmm",
    )

    assessment = extractor.assess(
        need=need,
        result=result,
        support_prefix="semantic",
    )

    assert assessment.status == "supported"
    assert len(assessment.supports) == 1
    assert assessment.supports[0].value is True
    assert (
        assessment.selected_paths[0]
        == "/provider_data/semantic_evidence/"
        "endpoint/operating_system/maintenance_state/reboot_required"
    )


def test_canonical_requested_fact_drives_semantic_evidence_without_reinterpreting_need():
    from orchestrator.conversation_evidence_support import (
        ConversationEvidenceSupportExtractor,
    )
    from orchestrator.conversation_kernel import (
        InformationNeed,
        InformationTarget,
    )
    from orchestrator.contracts import (
        ExecutionStage,
        OrchestrationResult,
        OrchestrationStatus,
    )

    class ExplodingReasoner:
        def select(self, *, question, sanitized_data):
            raise AssertionError(
                "governed canonical semantic evidence must bypass language selection"
            )

    extractor = ConversationEvidenceSupportExtractor(
        reasoner=ExplodingReasoner(),
    )

    need = InformationNeed(
        target=InformationTarget(
            kind="endpoint",
            source="verified_entity",
            reference="AOT-50282",
            entity_ref="endpoint:AOT-50282",
        ),
        need="what operating system does it have",
        authority="observe",
    )

    result = OrchestrationResult(
        execution_id="exec-os",
        correlation_id="corr-os",
        capability_name="endpoint.device.search",
        status=OrchestrationStatus.SUCCEEDED,
        stage=ExecutionStage.COMPLETED,
        reason_codes=("completed",),
        resolution=None,
        output={
            "provider": "datto_rmm",
            "data": {
                "provider_data": {
                    "semantic_evidence": {
                        "operating_system": {
                            "operating_system":
                                "Microsoft Windows 11 Pro 10.0.26200"
                        }
                    }
                }
            },
        },
        attempts=1,
        provider_id="datto_rmm",
    )

    assessment = extractor.assess(
        need=need,
        requested_facts=("operating system",),
        result=result,
        support_prefix="canonical",
    )

    assert assessment.status == "supported"
    assert (
        assessment.supports[0].value
        == "Microsoft Windows 11 Pro 10.0.26200"
    )
