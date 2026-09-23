#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START BROAD SEMANTIC KNOWLEDGE REGISTRY SEED =========="
echo "========== SECTION 1: PRECONDITIONS =========="
echo "HEAD: $(git rev-parse --short HEAD)"

DIRTY="$(git status --porcelain | grep -v '^?? FETCH_HEAD$' || true)"
if [[ -n "$DIRTY" ]]; then
  echo "ERROR: worktree must be clean before broad semantic seed work."
  printf '%s\n' "$DIRTY"
  exit 20
fi

echo "========== SECTION 2: EXTEND TRUSTED SEMANTIC SEED =========="
.venv/bin/python - <<'PY'
from pathlib import Path

path = Path("implementation/orchestrator/semantic_knowledge_seed.py")
text = path.read_text()

anchor = "    relationship = SemanticRelationshipDefinition(\n"
if anchor not in text:
    raise SystemExit("ERROR: trusted semantic seed relationship anchor missing")

insert = '''    broad_concepts = (\n        SemanticConcept(concept_id="operating_system.name", canonical_label="operating system", kind="fact", expected_shape="descriptive_string", evidence_contexts=("operating_system",), provenance=provenance, review_interval_days=180, retirement_criteria="retire only when superseded by a governed canonical operating-system concept"),\n        SemanticConcept(concept_id="firmware.bios.version", canonical_label="bios version", kind="fact", expected_shape="descriptive_string", evidence_contexts=("bios", "hardware_inventory"), provenance=provenance, review_interval_days=180, retirement_criteria="retire only when superseded by a governed firmware concept"),\n        SemanticConcept(concept_id="network.adapter.collection", canonical_label="network adapters", kind="fact", expected_shape="collection", evidence_contexts=("network", "hardware_inventory"), provenance=provenance, review_interval_days=180, retirement_criteria="retire only when superseded by governed network-interface inventory semantics"),\n        SemanticConcept(concept_id="storage.logical_disk.collection", canonical_label="logical disks", kind="fact", expected_shape="collection", evidence_contexts=("storage", "hardware_inventory"), provenance=provenance, review_interval_days=180, retirement_criteria="retire only when superseded by governed storage inventory semantics"),\n        SemanticConcept(concept_id="graphics.adapter.collection", canonical_label="display adapters", kind="fact", expected_shape="collection", evidence_contexts=("graphics", "hardware_inventory"), provenance=provenance, review_interval_days=180, retirement_criteria="retire only when superseded by governed graphics inventory semantics"),\n        SemanticConcept(concept_id="endpoint.hostname", canonical_label="endpoint hostname", kind="fact", expected_shape="descriptive_string", evidence_contexts=("identity", "endpoint"), provenance=provenance, review_interval_days=180, retirement_criteria="retire only when endpoint naming semantics are replaced by a governed identity concept"),\n        SemanticConcept(concept_id="endpoint.serial_number", canonical_label="endpoint serial number", kind="fact", expected_shape="descriptive_string", evidence_contexts=("identity", "hardware_inventory"), provenance=provenance, review_interval_days=180, retirement_criteria="retire only when superseded by governed hardware identity semantics"),\n        SemanticConcept(concept_id="endpoint.manufacturer", canonical_label="endpoint manufacturer", kind="fact", expected_shape="descriptive_string", evidence_contexts=("hardware_inventory",), provenance=provenance, review_interval_days=180, retirement_criteria="retire only when superseded by governed hardware inventory semantics"),\n        SemanticConcept(concept_id="endpoint.model", canonical_label="endpoint model", kind="fact", expected_shape="descriptive_string", evidence_contexts=("hardware_inventory",), provenance=provenance, review_interval_days=180, retirement_criteria="retire only when superseded by governed hardware inventory semantics"),\n        SemanticConcept(concept_id="endpoint.ip_address", canonical_label="ip address", kind="fact", expected_shape="descriptive_string", evidence_contexts=("network", "endpoint"), provenance=provenance, review_interval_days=90, retirement_criteria="retire only when superseded by governed endpoint network identity semantics"),\n        SemanticConcept(concept_id="endpoint.mac_address", canonical_label="mac address", kind="fact", expected_shape="descriptive_string", evidence_contexts=("network", "endpoint"), provenance=provenance, review_interval_days=180, retirement_criteria="retire only when superseded by governed endpoint network identity semantics"),\n        SemanticConcept(concept_id="endpoint.last_seen", canonical_label="endpoint last seen", kind="fact", expected_shape="timestamp", evidence_contexts=("endpoint", "presence"), provenance=provenance, review_interval_days=90, retirement_criteria="retire only when superseded by governed endpoint presence semantics"),\n        SemanticConcept(concept_id="software.installed.collection", canonical_label="installed software", kind="fact", expected_shape="collection", evidence_contexts=("software_inventory",), provenance=provenance, review_interval_days=90, retirement_criteria="retire only when superseded by governed software inventory semantics"),\n        SemanticConcept(concept_id="software.patch.status", canonical_label="patch status", kind="fact", expected_shape="descriptive_string", evidence_contexts=("patching", "software_inventory"), provenance=provenance, review_interval_days=90, retirement_criteria="retire only when superseded by governed patch-state semantics"),\n        SemanticConcept(concept_id="security.antivirus.status", canonical_label="antivirus status", kind="fact", expected_shape="descriptive_string", evidence_contexts=("security", "endpoint_protection"), provenance=provenance, review_interval_days=90, retirement_criteria="retire only when superseded by governed endpoint-protection semantics"),\n        SemanticConcept(concept_id="security.firewall.status", canonical_label="firewall status", kind="fact", expected_shape="descriptive_string", evidence_contexts=("security", "firewall"), provenance=provenance, review_interval_days=90, retirement_criteria="retire only when superseded by governed firewall semantics"),\n        SemanticConcept(concept_id="identity.email_address", canonical_label="email address", kind="fact", expected_shape="descriptive_string", evidence_contexts=("identity", "contact"), provenance=provenance, review_interval_days=180, retirement_criteria="retire only when superseded by governed identity-address semantics"),\n        SemanticConcept(concept_id="identity.account_name", canonical_label="account name", kind="fact", expected_shape="descriptive_string", evidence_contexts=("identity", "account"), provenance=provenance, review_interval_days=180, retirement_criteria="retire only when superseded by governed account identity semantics"),\n        SemanticConcept(concept_id="identity.account_enabled", canonical_label="account enabled", kind="fact", expected_shape="boolean", evidence_contexts=("identity", "account_state"), provenance=provenance, review_interval_days=90, retirement_criteria="retire only when superseded by governed account-state semantics"),\n        SemanticConcept(concept_id="organization.primary_contact", canonical_label="primary contact", kind="fact", expected_shape="descriptive_string", evidence_contexts=("organization", "contact_relationship"), provenance=provenance, review_interval_days=180, retirement_criteria="retire only when superseded by governed organization-contact semantics"),\n        SemanticConcept(concept_id="ticket.number", canonical_label="ticket number", kind="fact", expected_shape="descriptive_string", evidence_contexts=("ticket", "identity"), provenance=provenance, review_interval_days=180, retirement_criteria="retire only when superseded by governed ticket identity semantics"),\n        SemanticConcept(concept_id="ticket.priority", canonical_label="ticket priority", kind="fact", expected_shape="descriptive_string", evidence_contexts=("ticket", "workflow"), provenance=provenance, review_interval_days=180, retirement_criteria="retire only when superseded by governed ticket workflow semantics"),\n        SemanticConcept(concept_id="ticket.queue", canonical_label="ticket queue", kind="fact", expected_shape="descriptive_string", evidence_contexts=("ticket", "workflow"), provenance=provenance, review_interval_days=180, retirement_criteria="retire only when superseded by governed ticket routing semantics"),\n        SemanticConcept(concept_id="alert.severity", canonical_label="alert severity", kind="fact", expected_shape="descriptive_string", evidence_contexts=("alert", "risk"), provenance=provenance, review_interval_days=180, retirement_criteria="retire only when superseded by governed alert severity semantics"),\n        SemanticConcept(concept_id="compliance.control.identifier", canonical_label="control identifier", kind="fact", expected_shape="descriptive_string", evidence_contexts=("compliance", "control"), provenance=provenance, review_interval_days=180, retirement_criteria="retire only when superseded by governed compliance-control semantics"),\n        SemanticConcept(concept_id="microsoft365.license.assignment", canonical_label="microsoft 365 license assignment", kind="fact", expected_shape="collection", evidence_contexts=("microsoft365", "licensing"), provenance=provenance, review_interval_days=90, retirement_criteria="retire only when superseded by governed cloud licensing semantics"),\n        SemanticConcept(concept_id="microsoft365.mailbox.type", canonical_label="mailbox type", kind="fact", expected_shape="descriptive_string", evidence_contexts=("microsoft365", "mailbox"), provenance=provenance, review_interval_days=90, retirement_criteria="retire only when superseded by governed mailbox semantics"),\n    )\n\n    for concept in broad_concepts:\n        registry.add_concept(concept)\n        _activate_concept(registry, concept.concept_id)\n\n    broad_terms = {\n        "operating_system.name": ("operating system", "os", "windows version", "operating system version"),\n        "firmware.bios.version": ("bios", "bios version", "firmware bios version"),\n        "network.adapter.collection": ("network adapter", "network adapters", "nic", "nics", "network interfaces"),\n        "storage.logical_disk.collection": ("logical disk", "logical disks", "disk", "disks", "drives"),\n        "graphics.adapter.collection": ("display adapter", "display adapters", "video board", "video boards", "graphics adapter", "graphics adapters", "gpu", "gpus"),\n        "endpoint.hostname": ("hostname", "computer name", "device name", "endpoint name", "machine name"),\n        "endpoint.serial_number": ("serial number", "serial", "service tag", "device serial"),\n        "endpoint.manufacturer": ("manufacturer", "vendor", "device manufacturer"),\n        "endpoint.model": ("device model", "computer model", "machine model", "endpoint model"),\n        "endpoint.ip_address": ("ip address", "ip", "ipv4 address", "endpoint ip"),\n        "endpoint.mac_address": ("mac address", "mac", "hardware address"),\n        "endpoint.last_seen": ("last seen", "last online", "last check in", "last check-in", "last contact"),\n        "software.installed.collection": ("installed software", "installed apps", "installed applications", "software inventory", "application inventory"),\n        "software.patch.status": ("patch status", "patching status", "update status", "missing patches"),\n        "security.antivirus.status": ("antivirus status", "av status", "endpoint protection status", "antimalware status"),\n        "security.firewall.status": ("firewall status", "windows firewall status", "host firewall status"),\n        "identity.email_address": ("email address", "email", "mail address"),\n        "identity.account_name": ("account name", "username", "user name", "login name", "signin name", "sign in name"),\n        "identity.account_enabled": ("account enabled", "enabled account", "account active", "sign in enabled", "signin enabled"),\n        "organization.primary_contact": ("primary contact", "main contact", "company primary contact", "organization primary contact"),\n        "ticket.number": ("ticket number", "ticket id", "case number", "case id"),\n        "ticket.priority": ("ticket priority", "case priority", "priority level"),\n        "ticket.queue": ("ticket queue", "support queue", "work queue", "ticket routing queue"),\n        "alert.severity": ("alert severity", "severity level", "risk severity"),\n        "compliance.control.identifier": ("control identifier", "control id", "control number", "requirement id"),\n        "microsoft365.license.assignment": ("microsoft 365 license", "m365 license", "office 365 license", "license assignment", "assigned licenses"),\n        "microsoft365.mailbox.type": ("mailbox type", "shared mailbox", "user mailbox", "room mailbox", "equipment mailbox"),\n    }\n\n    for concept_id, aliases in broad_terms.items():\n        for term in aliases:\n            registry.add_term(SemanticTermBinding(term=term, concept_id=concept_id, provenance=provenance))\n            _activate_term(registry, term=term)\n\n    broad_relationships = (\n        SemanticRelationshipDefinition(relationship_id="person.member_of.organization", subject_type="person", target_type="organization", temporal_semantics=("unspecified", "current", "historical"), provenance=provenance),\n        SemanticRelationshipDefinition(relationship_id="person.owns.endpoint", subject_type="person", target_type="endpoint", temporal_semantics=("unspecified", "current", "historical"), provenance=provenance),\n        SemanticRelationshipDefinition(relationship_id="person.assigned_to.ticket", subject_type="person", target_type="ticket", temporal_semantics=("unspecified", "current", "historical"), provenance=provenance),\n        SemanticRelationshipDefinition(relationship_id="contact.belongs_to.organization", subject_type="contact", target_type="organization", temporal_semantics=("unspecified", "current", "historical"), provenance=provenance),\n        SemanticRelationshipDefinition(relationship_id="endpoint.belongs_to.organization", subject_type="endpoint", target_type="organization", temporal_semantics=("unspecified", "current", "historical"), provenance=provenance),\n        SemanticRelationshipDefinition(relationship_id="endpoint.located_at.site", subject_type="endpoint", target_type="site", temporal_semantics=("unspecified", "current", "historical"), provenance=provenance),\n        SemanticRelationshipDefinition(relationship_id="ticket.belongs_to.organization", subject_type="ticket", target_type="organization", temporal_semantics=("unspecified", "current", "historical"), provenance=provenance),\n        SemanticRelationshipDefinition(relationship_id="ticket.references.endpoint", subject_type="ticket", target_type="endpoint", temporal_semantics=("unspecified", "current", "historical"), provenance=provenance),\n        SemanticRelationshipDefinition(relationship_id="alert.affects.endpoint", subject_type="alert", target_type="endpoint", temporal_semantics=("unspecified", "current", "historical"), provenance=provenance),\n        SemanticRelationshipDefinition(relationship_id="control.applies_to.resource", subject_type="control", target_type="resource", temporal_semantics=("unspecified", "current", "historical"), provenance=provenance),\n    )\n\n    for relationship_item in broad_relationships:\n        registry.add_relationship(relationship_item)\n        _activate_relationship(registry, relationship_item.relationship_id)\n\n'''

text = text.replace(anchor, insert + anchor, 1)
path.write_text(text)
print(f"UPDATED: {path}")
PY

echo "========== SECTION 3: ADD BROAD SEED TESTS =========="
cat >> implementation/orchestrator/tests/test_semantic_knowledge_seed.py <<'PY'


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
PY

echo "========== SECTION 4: STATIC VALIDATION =========="
git diff --check

echo "========== SECTION 5: FOCUSED TESTS =========="
.venv/bin/python -m pytest -q \
  implementation/orchestrator/tests/test_semantic_knowledge_registry.py \
  implementation/orchestrator/tests/test_semantic_knowledge_seed.py \
  implementation/orchestrator/tests/test_semantic_fact_resolver.py \
  implementation/orchestrator/tests/test_semantic_request_bridge.py

echo "========== SECTION 6: CHANGE STATE =========="
git status --short

echo "========== RESULT =========="
echo "Broad trusted semantic seed added across endpoint, identity, software, security, Microsoft 365, ticketing, organization, compliance, temporal and relationship domains."
echo "Ambiguous generic words remain intentionally unresolved unless context or scope is explicit."
echo "NO PROVIDER-SPECIFIC MAPPINGS ADDED WITHOUT TRUSTED SOURCE EVIDENCE."
echo "NO DEPLOYMENT PERFORMED."
echo "NO COMMIT OR PUSH OF WORKTREE CHANGES PERFORMED."
echo "========== END BROAD SEMANTIC KNOWLEDGE REGISTRY SEED =========="
