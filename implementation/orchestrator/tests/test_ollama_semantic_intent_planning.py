from __future__ import annotations

from dataclasses import dataclass

import pytest

from orchestrator.ollama_semantic_intent_planning import OllamaSemanticIntentPlanningReasoner


@dataclass
class FakeClient:
    response: dict
    calls: list | None = None

    def complete(self, **kwargs):
        if self.calls is None:
            self.calls = []
        self.calls.append(kwargs)
        return dict(self.response)


def _base_response(status: str) -> dict:
    return {
        "status": status,
        "context_view": "semantic_knowledge",
        "context_query": "",
        "context_purpose": "",
        "plan_steps": [],
        "rationale_summary": "",
        "unresolved_requirements": [],
        "gap_summary": "",
    }


def test_reasoner_requests_only_governed_context_view():
    response = _base_response("request_context")
    response.update(
        {
            "context_view": "capability_registry",
            "context_query": "endpoint hostname",
            "context_purpose": "discover governed fulfillment capabilities",
        }
    )
    reasoner = OllamaSemanticIntentPlanningReasoner(FakeClient(response))
    turn = reasoner.next_turn(intent={"goal": "retrieve_fact"}, context={}, history=())
    assert turn.status == "request_context"
    assert turn.context_request is not None
    assert turn.context_request.view == "capability_registry"
    assert turn.context_request.query == {"query": "endpoint hostname"}


def test_reasoner_builds_provider_neutral_capability_plan():
    response = _base_response("propose_plan")
    response.update(
        {
            "plan_steps": [
                {
                    "capability_name": "endpoint.device.search",
                    "purpose": "retrieve endpoint facts",
                    "required_facts": ["endpoint.hostname"],
                    "expected_evidence": ["endpoint.hostname"],
                }
            ],
            "rationale_summary": "governed capability can retrieve the requested fact",
        }
    )
    reasoner = OllamaSemanticIntentPlanningReasoner(FakeClient(response))
    turn = reasoner.next_turn(intent={"goal": "retrieve_fact"}, context={}, history=())
    assert turn.status == "propose_plan"
    assert turn.plan is not None
    assert turn.plan.steps[0].capability_name == "endpoint.device.search"


def test_reasoner_declares_gap_without_inventing_route():
    response = _base_response("declare_gap")
    response["gap_summary"] = "no governed fulfillment route is established"
    reasoner = OllamaSemanticIntentPlanningReasoner(FakeClient(response))
    turn = reasoner.next_turn(intent={"goal": "retrieve_fact"}, context={}, history=())
    assert turn.status == "declare_gap"
    assert turn.gap_summary == "no governed fulfillment route is established"


def test_reasoner_rejects_unknown_context_view_even_if_model_returns_it():
    response = _base_response("request_context")
    response.update(
        {
            "context_view": "provider_api",
            "context_query": "anything",
            "context_purpose": "invalid",
        }
    )
    reasoner = OllamaSemanticIntentPlanningReasoner(FakeClient(response))
    with pytest.raises(PermissionError):
        reasoner.next_turn(intent={"goal": "retrieve_fact"}, context={}, history=())


def test_reasoner_schema_exposes_only_context_views_not_already_supplied():
    response = _base_response("request_context")
    response.update(
        {
            "context_view": "evidence_catalog",
            "context_query": "operating system display version",
            "context_purpose": "inspect governed evidence availability",
        }
    )
    client = FakeClient(response)
    reasoner = OllamaSemanticIntentPlanningReasoner(client)
    turn = reasoner.next_turn(
        intent={"goal": "retrieve_fact"},
        context={
            "semantic_knowledge": {"items": []},
            "capability_registry": {"items": []},
        },
        history=(),
    )
    assert turn.status == "request_context"
    assert client.calls is not None
    schema = client.calls[0]["schema"]
    assert schema["properties"]["context_view"]["enum"] == [
        "system_registry",
        "evidence_catalog",
        "derivation_registry",
    ]


def test_reasoner_rejects_model_request_for_context_already_supplied():
    response = _base_response("request_context")
    response.update(
        {
            "context_view": "semantic_knowledge",
            "context_query": "operating system display version",
            "context_purpose": "repeat supplied semantic context",
        }
    )
    reasoner = OllamaSemanticIntentPlanningReasoner(FakeClient(response))
    with pytest.raises(PermissionError, match="not requestable"):
        reasoner.next_turn(
            intent={"goal": "retrieve_fact"},
            context={"semantic_knowledge": {"items": []}},
            history=(),
        )
