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


class Reasoner:
    def __init__(self, proposals):
        self.proposals = proposals
        self.calls = []

    def locate(self, *, requested_facts, data):
        self.calls.append((requested_facts, data))
        return self.proposals


def result(*, data=None, provider="datto_rmm", status=OrchestrationStatus.SUCCEEDED):
    return OrchestrationResult(
        execution_id="exec-1",
        correlation_id="corr-1",
        capability_name="endpoint.device.search",
        status=status,
        stage=(ExecutionStage.COMPLETED if status is OrchestrationStatus.SUCCEEDED else ExecutionStage.FAILED),
        reason_codes=("capability_completed" if status is OrchestrationStatus.SUCCEEDED else "failed",),
        resolution=None,
        output={
            "provider": provider,
            "data": data
            if data is not None
            else {
                "devices": [
                    {
                        "hostname": "AOT-50282",
                        "lastUser": "AOT\\example.user",
                        "operatingSystem": "Windows 11 Pro",
                    }
                ]
            },
        },
        attempts=1,
        provider_id=provider,
    )


def intent(*facts):
    return ConversationIntent(
        capability_name="endpoint.device.search",
        arguments={
            "hostname": "AOT-50282",
            "requested_facts": facts or ("last logged in user",),
        },
        execution_mode="deterministic",
        permission_mode="observe",
    )


def test_reasoner_identifies_path_but_actual_provider_value_becomes_the_assertion():
    reasoner = Reasoner(
        [
            {
                "requested_fact": "last logged in user",
                "json_pointer": "/devices/0/lastUser",
                # Deliberately untrusted/hallucinated value: interpreter ignores it.
                "value": "WRONG\\user",
            }
        ]
    )
    interpreter = GovernedResourceEvidenceInterpreter(reasoner)

    facts = interpreter.interpret(
        result=result(),
        requested_facts=("last logged in user",),
    )

    assert facts[0].value == "AOT\\example.user"
    assert facts[0].json_pointer == "/devices/0/lastUser"


def test_renderer_returns_only_verified_requested_fact_with_source():
    renderer = GovernedTeamsResourceResponseRenderer(
        GovernedResourceEvidenceInterpreter(
            Reasoner(
                [
                    {
                        "requested_fact": "last logged in user",
                        "json_pointer": "/devices/0/lastUser",
                    }
                ]
            )
        )
    )

    text = renderer.render(result(), intent("last logged in user"))

    assert text == (
        "AOT-50282 — last logged in user: AOT\\example.user. Source: datto_rmm."
    )


def test_evidence_reasoner_cannot_assert_an_unrequested_provider_field():
    interpreter = GovernedResourceEvidenceInterpreter(
        Reasoner(
            [
                {
                    "requested_fact": "operating system",
                    "json_pointer": "/devices/0/operatingSystem",
                }
            ]
        )
    )

    with pytest.raises(PermissionError, match="unrequested fact"):
        interpreter.interpret(
            result=result(),
            requested_facts=("last logged in user",),
        )


def test_missing_evidence_pointer_fails_closed():
    interpreter = GovernedResourceEvidenceInterpreter(
        Reasoner(
            [
                {
                    "requested_fact": "last logged in user",
                    "json_pointer": "/devices/0/notARealField",
                }
            ]
        )
    )

    with pytest.raises(LookupError, match="does not exist"):
        interpreter.interpret(
            result=result(),
            requested_facts=("last logged in user",),
        )


def test_all_requested_facts_must_be_supported_before_response():
    interpreter = GovernedResourceEvidenceInterpreter(
        Reasoner(
            [
                {
                    "requested_fact": "last logged in user",
                    "json_pointer": "/devices/0/lastUser",
                }
            ]
        )
    )

    with pytest.raises(LookupError, match="did not support all requested facts"):
        interpreter.interpret(
            result=result(),
            requested_facts=("last logged in user", "operating system"),
        )


def test_inconsistent_provider_provenance_fails_closed():
    bad = result()
    bad = OrchestrationResult(
        execution_id=bad.execution_id,
        correlation_id=bad.correlation_id,
        capability_name=bad.capability_name,
        status=bad.status,
        stage=bad.stage,
        reason_codes=bad.reason_codes,
        resolution=None,
        output={"provider": "other", "data": bad.output["data"]},
        attempts=bad.attempts,
        provider_id="datto_rmm",
    )
    interpreter = GovernedResourceEvidenceInterpreter(Reasoner([]))

    with pytest.raises(RuntimeError, match="provenance"):
        interpreter.interpret(
            result=bad,
            requested_facts=("last logged in user",),
        )
