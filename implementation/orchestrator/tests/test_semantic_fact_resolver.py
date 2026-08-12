from orchestrator.semantic_fact_resolver import SemanticFactResolver
from orchestrator.semantic_knowledge_seed import build_trusted_semantic_registry


def test_registry_precedes_legacy_vocabulary_for_cpu():
    resolver = SemanticFactResolver()
    result = resolver.resolve("CPU")
    assert result is not None
    assert result.canonical_fact == "processor model"
    assert result.concept_id == "processor.model"
    assert result.source == "semantic_knowledge_registry"
    assert result.evidence_contexts == ("processor", "hardware_inventory")


def test_registry_precedes_legacy_vocabulary_for_ram():
    resolver = SemanticFactResolver()
    result = resolver.resolve("RAM")
    assert result is not None
    assert result.canonical_fact == "total memory"
    assert result.concept_id == "memory.total"
    assert result.source == "semantic_knowledge_registry"


def test_registry_supplies_windows_display_version_context():
    resolver = SemanticFactResolver()
    result = resolver.resolve("Windows Display Version")
    assert result is not None
    assert result.canonical_fact == "operating system display version"
    assert result.evidence_contexts == ("operating_system", "windows_release")


def test_bios_uses_registry_after_broad_seed_migration():
    resolver = SemanticFactResolver()
    result = resolver.resolve("BIOS")
    assert result is not None
    assert result.canonical_fact == "bios version"
    assert result.concept_id == "firmware.bios.version"
    assert result.source == "semantic_knowledge_registry"


def test_legacy_compatibility_fallback_remains_available_for_unmigrated_registry():
    from orchestrator.canonical_fact_vocabulary import DEFAULT_CANONICAL_FACT_VOCABULARY
    from orchestrator.semantic_knowledge_registry import SemanticKnowledgeRegistry

    resolver = SemanticFactResolver(
        registry=SemanticKnowledgeRegistry(),
        legacy_vocabulary=DEFAULT_CANONICAL_FACT_VOCABULARY,
    )
    result = resolver.resolve("BIOS")
    assert result is not None
    assert result.canonical_fact == "bios version"
    assert result.source == "canonical_fact_vocabulary_fallback"


def test_unknown_term_remains_unresolved():
    resolver = SemanticFactResolver()
    assert resolver.resolve("absolutely unknown hardware frobnicator") is None


def test_registry_canonicalizes_reasoner_cpu_fragment():
    resolver = SemanticFactResolver()
    result = resolver.canonicalize_requested_facts(
        human_text="What CPU is in AOT-50282?",
        requested_facts=("cpu",),
    )
    assert result == ("processor model",)


def test_registry_canonicalizes_windows_display_version_fragment():
    resolver = SemanticFactResolver()
    result = resolver.canonicalize_requested_facts(
        human_text="What is the Windows Display Version for AOT-50282?",
        requested_facts=("display", "version"),
    )
    assert result == ("operating system display version",)


def test_resolve_requested_facts_returns_registry_metadata_for_cpu():
    resolver = SemanticFactResolver(
        registry=build_trusted_semantic_registry(),
        legacy_vocabulary=None,
    )
    resolutions = resolver.resolve_requested_facts(
        human_text="What CPU does AOT-50282 have?",
        requested_facts=("CPU",),
    )
    assert len(resolutions) == 1
    resolution = resolutions[0]
    assert resolution.canonical_fact == "processor model"
    assert resolution.canonical_label == "processor model"
    assert resolution.concept_id == "processor.model"
    assert resolution.evidence_contexts == ("processor", "hardware_inventory")
    assert resolution.expected_shape == "descriptive_string"


def test_resolve_requested_facts_preserves_unknown_fact_without_inventing_semantics():
    resolver = SemanticFactResolver(
        registry=build_trusted_semantic_registry(),
        legacy_vocabulary=None,
    )
    resolutions = resolver.resolve_requested_facts(
        human_text="What quantum widget is on AOT-50282?",
        requested_facts=("quantum widget",),
    )
    assert len(resolutions) == 1
    resolution = resolutions[0]
    assert resolution.canonical_fact == "quantum widget"
    assert resolution.expected_shape is None
    assert resolution.evidence_contexts == ()
    assert resolution.source == "unresolved_passthrough"
