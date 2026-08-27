from __future__ import annotations

import pytest

from orchestrator.contracts import (
    ExecutionStage,
    OrchestrationResult,
    OrchestrationStatus,
)
from orchestrator.resource_evidence import (
    GovernedResourceEvidenceInterpreter,
    GovernedTeamsResourceResponseRenderer,
)
from orchestrator.teams_conversation_flow import ConversationIntent


class EmptyEvidenceReasoner:
    def locate(self, *, requested_facts, data):
        return ()


def _result(data):
    return OrchestrationResult(
        execution_id="exec-1",
        correlation_id="corr-1",
        capability_name="endpoint.device.read",
        status=OrchestrationStatus.SUCCEEDED,
        stage=ExecutionStage.COMPLETED,
        reason_codes=("completed",),
        resolution=None,
        output={
            "provider": "datto_rmm",
            "data": data,
        },
        attempts=1,
        provider_id="datto_rmm",
    )


def test_deterministic_fallback_preserves_datto_last_seen():
    interpreter = GovernedResourceEvidenceInterpreter(
        reasoner=EmptyEvidenceReasoner()
    )

    facts = interpreter.interpret(
        result=_result(
            {
                "uid": "device-123",
                "hostname": "AOT-50107",
                "lastSeen": "2026-08-19T16:42:00Z",
            }
        ),
        requested_facts=("endpoint last seen",),
    )

    assert len(facts) == 1
    assert facts[0].value == "2026-08-19T16:42:00Z"
    assert facts[0].json_pointer == "/lastSeen"


def test_renderer_returns_provider_value_when_reasoner_misses():
    renderer = GovernedTeamsResourceResponseRenderer(
        interpreter=GovernedResourceEvidenceInterpreter(
            reasoner=EmptyEvidenceReasoner()
        )
    )

    rendered = renderer.render(
        _result(
            {
                "uid": "device-123",
                "hostname": "AOT-50107",
                "lastSeen": "2026-08-19T16:42:00Z",
            }
        ),
        ConversationIntent(
            capability_name="endpoint.device.read",
            arguments={
                "hostname": "AOT-50107",
                "requested_facts": ["endpoint last seen"],
            },
            permission_mode="observe",
        ),
    )

    assert rendered == (
        "AOT-50107 — endpoint last seen: 2026-08-19T16:42:00Z. "
        "Source: datto_rmm."
    )


def test_fallback_fails_closed_when_fact_is_ambiguous():
    interpreter = GovernedResourceEvidenceInterpreter(
        reasoner=EmptyEvidenceReasoner()
    )

    with pytest.raises(LookupError):
        interpreter.interpret(
            result=_result(
                {
                    "devices": [
                        {"lastSeen": "2026-08-19T10:00:00Z"},
                        {"lastSeen": "2026-08-19T11:00:00Z"},
                    ]
                }
            ),
            requested_facts=("endpoint last seen",),
        )


def test_fallback_does_not_invent_missing_fact():
    interpreter = GovernedResourceEvidenceInterpreter(
        reasoner=EmptyEvidenceReasoner()
    )

    with pytest.raises(LookupError):
        interpreter.interpret(
            result=_result(
                {
                    "uid": "device-123",
                    "hostname": "AOT-50107",
                }
            ),
            requested_facts=("endpoint last seen",),
        )
