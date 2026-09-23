#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START RESOURCE EVIDENCE UNAVAILABLE RESPONSE REPAIR =========="
echo "========== SECTION 1: PRECONDITIONS =========="
echo "HEAD: $(git rev-parse --short HEAD)"

DIRTY="$(git status --porcelain | grep -v '^?? FETCH_HEAD$' || true)"
if [[ -n "$DIRTY" ]]; then
  echo "ERROR: unexpected worktree changes present."
  printf '%s\n' "$DIRTY"
  exit 20
fi

echo "========== SECTION 2: RETURN SAFE FACT-SPECIFIC UNAVAILABLE RESPONSE =========="
.venv/bin/python - <<'PY'
from pathlib import Path

path = Path("implementation/orchestrator/resource_evidence.py")
text = path.read_text()
old = '''        facts = self.interpreter.interpret(\n            result=result,\n            requested_facts=requested_facts,\n            evidence_contexts=evidence_contexts,\n        )\n\n        collection_facts = tuple(\n'''
new = '''        try:\n            facts = self.interpreter.interpret(\n                result=result,\n                requested_facts=requested_facts,\n                evidence_contexts=evidence_contexts,\n            )\n        except LookupError:\n            # A successful governed provider read can legitimately lack evidence for\n            # a requested semantic fact. That is not an unsafe action failure. Preserve\n            # fail-closed semantics while telling the human exactly what is unavailable.\n            rendered_facts = ", ".join(requested_facts)\n            return (\n                f"{subject} — {rendered_facts}: unavailable from the current governed "\n                f"provider evidence. Source: {source}."\n            )\n\n        collection_facts = tuple(\n'''
if old not in text:
    raise SystemExit("ERROR: resource evidence render anchor not found")
path.write_text(text.replace(old, new, 1))
print(f"UPDATED: {path}")
PY

echo "========== SECTION 3: ADD REGRESSION COVERAGE =========="
cat >> implementation/orchestrator/tests/test_resource_evidence.py <<'PY'


def test_renderer_reports_unavailable_fact_without_generic_failure():
    from orchestrator.resource_evidence import GovernedTeamsResourceResponseRenderer
    from orchestrator.teams_conversation_flow import ConversationIntent

    class MissingEvidenceInterpreter:
        def interpret(self, **kwargs):
            raise LookupError("requested facts were not located in governed provider evidence")

    renderer = GovernedTeamsResourceResponseRenderer(interpreter=MissingEvidenceInterpreter())
    response = renderer.render(
        result=result(data={"provider_data": {}}),
        intent=ConversationIntent(
            capability_name="endpoint.device.search",
            arguments={
                "hostname": "AOT-50282",
                "requested_facts": ("operating system display version",),
            },
        ),
    )
    assert "operating system display version: unavailable" in response
    assert "Source:" in response


def test_renderer_unavailable_response_does_not_invent_display_version_value():
    from orchestrator.resource_evidence import GovernedTeamsResourceResponseRenderer
    from orchestrator.teams_conversation_flow import ConversationIntent

    class MissingEvidenceInterpreter:
        def interpret(self, **kwargs):
            raise LookupError("provider evidence is outside required semantic context")

    renderer = GovernedTeamsResourceResponseRenderer(interpreter=MissingEvidenceInterpreter())
    response = renderer.render(
        result=result(data={"provider_data": {"displayVersion": "4.4.11965.11965"}}),
        intent=ConversationIntent(
            capability_name="endpoint.device.search",
            arguments={
                "hostname": "AOT-50282",
                "requested_facts": ("operating system display version",),
            },
        ),
    )
    assert "unavailable from the current governed provider evidence" in response
    assert "4.4.11965.11965" not in response
PY

echo "========== SECTION 4: STATIC VALIDATION =========="
git diff --check

echo "========== SECTION 5: FOCUSED TESTS =========="
.venv/bin/python -m pytest -q \
  implementation/orchestrator/tests/test_resource_evidence.py \
  implementation/orchestrator/tests/test_semantic_fact_resolver.py \
  implementation/orchestrator/tests/test_semantic_request_bridge.py \
  implementation/connectors/tests/test_datto_semantic_evidence.py

echo "========== SECTION 6: CHANGE STATE =========="
git status --short

echo "========== RESULT =========="
echo "Missing governed evidence now produces a specific unavailable-fact response instead of bubbling into the generic safe-failure message."
echo "Fail-closed evidence semantics remain unchanged and no value is invented."
echo "NO DEPLOYMENT PERFORMED."
echo "NO COMMIT OR PUSH OF WORKTREE CHANGES PERFORMED."
echo "========== END RESOURCE EVIDENCE UNAVAILABLE RESPONSE REPAIR =========="
