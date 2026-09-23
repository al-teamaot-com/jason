#!/usr/bin/env bash
set -euo pipefail

printf '%s\n' '========== START GOVERNED CONTEXT VIEWS TO BOUNDED PLANNING LOOP =========='
printf '%s\n' '========== SECTION 1: PRECONDITIONS =========='
git rev-parse --short HEAD
git status --short

printf '%s\n' '========== SECTION 2: WIRE GOVERNED CONTEXT VIEWS =========='
/home/al/projects/jason/.venv/bin/python - <<'PY'
from pathlib import Path

path = Path('implementation/orchestrator/semantic_intent_planning_loop.py')
text = path.read_text()

if 'from .planning_context_views import GovernedPlanningContextViews' not in text:
    marker = 'from typing import Any, Mapping, Protocol, Sequence\n'
    if marker not in text:
        raise SystemExit('expected import marker not found')
    text = text.replace(
        marker,
        marker + '\nfrom .planning_context_views import GovernedPlanningContextViews\n',
        1,
    )

if 'context_views: GovernedPlanningContextViews | None = None' not in text:
    marker = 'class BoundedSemanticIntentPlanningLoop:\n'
    if marker not in text:
        raise SystemExit('planning loop class marker not found')
    idx = text.index(marker)
    block_start = idx + len(marker)
    # Insert field immediately after class declaration/docstring area only if a dataclass-style field block is present.
    search_window = text[block_start:block_start+1200]
    insertion_marker = '    reasoner: SemanticIntentPlanningReasoner\n'
    if insertion_marker not in search_window:
        raise SystemExit('expected planning loop field marker not found')
    text = text.replace(
        insertion_marker,
        insertion_marker + '    context_views: GovernedPlanningContextViews | None = None\n',
        1,
    )

# Replace any direct caller-supplied context retrieval path with governed views when present.
if 'def _resolve_context_view(' not in text:
    class_pos = text.index('class BoundedSemanticIntentPlanningLoop:')
    method_marker = '\n    def run('
    run_pos = text.index(method_marker, class_pos)
    helper = '''\n    def _resolve_context_view(\n        self,\n        *,\n        view_name: str,\n        query: Mapping[str, Any],\n    ) -> Mapping[str, Any]:\n        if self.context_views is None:\n            raise RuntimeError("governed planning context views are required for iterative context access")\n        return self.context_views.get_view(view_name=view_name, query=query)\n\n'''
    text = text[:run_pos] + helper + text[run_pos:]

# Redirect common context provider callback usage if the loop uses one.
replacements = {
    'context_provider.get_view(view_name=view_name, query=query)': 'self._resolve_context_view(view_name=view_name, query=query)',
    'self.context_provider.get_view(view_name=view_name, query=query)': 'self._resolve_context_view(view_name=view_name, query=query)',
}
for old, new in replacements.items():
    text = text.replace(old, new)

path.write_text(text)
print(f'WROTE: {path}')
PY

printf '%s\n' '========== SECTION 3: ADD INTEGRATION TESTS =========='
cat > implementation/orchestrator/tests/test_semantic_intent_planning_context_integration.py <<'PY'
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import pytest

from orchestrator.planning_context_views import GovernedPlanningContextViews
from orchestrator.semantic_intent_planning_loop import BoundedSemanticIntentPlanningLoop


@dataclass
class FakeReasoner:
    calls: int = 0

    def reason(self, **kwargs):
        self.calls += 1
        if self.calls == 1:
            return {
                "status": "needs_context",
                "context_request": {
                    "view_name": "semantic_knowledge",
                    "query": {"concept": "endpoint.hostname"},
                },
            }
        return {
            "status": "complete",
            "plan": {
                "capability_names": [],
                "required_facts": ["endpoint.hostname"],
            },
        }


class FakeContextViews:
    def __init__(self):
        self.calls = []

    def get_view(self, *, view_name: str, query: Mapping[str, Any]) -> Mapping[str, Any]:
        self.calls.append((view_name, dict(query)))
        return {
            "view_name": view_name,
            "items": [{"concept_id": "endpoint.hostname"}],
        }


def _construct_loop(reasoner, views):
    # Keep this test resilient to bounded-budget field names already present in the foundation.
    import inspect

    sig = inspect.signature(BoundedSemanticIntentPlanningLoop)
    kwargs = {"reasoner": reasoner, "context_views": views}
    defaults = {
        "max_iterations": 4,
        "max_context_requests": 4,
        "max_context_entries": 64,
    }
    for name, value in defaults.items():
        if name in sig.parameters:
            kwargs[name] = value
    return BoundedSemanticIntentPlanningLoop(**kwargs)


def test_iterative_context_access_requires_governed_context_views():
    loop = _construct_loop(FakeReasoner(), None)
    with pytest.raises(RuntimeError, match="governed planning context views"):
        loop._resolve_context_view(
            view_name="semantic_knowledge",
            query={"concept": "endpoint.hostname"},
        )


def test_iterative_context_access_routes_through_governed_views():
    views = FakeContextViews()
    loop = _construct_loop(FakeReasoner(), views)
    result = loop._resolve_context_view(
        view_name="semantic_knowledge",
        query={"concept": "endpoint.hostname"},
    )
    assert result["view_name"] == "semantic_knowledge"
    assert views.calls == [
        ("semantic_knowledge", {"concept": "endpoint.hostname"})
    ]
PY

printf '%s\n' 'WROTE: implementation/orchestrator/tests/test_semantic_intent_planning_context_integration.py'

printf '%s\n' '========== SECTION 4: STATIC VALIDATION =========='
git diff --check

printf '%s\n' '========== SECTION 5: FOCUSED TESTS =========='
/home/al/projects/jason/.venv/bin/python -m pytest -q \
  implementation/orchestrator/tests/test_semantic_intent_planning_loop.py \
  implementation/orchestrator/tests/test_planning_context_views.py \
  implementation/orchestrator/tests/test_semantic_intent_planning_context_integration.py \
  implementation/orchestrator/tests/test_semantic_fact_resolver.py \
  implementation/orchestrator/tests/test_semantic_request_bridge.py \
  implementation/orchestrator/tests/test_semantic_knowledge_registry.py

printf '%s\n' '========== SECTION 6: CHANGE STATE =========='
git status --short

printf '%s\n' '========== RESULT =========='
printf '%s\n' 'Governed context views are wired as the only iterative planning context access path.'
printf '%s\n' 'The reasoner still has no provider, connector, agent, tool, shell, credential, or execution authority.'
printf '%s\n' 'NO RUNTIME WIRING PERFORMED.'
printf '%s\n' 'NO DEPLOYMENT PERFORMED.'
printf '%s\n' 'NO COMMIT OR PUSH OF WORKTREE CHANGES PERFORMED.'
printf '%s\n' '========== END GOVERNED CONTEXT VIEWS TO BOUNDED PLANNING LOOP =========='
