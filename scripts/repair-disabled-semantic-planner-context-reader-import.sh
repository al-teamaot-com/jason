#!/usr/bin/env bash
set -euo pipefail

printf '%s\n' '========== START DISABLED SEMANTIC PLANNER CONTEXT READER IMPORT REPAIR =========='
printf '%s\n' '========== SECTION 1: CURRENT STATE =========='
git rev-parse --short HEAD
git status --short

PY="/home/al/projects/jason/.venv/bin/python"
if [ ! -x "$PY" ]; then
  echo "ERROR: project Python not found at $PY"
  exit 20
fi

printf '%s\n' '========== SECTION 2: ALIGN COMPOSITION WITH EXISTING ADAPTER CONTRACT =========='
"$PY" - <<'PY'
from pathlib import Path

path = Path('implementation/runtime_service/src/jason_runtime/composition.py')
text = path.read_text()
old_import = 'from orchestrator.planning_context_reader import GovernedPlanningContextReader\n'
new_import = 'from orchestrator.planning_context_reader import GovernedPlanningContextReaderAdapter\n'
if old_import in text:
    text = text.replace(old_import, new_import, 1)
elif new_import not in text:
    raise SystemExit('expected planning context reader import not found')

old_ctor = '    reader = GovernedPlanningContextReader(catalog=context_catalog)\n'
new_ctor = '    reader = GovernedPlanningContextReaderAdapter(catalog=context_catalog)\n'
if old_ctor in text:
    text = text.replace(old_ctor, new_ctor, 1)
elif new_ctor not in text:
    raise SystemExit('expected planning context reader construction not found')

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
printf '%s\n' 'Disabled semantic planner composition now uses the existing governed context reader adapter contract.'
printf '%s\n' 'No planning-loop contract was renamed or weakened.'
printf '%s\n' 'NO RUNTIME ACTIVATION PERFORMED.'
printf '%s\n' 'NO DEPLOYMENT PERFORMED.'
printf '%s\n' 'NO COMMIT OR PUSH OF WORKTREE CHANGES PERFORMED.'
printf '%s\n' '========== END DISABLED SEMANTIC PLANNER CONTEXT READER IMPORT REPAIR =========='
