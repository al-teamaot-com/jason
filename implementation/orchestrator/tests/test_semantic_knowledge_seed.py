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


def test_case_equivalent_provider_aliases_seed_once():
    registry = build_trusted_semantic_registry()
    lower = registry.resolve_provider_field(
        provider="datto_rmm",
        resource_type="endpoint",
        provider_field="displayVersion",
    )
    upper = registry.resolve_provider_field(
        provider="datto_rmm",
        resource_type="endpoint",
        provider_field="DisplayVersion",
    )
    assert lower is not None and upper is not None
    assert lower.concept_id == "operating_system.windows.display_version"
    assert upper.concept_id == lower.concept_id
