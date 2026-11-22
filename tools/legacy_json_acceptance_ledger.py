"""Reconcile the exact legacy registry with 19 source-only JSON artifacts.

An independently validated, correct procedure is required for acceptance;
schema parse, source mapping and synthetic branch tests are not acceptance.
This tool never stages, activates, retires, merges or calls a provider.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from implementation.autonomous_remediation.playbook_document import (
    validate_playbook_document,
)
from tools.legacy_json_conversion_drafts import ALREADY_DETAILED, ROOT

REGISTRY = ROOT / "implementation/autonomous_remediation/playbook_registry.json"
SCHEMA = ROOT / "docs/playbooks/json/playbook-v1.schema.json"
CAPABILITIES = ROOT / "docs/playbooks/json/migration/live-capability-snapshot-20261119.json"
BASE = ROOT / "docs/playbooks/json/migration"
LEDGER = BASE / "acceptance-ledger-20261119.json"


def verify_no_source_mutation_expansion(
    *, identifier: str, declared_capabilities: set[str],
    legacy_allowed_capabilities: set[str],
    live_catalog: dict[str, dict],
) -> tuple[list[str], list[str]]:
    """No source artifact can introduce capabilities outside legacy write authority."""
    unknown = sorted(
        capability for capability in declared_capabilities
        if live_catalog.get(capability, {}).get("write_capability") is None
    )
    if unknown:
        raise ValueError(
            f"{identifier}:CAPABILITY_RISK_METADATA_MISSING:{unknown}"
        )
    declared_writes = sorted(
        capability for capability in declared_capabilities
        if live_catalog[capability]["write_capability"] is True
    )
    source_allowed_writes = sorted(
        capability for capability in legacy_allowed_capabilities
        if live_catalog.get(capability, {}).get("write_capability") is True
    )
    extras = sorted(set(declared_writes) - set(source_allowed_writes))
    if extras:
        raise ValueError(
            f"{identifier}:MUTATION_NOT_AUTHORIZED_IN_LEGACY_REGISTRY:{extras}"
        )
    return declared_writes, source_allowed_writes


def build() -> dict:
    schema = json.loads(SCHEMA.read_text())
    validator = Draft202012Validator(schema)
    live = json.loads(CAPABILITIES.read_text())
    active_caps = {
        item["name"] for item in live["items"] if item["lifecycle"] == "active"
    }
    registry = json.loads(REGISTRY.read_text())
    source_maps = BASE / "source_maps"
    outcomes = []
    for row in registry["playbooks"]:
        if row.get("enabled") is not True:
            continue
        identifier = row["id"]
        kind = "candidate" if identifier in ALREADY_DETAILED else "structural_draft"
        relpath = (
            f"candidates/{identifier}.v1.json"
            if identifier in ALREADY_DETAILED else
            f"drafts/{identifier}.v1.json"
        )
        filepath = BASE / relpath
        source_map = json.loads(
            (source_maps / f"{identifier}.source-map.json").read_text())
        doc = json.loads(filepath.read_text())
        validator.validate(doc)
        validated = validate_playbook_document(doc, known_capabilities=active_caps)
        if validated.playbook_id != identifier:
            raise ValueError(f"{identifier}:CANDIDATE_ID_MISMATCH")
        metadata = {item["name"]: item for item in live["items"]}
        declared_writes, allowed_writes = verify_no_source_mutation_expansion(
            identifier=identifier,
            declared_capabilities=set(validated.capabilities),
            legacy_allowed_capabilities=set(
                row.get("autonomy", {}).get("allowed_capabilities", [])
            ),
            live_catalog=metadata,
        )
        if doc["autonomy"]["activation"] != "shadow":
            raise ValueError(f"{identifier}:MIGRATION_ACTIVATION_NOT_SHADOW")
        if doc["scope"]["direct_provider_access"] is not False:
            raise ValueError(f"{identifier}:PROVIDER_BYPASS_DECLARED")
        if doc["migration"]["production_activation_authorized"] is not False:
            raise ValueError(f"{identifier}:PRODUCTION_AUTHORITY_FABRICATED")
        source_path = ROOT / row["source"]
        digest = sha256(source_path.read_bytes()).hexdigest()
        if digest != source_map["source_sha256"]:
            raise ValueError(f"{identifier}:SOURCE_CHANGED")
        accepted = False
        # Windows Time is proven against the installed *shadow classifier*
        # only. The authoritative Markdown also specifies future self-heal,
        # approved component remediation and provider alert verification.
        # Those branches have NOT migrated; never count this as full parity.
        installed_shadow_classifier_parity = identifier == "windows_time_source"
        gaps = (
            doc["migration"].get("missing_or_unimplemented_parity")
            or doc["migration"].get("known_gaps")
            or []
        )
        if installed_shadow_classifier_parity:
            gaps = list(gaps) + [
                "Full Windows Time Self-Heal definition includes governed diagnostic component, domain-member remediation, per-action Owner approvals, bounded jobs/retries, exact alert and ticket readback, and protected DC/security branches; these are not represented in read-only shadow JSON.",
                "The current isolated preproduction composition is synthetic and has not been deployed or tested with a real client-bound provider session.",
                "No source-to-runtime activation/cutover or coexistence acceptance is authorized.",
            ]
        outcomes.append({
            "id": identifier,
            "legacy_source": row["source"],
            "legacy_registry_version": row["version"],
            "legacy_source_sha256": digest,
            "legacy_source_blob_sha": source_map["source_blob_sha"],
            "json_source_path": f"docs/playbooks/json/migration/{relpath}",
            "json_version": validated.version,
            "json_fingerprint": validated.fingerprint,
            "artifact_kind": kind,
            "json_schema_pass": True,
            "no_legacy_registry_mutation_authority_expansion": True,
            "source_declared_write_capabilities": declared_writes,
            "source_legacy_allowed_write_capabilities": allowed_writes,
            "json_semantic_known_capabilities_pass": True,
            "json_activation": "shadow",
            "synthetic_dry_run_smoke_available": True,
            "narrow_same_fixture_legacy_intent_parity": (
                identifier in ALREADY_DETAILED
            ),
            "installed_readonly_shadow_behavior_parity": (
                installed_shadow_classifier_parity
            ),
            "full_legacy_parity_pass": False,
            "exact_authority_boundary_end_to_end_pass": False,
            "interruption_recovery_end_to_end_pass": False,
            "isolated_live_provider_shadow_pass": False,
            "accepted_source_migration": accepted,
            "merged_to_protected_main": False,
            "production_json_activated": False,
            "legacy_retired": False,
            "unresolved_gaps": gaps,
        })
    if len(outcomes) != len({x["id"] for x in outcomes}):
        raise ValueError("RECONCILIATION_DUPLICATE_SOURCE_ID")
    return {
        "source_registry": str(REGISTRY.relative_to(ROOT)),
        "source_registry_blob_sha": json.loads(
            (source_maps / "INDEX.json").read_text()
        )["registry_blob_sha"],
        "verified_inventory": len(outcomes),
        "source_mapped": sum(
            bool(row["legacy_source_sha256"]) for row in outcomes
        ),
        "canonical_json_source_artifacts": len(outcomes),
        "detailed_candidates": sum(
            row["artifact_kind"] == "candidate" for row in outcomes
        ),
        "structural_unaccepted_drafts": sum(
            row["artifact_kind"] == "structural_draft" for row in outcomes
        ),
        "fully_accepted_migrations": 0,
        "standalone_readonly_shadow_pilot": {
            "id": "drmm_recent_alert_readonly_shadow_pilot",
            "version": "0.1.0",
            "isolated_synthetic_branch_acceptance": True,
            "live_preproduction_provider_acceptance": False,
            "counts_as_legacy_conversion": False,
        },
        "production_activation_authorized": False,
        "accepted_only_when_all_independent_gates_pass": True,
        "entries": outcomes,
    }


def publish() -> dict:
    report = build()
    LEDGER.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


if __name__ == "__main__":
    result = publish()
    print(
        f"legacy={result['verified_inventory']} json_artifacts={result['canonical_json_source_artifacts']} "
        f"detailed={result['detailed_candidates']} partial={result['structural_unaccepted_drafts']} "
        f"accepted={result['fully_accepted_migrations']}"
    )
