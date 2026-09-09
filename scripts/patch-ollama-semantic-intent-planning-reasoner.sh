#!/usr/bin/env bash
set -euo pipefail

printf '%s\n' '========== START OLLAMA SEMANTIC INTENT PLANNING REASONER =========='
printf '%s\n' '========== SECTION 1: PRECONDITIONS =========='
git rev-parse --short HEAD
git status --short

printf '%s\n' '========== SECTION 2: ADD OLLAMA PLANNING REASONER =========='
cat > implementation/orchestrator/ollama_semantic_intent_planning.py <<'PY'
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .ollama_reasoning import OllamaStructuredJsonClient
from .semantic_intent_planning_loop import (
    FulfillmentPlanCandidate,
    FulfillmentPlanStepCandidate,
    PlanningContextRequest,
    PlanningTraceEntry,
    PlanningTurn,
)


@dataclass(frozen=True, slots=True)
class OllamaSemanticIntentPlanningReasoner:
    """Bounded provider-neutral planning over governed context snapshots only."""

    client: OllamaStructuredJsonClient

    def next_turn(
        self,
        *,
        intent: Mapping[str, Any],
        context: Mapping[str, Any],
        history: Sequence[PlanningTraceEntry],
    ) -> PlanningTurn:
        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["request_context", "propose_plan", "declare_gap"],
                },
                "context_view": {
                    "type": "string",
                    "enum": [
                        "semantic_knowledge",
                        "capability_registry",
                        "system_registry",
                        "evidence_catalog",
                        "derivation_registry",
                    ],
                },
                "context_query": {"type": "string"},
                "context_purpose": {"type": "string"},
                "plan_steps": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "capability_name": {"type": "string"},
                            "purpose": {"type": "string"},
                            "required_facts": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "expected_evidence": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                        "required": [
                            "capability_name",
                            "purpose",
                            "required_facts",
                            "expected_evidence",
                        ],
                    },
                },
                "rationale_summary": {"type": "string"},
                "unresolved_requirements": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "gap_summary": {"type": "string"},
            },
            "required": [
                "status",
                "context_view",
                "context_query",
                "context_purpose",
                "plan_steps",
                "rationale_summary",
                "unresolved_requirements",
                "gap_summary",
            ],
        }

        result = self.client.complete(
            system=(
                "You are Jason's bounded semantic fulfillment planner. Determine how the supplied "
                "provider-neutral intent can be satisfied using only governed context already supplied "
                "or by requesting one approved context view. You have no authority to execute anything. "
                "Never name or choose providers, connectors, agents, tools, URLs, shell commands, "
                "credentials, or secrets. Never invent facts or evidence. Request additional context when "
                "needed. A proposed plan may reference only capability names present in governed capability "
                "registry context. Prefer direct authoritative evidence; otherwise consider alternate governed "
                "capabilities or approved derivations represented in context. If no governed fulfillment path "
                "is established, declare a knowledge gap. Keep reasoning concise and structured."
            ),
            user=json.dumps(
                {
                    "intent": dict(intent),
                    "governed_context": dict(context),
                    "history": [
                        {
                            "iteration": item.iteration,
                            "status": item.status,
                            "context_view": item.context_view,
                        }
                        for item in history
                    ],
                },
                sort_keys=True,
            ),
            schema=schema,
            max_output_tokens=320,
        )

        status = str(result.get("status", "")).strip()
        if status == "request_context":
            view = str(result.get("context_view", "")).strip()
            query = str(result.get("context_query", "")).strip()
            purpose = str(result.get("context_purpose", "")).strip()
            return PlanningTurn(
                status="request_context",
                context_request=PlanningContextRequest(
                    view=view,
                    query={"query": query} if query else {},
                    purpose=purpose,
                ),
            )

        if status == "propose_plan":
            steps = []
            raw_steps = result.get("plan_steps", [])
            if not isinstance(raw_steps, list):
                raise ValueError("Ollama semantic planning plan_steps must be a list")
            for raw_step in raw_steps:
                if not isinstance(raw_step, Mapping):
                    raise ValueError("Ollama semantic planning step must be an object")
                steps.append(
                    FulfillmentPlanStepCandidate(
                        capability_name=str(raw_step.get("capability_name", "")).strip(),
                        purpose=str(raw_step.get("purpose", "")).strip(),
                        required_facts=tuple(
                            str(item).strip()
                            for item in raw_step.get("required_facts", [])
                            if str(item).strip()
                        ),
                        expected_evidence=tuple(
                            str(item).strip()
                            for item in raw_step.get("expected_evidence", [])
                            if str(item).strip()
                        ),
                    )
                )
            unresolved = tuple(
                str(item).strip()
                for item in result.get("unresolved_requirements", [])
                if str(item).strip()
            )
            return PlanningTurn(
                status="propose_plan",
                plan=FulfillmentPlanCandidate(
                    steps=tuple(steps),
                    rationale_summary=str(result.get("rationale_summary", "")).strip(),
                    unresolved_requirements=unresolved,
                ),
            )

        if status != "declare_gap":
            raise ValueError("Ollama semantic planning returned invalid status")
        return PlanningTurn(
            status="declare_gap",
            gap_summary=str(result.get("gap_summary", "")).strip(),
        )
PY
printf '%s\n' 'WROTE: implementation/orchestrator/ollama_semantic_intent_planning.py'

printf '%s\n' '========== SECTION 3: ADD CONTRACT TESTS =========='
cat > implementation/orchestrator/tests/test_ollama_semantic_intent_planning.py <<'PY'
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
PY
printf '%s\n' 'WROTE: implementation/orchestrator/tests/test_ollama_semantic_intent_planning.py'

printf '%s\n' '========== SECTION 4: STATIC VALIDATION =========='
git diff --check

printf '%s\n' '========== SECTION 5: FOCUSED TESTS =========='
/home/al/projects/jason/.venv/bin/python -m pytest -q \
  implementation/orchestrator/tests/test_ollama_semantic_intent_planning.py \
  implementation/orchestrator/tests/test_semantic_intent_planning_loop.py \
  implementation/orchestrator/tests/test_planning_context_views.py \
  implementation/orchestrator/tests/test_planning_context_reader.py \
  implementation/orchestrator/tests/test_semantic_fact_resolver.py \
  implementation/orchestrator/tests/test_semantic_request_bridge.py \
  implementation/orchestrator/tests/test_semantic_knowledge_registry.py

printf '%s\n' '========== SECTION 6: CHANGE STATE =========='
git status --short

printf '%s\n' '========== RESULT =========='
printf '%s\n' 'Ollama semantic intent planning reasoner added and validated against bounded governed planning contracts.'
printf '%s\n' 'The model can request only governed context views, propose only provider-neutral capability plans, or declare a knowledge gap.'
printf '%s\n' 'NO RUNTIME WIRING PERFORMED.'
printf '%s\n' 'NO DEPLOYMENT PERFORMED.'
printf '%s\n' 'NO COMMIT OR PUSH OF WORKTREE CHANGES PERFORMED.'
printf '%s\n' '========== END OLLAMA SEMANTIC INTENT PLANNING REASONER =========='
