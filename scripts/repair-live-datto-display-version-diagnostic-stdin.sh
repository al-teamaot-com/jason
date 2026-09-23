#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START LIVE DATTO DISPLAY VERSION DIAGNOSTIC STDIN REPAIR =========="
echo "========== SECTION 1: CURRENT STATE =========="
git status --short

echo "========== SECTION 2: REPAIR DOCKER EXEC STDIN =========="
python3 - <<'PY'
from pathlib import Path

path = Path("scripts/diagnose-live-datto-display-version-evidence.sh")
text = path.read_text(encoding="utf-8")
old = "docker exec jason-runtime python - <<'PY'\n"
new = "docker exec -i jason-runtime python - <<'PY'\n"
if new in text:
    print(f"PASS: {path} already uses interactive stdin for docker exec")
elif old in text:
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print(f"UPDATED: {path}")
else:
    raise SystemExit("ERROR: docker exec diagnostic anchor not found")
PY

echo "========== SECTION 3: STATIC VALIDATION =========="
bash -n scripts/diagnose-live-datto-display-version-evidence.sh
git diff --check

echo "========== SECTION 4: RUN REPAIRED READ-ONLY DIAGNOSTIC =========="
bash scripts/diagnose-live-datto-display-version-evidence.sh

echo "========== SECTION 5: CHANGE STATE =========="
git status --short

echo "========== RESULT =========="
echo "The prior diagnostic produced no Python output because docker exec did not keep stdin open for the heredoc."
echo "The repaired diagnostic uses docker exec -i and executes the same read-only governed Datto evidence probe."
echo "NO PROVIDER MUTATION PERFORMED."
echo "NO DEPLOYMENT PERFORMED."
echo "NO COMMIT OR PUSH OF WORKTREE CHANGES PERFORMED."
echo "========== END LIVE DATTO DISPLAY VERSION DIAGNOSTIC STDIN REPAIR =========="
