#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START SEMANTIC FACT RESOLVER TEST IMPORT REPAIR =========="
echo "========== SECTION 1: CURRENT STATE =========="
git status --short

echo "========== SECTION 2: ENSURE TRUSTED REGISTRY BUILDER TEST IMPORT =========="
.venv/bin/python - <<'PY'
from pathlib import Path

path = Path("implementation/orchestrator/tests/test_semantic_fact_resolver.py")
text = path.read_text()
needle = "from orchestrator.semantic_knowledge_seed import build_trusted_semantic_registry"
if needle in text:
    print(f"PASS: trusted semantic registry builder import already present in {path}")
else:
    lines = text.splitlines()
    insert_at = 0
    for index, line in enumerate(lines):
        if line.startswith("from ") or line.startswith("import "):
            insert_at = index + 1
        elif insert_at and line.strip():
            break
    lines.insert(insert_at, needle)
    path.write_text("\n".join(lines) + "\n")
    print(f"UPDATED: {path}")
PY

echo "========== SECTION 3: STATIC VALIDATION =========="
git diff --check

echo "========== SECTION 4: FOCUSED TESTS =========="
.venv/bin/python -m pytest -q \
  implementation/orchestrator/tests/test_semantic_fact_resolver.py \
  implementation/orchestrator/tests/test_semantic_request_bridge.py \
  implementation/orchestrator/tests/test_semantic_knowledge_seed.py \
  implementation/orchestrator/tests/test_conversation_resource_intent.py

echo "========== SECTION 5: CHANGE STATE =========="
git status --short

echo "========== RESULT =========="
echo "Semantic fact resolver batch-resolution tests now import the trusted registry builder explicitly."
echo "NO DEPLOYMENT PERFORMED."
echo "NO COMMIT OR PUSH OF WORKTREE CHANGES PERFORMED."
echo "========== END SEMANTIC FACT RESOLVER TEST IMPORT REPAIR =========="
