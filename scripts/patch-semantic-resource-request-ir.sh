#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START SEMANTIC RESOURCE REQUEST IR FOUNDATION =========="
echo "========== SECTION 1: PRECONDITIONS =========="
DIRTY="$(git status --porcelain | grep -v '^?? FETCH_HEAD$' || true)"
if [[ -n "$DIRTY" ]]; then
  echo "ERROR: worktree must be clean before semantic resource IR patch."
  printf '%s\n' "$DIRTY"
  exit 20
fi

echo "HEAD: $(git rev-parse --short HEAD)"
PY=.venv/bin/python
if [[ ! -x "$PY" ]]; then
  echo "ERROR: .venv/bin/python is required."
  exit 21
fi

echo "========== SECTION 2: ADD PROVIDER-NEUTRAL SEMANTIC REQUEST CONTRACT =========="
cat > implementation/orchestrator/semantic_resource_request.py <<'PY'
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True, slots=True)
class SemanticEntityReference:
    """Human-grounded reference to an entity before provider resolution.

    This is deliberately provider-neutral. A person can later resolve through
    Microsoft, Datto, Autotask, IT Glue, or another governed resource without the
    human-language layer selecting that provider.
    """

    entity_type: str
    reference: str
    selector_kind: str = "natural_reference"

    def __post_init__(self) -> None:
        if not self.entity_type.strip():
            raise ValueError("semantic entity_type is required")
        if not self.reference.strip():
            raise ValueError("semantic entity reference is required")
        if not self.selector_kind.strip():
            raise ValueError("semantic selector_kind is required")


@dataclass(frozen=True, slots=True)
class SemanticRelationship:
    """Provider-neutral relationship requested by the human."""

    relationship_type: str
    target_resource_type: str
    temporal_semantics: str = "unspecified"

    def __post_init__(self) -> None:
        if not self.relationship_type.strip():
            raise ValueError("semantic relationship_type is required")
        if not self.target_resource_type.strip():
            raise ValueError("semantic target_resource_type is required")
        if self.temporal_semantics not in {
            "unspecified",
            "current",
            "most_recent",
            "historical",
        }:
            raise ValueError("semantic temporal_semantics is invalid")


@dataclass(frozen=True, slots=True)
class SemanticEvidenceConstraint:
    """Meaning-level evidence requirement, never a provider path."""

    contexts: tuple[str, ...] = ()
    expected_shape: str | None = None

    def __post_init__(self) -> None:
        if any(not item.strip() for item in self.contexts):
            raise ValueError("semantic evidence contexts must be non-empty")
        if self.expected_shape is not None and not self.expected_shape.strip():
            raise ValueError("semantic expected_shape must be non-empty when supplied")


@dataclass(frozen=True, slots=True)
class SemanticResourceRequest:
    """Canonical intermediate representation between human language and orchestration.

    The request states WHAT the human means: subject/entity, relationship, target
    resource, requested facts, outcome, temporal meaning, and semantic evidence
    constraints. It contains no provider, connector, API path, credential, or script.
    Provider/capability selection remains the Central Orchestrator's responsibility.
    """

    subject: SemanticEntityReference | None
    target_resource_type: str
    requested_facts: tuple[str, ...]
    relationship: SemanticRelationship | None = None
    evidence_constraints: Mapping[str, SemanticEvidenceConstraint] | None = None
    result_intent: str = "summary"
    completeness_requirement: str = "sufficient"
    permission_mode: str = "observe"

    def __post_init__(self) -> None:
        if not self.target_resource_type.strip():
            raise ValueError("semantic target_resource_type is required")
        if not self.requested_facts:
            raise ValueError("semantic requested_facts are required")
        if any(not fact.strip() for fact in self.requested_facts):
            raise ValueError("semantic requested facts must be non-empty")
        if self.permission_mode != "observe":
            raise PermissionError("semantic resource requests are read-only")
        if self.result_intent not in {
            "summary",
            "enumerate",
            "count",
            "search",
            "inspect",
        }:
            raise ValueError("semantic result_intent is invalid")
        if self.completeness_requirement not in {"sufficient", "complete"}:
            raise ValueError("semantic completeness_requirement is invalid")
        if self.relationship is not None:
            if self.subject is None:
                raise ValueError("semantic relationship requires a subject")
            if self.relationship.target_resource_type != self.target_resource_type:
                raise ValueError("semantic relationship target does not match request target")
        if self.evidence_constraints is not None:
            unknown = set(self.evidence_constraints).difference(self.requested_facts)
            if unknown:
                raise ValueError(
                    "semantic evidence constraints reference unrequested facts: "
                    + ", ".join(sorted(unknown))
                )
PY

echo "WROTE: implementation/orchestrator/semantic_resource_request.py"

echo "========== SECTION 3: ADD GENERIC CONTRACT TESTS =========="
cat > implementation/orchestrator/tests/test_semantic_resource_request.py <<'PY'
from __future__ import annotations

import pytest

from orchestrator.semantic_resource_request import (
    SemanticEntityReference,
    SemanticEvidenceConstraint,
    SemanticRelationship,
    SemanticResourceRequest,
)


def test_person_to_endpoint_relationship_is_provider_neutral():
    request = SemanticResourceRequest(
        subject=SemanticEntityReference(
            entity_type="person",
            reference="Lindsey Collins",
        ),
        target_resource_type="endpoint",
        relationship=SemanticRelationship(
            relationship_type="logged_in_to",
            target_resource_type="endpoint",
            temporal_semantics="most_recent",
        ),
        requested_facts=("hostname",),
    )

    assert request.subject.reference == "Lindsey Collins"
    assert request.relationship.relationship_type == "logged_in_to"
    assert request.relationship.temporal_semantics == "most_recent"
    assert not hasattr(request, "provider")
    assert not hasattr(request, "connector")


def test_fact_evidence_context_is_semantic_not_provider_path():
    request = SemanticResourceRequest(
        subject=SemanticEntityReference(
            entity_type="endpoint",
            reference="AOT-50282",
            selector_kind="hostname",
        ),
        target_resource_type="endpoint",
        requested_facts=("operating system display version",),
        evidence_constraints={
            "operating system display version": SemanticEvidenceConstraint(
                contexts=("operating_system", "windows_release"),
                expected_shape="descriptive_string",
            )
        },
    )

    constraint = request.evidence_constraints["operating system display version"]
    assert "operating_system" in constraint.contexts
    assert all(not context.startswith("/") for context in constraint.contexts)


def test_relationship_target_must_match_requested_resource():
    with pytest.raises(ValueError, match="relationship target"):
        SemanticResourceRequest(
            subject=SemanticEntityReference(entity_type="person", reference="Al Davis"),
            target_resource_type="ticket",
            relationship=SemanticRelationship(
                relationship_type="uses",
                target_resource_type="endpoint",
            ),
            requested_facts=("ticket number",),
        )


def test_evidence_constraints_cannot_expand_requested_facts():
    with pytest.raises(ValueError, match="unrequested facts"):
        SemanticResourceRequest(
            subject=None,
            target_resource_type="organization",
            requested_facts=("name",),
            evidence_constraints={
                "secret field": SemanticEvidenceConstraint(contexts=("organization",))
            },
        )
PY

echo "WROTE: implementation/orchestrator/tests/test_semantic_resource_request.py"

echo "========== SECTION 4: VALIDATE =========="
git diff --check
$PY -m py_compile implementation/orchestrator/semantic_resource_request.py
$PY -m pytest -q implementation/orchestrator/tests/test_semantic_resource_request.py

echo "========== SECTION 5: CHANGE STATE =========="
git status --short

echo "========== RESULT =========="
echo "Provider-neutral semantic resource request IR foundation validated."
echo "This establishes entity + relationship + fact + temporal + evidence-context semantics."
echo "It does not yet replace ResourceInquiry or select any provider."
echo "NO DEPLOYMENT PERFORMED."
echo "NO COMMIT OR PUSH OF WORKTREE CHANGES PERFORMED."
echo "========== END SEMANTIC RESOURCE REQUEST IR FOUNDATION =========="
