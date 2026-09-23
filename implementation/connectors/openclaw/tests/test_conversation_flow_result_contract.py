from __future__ import annotations

from types import SimpleNamespace

from jason_openclaw.conversation_ingress import _conversation_orchestration_status
from orchestrator.contracts import (
    ExecutionStage,
    OrchestrationResult,
    OrchestrationStatus,
)
from orchestrator.teams_conversation_flow import TeamsConversationFlowResult


def orchestration():
    return OrchestrationResult(
        execution_id="exec-1",
        correlation_id="corr-1",
        capability_name="endpoint.device.search",
        status=OrchestrationStatus.SUCCEEDED,
        stage=ExecutionStage.COMPLETED,
        reason_codes=("test",),
        resolution=None,
        output={"provider": "provider-one", "data": {}},
        attempts=1,
        provider_id="provider-one",
    )


def test_existing_conversation_flow_result_keeps_legacy_orchestration_status_contract():
    result = TeamsConversationFlowResult(
        orchestration=orchestration(),
        transport_message_id="message-1",
    )

    assert _conversation_orchestration_status(result) == "succeeded"


def test_conversation_experience_can_report_no_orchestration_without_faking_execution():
    result = SimpleNamespace(
        transport_message_id="message-2",
        orchestration_status="not_required",
        orchestrations=(),
    )

    assert _conversation_orchestration_status(result) == "not_required"


def test_explicit_aggregate_status_takes_precedence_over_single_orchestration_shape():
    result = SimpleNamespace(
        transport_message_id="message-3",
        orchestration_status="partial",
        orchestration=orchestration(),
    )

    assert _conversation_orchestration_status(result) == "partial"
