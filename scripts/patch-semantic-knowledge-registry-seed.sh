#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START SEMANTIC KNOWLEDGE REGISTRY SEED =========="
echo "========== SECTION 1: PRECONDITIONS =========="
echo "HEAD: $(git rev-parse --short HEAD)"

DIRTY="$(git status --porcelain | grep -v '^?? FETCH_HEAD$' || true)"
if [[ -n "$DIRTY" ]]; then
  echo "ERROR: worktree must be clean before registry seed work."
  printf '%s\n' "$DIRTY"
  exit 20
fi

echo "========== SECTION 2: ADD ACTIVE TRUSTED KNOWLEDGE SEED =========="
cat > implementation/orchestrator/semantic_knowledge_seed.py <<'PY'
from __future__ import annotations

from orchestrator.semantic_knowledge_registry import (
    SemanticConcept,
    SemanticKnowledgeRegistry,
    SemanticLifecycleState,
    SemanticProviderFieldBinding,
    SemanticProvenance,
    SemanticRelationshipDefinition,
    SemanticTermBinding,
)


def _activate_concept(registry: SemanticKnowledgeRegistry, concept_id: str) -> None:
    for state in (
        SemanticLifecycleState.REVIEWED,
        SemanticLifecycleState.APPROVED,
        SemanticLifecycleState.ACTIVE,
    ):
        registry.transition_concept(concept_id, state)


def _activate_term(registry: SemanticKnowledgeRegistry, *, term: str, scope: str = "global") -> None:
    for state in (
        SemanticLifecycleState.REVIEWED,
        SemanticLifecycleState.APPROVED,
        SemanticLifecycleState.ACTIVE,
    ):
        registry.transition_term(term=term, scope=scope, target=state)


def _activate_provider_field(
    registry: SemanticKnowledgeRegistry,
    *,
    provider: str,
    resource_type: str,
    provider_field: str,
) -> None:
    for state in (
        SemanticLifecycleState.REVIEWED,
        SemanticLifecycleState.APPROVED,
        SemanticLifecycleState.ACTIVE,
    ):
        registry.transition_provider_field(
            provider=provider,
            resource_type=resource_type,
            provider_field=provider_field,
            target=state,
        )


def _activate_relationship(registry: SemanticKnowledgeRegistry, relationship_id: str) -> None:
    for state in (
        SemanticLifecycleState.REVIEWED,
        SemanticLifecycleState.APPROVED,
        SemanticLifecycleState.ACTIVE,
    ):
        registry.transition_relationship(relationship_id, state)


def build_trusted_semantic_registry() -> SemanticKnowledgeRegistry:
    registry = SemanticKnowledgeRegistry()
    provenance = SemanticProvenance(
        source="project-jason-existing-governed-semantics",
        evidence="migrated from validated canonical vocabulary, semantic request contracts, and Datto semantic adapter declarations",
    )

    concepts = (
        SemanticConcept(
            concept_id="processor.model",
            canonical_label="processor model",
            kind="fact",
            expected_shape="descriptive_string",
            evidence_contexts=("processor", "hardware_inventory"),
            provenance=provenance,
            review_interval_days=180,
            retirement_criteria="retire only when superseded by a governed canonical processor concept",
        ),
        SemanticConcept(
            concept_id="processor.logical_count",
            canonical_label="logical processor count",
            kind="fact",
            expected_shape="integer_count",
            evidence_contexts=("processor", "hardware_inventory"),
            provenance=provenance,
            review_interval_days=180,
            retirement_criteria="retire only when superseded by a governed canonical processor-count concept",
        ),
        SemanticConcept(
            concept_id="memory.total",
            canonical_label="total memory",
            kind="fact",
            expected_shape="capacity",
            canonical_unit="byte",
            evidence_contexts=("memory", "hardware_inventory"),
            provenance=provenance,
            review_interval_days=180,
            retirement_criteria="retire only when superseded by a governed canonical memory concept",
        ),
        SemanticConcept(
            concept_id="operating_system.windows.display_version",
            canonical_label="operating system display version",
            kind="fact",
            expected_shape="descriptive_string",
            evidence_contexts=("operating_system", "windows_release"),
            provenance=provenance,
            review_interval_days=180,
            retirement_criteria="retire only when Windows release semantics are replaced by a governed canonical concept",
        ),
        SemanticConcept(
            concept_id="operating_system.build",
            canonical_label="operating system build",
            kind="fact",
            expected_shape="descriptive_string",
            evidence_contexts=("operating_system",),
            provenance=provenance,
            review_interval_days=180,
            retirement_criteria="retire only when superseded by a governed canonical OS-build concept",
        ),
    )

    for concept in concepts:
        registry.add_concept(concept)
        _activate_concept(registry, concept.concept_id)

    terms = {
        "processor.model": (
            "processor model",
            "processor",
            "cpu",
            "cpu model",
            "processor name",
            "cpu name",
        ),
        "processor.logical_count": (
            "logical processors",
            "logical processor count",
            "cpu count",
            "processor count",
            "threads",
            "thread count",
        ),
        "memory.total": (
            "total memory",
            "memory",
            "ram",
            "physical memory",
            "installed memory",
            "total ram",
            "memory total",
        ),
        "operating_system.windows.display_version": (
            "operating system display version",
            "windows display version",
            "displayversion",
            "windows release version",
            "windows feature version",
            "os display version",
        ),
        "operating_system.build": (
            "operating system build",
            "windows build",
            "os build",
            "operating system build number",
            "windows build number",
        ),
    }

    for concept_id, aliases in terms.items():
        for term in aliases:
            registry.add_term(
                SemanticTermBinding(
                    term=term,
                    concept_id=concept_id,
                    provenance=provenance,
                )
            )
            _activate_term(registry, term=term)

    datto_fields = {
        "processor.model": ("processor", "processorModel", "cpu", "cpuModel", "processorName"),
        "processor.logical_count": ("logicalProcessors", "logicalProcessorCount", "processorCount", "threadCount"),
        "memory.total": ("totalMemory", "physicalMemory", "totalPhysicalMemory", "ram"),
        "operating_system.windows.display_version": ("displayVersion", "DisplayVersion", "display_version", "windowsDisplayVersion"),
        "operating_system.build": ("build", "buildNumber", "osBuild", "osBuildNumber"),
    }

    for concept_id, provider_fields in datto_fields.items():
        for provider_field in provider_fields:
            registry.add_provider_field(
                SemanticProviderFieldBinding(
                    provider="datto_rmm",
                    resource_type="endpoint",
                    provider_field=provider_field,
                    concept_id=concept_id,
                    provenance=provenance,
                )
            )
            _activate_provider_field(
                registry,
                provider="datto_rmm",
                resource_type="endpoint",
                provider_field=provider_field,
            )

    relationship = SemanticRelationshipDefinition(
        relationship_id="person.logged_in_to.endpoint",
        subject_type="person",
        target_type="endpoint",
        temporal_semantics=("current", "most_recent", "historical"),
        provenance=provenance,
    )
    registry.add_relationship(relationship)
    _activate_relationship(registry, relationship.relationship_id)

    return registry
PY

echo "WROTE: implementation/orchestrator/semantic_knowledge_seed.py"

echo "========== SECTION 3: ADD SEED TESTS =========="
cat > implementation/orchestrator/tests/test_semantic_knowledge_seed.py <<'PY'
from orchestrator.semantic_knowledge_seed import build_trusted_semantic_registry


def test_cpu_and_processor_resolve_to_same_active_concept():
    registry = build_trusted_semantic_registry()
    cpu = registry.resolve_term("CPU")
    processor = registry.resolve_term("processor")
    assert cpu is not None and processor is not None
    assert cpu.concept_id == "processor.model"
    assert processor.concept_id == "processor.model"


def test_ram_and_memory_resolve_to_same_active_concept():
    registry = build_trusted_semantic_registry()
    ram = registry.resolve_term("RAM")
    memory = registry.resolve_term("memory")
    assert ram is not None and memory is not None
    assert ram.concept_id == "memory.total"
    assert memory.concept_id == "memory.total"
    assert ram.canonical_unit == "byte"


def test_windows_display_version_carries_required_windows_release_context():
    registry = build_trusted_semantic_registry()
    concept = registry.resolve_term("Windows Display Version")
    assert concept is not None
    assert concept.concept_id == "operating_system.windows.display_version"
    assert concept.evidence_contexts == ("operating_system", "windows_release")


def test_datto_processor_field_is_provider_scoped():
    registry = build_trusted_semantic_registry()
    concept = registry.resolve_provider_field(
        provider="datto_rmm",
        resource_type="endpoint",
        provider_field="cpuModel",
    )
    assert concept is not None
    assert concept.concept_id == "processor.model"
    assert registry.resolve_provider_field(
        provider="autotask",
        resource_type="endpoint",
        provider_field="cpuModel",
    ) is None


def test_person_endpoint_relationship_is_active_with_temporal_semantics():
    registry = build_trusted_semantic_registry()
    relationship = registry.active_relationship("person.logged_in_to.endpoint")
    assert relationship is not None
    assert relationship.subject_type == "person"
    assert relationship.target_type == "endpoint"
    assert set(relationship.temporal_semantics) == {"current", "most_recent", "historical"}
PY

echo "WROTE: implementation/orchestrator/tests/test_semantic_knowledge_seed.py"

echo "========== SECTION 4: VALIDATE =========="
git diff --check
.venv/bin/python -m pytest -q \
  implementation/orchestrator/tests/test_semantic_knowledge_registry.py \
  implementation/orchestrator/tests/test_semantic_knowledge_seed.py \
  implementation/orchestrator/tests/test_canonical_fact_vocabulary.py \
  implementation/orchestrator/tests/test_semantic_resource_request.py

echo "========== SECTION 5: CHANGE STATE =========="ngit status --short

echo "========== RESULT =========="necho "Trusted existing semantic knowledge is seeded into the governed registry without changing runtime resolution yet."
echo "NO DEPLOYMENT PERFORMED."
echo "NO COMMIT OR PUSH OF WORKTREE CHANGES PERFORMED."
echo "========== END SEMANTIC KNOWLEDGE REGISTRY SEED =========="
