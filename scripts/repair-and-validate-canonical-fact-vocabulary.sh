#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START CANONICAL FACT VOCABULARY REPAIR + VALIDATION =========="

echo "========== SECTION 1: CURRENT STATE =========="
git status --short

echo "========== SECTION 2: REPAIR RESOURCE INTERPRETER IDEMPOTENTLY =========="
python3 - <<'PY'
from pathlib import Path
import re

p = Path('implementation/orchestrator/conversation_resource_intent.py')
s = p.read_text(encoding='utf-8')

import_line = 'from .canonical_fact_vocabulary import CanonicalFactVocabulary\n'
anchor = 'from .resource_inquiry import GovernedResourceInquiryPlanner, ResourceInquiry\n'
if import_line not in s:
    if anchor not in s:
        raise SystemExit('ERROR: resource intent import anchor missing')
    s = s.replace(anchor, import_line + anchor, 1)

if 'fact_vocabulary: CanonicalFactVocabulary | None = None' not in s:
    pattern = r'(class ReasonedResourceInquiryInterpreter:\n\s+reasoner: StructuredResourceInquiryReasoner\n)'
    s, count = re.subn(
        pattern,
        r'\1    fact_vocabulary: CanonicalFactVocabulary | None = None\n',
        s,
        count=1,
    )
    if count != 1:
        raise SystemExit('ERROR: reasoned interpreter declaration not found')

if 'requested_facts=normalized_facts,' not in s:
    pattern = re.compile(
        r'(?P<indent>\s*)return ResourceInquiry\(\n'
        r'(?P<body>\s*resource_type=resource_type,\n'
        r'\s*resource_selector=normalized_selector,\n)'
        r'\s*requested_facts=tuple\(str\(item\)\.strip\(\) for item in requested_facts\),\n'
    )
    match = pattern.search(s)
    if not match:
        raise SystemExit('ERROR: requested fact construction not found and normalized form absent')
    indent = match.group('indent')
    body = match.group('body')
    replacement = (
        f'{indent}normalized_facts = tuple(str(item).strip() for item in requested_facts)\n'
        f'{indent}if self.fact_vocabulary is not None:\n'
        f'{indent}    normalized_facts = tuple(\n'
        f'{indent}        self.fact_vocabulary.canonicalize(item)\n'
        f'{indent}        for item in normalized_facts\n'
        f'{indent}    )\n\n'
        f'{indent}return ResourceInquiry(\n'
        f'{body}'
        f'{indent}    requested_facts=normalized_facts,\n'
    )
    s = s[:match.start()] + replacement + s[match.end():]

p.write_text(s, encoding='utf-8')
print('PASS: resource interpreter canonical normalization present')
PY

echo "========== SECTION 3: REPAIR PRODUCTION COMPOSITION IDEMPOTENTLY =========="
python3 - <<'PY'
from pathlib import Path

p = Path('implementation/runtime_service/src/jason_runtime/composition.py')
s = p.read_text(encoding='utf-8')

imp = 'from orchestrator.canonical_fact_vocabulary import DEFAULT_CANONICAL_FACT_VOCABULARY\n'
anchor = 'from orchestrator.conversation_resource_intent import (\n'
if imp not in s:
    if anchor not in s:
        raise SystemExit('ERROR: composition import anchor missing')
    s = s.replace(anchor, imp + anchor, 1)

if 'fact_vocabulary=DEFAULT_CANONICAL_FACT_VOCABULARY,' not in s:
    needle = '''                    fact_hints=fact_hints,\n                )\n            ),\n'''
    replacement = '''                    fact_hints=fact_hints,\n                ),\n                fact_vocabulary=DEFAULT_CANONICAL_FACT_VOCABULARY,\n            ),\n'''
    if needle not in s:
        raise SystemExit('ERROR: production reasoned-fallback construction not found')
    s = s.replace(needle, replacement, 1)

p.write_text(s, encoding='utf-8')
print('PASS: production canonical vocabulary wiring present')
PY

echo "========== SECTION 4: VERIFY TEST FILES =========="
test -f implementation/orchestrator/canonical_fact_vocabulary.py
test -f implementation/orchestrator/tests/test_canonical_fact_vocabulary.py
grep -q 'test_reasoned_requested_facts_can_be_normalized_to_canonical_vocabulary' implementation/orchestrator/tests/test_conversation_resource_intent.py
echo "PASS: canonical vocabulary and regression tests present"

echo "========== SECTION 5: STATIC VALIDATION =========="
git diff --check
python3 -m py_compile \
  implementation/orchestrator/canonical_fact_vocabulary.py \
  implementation/orchestrator/conversation_resource_intent.py \
  implementation/runtime_service/src/jason_runtime/composition.py

echo "PASS: static validation"

echo "========== SECTION 6: FIND PROJECT TEST RUNNER =========="
PYTEST_CMD=()
for candidate in \
  .venv/bin/python \
  venv/bin/python \
  implementation/.venv/bin/python \
  implementation/venv/bin/python; do
  if [[ -x "$candidate" ]] && "$candidate" -c 'import pytest' >/dev/null 2>&1; then
    PYTEST_CMD=("$candidate" -m pytest)
    break
  fi
done
if [[ ${#PYTEST_CMD[@]} -eq 0 ]] && python3 -c 'import pytest' >/dev/null 2>&1; then
  PYTEST_CMD=(python3 -m pytest)
fi
if [[ ${#PYTEST_CMD[@]} -eq 0 ]] && command -v pytest >/dev/null 2>&1; then
  PYTEST_CMD=(pytest)
fi

if [[ ${#PYTEST_CMD[@]} -eq 0 ]]; then
  echo "ERROR: no existing pytest runner found."
  echo "Search locations checked: .venv, venv, implementation/.venv, implementation/venv, python3, PATH."
  exit 30
fi

echo "Pytest runner: ${PYTEST_CMD[*]}"

echo "========== SECTION 7: FOCUSED TESTS =========="
"${PYTEST_CMD[@]}" -q \
  implementation/orchestrator/tests/test_canonical_fact_vocabulary.py \
  implementation/orchestrator/tests/test_conversation_resource_intent.py \
  implementation/runtime_service/tests/test_composition.py

echo "========== SECTION 8: CHANGE STATE =========="
git status --short

echo "========== RESULT =========="
echo "Canonical fact vocabulary foundation repaired and validated."
echo "NO DEPLOYMENT PERFORMED."
echo "NO COMMIT OR PUSH PERFORMED."
echo "========== END CANONICAL FACT VOCABULARY REPAIR + VALIDATION =========="
