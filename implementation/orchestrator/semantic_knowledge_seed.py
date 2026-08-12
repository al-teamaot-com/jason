from __future__ import annotations

from orchestrator.semantic_knowledge_registry import (
    SemanticConcept,
    SemanticKnowledgeRegistry,
    SemanticLifecycleState,
    SemanticProviderFieldBinding,
    SemanticProvenance,
    SemanticRelationshipDefinition,
    SemanticTermBinding,
    normalize_semantic_term,
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
        "operating_system.build": ("build", "buildNumber", "osBuild", "osBuildNumber"),
    }

    for concept_id, provider_fields in datto_fields.items():
        seen_provider_fields: set[str] = set()
        for provider_field in provider_fields:
            normalized_provider_field = normalize_semantic_term(provider_field)
            if normalized_provider_field in seen_provider_fields:
                continue
            seen_provider_fields.add(normalized_provider_field)
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

    broad_concepts = (
        SemanticConcept(concept_id="operating_system.name", canonical_label="operating system", kind="fact", expected_shape="descriptive_string", evidence_contexts=("operating_system",), provenance=provenance, review_interval_days=180, retirement_criteria="retire only when superseded by a governed canonical operating-system concept"),
        SemanticConcept(concept_id="firmware.bios.version", canonical_label="bios version", kind="fact", expected_shape="descriptive_string", evidence_contexts=("bios", "hardware_inventory"), provenance=provenance, review_interval_days=180, retirement_criteria="retire only when superseded by a governed firmware concept"),
        SemanticConcept(concept_id="network.adapter.collection", canonical_label="network adapters", kind="fact", expected_shape="collection", evidence_contexts=("network", "hardware_inventory"), provenance=provenance, review_interval_days=180, retirement_criteria="retire only when superseded by governed network-interface inventory semantics"),
        SemanticConcept(concept_id="storage.logical_disk.collection", canonical_label="logical disks", kind="fact", expected_shape="collection", evidence_contexts=("storage", "hardware_inventory"), provenance=provenance, review_interval_days=180, retirement_criteria="retire only when superseded by governed storage inventory semantics"),
        SemanticConcept(concept_id="graphics.adapter.collection", canonical_label="display adapters", kind="fact", expected_shape="collection", evidence_contexts=("graphics", "hardware_inventory"), provenance=provenance, review_interval_days=180, retirement_criteria="retire only when superseded by governed graphics inventory semantics"),
        SemanticConcept(concept_id="endpoint.hostname", canonical_label="endpoint hostname", kind="fact", expected_shape="descriptive_string", evidence_contexts=("identity", "endpoint"), provenance=provenance, review_interval_days=180, retirement_criteria="retire only when endpoint naming semantics are replaced by a governed identity concept"),
        SemanticConcept(concept_id="endpoint.serial_number", canonical_label="endpoint serial number", kind="fact", expected_shape="descriptive_string", evidence_contexts=("identity", "hardware_inventory"), provenance=provenance, review_interval_days=180, retirement_criteria="retire only when superseded by governed hardware identity semantics"),
        SemanticConcept(concept_id="endpoint.manufacturer", canonical_label="endpoint manufacturer", kind="fact", expected_shape="descriptive_string", evidence_contexts=("hardware_inventory",), provenance=provenance, review_interval_days=180, retirement_criteria="retire only when superseded by governed hardware inventory semantics"),
        SemanticConcept(concept_id="endpoint.model", canonical_label="endpoint model", kind="fact", expected_shape="descriptive_string", evidence_contexts=("hardware_inventory",), provenance=provenance, review_interval_days=180, retirement_criteria="retire only when superseded by governed hardware inventory semantics"),
        SemanticConcept(concept_id="endpoint.ip_address", canonical_label="ip address", kind="fact", expected_shape="descriptive_string", evidence_contexts=("network", "endpoint"), provenance=provenance, review_interval_days=90, retirement_criteria="retire only when superseded by governed endpoint network identity semantics"),
        SemanticConcept(concept_id="endpoint.mac_address", canonical_label="mac address", kind="fact", expected_shape="descriptive_string", evidence_contexts=("network", "endpoint"), provenance=provenance, review_interval_days=180, retirement_criteria="retire only when superseded by governed endpoint network identity semantics"),
        SemanticConcept(concept_id="endpoint.last_seen", canonical_label="endpoint last seen", kind="fact", expected_shape="timestamp", evidence_contexts=("endpoint", "presence"), provenance=provenance, review_interval_days=90, retirement_criteria="retire only when superseded by governed endpoint presence semantics"),
        SemanticConcept(concept_id="software.installed.collection", canonical_label="installed software", kind="fact", expected_shape="collection", evidence_contexts=("software_inventory",), provenance=provenance, review_interval_days=90, retirement_criteria="retire only when superseded by governed software inventory semantics"),
        SemanticConcept(concept_id="software.patch.status", canonical_label="patch status", kind="fact", expected_shape="descriptive_string", evidence_contexts=("patching", "software_inventory"), provenance=provenance, review_interval_days=90, retirement_criteria="retire only when superseded by governed patch-state semantics"),
        SemanticConcept(concept_id="security.antivirus.status", canonical_label="antivirus status", kind="fact", expected_shape="descriptive_string", evidence_contexts=("security", "endpoint_protection"), provenance=provenance, review_interval_days=90, retirement_criteria="retire only when superseded by governed endpoint-protection semantics"),
        SemanticConcept(concept_id="security.firewall.status", canonical_label="firewall status", kind="fact", expected_shape="descriptive_string", evidence_contexts=("security", "firewall"), provenance=provenance, review_interval_days=90, retirement_criteria="retire only when superseded by governed firewall semantics"),
        SemanticConcept(concept_id="identity.email_address", canonical_label="email address", kind="fact", expected_shape="descriptive_string", evidence_contexts=("identity", "contact"), provenance=provenance, review_interval_days=180, retirement_criteria="retire only when superseded by governed identity-address semantics"),
        SemanticConcept(concept_id="identity.account_name", canonical_label="account name", kind="fact", expected_shape="descriptive_string", evidence_contexts=("identity", "account"), provenance=provenance, review_interval_days=180, retirement_criteria="retire only when superseded by governed account identity semantics"),
        SemanticConcept(concept_id="identity.account_enabled", canonical_label="account enabled", kind="fact", expected_shape="boolean", evidence_contexts=("identity", "account_state"), provenance=provenance, review_interval_days=90, retirement_criteria="retire only when superseded by governed account-state semantics"),
        SemanticConcept(concept_id="organization.primary_contact", canonical_label="primary contact", kind="fact", expected_shape="descriptive_string", evidence_contexts=("organization", "contact_relationship"), provenance=provenance, review_interval_days=180, retirement_criteria="retire only when superseded by governed organization-contact semantics"),
        SemanticConcept(concept_id="ticket.number", canonical_label="ticket number", kind="fact", expected_shape="descriptive_string", evidence_contexts=("ticket", "identity"), provenance=provenance, review_interval_days=180, retirement_criteria="retire only when superseded by governed ticket identity semantics"),
        SemanticConcept(concept_id="ticket.priority", canonical_label="ticket priority", kind="fact", expected_shape="descriptive_string", evidence_contexts=("ticket", "workflow"), provenance=provenance, review_interval_days=180, retirement_criteria="retire only when superseded by governed ticket workflow semantics"),
        SemanticConcept(concept_id="ticket.queue", canonical_label="ticket queue", kind="fact", expected_shape="descriptive_string", evidence_contexts=("ticket", "workflow"), provenance=provenance, review_interval_days=180, retirement_criteria="retire only when superseded by governed ticket routing semantics"),
        SemanticConcept(concept_id="alert.severity", canonical_label="alert severity", kind="fact", expected_shape="descriptive_string", evidence_contexts=("alert", "risk"), provenance=provenance, review_interval_days=180, retirement_criteria="retire only when superseded by governed alert severity semantics"),
        SemanticConcept(concept_id="compliance.control.identifier", canonical_label="control identifier", kind="fact", expected_shape="descriptive_string", evidence_contexts=("compliance", "control"), provenance=provenance, review_interval_days=180, retirement_criteria="retire only when superseded by governed compliance-control semantics"),
        SemanticConcept(concept_id="microsoft365.license.assignment", canonical_label="microsoft 365 license assignment", kind="fact", expected_shape="collection", evidence_contexts=("microsoft365", "licensing"), provenance=provenance, review_interval_days=90, retirement_criteria="retire only when superseded by governed cloud licensing semantics"),
        SemanticConcept(concept_id="microsoft365.mailbox.type", canonical_label="mailbox type", kind="fact", expected_shape="descriptive_string", evidence_contexts=("microsoft365", "mailbox"), provenance=provenance, review_interval_days=90, retirement_criteria="retire only when superseded by governed mailbox semantics"),
    )

    for concept in broad_concepts:
        registry.add_concept(concept)
        _activate_concept(registry, concept.concept_id)

    broad_terms = {
        "operating_system.name": ("operating system", "os", "windows version", "operating system version"),
        "firmware.bios.version": ("bios", "bios version", "firmware bios version"),
        "network.adapter.collection": ("network adapter", "network adapters", "nic", "nics", "network interfaces"),
        "storage.logical_disk.collection": ("logical disk", "logical disks", "disk", "disks", "drives"),
        "graphics.adapter.collection": ("display adapter", "display adapters", "video board", "video boards", "graphics adapter", "graphics adapters", "gpu", "gpus"),
        "endpoint.hostname": ("hostname", "computer name", "device name", "endpoint name", "machine name"),
        "endpoint.serial_number": ("serial number", "serial", "service tag", "device serial"),
        "endpoint.manufacturer": ("manufacturer", "vendor", "device manufacturer"),
        "endpoint.model": ("device model", "computer model", "machine model", "endpoint model"),
        "endpoint.ip_address": ("ip address", "ip", "ipv4 address", "endpoint ip"),
        "endpoint.mac_address": ("mac address", "mac", "hardware address"),
        "endpoint.last_seen": ("last seen", "last online", "last check in", "last check-in", "last contact"),
        "software.installed.collection": ("installed software", "installed apps", "installed applications", "software inventory", "application inventory"),
        "software.patch.status": ("patch status", "patching status", "update status", "missing patches"),
        "security.antivirus.status": ("antivirus status", "av status", "endpoint protection status", "antimalware status"),
        "security.firewall.status": ("firewall status", "windows firewall status", "host firewall status"),
        "identity.email_address": ("email address", "email", "mail address"),
        "identity.account_name": ("account name", "username", "user name", "login name", "signin name", "sign in name"),
        "identity.account_enabled": ("account enabled", "enabled account", "account active", "sign in enabled", "signin enabled"),
        "organization.primary_contact": ("primary contact", "main contact", "company primary contact", "organization primary contact"),
        "ticket.number": ("ticket number", "ticket id", "case number", "case id"),
        "ticket.priority": ("ticket priority", "case priority", "priority level"),
        "ticket.queue": ("ticket queue", "support queue", "work queue", "ticket routing queue"),
        "alert.severity": ("alert severity", "severity level", "risk severity"),
        "compliance.control.identifier": ("control identifier", "control id", "control number", "requirement id"),
        "microsoft365.license.assignment": ("microsoft 365 license", "m365 license", "office 365 license", "license assignment", "assigned licenses"),
        "microsoft365.mailbox.type": ("mailbox type", "shared mailbox", "user mailbox", "room mailbox", "equipment mailbox"),
    }

    seen_broad_terms: dict[tuple[str, str], str] = {}
    for concept_id, aliases in broad_terms.items():
        for term in aliases:
            normalized_term = normalize_semantic_term(term)
            key = ("global", normalized_term)
            existing_concept_id = seen_broad_terms.get(key)
            if existing_concept_id is not None:
                if existing_concept_id != concept_id:
                    raise ValueError(
                        f"broad semantic term is ambiguous: {term!r} maps to both "
                        f"{existing_concept_id!r} and {concept_id!r}"
                    )
                continue
            seen_broad_terms[key] = concept_id
            registry.add_term(SemanticTermBinding(term=term, concept_id=concept_id, provenance=provenance))
            _activate_term(registry, term=term)

    broad_relationships = (
        SemanticRelationshipDefinition(relationship_id="person.member_of.organization", subject_type="person", target_type="organization", temporal_semantics=("unspecified", "current", "historical"), provenance=provenance),
        SemanticRelationshipDefinition(relationship_id="person.owns.endpoint", subject_type="person", target_type="endpoint", temporal_semantics=("unspecified", "current", "historical"), provenance=provenance),
        SemanticRelationshipDefinition(relationship_id="person.assigned_to.ticket", subject_type="person", target_type="ticket", temporal_semantics=("unspecified", "current", "historical"), provenance=provenance),
        SemanticRelationshipDefinition(relationship_id="contact.belongs_to.organization", subject_type="contact", target_type="organization", temporal_semantics=("unspecified", "current", "historical"), provenance=provenance),
        SemanticRelationshipDefinition(relationship_id="endpoint.belongs_to.organization", subject_type="endpoint", target_type="organization", temporal_semantics=("unspecified", "current", "historical"), provenance=provenance),
        SemanticRelationshipDefinition(relationship_id="endpoint.located_at.site", subject_type="endpoint", target_type="site", temporal_semantics=("unspecified", "current", "historical"), provenance=provenance),
        SemanticRelationshipDefinition(relationship_id="ticket.belongs_to.organization", subject_type="ticket", target_type="organization", temporal_semantics=("unspecified", "current", "historical"), provenance=provenance),
        SemanticRelationshipDefinition(relationship_id="ticket.references.endpoint", subject_type="ticket", target_type="endpoint", temporal_semantics=("unspecified", "current", "historical"), provenance=provenance),
        SemanticRelationshipDefinition(relationship_id="alert.affects.endpoint", subject_type="alert", target_type="endpoint", temporal_semantics=("unspecified", "current", "historical"), provenance=provenance),
        SemanticRelationshipDefinition(relationship_id="control.applies_to.resource", subject_type="control", target_type="resource", temporal_semantics=("unspecified", "current", "historical"), provenance=provenance),
    )

    for relationship_item in broad_relationships:
        registry.add_relationship(relationship_item)
        _activate_relationship(registry, relationship_item.relationship_id)

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
