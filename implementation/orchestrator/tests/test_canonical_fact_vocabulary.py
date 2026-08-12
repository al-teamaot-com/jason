from orchestrator.canonical_fact_vocabulary import DEFAULT_CANONICAL_FACT_VOCABULARY


def canonical(value: str) -> str:
    return DEFAULT_CANONICAL_FACT_VOCABULARY.canonicalize(value)


def test_processor_language_normalizes_to_model_concept():
    assert canonical("processor") == "processor model"
    assert canonical("CPU") == "processor model"
    assert canonical("cpu model") == "processor model"


def test_processor_count_language_is_distinct_from_model():
    assert canonical("processor count") == "logical processor count"
    assert canonical("logical processors") == "logical processor count"
    assert canonical("threads") == "logical processor count"


def test_memory_aliases_and_bounded_typo_normalize():
    assert canonical("RAM") == "total memory"
    assert canonical("memory") == "total memory"
    assert canonical("physical memory") == "total memory"
    assert canonical("memore") == "total memory"


def test_windows_display_version_is_not_graphics_display():
    assert canonical("Windows Display Version") == "operating system display version"
    assert canonical("DisplayVersion") == "operating system display version"
    assert canonical("display") == "display"
    assert canonical("GPU") == "display adapters"


def test_unknown_or_ambiguous_language_is_not_invented():
    assert canonical("temperature") == "temperature"
    assert canonical("count") == "count"


def test_canonical_facts_expose_provider_neutral_evidence_hints():
    vocab = DEFAULT_CANONICAL_FACT_VOCABULARY
    processor = vocab.resolve("processor")
    display_version = vocab.resolve("Windows Display Version")
    assert processor is not None and "model" in processor.evidence_hints
    assert display_version is not None and "displayversion" in display_version.evidence_hints
