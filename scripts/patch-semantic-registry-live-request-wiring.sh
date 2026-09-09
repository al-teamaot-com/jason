#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START SEMANTIC REGISTRY LIVE REQUEST WIRING =========="
echo "========== SECTION 1: PRECONDITIONS =========="
echo "HEAD: $(git rev-parse --short HEAD)"

DIRTY="$(git status --porcelain | grep -v '^?? FETCH_HEAD$' || true)"
if [[ -n "$DIRTY" ]]; then
  echo "ERROR: worktree must be clean before live request wiring."
  printf '%s\n' "$DIRTY"
  exit 20
fi

echo "========== SECTION 2: LOCATE CURRENT REQUEST FACT CANONICALIZATION =========="
MATCHES="$(grep -RIl --exclude='test_*' --exclude='*.md' --exclude='*.sh' 'canonicalize_requested_facts' implementation/orchestrator implementation 2>/dev/null || true)"
if [[ -z "$MATCHES" ]]; then
  echo "ERROR: could not locate current canonicalize_requested_facts runtime call site."
  exit 21
fi
printf '%s\n' "$MATCHES"

TARGET="$(printf '%s\n' "$MATCHES" | head -n 1)"
echo "TARGET: $TARGET"

cp "$TARGET" "$TARGET.semantic-registry-wiring.bak"

python3 - "$TARGET" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text()

if "SemanticFactResolver" not in text:
    import_anchor = "from orchestrator.canonical_fact_vocabulary import"
    if import_anchor in text:
        lines = text.splitlines()
        insert_at = 0
        for i, line in enumerate(lines):
            if line.startswith("from orchestrator.") or line.startswith("import "):
                insert_at = i + 1
        lines.insert(insert_at, "from orchestrator.semantic_fact_resolver import DEFAULT_SEMANTIC_FACT_RESOLVER")
        text = "\n".join(lines) + ("\n" if path.read_text().endswith("\n") else "")
    else:
        text = "from orchestrator.semantic_fact_resolver import DEFAULT_SEMANTIC_FACT_RESOLVER\n" + text

old = ".canonicalize_requested_facts("
if old not in text:
    raise SystemExit("ERROR: expected canonicalize_requested_facts call not found in target")

# Preserve surrounding arguments and behavior while replacing only the owning resolver.
# The compatibility resolver exposes canonicalize_requested_facts with the same contract.
text = text.replace(old, ".canonicalize_requested_facts(", 1)

# Replace the object immediately preceding the first call when it is a known vocabulary symbol.
for symbol in (
    "DEFAULT_CANONICAL_FACT_VOCABULARY",
    "self._canonical_fact_vocabulary",
    "self.canonical_fact_vocabulary",
    "canonical_fact_vocabulary",
):
    needle = symbol + ".canonicalize_requested_facts("
    if needle in text:
        text = text.replace(
            needle,
            "DEFAULT_SEMANTIC_FACT_RESOLVER.canonicalize_requested_facts(",
            1,
        )
        break
else:
    raise SystemExit("ERROR: found method call but could not identify its vocabulary owner safely")

path.write_text(text)
PY

rm -f "$TARGET.semantic-registry-wiring.bak"

echo "UPDATED: $TARGET"

echo "========== SECTION 3: STATIC VALIDATION =========="ngit diff --check

echo "========== SECTION 4: FOCUSED TESTS =========="n.venv/bin/python -m pytest -q \
  implementation/orchestrator/tests/test_semantic_fact_resolver.py \
  implementation/orchestrator/tests/test_semantic_knowledge_seed.py \
  implementation/orchestrator/tests/test_canonical_fact_vocabulary.py \
  implementation/orchestrator/tests/test_semantic_resource_request.py

echo "========== SECTION 5: CHANGE STATE =========="ngit status --short

echo "========== RESULT =========="necho "Live request fact canonicalization now consults the Semantic Knowledge Registry first through the compatibility resolver."
echo "Legacy vocabulary remains fallback for concepts not yet migrated."
echo "NO DEPLOYMENT PERFORMED."
echo "NO COMMIT OR PUSH OF WORKTREE CHANGES PERFORMED."
echo "========== END SEMANTIC REGISTRY LIVE REQUEST WIRING =========="