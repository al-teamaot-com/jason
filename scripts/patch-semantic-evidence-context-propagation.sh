#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START SEMANTIC EVIDENCE CONTEXT PROPAGATION =========="
echo "========== SECTION 1: PRECONDITIONS =========="
DIRTY="$(git status --porcelain | grep -v '^?? FETCH_HEAD$' || true)"
if [[ -n "$DIRTY" ]]; then
  echo "ERROR: worktree must be clean before semantic evidence propagation patch."
  printf '%s\n' "$DIRTY"
  exit 20
fi
PY=.venv/bin/python
if [[ ! -x "$PY" ]]; then
  echo "ERROR: .venv/bin/python is required."
  exit 21
fi

echo "HEAD: $(git rev-parse --short HEAD)"

echo "========== SECTION 2: CARRY SEMANTIC CONTEXT THROUGH LEGACY RESOURCE INQUIRY =========="
$PY - <<'PY'
from pathlib import Path
p = Path('implementation/orchestrator/resource_inquiry.py')
s = p.read_text(encoding='utf-8')
old = '''    completeness_requirement: str = "sufficient"\n'''
new = '''    completeness_requirement: str = "sufficient"\n    evidence_contexts: Mapping[str, tuple[str, ...]] | None = None\n    relationship_type: str | None = None\n    temporal_semantics: str = "unspecified"\n'''
if new not in s:
    if old not in s:
        raise SystemExit('ERROR: ResourceInquiry field anchor missing')
    s = s.replace(old, new, 1)

anchor = '''        if self.completeness_requirement not in {\n            "sufficient",\n            "complete",\n        }:\n            raise ValueError("resource completeness_requirement is invalid")\n'''
addition = anchor + '''        if self.evidence_contexts is not None:\n            unknown = set(self.evidence_contexts).difference(self.requested_facts)\n            if unknown:\n                raise ValueError(\n                    "resource evidence contexts reference unrequested facts: "\n                    + ", ".join(sorted(unknown))\n                )\n            for contexts in self.evidence_contexts.values():\n                if any(not str(item).strip() for item in contexts):\n                    raise ValueError("resource evidence contexts must be non-empty")\n        if self.relationship_type is not None and not self.relationship_type.strip():\n            raise ValueError("resource relationship_type must be non-empty when supplied")\n        if self.temporal_semantics not in {\n            "unspecified",\n            "current",\n            "most_recent",\n            "historical",\n        }:\n            raise ValueError("resource temporal_semantics is invalid")\n'''
if 'resource evidence contexts reference unrequested facts' not in s:
    if anchor not in s:
        raise SystemExit('ERROR: ResourceInquiry validation anchor missing')
    s = s.replace(anchor, addition, 1)
p.write_text(s, encoding='utf-8')
print('UPDATED:', p)
PY

echo "========== SECTION 3: LOWER SEMANTIC CONTEXT INTO RESOURCE INQUIRY =========="
$PY - <<'PY'
from pathlib import Path
p = Path('implementation/orchestrator/semantic_request_bridge.py')
s = p.read_text(encoding='utf-8')
old = '''        return ResourceInquiry(\n            resource_type=request.target_resource_type,\n            resource_selector=dict(selector),\n            requested_facts=request.requested_facts,\n            execution_mode="deterministic",\n            permission_mode=request.permission_mode,\n            result_intent=request.result_intent,\n            completeness_requirement=request.completeness_requirement,\n        )\n'''
new = '''        evidence_contexts = None\n        if request.evidence_constraints is not None:\n            evidence_contexts = {\n                fact: tuple(constraint.contexts)\n                for fact, constraint in request.evidence_constraints.items()\n                if constraint.contexts\n            } or None\n\n        return ResourceInquiry(\n            resource_type=request.target_resource_type,\n            resource_selector=dict(selector),\n            requested_facts=request.requested_facts,\n            execution_mode="deterministic",\n            permission_mode=request.permission_mode,\n            result_intent=request.result_intent,\n            completeness_requirement=request.completeness_requirement,\n            evidence_contexts=evidence_contexts,\n            relationship_type=(\n                request.relationship.relationship_type\n                if request.relationship is not None\n                else None\n            ),\n            temporal_semantics=(\n                request.relationship.temporal_semantics\n                if request.relationship is not None\n                else "unspecified"\n            ),\n        )\n'''
if old in s:
    s = s.replace(old, new, 1)
elif new not in s:
    raise SystemExit('ERROR: semantic lowering block missing')
p.write_text(s, encoding='utf-8')
print('UPDATED:', p)
PY

echo "========== SECTION 4: PROPAGATE SEMANTICS INTO CAPABILITY ARGUMENTS =========="
$PY - <<'PY'
from pathlib import Path
p = Path('implementation/orchestrator/ollama_reasoning.py')
s = p.read_text(encoding='utf-8')
anchor = '''        arguments["completeness_requirement"] = inquiry.completeness_requirement\n'''
addition = anchor + '''        if inquiry.evidence_contexts:\n            arguments["evidence_contexts"] = {\n                fact: list(contexts)\n                for fact, contexts in inquiry.evidence_contexts.items()\n            }\n        if inquiry.relationship_type:\n            arguments["relationship_type"] = inquiry.relationship_type\n        if inquiry.temporal_semantics != "unspecified":\n            arguments["temporal_semantics"] = inquiry.temporal_semantics\n'''
if 'arguments["evidence_contexts"]' not in s:
    if anchor not in s:
        raise SystemExit('ERROR: capability argument anchor missing')
    s = s.replace(anchor, addition, 1)
p.write_text(s, encoding='utf-8')
print('UPDATED:', p)
PY

echo "========== SECTION 5: ENFORCE EVIDENCE CONTEXT AT VERIFICATION BOUNDARY =========="
$PY - <<'PY'
from pathlib import Path
p = Path('implementation/orchestrator/resource_evidence.py')
s = p.read_text(encoding='utf-8')
old_sig = '''    def interpret(\n        self,\n        *,\n        result: OrchestrationResult,\n        requested_facts: tuple[str, ...],\n    ) -> tuple[VerifiedResourceFact, ...]:\n'''
new_sig = '''    def interpret(\n        self,\n        *,\n        result: OrchestrationResult,\n        requested_facts: tuple[str, ...],\n        evidence_contexts: Mapping[str, tuple[str, ...]] | None = None,\n    ) -> tuple[VerifiedResourceFact, ...]:\n'''
if old_sig in s:
    s = s.replace(old_sig, new_sig, 1)
elif new_sig not in s:
    raise SystemExit('ERROR: evidence interpreter signature missing')

old_direct = '''        verified_by_fact = {\n            fact.requested_fact: fact\n            for fact in _deterministic_direct_facts(\n                data=data,\n                requested_facts=requested_facts,\n            )\n        }\n'''
new_direct = '''        direct_facts = _deterministic_direct_facts(\n            data=data,\n            requested_facts=requested_facts,\n        )\n        verified_by_fact: dict[str, VerifiedResourceFact] = {}\n        for fact in direct_facts:\n            if not _evidence_matches_contexts(\n                pointer=fact.json_pointer,\n                contexts=(evidence_contexts or {}).get(fact.requested_fact, ()),\n            ):\n                continue\n            if self.fact_vocabulary is not None:\n                definition = self.fact_vocabulary.resolve(fact.requested_fact)\n                if definition is not None and not _value_matches_expected_shape(\n                    fact.value,\n                    definition.expected_shape,\n                ):\n                    continue\n            verified_by_fact[fact.requested_fact] = fact\n'''
if old_direct in s:
    s = s.replace(old_direct, new_direct, 1)
elif new_direct not in s:
    raise SystemExit('ERROR: direct evidence block missing')

needle = '''                actual = _resolve_json_pointer(data, pointer)\n                if self.fact_vocabulary is not None:\n'''
replacement = '''                actual = _resolve_json_pointer(data, pointer)\n                required_contexts = (evidence_contexts or {}).get(requested_fact, ())\n                if not _evidence_matches_contexts(\n                    pointer=pointer,\n                    contexts=required_contexts,\n                ):\n                    raise LookupError(\n                        f"provider evidence is outside required semantic context for {requested_fact}"\n                    )\n                if self.fact_vocabulary is not None:\n'''
if replacement not in s:
    if needle not in s:
        raise SystemExit('ERROR: reasoned evidence validation anchor missing')
    s = s.replace(needle, replacement, 1)

anchor = '''def _value_matches_expected_shape(value: Any, expected_shape: str) -> bool:\n'''
helper = '''def _normalized_semantic_tokens(value: str) -> set[str]:\n    return {\n        token\n        for token in \"\".join(\n            character if character.isalnum() else \" \"\n            for character in value.casefold()\n        ).split()\n        if token\n    }\n\n\ndef _evidence_matches_contexts(*, pointer: str, contexts: tuple[str, ...]) -> bool:\n    \"\"\"Require evidence location to carry provider-neutral semantic context.\n\n    Contexts describe meaning domains, not provider field paths. Matching is deliberately\n    conservative: every required context contributes at least one token that must be\n    present in the JSON pointer. A provider adapter can later expose normalized semantic\n    containers when native field names do not carry enough meaning.\n    \"\"\"\n    if not contexts:\n        return True\n    pointer_tokens = _normalized_semantic_tokens(pointer)\n    if not pointer_tokens:\n        return False\n    for context in contexts:\n        context_tokens = _normalized_semantic_tokens(context)\n        if not context_tokens:\n            continue\n        if pointer_tokens.isdisjoint(context_tokens):\n            return False\n    return True\n\n\n'''
if 'def _evidence_matches_contexts(' not in s:
    if anchor not in s:
        raise SystemExit('ERROR: evidence helper anchor missing')
    s = s.replace(anchor, helper + anchor, 1)

old_call = '''        facts = self.interpreter.interpret(\n            result=result,\n            requested_facts=requested_facts,\n        )\n'''
new_call = '''        raw_contexts = intent.arguments.get("evidence_contexts")\n        evidence_contexts: dict[str, tuple[str, ...]] | None = None\n        if isinstance(raw_contexts, Mapping):\n            evidence_contexts = {}\n            for raw_fact, raw_values in raw_contexts.items():\n                if not isinstance(raw_values, (list, tuple)):\n                    raise ValueError("conversation evidence contexts must be a list/tuple")\n                evidence_contexts[str(raw_fact).strip()] = tuple(\n                    str(item).strip() for item in raw_values if str(item).strip()\n                )\n\n        facts = self.interpreter.interpret(\n            result=result,\n            requested_facts=requested_facts,\n            evidence_contexts=evidence_contexts,\n        )\n'''
if old_call in s:
    s = s.replace(old_call, new_call, 1)
elif new_call not in s:
    raise SystemExit('ERROR: renderer evidence call missing')
p.write_text(s, encoding='utf-8')
print('UPDATED:', p)
PY

echo "========== SECTION 6: ADD REGRESSION COVERAGE =========="
cat >> implementation/orchestrator/tests/test_semantic_request_bridge.py <<'PY'


def test_lowering_preserves_evidence_and_relationship_semantics():
    b = bridge()
    semantic = b.build(
        human_text="Which endpoint was Lindsey Collins last logged into?",
        resource_type="endpoint",
        resource_selector={"user_identity": "Lindsey Collins"},
        requested_facts=("hostname",),
        result_intent="summary",
        completeness_requirement="sufficient",
        permission_mode="observe",
    )
    inquiry = b.lower(semantic, selector={"user_identity": "Lindsey Collins"})
    assert inquiry.relationship_type == "logged_in_to"
    assert inquiry.temporal_semantics == "most_recent"


def test_windows_display_version_lowering_preserves_evidence_contexts():
    b = bridge()
    semantic = b.build(
        human_text="What is the Windows Display Version for AOT-50282?",
        resource_type="endpoint",
        resource_selector={"hostname": "AOT-50282"},
        requested_facts=("display", "version"),
        result_intent="summary",
        completeness_requirement="sufficient",
        permission_mode="observe",
    )
    inquiry = b.lower(semantic, selector={"hostname": "AOT-50282"})
    assert inquiry.evidence_contexts == {
        "operating system display version": ("operating_system", "windows_release")
    }
PY

cat >> implementation/orchestrator/tests/test_resource_evidence.py <<'PY'


def test_semantic_context_rejects_unrelated_descriptive_version():
    interpreter = GovernedResourceEvidenceInterpreter(
        reasoner=FakeEvidenceReasoner([
            {
                "requested_fact": "operating system display version",
                "json_pointer": "/provider_data/health/version",
            }
        ]),
        fact_vocabulary=DEFAULT_CANONICAL_FACT_VOCABULARY,
    )
    result = succeeded_result(
        data={
            "provider_data": {
                "health": {
                    "version": "Unhealthy - Local user changes detected",
                }
            }
        }
    )
    with pytest.raises(LookupError, match="outside required semantic context"):
        interpreter.interpret(
            result=result,
            requested_facts=("operating system display version",),
            evidence_contexts={
                "operating system display version": ("operating_system", "windows_release")
            },
        )


def test_semantic_context_accepts_operating_system_release_path():
    interpreter = GovernedResourceEvidenceInterpreter(
        reasoner=FakeEvidenceReasoner([
            {
                "requested_fact": "operating system display version",
                "json_pointer": "/provider_data/operating_system/windows_release/display_version",
            }
        ]),
        fact_vocabulary=DEFAULT_CANONICAL_FACT_VOCABULARY,
    )
    result = succeeded_result(
        data={
            "provider_data": {
                "operating_system": {
                    "windows_release": {
                        "display_version": "24H2",
                    }
                }
            }
        }
    )
    facts = interpreter.interpret(
        result=result,
        requested_facts=("operating system display version",),
        evidence_contexts={
            "operating system display version": ("operating_system", "windows_release")
        },
    )
    assert facts[0].value == "24H2"
PY

echo "========== SECTION 7: VALIDATE =========="
git diff --check
$PY -m py_compile \
  implementation/orchestrator/resource_inquiry.py \
  implementation/orchestrator/semantic_request_bridge.py \
  implementation/orchestrator/ollama_reasoning.py \
  implementation/orchestrator/resource_evidence.py
$PY -m pytest -q \
  implementation/orchestrator/tests/test_semantic_resource_request.py \
  implementation/orchestrator/tests/test_semantic_request_bridge.py \
  implementation/orchestrator/tests/test_conversation_resource_intent.py \
  implementation/orchestrator/tests/test_resource_evidence.py \
  implementation/orchestrator/tests/test_canonical_fact_vocabulary.py

echo "========== SECTION 8: CHANGE STATE =========="
git status --short

echo "========== RESULT =========="
echo "Semantic evidence context propagation implemented and validated."
echo "Meaning-level evidence constraints now survive semantic lowering and are enforced at evidence verification."
echo "Relationship and temporal semantics now survive into governed capability arguments for provider adaptation."
echo "NO DEPLOYMENT PERFORMED."
echo "NO COMMIT OR PUSH OF WORKTREE CHANGES PERFORMED."
echo "========== END SEMANTIC EVIDENCE CONTEXT PROPAGATION =========="
