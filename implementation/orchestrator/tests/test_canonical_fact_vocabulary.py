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


def test_fragmented_windows_display_version_is_recombined_from_human_text():
    assert DEFAULT_CANONICAL_FACT_VOCABULARY.canonicalize_requested_facts(
        human_text="What is the Windows Display Version for AOT-50282?",
        requested_facts=("display", "version"),
    ) == ("operating system display version",)


def test_qualified_fact_internal_ip_resolves_lan():
    result = (
        DEFAULT_CANONICAL_FACT_VOCABULARY
        .resolve_qualified_human_text(
            human_text=(
                "What IP is AOT-50282 "
                "using internally?"
            ),
            eligible_facts=(
                "LAN IP address",
                "WAN IP address",
            ),
        )
    )

    assert result.status == "resolved"
    assert result.definition is not None
    assert (
        result.definition.canonical_fact
        == "LAN IP address"
    )


def test_qualified_fact_internet_facing_ip_resolves_wan():
    result = (
        DEFAULT_CANONICAL_FACT_VOCABULARY
        .resolve_qualified_human_text(
            human_text=(
                "What is the internet-facing "
                "IP for AOT-50282?"
            ),
            eligible_facts=(
                "LAN IP address",
                "WAN IP address",
            ),
        )
    )

    assert result.status == "resolved"
    assert result.definition is not None
    assert (
        result.definition.canonical_fact
        == "WAN IP address"
    )


def test_qualified_fact_bare_ip_is_ambiguous():
    result = (
        DEFAULT_CANONICAL_FACT_VOCABULARY
        .resolve_qualified_human_text(
            human_text=(
                "What IP does AOT-50282 have?"
            ),
            eligible_facts=(
                "LAN IP address",
                "WAN IP address",
            ),
        )
    )

    assert result.status == "ambiguous"
    assert result.definition is None
    assert result.qualifier_conflict is False


def test_qualified_fact_conflicting_ip_is_ambiguous():
    result = (
        DEFAULT_CANONICAL_FACT_VOCABULARY
        .resolve_qualified_human_text(
            human_text=(
                "What is the internal public "
                "IP of AOT-50282?"
            ),
            eligible_facts=(
                "LAN IP address",
                "WAN IP address",
            ),
        )
    )

    assert result.status == "ambiguous"
    assert result.definition is None
    assert result.qualifier_conflict is True


def test_qualified_fact_unrelated_language_is_not_applicable():
    result = (
        DEFAULT_CANONICAL_FACT_VOCABULARY
        .resolve_qualified_human_text(
            human_text=(
                "Which internal user is "
                "on AOT-50282?"
            ),
            eligible_facts=(
                "LAN IP address",
                "WAN IP address",
            ),
        )
    )

    assert result.status == "not_applicable"
    assert result.definition is None


def test_ambiguous_qualified_fact_returns_only_active_competing_facts():
    result = (
        DEFAULT_CANONICAL_FACT_VOCABULARY
        .resolve_qualified_human_text(
            human_text=(
                "What IP does AOT-50282 have?"
            ),
            eligible_facts=(
                "LAN IP address",
                "WAN IP address",
                "last logged in user",
            ),
        )
    )

    assert result.status == "ambiguous"

    assert tuple(
        item.canonical_fact
        for item in result.candidates
    ) == (
        "LAN IP address",
        "WAN IP address",
    )
