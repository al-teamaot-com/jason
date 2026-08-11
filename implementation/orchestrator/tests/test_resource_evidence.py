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


def canonical_search_data(*matches, provider_data=None):
    return {
        "resource_matches": list(matches),
        "provider_data": provider_data
        if provider_data is not None
        else {
            "devices": [
                {
                    "uid": "device-uid-1",
                    "hostname": "AOT-50282",
                    "lastUser": "AOT\\example.user",
                }
            ]
        },
    }


def intent(*facts, hostname="AOT-50282", site=None):
    arguments = {
        "hostname": hostname,
        "requested_facts": facts or ("last logged in user",),
    }
    if site is not None:
        arguments["site"] = site
    return ConversationIntent(
        capability_name="endpoint.device.search",
        arguments=arguments,
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


def test_renderer_returns_only_verified_requested_fact_after_unique_identity_resolution():
    reasoner = Reasoner(
        [
            {
                "requested_fact": "last logged in user",
                "json_pointer": "/provider_data/devices/0/lastUser",
            }
        ]
    )
    renderer = GovernedTeamsResourceResponseRenderer(
        GovernedResourceEvidenceInterpreter(reasoner)
    )
    data = canonical_search_data(
        {
            "resource_id": "device-uid-1",
            "hostname": "AOT-50282",
            "site": "Customer-A",
        }
    )

    text = renderer.render(result(data=data), intent("last logged in user"))

    assert text == (
        "AOT-50282 — last logged in user: AOT\\example.user. Source: datto_rmm."
    )
    assert reasoner.calls


def test_ambiguous_endpoint_name_never_selects_first_result_or_exposes_candidate_details():
    reasoner = Reasoner([])
    renderer = GovernedTeamsResourceResponseRenderer(
        GovernedResourceEvidenceInterpreter(reasoner)
    )
    data = canonical_search_data(
        {
            "resource_id": "device-uid-a",
            "hostname": "SERVER",
            "site": "Customer-A",
        },
        {
            "resource_id": "device-uid-b",
            "hostname": "SERVER",
            "site": "Customer-B",
        },
    )

    text = renderer.render(result(data=data), intent(hostname="SERVER"))

    assert text == (
        "SERVER is ambiguous: 2 managed endpoints matched. "
        "Please specify the site/client or a durable resource identifier. "
        "No device was selected. Source: datto_rmm."
    )
    assert "Customer-A" not in text
    assert "Customer-B" not in text
    assert "device-uid" not in text
    assert reasoner.calls == []


def test_no_endpoint_match_returns_deterministic_no_match_without_reasoner():
    reasoner = Reasoner([])
    renderer = GovernedTeamsResourceResponseRenderer(
        GovernedResourceEvidenceInterpreter(reasoner)
    )

    text = renderer.render(
        result(data=canonical_search_data()),
        intent(hostname="MISSING-SERVER"),
    )

    assert text == (
        "MISSING-SERVER — no matching managed endpoint was found. Source: datto_rmm."
    )
    assert reasoner.calls == []


def test_unique_endpoint_match_requires_durable_resource_identity():
    renderer = GovernedTeamsResourceResponseRenderer(
        GovernedResourceEvidenceInterpreter(Reasoner([]))
    )
    data = canonical_search_data({"hostname": "SERVER", "site": "Customer-A"})

    with pytest.raises(LookupError, match="durable resource identity"):
        renderer.render(result(data=data), intent(hostname="SERVER"))


def test_search_result_missing_canonical_matches_fails_closed():
    renderer = GovernedTeamsResourceResponseRenderer(
        GovernedResourceEvidenceInterpreter(Reasoner([]))
    )

    with pytest.raises(RuntimeError, match="canonical resource_matches"):
        renderer.render(result(), intent())


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
