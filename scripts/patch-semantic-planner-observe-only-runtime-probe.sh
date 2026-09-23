#!/usr/bin/env bash
set -euo pipefail

printf '%s\n' '========== START SEMANTIC PLANNER OBSERVE-ONLY RUNTIME PROBE =========='
printf '%s\n' '========== SECTION 1: PRECONDITIONS =========='
git rev-parse --short HEAD
git status --short

printf '%s\n' '========== SECTION 2: ADD OBSERVE-ONLY RUNTIME PROBE =========='
cat > implementation/runtime_service/tests/test_semantic_planner_observe_only_probe.py <<'PY'
from __future__ import annotations

from dataclasses import replace

from jason_runtime.composition import RuntimeSettings, build_disabled_semantic_intent_planner
from orchestrator.ollama_reasoning import OllamaStructuredJsonClient
from orchestrator.planning_context_views import GovernedPlanningContextCatalog, StaticPlanningContextProvider


class ScriptedTransport:
    def __init__(self):
        self.calls = 0

    def request(self, **kwargs):
        self.calls += 1
        if self.calls == 1:
            return {
                "message": {
                    "content": '{"status":"request_context","context_request":{"view":"capability_registry","query":{"resource_type":"endpoint"},"purpose":"inspect governed capabilities"}}'
                }
            }
        return {
            "message": {
                "content": '{"status":"propose_plan","plan":{"steps":[{"capability_name":"endpoint.device.search","purpose":"retrieve requested governed resource facts","required_facts":["endpoint.hostname"],"expected_evidence":["endpoint.hostname"]}],"rationale_summary":"use an approved governed capability","unresolved_requirements":[]}}'
            }
        }


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
    assert outcome.plan.steps[0].capability_name == "endpoint.device.search"
    assert transport.calls == 2
PY

printf '%s\n' 'WROTE: implementation/runtime_service/tests/test_semantic_planner_observe_only_probe.py'

printf '%s\n' '========== SECTION 3: STATIC VALIDATION =========='
git diff --check

printf '%s\n' '========== SECTION 4: FOCUSED TESTS =========='
/home/al/projects/jason/.venv/bin/python -m pytest -q \
  implementation/orchestrator/tests/test_semantic_intent_planning_loop.py \
  implementation/orchestrator/tests/test_planning_context_views.py \
  implementation/orchestrator/tests/test_planning_context_reader.py \
  implementation/orchestrator/tests/test_ollama_semantic_intent_planning.py \
  implementation/runtime_service/tests/test_semantic_planner_composition.py \
  implementation/runtime_service/tests/test_semantic_planner_observe_only_probe.py

printf '%s\n' '========== SECTION 5: CHANGE STATE =========='
git status --short

printf '%s\n' '========== RESULT =========='
printf '%s\n' 'Observe-only runtime probe added for iterative semantic planning.'
printf '%s\n' 'The probe validates context request -> governed context read -> revised plan proposal.'
printf '%s\n' 'NO EXECUTION PATH IS CONNECTED.'
printf '%s\n' 'NO PROVIDER, CONNECTOR, TOOL, AGENT, CREDENTIAL, OR ACTION AUTHORITY IS GRANTED.'
printf '%s\n' 'NO DEPLOYMENT PERFORMED.'
printf '%s\n' 'NO COMMIT OR PUSH OF WORKTREE CHANGES PERFORMED.'
printf '%s\n' '========== END SEMANTIC PLANNER OBSERVE-ONLY RUNTIME PROBE =========='
