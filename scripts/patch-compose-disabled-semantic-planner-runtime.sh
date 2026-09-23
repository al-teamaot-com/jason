#!/usr/bin/env bash
set -euo pipefail

printf '%s\n' '========== START DISABLED SEMANTIC PLANNER RUNTIME COMPOSITION =========='
printf '%s\n' '========== SECTION 1: PRECONDITIONS =========='
git rev-parse --short HEAD
git status --short

printf '%s\n' '========== SECTION 2: ADD DISABLED RUNTIME COMPOSITION =========='
/home/al/projects/jason/.venv/bin/python - <<'PY'
from pathlib import Path

path = Path('implementation/runtime_service/src/jason_runtime/composition.py')
text = path.read_text()

imports = '''from orchestrator.ollama_semantic_intent_planning import OllamaSemanticIntentPlanningReasoner\nfrom orchestrator.planning_context_reader import GovernedPlanningContextReader\nfrom orchestrator.planning_context_views import GovernedPlanningContextCatalog\nfrom orchestrator.semantic_intent_planning_loop import (\n    BoundedSemanticIntentPlanningLoop,\n    IntentPlanningBudget,\n)\n'''

marker = 'from orchestrator.ollama_action_reasoning import OllamaActionIntentReasoner\n'
if imports not in text:
    if marker not in text:
        raise SystemExit('expected Ollama action reasoning import marker not found')
    text = text.replace(marker, marker + imports, 1)

if 'semantic_planner_enabled: bool = False' not in text:
    marker = '    ollama_model: str\n'
    if marker not in text:
        raise SystemExit('RuntimeSettings ollama_model marker not found')
    text = text.replace(marker, marker + '    semantic_planner_enabled: bool = False\n', 1)

if 'semantic_planner_enabled=os.getenv(' not in text:
    marker = '            ollama_model=os.getenv("JASON_OLLAMA_MODEL", "").strip(),\n'
    if marker not in text:
        raise SystemExit('RuntimeSettings from_env ollama_model marker not found')
    addition = '''            semantic_planner_enabled=os.getenv(\n                "JASON_SEMANTIC_PLANNER_ENABLED", "false"\n            ).strip().casefold() in {"1", "true", "yes", "on"},\n'''
    text = text.replace(marker, marker + addition, 1)

helper_name = 'def build_disabled_semantic_intent_planner('
if helper_name not in text:
    insert_marker = '\n\n@dataclass(frozen=True, slots=True)\nclass ConnectorEventAudit:'
    if insert_marker not in text:
        raise SystemExit('ConnectorEventAudit insertion marker not found')
    helper = '''\n\ndef build_disabled_semantic_intent_planner(\n    *,\n    settings: RuntimeSettings,\n    client: OllamaStructuredJsonClient,\n    context_catalog: GovernedPlanningContextCatalog,\n) -> BoundedSemanticIntentPlanningLoop | None:\n    \"\"\"Compose the semantic planner only when explicitly enabled.\n\n    This helper intentionally performs no execution wiring. The returned planner can\n    reason only over governed context snapshots and can only propose provider-neutral\n    capability plans.\n    \"\"\"\n    if not settings.semantic_planner_enabled:\n        return None\n\n    reasoner = OllamaSemanticIntentPlanningReasoner(client=client)\n    reader = GovernedPlanningContextReader(catalog=context_catalog)\n    return BoundedSemanticIntentPlanningLoop(\n        reasoner=reasoner,\n        context_reader=reader,\n        budget=IntentPlanningBudget(max_iterations=6, max_context_requests=6),\n    )\n'''
    text = text.replace(insert_marker, helper + insert_marker, 1)

path.write_text(text)
print(f'WROTE: {path}')
PY

printf '%s\n' '========== SECTION 3: ADD COMPOSITION TESTS =========='
cat > implementation/runtime_service/tests/test_semantic_planner_composition.py <<'PY'
from __future__ import annotations

from dataclasses import replace

from jason_runtime.composition import RuntimeSettings, build_disabled_semantic_intent_planner
from orchestrator.ollama_reasoning import OllamaStructuredJsonClient
from orchestrator.planning_context_views import GovernedPlanningContextCatalog


class NoopTransport:
    def request(self, **kwargs):
        raise AssertionError('no model call expected during composition')


def _settings() -> RuntimeSettings:
    return RuntimeSettings.from_env()


def test_semantic_planner_is_disabled_by_default(monkeypatch):
    monkeypatch.setenv('JASON_OLLAMA_MODEL', 'test-model')
    settings = _settings()
    planner = build_disabled_semantic_intent_planner(
        settings=settings,
        client=OllamaStructuredJsonClient(transport=NoopTransport(), model='test-model'),
        context_catalog=GovernedPlanningContextCatalog(providers={}),
    )
    assert planner is None


def test_semantic_planner_can_be_composed_without_execution_wiring(monkeypatch):
    monkeypatch.setenv('JASON_OLLAMA_MODEL', 'test-model')
    settings = replace(_settings(), semantic_planner_enabled=True)
    planner = build_disabled_semantic_intent_planner(
        settings=settings,
        client=OllamaStructuredJsonClient(transport=NoopTransport(), model='test-model'),
        context_catalog=GovernedPlanningContextCatalog(providers={}),
    )
    assert planner is not None
    assert planner.budget.max_iterations == 6
    assert planner.budget.max_context_requests == 6
PY

printf '%s\n' 'WROTE: implementation/runtime_service/tests/test_semantic_planner_composition.py'

printf '%s\n' '========== SECTION 4: STATIC VALIDATION =========='
git diff --check

printf '%s\n' '========== SECTION 5: FOCUSED TESTS =========='
/home/al/projects/jason/.venv/bin/python -m pytest -q \
  implementation/orchestrator/tests/test_semantic_intent_planning_loop.py \
  implementation/orchestrator/tests/test_planning_context_views.py \
  implementation/orchestrator/tests/test_planning_context_reader.py \
  implementation/orchestrator/tests/test_ollama_semantic_intent_planning.py \
  implementation/runtime_service/tests/test_semantic_planner_composition.py

printf '%s\n' '========== SECTION 6: CHANGE STATE =========='
git status --short

printf '%s\n' '========== RESULT =========='
printf '%s\n' 'Semantic planner can now be composed behind an explicit disabled-by-default runtime flag.'
printf '%s\n' 'No execution path is connected.'
printf '%s\n' 'No provider, connector, tool, agent, credential, or action authority is granted.'
printf '%s\n' 'NO DEPLOYMENT PERFORMED.'
printf '%s\n' 'NO COMMIT OR PUSH OF WORKTREE CHANGES PERFORMED.'
printf '%s\n' '========== END DISABLED SEMANTIC PLANNER RUNTIME COMPOSITION =========='
