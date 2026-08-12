from orchestrator.semantic_fact_resolver import SemanticFactResolver


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


def test_unmigrated_concept_uses_legacy_compatibility_fallback():
    resolver = SemanticFactResolver()
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
