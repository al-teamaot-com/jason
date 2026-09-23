#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START SEMANTIC REQUEST CONVERSATION BRIDGE REPAIR =========="
echo "========== SECTION 1: CURRENT STATE =========="
git status --short

PY=.venv/bin/python
if [[ ! -x "$PY" ]]; then
  echo "ERROR: .venv/bin/python is required."
  exit 21
fi

echo "========== SECTION 2: PRESERVE PERMISSION AUTHORITY THROUGH SEMANTIC IR =========="
$PY - <<'PY'
from pathlib import Path
p = Path('implementation/orchestrator/semantic_request_bridge.py')
s = p.read_text(encoding='utf-8')
old = '''        requested_facts: tuple[str, ...],\n        result_intent: str,\n        completeness_requirement: str,\n    ) -> SemanticResourceRequest:\n'''
new = '''        requested_facts: tuple[str, ...],\n        result_intent: str,\n        completeness_requirement: str,\n        permission_mode: str = "observe",\n    ) -> SemanticResourceRequest:\n'''
if old in s:
    s = s.replace(old, new, 1)
elif new not in s:
    raise SystemExit('ERROR: semantic bridge build signature anchor missing')
old = '''            result_intent=result_intent,\n            completeness_requirement=completeness_requirement,\n        )\n'''
new = '''            result_intent=result_intent,\n            completeness_requirement=completeness_requirement,\n            permission_mode=permission_mode,\n        )\n'''
if old in s:
    s = s.replace(old, new, 1)
elif new not in s:
    raise SystemExit('ERROR: semantic request construction anchor missing')
p.write_text(s, encoding='utf-8')
print('UPDATED:', p)
PY

$PY - <<'PY'
from pathlib import Path
p = Path('implementation/orchestrator/conversation_resource_intent.py')
s = p.read_text(encoding='utf-8')
old = '''            requested_facts=normalized_facts,\n            result_intent=result_intent,\n            completeness_requirement=completeness_requirement,\n        )\n'''
new = '''            requested_facts=normalized_facts,\n            result_intent=result_intent,\n            completeness_requirement=completeness_requirement,\n            permission_mode=str(proposed.get("permission_mode", "observe")).strip(),\n        )\n'''
if old in s:
    s = s.replace(old, new, 1)
elif new not in s:
    raise SystemExit('ERROR: semantic bridge call anchor missing')
p.write_text(s, encoding='utf-8')
print('UPDATED:', p)
PY

echo "========== SECTION 3: MAKE CURRENT RELATIONSHIP TEMPORAL PARSING STRUCTURAL =========="
$PY - <<'PY'
from pathlib import Path
p = Path('implementation/orchestrator/semantic_request_bridge.py')
s = p.read_text(encoding='utf-8')
old = '''    @staticmethod\n    def _temporal_semantics(human_text: str) -> str:\n        normalized = " ".join(human_text.casefold().split())\n        if any(phrase in normalized for phrase in ("last logged", "most recent", "last used", "last on")):\n            return "most_recent"\n        if any(phrase in normalized for phrase in ("currently", "right now", "is on", "using", "logged into")):\n            return "current"\n        return "unspecified"\n'''
new = '''    @staticmethod\n    def _temporal_semantics(human_text: str) -> str:\n        normalized = " ".join(human_text.casefold().split())\n        words = set(normalized.replace("?", " ").replace(".", " ").split())\n\n        if any(phrase in normalized for phrase in (\n            "last logged",\n            "most recent",\n            "last used",\n            "last on",\n        )):\n            return "most_recent"\n\n        # Current-state language is semantic rather than a fixed adjacent phrase.\n        # "What device is Lindsey Collins on?" contains the relationship operator\n        # as separated words, while "currently", "right now", "using", and\n        # "logged into" are explicit current-state forms.\n        if (\n            "currently" in words\n            or "right now" in normalized\n            or "using" in words\n            or "logged into" in normalized\n            or ("is" in words and "on" in words)\n        ):\n            return "current"\n\n        return "unspecified"\n'''
if old in s:
    s = s.replace(old, new, 1)
elif new not in s:
    raise SystemExit('ERROR: temporal semantics block missing')
p.write_text(s, encoding='utf-8')
print('UPDATED:', p)
PY

echo "========== SECTION 4: ADD REGRESSION COVERAGE =========="
cat >> implementation/orchestrator/tests/test_semantic_request_bridge.py <<'PY'


def test_semantic_bridge_rejects_execute_permission_mode():
    import pytest

    with pytest.raises(PermissionError, match="read-only"):
        bridge().build(
            human_text="What processor is on AOT-50282?",
            resource_type="endpoint",
            resource_selector={"hostname": "AOT-50282"},
            requested_facts=("processor",),
            result_intent="summary",
            completeness_requirement="sufficient",
            permission_mode="execute",
        )
PY

echo "========== SECTION 5: VALIDATE =========="
git diff --check
$PY -m py_compile \
  implementation/orchestrator/semantic_request_bridge.py \
  implementation/orchestrator/conversation_resource_intent.py
$PY -m pytest -q \
  implementation/orchestrator/tests/test_semantic_resource_request.py \
  implementation/orchestrator/tests/test_semantic_request_bridge.py \
  implementation/orchestrator/tests/test_conversation_resource_intent.py \
  implementation/orchestrator/tests/test_canonical_fact_vocabulary.py

echo "========== SECTION 6: CHANGE STATE =========="
git status --short

echo "========== RESULT =========="
echo "Semantic request conversation bridge repaired and validated."
echo "Current relationship semantics are structural rather than fixed-phrase only."
echo "Permission mode now survives semantic translation and non-observe authority fails closed."
echo "NO DEPLOYMENT PERFORMED."
echo "NO COMMIT OR PUSH OF WORKTREE CHANGES PERFORMED."
echo "========== END SEMANTIC REQUEST CONVERSATION BRIDGE REPAIR =========="
