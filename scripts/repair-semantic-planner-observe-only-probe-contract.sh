#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START SEMANTIC PLANNER OBSERVE-ONLY PROBE CONTRACT REPAIR =========="
echo "========== SECTION 1: CURRENT STATE =========="
git rev-parse --short HEAD
git status --short

PY="/home/al/projects/jason/.venv/bin/python"
if [ ! -x "$PY" ]; then
  echo "ERROR: project Python not found at $PY"
  exit 20
fi

echo "========== SECTION 2: ALIGN PROBE WITH ACTUAL OLLAMA PLANNING CONTRACT =========="
cat > implementation/runtime_service/tests/test_semantic_planner_observe_only_probe.py <<'PY'
from __future__ import annotations

import json
from dataclasses import replace

from jason_runtime.composition import RuntimeSettings, build_disabled_semantic_intent_planner
from orchestrator.ollama_reasoning import OllamaStructuredJsonClient
from orchestrator.planning_context_views import (
    GovernedPlanningContextCatalog,
    StaticPlanningContextProvider,
)


class ScriptedTransport:
    def __init__(self):
        self.calls = []
        self.responses = [
            {
                "status": "request_context",
                "context_view": "capability_registry",
                "context_query": "endpoint device search",
                "context_purpose": "find a governed capability that can retrieve the requested endpoint fact",
                "plan_steps": [],
                "rationale_summary": "",
                "unresolved_requirements": [],
                "gap_summary": "",
            },
            {
                "status": "propose_plan",
                "context_view": "semantic_knowledge",
                "context_query": "",
                "context_purpose": "",
                "plan_steps": [
                    {
                        "capability_name": "endpoint.device.search",
                        "purpose": "retrieve the requested governed endpoint fact",
                        "required_facts": ["endpoint.hostname"],
                        "expected_evidence": ["endpoint.hostname"],
                    }
                ],
                "rationale_summary": "The governed capability registry exposes a capability that can retrieve the requested endpoint fact.",
                "unresolved_requirements": [],
                "gap_summary": "",
            },
        ]

    def request(self, **kwargs):
        self.calls.append(kwargs)
        if not self.responses:
            raise AssertionError("unexpected additional Ollama call")
        payload = self.responses.pop(0)
        return {"message": {"content": json.dumps(payload)}}


def test_semantic_planner_runs_iteratively_without_execution(monkeypatch):
    monkeypatch.setenv("JASON_OLLAMA_MODEL", "test-model")
    settings = replace(RuntimeSettings.from_env(), semantic_planner_enabled=True)
    transport = ScriptedTransport()
    client = OllamaStructuredJsonClient(transport=transport, model="test-model")
    catalog = GovernedPlanningContextCatalog(
        providers={
            "capabilities": StaticPlanningContextProvider(
                view_name="capabilities",
                records=(
                    {
                        "capability_name": "endpoint.device.search",
                        "display_name": "Endpoint Device Search",
                    },
                ),
                searchable_fields=("capability_name", "display_name"),
            )
        }
    )
    planner = build_disabled_semantic_intent_planner(
        settings=settings,
        client=client,
        context_catalog=catalog,
    )
    assert planner is not None

    outcome = planner.plan(
        intent={
            "resource_type": "endpoint",
            "resource_selector": {"hostname": "AOT-EXAMPLE"},
            "requested_facts": ["endpoint.hostname"],
            "permission_mode": "observe",
        }
    )

    assert outcome.status == "planned"
    assert outcome.iterations_used == 2
    assert outcome.context_requests_used == 1
    assert outcome.plan is not None
    assert [step.capability_name for step in outcome.plan.steps] == [
        "endpoint.device.search"
    ]
    assert len(transport.calls) == 2

    first_user_payload = json.loads(transport.calls[0]["json"]["messages"][1]["content"])
    second_user_payload = json.loads(transport.calls[1]["json"]["messages"][1]["content"])
    assert first_user_payload["governed_context"] == {}
    assert "capability_registry" in second_user_payload["governed_context"]
    assert second_user_payload["governed_context"]["capability_registry"]["capability_names"] == [
        "endpoint.device.search"
    ] or tuple(second_user_payload["governed_context"]["capability_registry"]["capability_names"]) == (
        "endpoint.device.search",
    )
PY

echo "UPDATED: implementation/runtime_service/tests/test_semantic_planner_observe_only_probe.py"

echo "========== SECTION 3: STATIC VALIDATION =========="ngit diff --check

echo "========== SECTION 4: FOCUSED TESTS =========="n"$PY" -m pytest -q \
  implementation/orchestrator/tests/test_semantic_intent_planning_loop.py \
  implementation/orchestrator/tests/test_planning_context_views.py \
  implementation/orchestrator/tests/test_planning_context_reader.py \
  implementation/orchestrator/tests/test_ollama_semantic_intent_planning.py \
  implementation/runtime_service/tests/test_semantic_planner_composition.py \
  implementation/runtime_service/tests/test_semantic_planner_observe_only_probe.py

echo "========== SECTION 5: CHANGE STATE =========="ngit status --short

echo "========== RESULT =========="necho "Observe-only runtime probe now uses the actual Ollama semantic planning schema and verifies a two-turn governed planning cycle."
echo "The probe does not execute the proposed capability."
echo "NO RUNTIME ACTIVATION PERFORMED."
echo "NO DEPLOYMENT PERFORMED."
echo "NO COMMIT OR PUSH OF WORKTREE CHANGES PERFORMED."
echo "========== END SEMANTIC PLANNER OBSERVE-ONLY PROBE CONTRACT REPAIR =========="
