#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START SEMANTIC REGISTRY PRODUCTION COMPOSITION WIRING =========="
echo "========== SECTION 1: PRECONDITIONS =========="
echo "HEAD: $(git rev-parse --short HEAD)"

DIRTY="$(git status --porcelain | grep -v '^?? FETCH_HEAD$' || true)"
if [[ -n "$DIRTY" ]]; then
  echo "ERROR: worktree must be clean before production semantic composition wiring."
  printf '%s\n' "$DIRTY"
  exit 20
fi

echo "========== SECTION 2: WIRE REGISTRY-FIRST RESOLVER INTO REASONED RESOURCE INTERPRETER =========="
.venv/bin/python - <<'PY'
from pathlib import Path

path = Path("implementation/orchestrator/conversation_resource_intent.py")
text = path.read_text()

old_import = "from .canonical_fact_vocabulary import CanonicalFactVocabulary\n"
new_import = (
    "from .canonical_fact_vocabulary import CanonicalFactVocabulary\n"
    "from .semantic_fact_resolver import SemanticFactResolver\n"
)
if "from .semantic_fact_resolver import SemanticFactResolver" not in text:
    if old_import not in text:
        raise SystemExit("ERROR: canonical vocabulary import anchor missing")
    text = text.replace(old_import, new_import, 1)

old_field = "    fact_vocabulary: CanonicalFactVocabulary | None = None\n"
new_field = (
    "    fact_vocabulary: CanonicalFactVocabulary | None = None\n"
    "    fact_resolver: SemanticFactResolver | None = None\n"
)
if "fact_resolver: SemanticFactResolver | None = None" not in text:
    if old_field not in text:
        raise SystemExit("ERROR: reasoned interpreter vocabulary field anchor missing")
    text = text.replace(old_field, new_field, 1)

old_bridge = "        bridge = SemanticRequestBridge(fact_vocabulary=self.fact_vocabulary)\n"
new_bridge = (
    "        bridge = SemanticRequestBridge(\n"
    "            fact_vocabulary=self.fact_vocabulary,\n"
    "            fact_resolver=self.fact_resolver,\n"
    "        )\n"
)
if "fact_resolver=self.fact_resolver" not in text:
    if old_bridge not in text:
        raise SystemExit("ERROR: SemanticRequestBridge construction anchor missing")
    text = text.replace(old_bridge, new_bridge, 1)

path.write_text(text)
print(f"UPDATED: {path}")
PY

echo "========== SECTION 3: WIRE PRODUCTION COMPOSITION =========="
.venv/bin/python - <<'PY'
from pathlib import Path

path = Path("implementation/runtime_service/src/jason_runtime/composition.py")
text = path.read_text()

old_import = "from orchestrator.resource_inquiry import GovernedResourceInquiryPlanner\n"
new_import = (
    "from orchestrator.resource_inquiry import GovernedResourceInquiryPlanner\n"
    "from orchestrator.semantic_fact_resolver import DEFAULT_SEMANTIC_FACT_RESOLVER\n"
)
if "from orchestrator.semantic_fact_resolver import DEFAULT_SEMANTIC_FACT_RESOLVER" not in text:
    if old_import not in text:
        raise SystemExit("ERROR: runtime composition resource inquiry import anchor missing")
    text = text.replace(old_import, new_import, 1)

old_ctor = '''            fallback=ReasonedResourceInquiryInterpreter(\n                reasoner=OllamaResourceInquiryReasoner(\n                    ollama_client,\n                    resource_types=resource_types,\n                    selector_keys=selector_keys,\n                    fact_hints=fact_hints,\n                ),\n                fact_vocabulary=DEFAULT_CANONICAL_FACT_VOCABULARY,\n            ),\n'''
new_ctor = '''            fallback=ReasonedResourceInquiryInterpreter(\n                reasoner=OllamaResourceInquiryReasoner(\n                    ollama_client,\n                    resource_types=resource_types,\n                    selector_keys=selector_keys,\n                    fact_hints=fact_hints,\n                ),\n                fact_vocabulary=DEFAULT_CANONICAL_FACT_VOCABULARY,\n                fact_resolver=DEFAULT_SEMANTIC_FACT_RESOLVER,\n            ),\n'''
if "fact_resolver=DEFAULT_SEMANTIC_FACT_RESOLVER" not in text:
    if old_ctor not in text:
        raise SystemExit("ERROR: production ReasonedResourceInquiryInterpreter construction anchor missing")
    text = text.replace(old_ctor, new_ctor, 1)

path.write_text(text)
print(f"UPDATED: {path}")
PY

echo "========== SECTION 4: ADD PRODUCTION WIRING REGRESSION COVERAGE =========="
cat >> implementation/orchestrator/tests/test_conversation_resource_intent.py <<'PY'


def test_reasoned_resource_interpreter_uses_injected_registry_first_fact_resolver():
    from orchestrator.semantic_fact_resolver import SemanticFactResolver
    from orchestrator.semantic_knowledge_seed import build_trusted_semantic_registry

    class CpuReasoner:
        def propose(self, *, text, organization_id, client_id):
            return {
                "resource_type": "endpoint",
                "resource_selector": {"hostname": "AOT-50282"},
                "requested_facts": ["CPU"],
                "result_intent": "summary",
                "completeness_requirement": "sufficient",
                "permission_mode": "observe",
            }

    interpreter = ReasonedResourceInquiryInterpreter(
        reasoner=CpuReasoner(),
        fact_resolver=SemanticFactResolver(
            registry=build_trusted_semantic_registry(),
            legacy_vocabulary=None,
        ),
    )
    inquiry = interpreter.interpret(
        text="What CPU does AOT-50282 have?",
        principal=BoundConversationPrincipal(
            principal_id="person-al",
            organization_id="aot",
            client_id=None,
        ),
    )

    assert inquiry is not None
    assert inquiry.requested_facts == ("processor model",)
    assert inquiry.evidence_contexts == {
        "processor model": ("processor", "hardware_inventory")
    }
PY

echo "========== SECTION 5: STATIC VALIDATION =========="
git diff --check

echo "========== SECTION 6: FOCUSED TESTS =========="
.venv/bin/python -m pytest -q \
  implementation/orchestrator/tests/test_conversation_resource_intent.py \
  implementation/orchestrator/tests/test_semantic_request_bridge.py \
  implementation/orchestrator/tests/test_semantic_fact_resolver.py \
  implementation/orchestrator/tests/test_semantic_knowledge_seed.py \
  implementation/runtime_service/tests

echo "========== SECTION 7: CHANGE STATE =========="
git status --short

echo "========== RESULT =========="
echo "Production reasoned resource composition now supplies the governed registry-first semantic fact resolver."
echo "Legacy canonical vocabulary remains available as compatibility fallback."
echo "NO DEPLOYMENT PERFORMED."
echo "NO COMMIT OR PUSH OF WORKTREE CHANGES PERFORMED."
echo "========== END SEMANTIC REGISTRY PRODUCTION COMPOSITION WIRING =========="