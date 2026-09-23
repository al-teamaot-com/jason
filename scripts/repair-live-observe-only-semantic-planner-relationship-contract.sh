#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START LIVE OBSERVE-ONLY SEMANTIC PLANNER RELATIONSHIP CONTRACT REPAIR =========="
echo "========== SECTION 1: CURRENT STATE =========="
git rev-parse --short HEAD
git status --short

PY="/home/al/projects/jason/.venv/bin/python"
if [ ! -x "$PY" ]; then
  echo "ERROR: project Python not found at $PY"
  exit 20
fi

echo "========== SECTION 2: ALIGN PROBE WITH AUTHORITATIVE RELATIONSHIP CONTRACT =========="
"$PY" - <<'PY'
from pathlib import Path

path = Path("scripts/run-live-observe-only-semantic-planner-intent-probe.sh")
text = path.read_text()

old = '''        "source_concept_id": rel.source_concept_id,\n        "target_concept_id": rel.target_concept_id,\n'''
new = '''        "subject_type": rel.subject_type,\n        "target_type": rel.target_type,\n'''
if old not in text:
    raise SystemExit("expected stale relationship-field block not found")
text = text.replace(old, new, 1)

old_fields = 'searchable_fields=("relationship_id", "source_concept_id", "target_concept_id"),'
new_fields = 'searchable_fields=("relationship_id", "subject_type", "target_type"),'
if old_fields not in text:
    raise SystemExit("expected stale relationship searchable_fields not found")
text = text.replace(old_fields, new_fields, 1)

# Repair two previously malformed shell command joins in the probe if still present.
text = text.replace('echo "========== SECTION 3: CHANGE STATE =========="\\ngit status --short', 'echo "========== SECTION 3: CHANGE STATE =========="\ngit status --short')
text = text.replace('echo "========== RESULT =========="\\necho "Live local-Ollama semantic intent planning probe completed in observe-only mode."', 'echo "========== RESULT =========="\necho "Live local-Ollama semantic intent planning probe completed in observe-only mode."')

path.write_text(text)
print(f"UPDATED: {path}")
PY

echo "========== SECTION 3: STATIC VALIDATION =========="
git diff --check

echo "========== SECTION 4: CONTRACT SANITY =========="
"$PY" - <<'PY'
from orchestrator.semantic_knowledge_seed import build_trusted_semantic_registry

registry = build_trusted_semantic_registry()
relationships = registry.active_relationships()
for rel in relationships:
    assert isinstance(rel.relationship_id, str) and rel.relationship_id
    assert isinstance(rel.subject_type, str) and rel.subject_type
    assert isinstance(rel.target_type, str) and rel.target_type
print(f"PASS: {len(relationships)} active relationships use relationship_id/subject_type/target_type contract.")
PY

echo "========== SECTION 5: CHANGE STATE =========="
git status --short

echo "========== RESULT =========="
echo "Live observe-only planner probe now consumes the authoritative SemanticRelationshipDefinition contract."
echo "No semantic registry, runtime, provider, capability, or execution contract was changed."
echo "NO RUNTIME ACTIVATION PERFORMED."
echo "NO DEPLOYMENT PERFORMED."
echo "NO PROVIDER READ OR MUTATION PERFORMED."
echo "========== END LIVE OBSERVE-ONLY SEMANTIC PLANNER RELATIONSHIP CONTRACT REPAIR =========="
