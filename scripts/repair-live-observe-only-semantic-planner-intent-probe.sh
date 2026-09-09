#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START LIVE OBSERVE-ONLY SEMANTIC PLANNER INTENT PROBE REPAIR =========="
echo "========== SECTION 1: CURRENT STATE =========="
git rev-parse --short HEAD
git status --short

PY="/home/al/projects/jason/.venv/bin/python"
if [ ! -x "$PY" ]; then
  echo "ERROR: project Python not found at $PY"
  exit 20
fi

echo "========== SECTION 2: ALIGN PROBE WITH SEMANTIC CONCEPT CONTRACT =========="
"$PY" - <<'PY'
from pathlib import Path

path = Path('scripts/run-live-observe-only-semantic-planner-intent-probe.sh')
text = path.read_text()

old = '"canonical_name": concept.canonical_name,'
new = '"canonical_name": concept.canonical_label,'
if old in text:
    text = text.replace(old, new)
elif new not in text:
    raise SystemExit('expected semantic concept field reference not found')

text = text.replace(
    'echo "========== SECTION 3: CHANGE STATE =========="ngit status --short',
    'echo "========== SECTION 3: CHANGE STATE =========="\ngit status --short',
)
text = text.replace(
    'echo "========== RESULT =========="necho "Live local-Ollama semantic intent planning probe completed in observe-only mode."',
    'echo "========== RESULT =========="\necho "Live local-Ollama semantic intent planning probe completed in observe-only mode."',
)

path.write_text(text)
print(f'UPDATED: {path}')
PY

echo "========== SECTION 3: STATIC VALIDATION =========="
git diff --check

echo "========== SECTION 4: VERIFY PROBE CONTRACT =========="
grep -q 'concept.canonical_label' scripts/run-live-observe-only-semantic-planner-intent-probe.sh
if grep -q 'concept.canonical_name' scripts/run-live-observe-only-semantic-planner-intent-probe.sh; then
  echo "ERROR: stale semantic concept field reference remains."
  exit 21
fi

echo "========== SECTION 5: CHANGE STATE =========="
git status --short

echo "========== RESULT =========="
echo "Live observe-only planner probe now consumes the actual SemanticConcept canonical_label contract."
echo "No planner authority, provider access, execution path, or runtime activation was changed."
echo "NO DEPLOYMENT PERFORMED."
echo "NO COMMIT OR PUSH OF WORKTREE CHANGES PERFORMED."
echo "========== END LIVE OBSERVE-ONLY SEMANTIC PLANNER INTENT PROBE REPAIR =========="
