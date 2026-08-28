#!/usr/bin/env bash
set -euo pipefail

printf '%s\n' '========== START DISABLED SEMANTIC PLANNER RUNTIME SETTINGS FIELD ORDER REPAIR =========='
printf '%s\n' '========== SECTION 1: CURRENT STATE =========='
git rev-parse --short HEAD
git status --short

PY='/home/al/projects/jason/.venv/bin/python'
if [ ! -x "$PY" ]; then
  echo 'ERROR: project Python not found.'
  exit 20
fi

printf '%s\n' '========== SECTION 2: RESTORE DATACLASS REQUIRED-BEFORE-DEFAULT FIELD ORDER =========='
"$PY" - <<'PY'
from pathlib import Path

path = Path('implementation/runtime_service/src/jason_runtime/composition.py')
text = path.read_text()

old = '''    ollama_url: str\n    ollama_model: str\n    semantic_planner_enabled: bool = False\n    allowed_machine_identities: frozenset[str]\n'''
new = '''    ollama_url: str\n    ollama_model: str\n    allowed_machine_identities: frozenset[str]\n    semantic_planner_enabled: bool = False\n'''

if old in text:
    text = text.replace(old, new, 1)
elif new in text:
    print('PASS: RuntimeSettings field order already repaired')
else:
    raise SystemExit('expected RuntimeSettings semantic planner field block not found')

# Ensure the composition uses the adapter contract established by the prior workstream.
text = text.replace(
    'from orchestrator.planning_context_reader import GovernedPlanningContextReader\n',
    'from orchestrator.planning_context_reader import GovernedPlanningContextReaderAdapter\n',
)
text = text.replace(
    'reader = GovernedPlanningContextReader(catalog=context_catalog)',
    'reader = GovernedPlanningContextReaderAdapter(catalog=context_catalog)',
)

path.write_text(text)
print(f'UPDATED: {path}')
PY

printf '%s\n' '========== SECTION 3: STATIC VALIDATION =========='
git diff --check

printf '%s\n' '========== SECTION 4: FOCUSED TESTS =========='
"$PY" -m pytest -q \
  implementation/orchestrator/tests/test_semantic_intent_planning_loop.py \
  implementation/orchestrator/tests/test_planning_context_views.py \
  implementation/orchestrator/tests/test_planning_context_reader.py \
  implementation/orchestrator/tests/test_ollama_semantic_intent_planning.py \
  implementation/runtime_service/tests/test_semantic_planner_composition.py

printf '%s\n' '========== SECTION 5: CHANGE STATE =========='
git status --short

printf '%s\n' '========== RESULT =========='
printf '%s\n' 'RuntimeSettings preserves Python dataclass required-before-default field ordering.'
printf '%s\n' 'Disabled semantic planner composition still uses the governed planning context reader adapter.'
printf '%s\n' 'NO RUNTIME ACTIVATION PERFORMED.'
printf '%s\n' 'NO DEPLOYMENT PERFORMED.'
printf '%s\n' 'NO COMMIT OR PUSH OF WORKTREE CHANGES PERFORMED.'
printf '%s\n' '========== END DISABLED SEMANTIC PLANNER RUNTIME SETTINGS FIELD ORDER REPAIR =========='
