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


def test_datto_display_version_is_not_seeded_as_windows_release_provider_evidence():
    registry = build_trusted_semantic_registry()
    for provider_field in ("displayVersion", "DisplayVersion", "display_version", "windowsDisplayVersion"):
        assert registry.resolve_provider_field(
            provider="datto_rmm",
            resource_type="endpoint",
            provider_field=provider_field,
        ) is None


def test_broad_seed_covers_endpoint_and_identity_terms():
    registry = build_trusted_semantic_registry()
    expected = {
        "hostname": "endpoint.hostname",
        "serial number": "endpoint.serial_number",
        "installed software": "software.installed.collection",
        "firewall status": "security.firewall.status",
        "email address": "identity.email_address",
        "m365 license": "microsoft365.license.assignment",
    }
    for term, concept_id in expected.items():
        concept = registry.resolve_term(term)
        assert concept is not None
        assert concept.concept_id == concept_id


def test_broad_seed_preserves_ambiguous_generic_words_as_unresolved():
    registry = build_trusted_semantic_registry()
    for term in ("version", "status", "name", "owner", "user"):
        assert registry.resolve_term(term) is None


def test_broad_seed_has_common_cross_system_relationships():
    registry = build_trusted_semantic_registry()
    relationship_ids = {
        "person.member_of.organization",
        "person.owns.endpoint",
        "person.assigned_to.ticket",
        "contact.belongs_to.organization",
        "endpoint.belongs_to.organization",
        "endpoint.located_at.site",
        "ticket.belongs_to.organization",
        "ticket.references.endpoint",
        "alert.affects.endpoint",
        "control.applies_to.resource",
    }
    active = {item.relationship_id for item in registry.active_relationships()}
    assert relationship_ids.issubset(active)


def test_broad_seed_collapses_equivalent_normalized_term_aliases():
    registry = build_trusted_semantic_registry()
    spaced = registry.resolve_term("last check in")
    hyphenated = registry.resolve_term("last check-in")
    assert spaced is not None and hyphenated is not None
    assert spaced.concept_id == "endpoint.last_seen"
    assert hyphenated.concept_id == "endpoint.last_seen"
