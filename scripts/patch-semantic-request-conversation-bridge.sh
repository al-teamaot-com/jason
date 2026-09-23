#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START SEMANTIC REQUEST CONVERSATION BRIDGE =========="
echo "========== SECTION 1: PRECONDITIONS =========="
DIRTY="$(git status --porcelain | grep -v '^?? FETCH_HEAD$' || true)"
if [[ -n "$DIRTY" ]]; then
  echo "ERROR: worktree must be clean before semantic bridge patch."
  printf '%s\n' "$DIRTY"
  exit 20
fi

echo "HEAD: $(git rev-parse --short HEAD)"
PY=.venv/bin/python
if [[ ! -x "$PY" ]]; then
  echo "ERROR: .venv/bin/python is required."
  exit 21
fi

echo "========== SECTION 2: ADD PROVIDER-NEUTRAL SEMANTIC LOWERING =========="
cat > implementation/orchestrator/semantic_request_bridge.py <<'PY'
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .canonical_fact_vocabulary import CanonicalFactVocabulary
from .resource_inquiry import ResourceInquiry
from .semantic_resource_request import (
    SemanticEntityReference,
    SemanticEvidenceConstraint,
    SemanticRelationship,
    SemanticResourceRequest,
)


@dataclass(frozen=True, slots=True)
class SemanticRequestBridge:
    """Translate grounded human resource meaning into the legacy planner contract.

    This bridge is intentionally provider-neutral. It lets the conversation layer use
    a richer semantic IR now while the existing governed capability planner remains in
    place. Providers, connectors, API paths, credentials, and scripts never appear in
    this contract.
    """

    fact_vocabulary: CanonicalFactVocabulary | None = None

    def build(
        self,
        *,
        human_text: str,
        resource_type: str,
        resource_selector: Mapping[str, str],
        requested_facts: tuple[str, ...],
        result_intent: str,
        completeness_requirement: str,
    ) -> SemanticResourceRequest:
        facts = requested_facts
        if self.fact_vocabulary is not None:
            facts = self.fact_vocabulary.canonicalize_requested_facts(
                human_text=human_text,
                requested_facts=facts,
            )

        subject: SemanticEntityReference | None = None
        relationship: SemanticRelationship | None = None
        selector = dict(resource_selector)

        user_identity = str(selector.get("user_identity", "")).strip()
        if user_identity:
            temporal = self._temporal_semantics(human_text)
            subject = SemanticEntityReference(
                entity_type="person",
                reference=user_identity,
                selector_kind="human_identity",
            )
            relationship = SemanticRelationship(
                relationship_type="logged_in_to",
                target_resource_type=resource_type,
                temporal_semantics=temporal,
            )
        elif selector:
            # Preserve the human-grounded selector as an entity reference without
            # pretending the selector is durable identity.
            key, value = next(iter(selector.items()))
            subject = SemanticEntityReference(
                entity_type=resource_type,
                reference=str(value),
                selector_kind=str(key),
            )

        constraints: dict[str, SemanticEvidenceConstraint] = {}
        if self.fact_vocabulary is not None:
            for fact in facts:
                definition = self.fact_vocabulary.resolve(fact)
                if definition is None:
                    continue
                contexts = self._semantic_contexts(definition.canonical_fact)
                constraints[fact] = SemanticEvidenceConstraint(
                    contexts=contexts,
                    expected_shape=definition.expected_shape,
                )

        return SemanticResourceRequest(
            subject=subject,
            target_resource_type=resource_type,
            requested_facts=facts,
            relationship=relationship,
            evidence_constraints=constraints or None,
            result_intent=result_intent,
            completeness_requirement=completeness_requirement,
        )

    @staticmethod
    def lower(request: SemanticResourceRequest, *, selector: Mapping[str, str]) -> ResourceInquiry:
        """Lower semantic meaning into the existing governed planner contract."""
        return ResourceInquiry(
            resource_type=request.target_resource_type,
            resource_selector=dict(selector),
            requested_facts=request.requested_facts,
            execution_mode="deterministic",
            permission_mode=request.permission_mode,
            result_intent=request.result_intent,
            completeness_requirement=request.completeness_requirement,
        )

    @staticmethod
    def _temporal_semantics(human_text: str) -> str:
        normalized = " ".join(human_text.casefold().split())
        if any(phrase in normalized for phrase in ("last logged", "most recent", "last used", "last on")):
            return "most_recent"
        if any(phrase in normalized for phrase in ("currently", "right now", "is on", "using", "logged into")):
            return "current"
        return "unspecified"

    @staticmethod
    def _semantic_contexts(canonical_fact: str) -> tuple[str, ...]:
        """Provider-neutral evidence domains, never provider field names or paths."""
        contexts = {
            "operating system display version": ("operating_system", "windows_release"),
            "operating system build": ("operating_system",),
            "operating system": ("operating_system",),
            "processor model": ("processor", "hardware_inventory"),
            "logical processor count": ("processor", "hardware_inventory"),
            "total memory": ("memory", "hardware_inventory"),
            "bios version": ("bios", "hardware_inventory"),
            "network adapters": ("network", "hardware_inventory"),
            "logical disks": ("storage", "hardware_inventory"),
            "display adapters": ("graphics", "hardware_inventory"),
        }
        return contexts.get(canonical_fact, ())
PY

echo "WROTE: implementation/orchestrator/semantic_request_bridge.py"

echo "========== SECTION 3: ROUTE REASONED CONVERSATION THROUGH SEMANTIC IR =========="
$PY - <<'PY'
from pathlib import Path
p = Path('implementation/orchestrator/conversation_resource_intent.py')
s = p.read_text(encoding='utf-8')
if 'from .semantic_request_bridge import SemanticRequestBridge' not in s:
    s = s.replace(
        'from .resource_inquiry import GovernedResourceInquiryPlanner, ResourceInquiry\n',
        'from .resource_inquiry import GovernedResourceInquiryPlanner, ResourceInquiry\nfrom .semantic_request_bridge import SemanticRequestBridge\n',
        1,
    )
old = '''        normalized_facts = tuple(str(item).strip() for item in requested_facts)\n        if self.fact_vocabulary is not None:\n            normalized_facts = self.fact_vocabulary.canonicalize_requested_facts(\n                human_text=text,\n                requested_facts=normalized_facts,\n            )\n\n        return ResourceInquiry(\n            resource_type=resource_type,\n            resource_selector=normalized_selector,\n            requested_facts=normalized_facts,\n            execution_mode=str(proposed.get("execution_mode", "deterministic")).strip(),\n            permission_mode=str(proposed.get("permission_mode", "observe")).strip(),\n            result_intent=result_intent,\n            completeness_requirement=completeness_requirement,\n        )\n'''
new = '''        normalized_facts = tuple(str(item).strip() for item in requested_facts)\n        bridge = SemanticRequestBridge(fact_vocabulary=self.fact_vocabulary)\n        semantic_request = bridge.build(\n            human_text=text,\n            resource_type=resource_type,\n            resource_selector=normalized_selector,\n            requested_facts=normalized_facts,\n            result_intent=result_intent,\n            completeness_requirement=completeness_requirement,\n        )\n        return bridge.lower(semantic_request, selector=normalized_selector)\n'''
if old in s:
    s = s.replace(old, new, 1)
elif new not in s:
    raise SystemExit('ERROR: reasoned ResourceInquiry construction block not found')
p.write_text(s, encoding='utf-8')
print('UPDATED:', p)
PY

echo "========== SECTION 4: ADD BRIDGE REGRESSION TESTS =========="
cat > implementation/orchestrator/tests/test_semantic_request_bridge.py <<'PY'
from orchestrator.canonical_fact_vocabulary import DEFAULT_CANONICAL_FACT_VOCABULARY
from orchestrator.semantic_request_bridge import SemanticRequestBridge


def bridge():
    return SemanticRequestBridge(DEFAULT_CANONICAL_FACT_VOCABULARY)


def test_windows_display_version_gets_semantic_evidence_context():
    semantic = bridge().build(
        human_text="What is the Windows Display Version for AOT-50282?",
        resource_type="endpoint",
        resource_selector={"hostname": "AOT-50282"},
        requested_facts=("display", "version"),
        result_intent="summary",
        completeness_requirement="sufficient",
    )
    assert semantic.requested_facts == ("operating system display version",)
    constraint = semantic.evidence_constraints["operating system display version"]
    assert constraint.contexts == ("operating_system", "windows_release")
    assert constraint.expected_shape == "descriptive_string"


def test_person_device_question_becomes_relationship_semantics():
    semantic = bridge().build(
        human_text="What device is Lindsey Collins on?",
        resource_type="endpoint",
        resource_selector={"user_identity": "Lindsey Collins"},
        requested_facts=("hostname",),
        result_intent="summary",
        completeness_requirement="sufficient",
    )
    assert semantic.subject.entity_type == "person"
    assert semantic.subject.reference == "Lindsey Collins"
    assert semantic.relationship.relationship_type == "logged_in_to"
    assert semantic.relationship.target_resource_type == "endpoint"
    assert semantic.relationship.temporal_semantics == "current"


def test_last_logged_into_becomes_most_recent_semantics():
    semantic = bridge().build(
        human_text="Which endpoint was AzureAD\\LindseyCollins last logged into?",
        resource_type="endpoint",
        resource_selector={"user_identity": "AzureAD\\LindseyCollins"},
        requested_facts=("hostname",),
        result_intent="summary",
        completeness_requirement="sufficient",
    )
    assert semantic.relationship.temporal_semantics == "most_recent"


def test_lowering_preserves_existing_governed_planner_contract():
    b = bridge()
    semantic = b.build(
        human_text="How much RAM is in AOT-50282?",
        resource_type="endpoint",
        resource_selector={"hostname": "AOT-50282"},
        requested_facts=("ram",),
        result_intent="summary",
        completeness_requirement="sufficient",
    )
    inquiry = b.lower(semantic, selector={"hostname": "AOT-50282"})
    assert inquiry.resource_type == "endpoint"
    assert inquiry.resource_selector == {"hostname": "AOT-50282"}
    assert inquiry.requested_facts == ("total memory",)
PY

echo "WROTE: implementation/orchestrator/tests/test_semantic_request_bridge.py"

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
echo "Semantic request conversation bridge validated."
echo "Human language now passes through provider-neutral semantic IR before legacy ResourceInquiry lowering."
echo "This stage does not yet enforce semantic evidence contexts during provider evidence verification."
echo "NO DEPLOYMENT PERFORMED."
echo "NO COMMIT OR PUSH OF WORKTREE CHANGES PERFORMED."
echo "========== END SEMANTIC REQUEST CONVERSATION BRIDGE =========="
