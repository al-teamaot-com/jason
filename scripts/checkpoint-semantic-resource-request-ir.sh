#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START SEMANTIC RESOURCE REQUEST IR CHECKPOINT =========="

echo "========== SECTION 1: VALIDATE CHANGE SET =========="
ALLOWED_ONE="implementation/orchestrator/semantic_resource_request.py"
ALLOWED_TWO="implementation/orchestrator/tests/test_semantic_resource_request.py"
UNEXPECTED=""
SEEN_ONE=0
SEEN_TWO=0
while IFS= read -r line; do
  [[ -z "$line" ]] && continue
  [[ "$line" == "?? FETCH_HEAD" ]] && continue
  path="${line:3}"
  case "$path" in
    "$ALLOWED_ONE") SEEN_ONE=1 ;;
    "$ALLOWED_TWO") SEEN_TWO=1 ;;
    *) UNEXPECTED+="$line"$'\n' ;;
  esac
done < <(git status --porcelain)

if [[ -n "$UNEXPECTED" ]]; then
  echo "ERROR: unexpected worktree changes present."
  printf '%s' "$UNEXPECTED"
  exit 20
fi

if [[ ! -f "$ALLOWED_ONE" || ! -f "$ALLOWED_TWO" ]]; then
  echo "ERROR: semantic IR source/test files are missing."
  git status --short
  exit 21
fi

if [[ "$SEEN_ONE" -eq 0 && "$SEEN_TWO" -eq 0 ]]; then
  if git ls-files --error-unmatch "$ALLOWED_ONE" >/dev/null 2>&1 && \
     git ls-files --error-unmatch "$ALLOWED_TWO" >/dev/null 2>&1; then
    echo "NOTE: semantic IR files are already tracked; validating whether a checkpoint is already durable."
  else
    echo "ERROR: semantic IR files exist but git does not report the expected workstream state."
    git status --short
    exit 22
  fi
fi

echo "PASS: worktree changes are limited to the semantic resource request IR foundation."

echo "========== SECTION 2: REVALIDATE =========="
git diff --check
.venv/bin/python -m py_compile "$ALLOWED_ONE"
.venv/bin/python -m pytest -q "$ALLOWED_TWO"

echo "========== SECTION 3: COMMIT =========="
git add "$ALLOWED_ONE" "$ALLOWED_TWO"
if git diff --cached --quiet; then
  echo "NOTE: no semantic IR changes are staged; no new commit required."
else
  git commit -m "Add provider-neutral semantic resource request IR"
fi

echo "========== SECTION 4: PUSH =========="
bash scripts/jason-push-checkpoint.sh

echo "========== FINAL STATUS =========="
git log -1 --oneline --decorate
echo "PASS: semantic resource request IR is durable in GitHub."
echo "========== END SEMANTIC RESOURCE REQUEST IR CHECKPOINT =========="