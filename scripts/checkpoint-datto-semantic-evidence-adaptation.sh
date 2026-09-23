#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START DATTO SEMANTIC EVIDENCE ADAPTATION CHECKPOINT =========="
echo "========== SECTION 1: VALIDATE CHANGE SET =========="

allowed=(
  "implementation/connectors/datto_rmm/connector.py"
  "implementation/connectors/datto_rmm/semantic_evidence.py"
  "implementation/connectors/tests/test_datto_semantic_evidence.py"
)

unexpected=""
while IFS= read -r line; do
  [[ -z "$line" ]] && continue
  path="${line:3}"
  [[ "$path" == "FETCH_HEAD" ]] && continue
  ok=0
  for expected in "${allowed[@]}"; do
    if [[ "$path" == "$expected" ]]; then
      ok=1
      break
    fi
  done
  if [[ $ok -ne 1 ]]; then
    unexpected+="$line"$'\n'
  fi
done < <(git status --porcelain)

if [[ -n "$unexpected" ]]; then
  echo "ERROR: unexpected worktree changes present."
  printf '%s' "$unexpected"
  exit 20
fi

echo "PASS: local changes are limited to Datto semantic evidence adaptation."

PY=.venv/bin/python
if [[ ! -x "$PY" ]]; then
  echo "ERROR: .venv/bin/python is required."
  exit 21
fi

echo "========== SECTION 2: REVALIDATE =========="
git diff --check
$PY -m py_compile \
  implementation/connectors/datto_rmm/semantic_evidence.py \
  implementation/connectors/datto_rmm/connector.py
$PY -m pytest -q \
  implementation/connectors/tests/test_datto_semantic_evidence.py \
  implementation/connectors/tests/test_datto_rmm_connector.py \
  implementation/orchestrator/tests/test_resource_evidence.py \
  implementation/orchestrator/tests/test_semantic_request_bridge.py

echo "========== SECTION 3: COMMIT =========="
git add \
  implementation/connectors/datto_rmm/connector.py \
  implementation/connectors/datto_rmm/semantic_evidence.py \
  implementation/connectors/tests/test_datto_semantic_evidence.py

if git diff --cached --quiet; then
  echo "NOTE: no Datto semantic evidence changes are staged; no new commit required."
else
  git commit -m "Adapt Datto device evidence into semantic contexts"
fi

echo "========== SECTION 4: PUSH =========="
bash scripts/jason-push-checkpoint.sh

echo "========== FINAL STATUS =========="
git log -1 --oneline --decorate
echo "PASS: Datto semantic evidence adaptation is durable in GitHub."
echo "========== END DATTO SEMANTIC EVIDENCE ADAPTATION CHECKPOINT =========="
