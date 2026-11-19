"""Fail-closed 19-of-19 reconciliation; no partial draft is accepted."""
from hashlib import sha256
import json

from tools.legacy_json_acceptance_ledger import (
    ROOT, LEDGER, build, publish,
)


def test_all_19_have_exact_source_and_valid_json_but_zero_accepted():
    report = build()
    assert report["verified_inventory"] == 19
    assert report["source_mapped"] == 19
    assert report["canonical_json_source_artifacts"] == 19
    assert report["detailed_candidates"] == 9
    assert report["structural_unaccepted_drafts"] == 10
    time_source = next(
        e for e in report["entries"] if e["id"] == "windows_time_source"
    )
    assert time_source["installed_readonly_shadow_behavior_parity"] is True
    assert time_source["full_legacy_parity_pass"] is False
    assert not time_source["accepted_source_migration"]
    assert len(time_source["unresolved_gaps"]) >= 3
    assert report["fully_accepted_migrations"] == 0
    assert report["production_activation_authorized"] is False
    assert len({entry["id"] for entry in report["entries"]}) == 19
    assert all(entry["json_schema_pass"] and
               entry["json_semantic_known_capabilities_pass"]
               for entry in report["entries"])
    assert all(not entry["accepted_source_migration"] for entry in report["entries"])
    assert all(not entry["full_legacy_parity_pass"] for entry in report["entries"])
    assert all(not entry["production_json_activated"] and
               not entry["legacy_retired"] and
               not entry["merged_to_protected_main"]
               for entry in report["entries"])
    assert all(entry["unresolved_gaps"] for entry in report["entries"])
    for entry in report["entries"]:
        data = (ROOT / entry["legacy_source"]).read_bytes()
        assert sha256(data).hexdigest() == entry["legacy_source_sha256"]
        assert len(entry["json_fingerprint"]) == 64
        assert entry["json_activation"] == "shadow"


def test_generated_reconciliation_ledger_is_stable():
    previous = LEDGER.read_bytes()
    assert sha256(previous).hexdigest() == sha256((
        json.dumps(build(), indent=2, sort_keys=True) + "\n").encode()
    ).hexdigest()
    publish()
    assert LEDGER.read_bytes() == previous


def test_readonly_pilot_is_separate_not_fake_migration():
    report = build()
    pilot = report["standalone_readonly_shadow_pilot"]
    assert pilot["isolated_synthetic_branch_acceptance"] is True
    assert pilot["live_preproduction_provider_acceptance"] is False
    assert pilot["counts_as_legacy_conversion"] is False
    assert pilot["id"] not in {row["id"] for row in report["entries"]}


def test_declaring_unapproved_mutation_cannot_pass_reconciliation():
    import pytest
    from tools.legacy_json_acceptance_ledger import (
        verify_no_source_mutation_expansion,
    )
    catalog = {
        "endpoint.alert.resolve": {"write_capability": True},
        "service.ticket.note.create": {"write_capability": True},
        "endpoint.alert.history.search": {"write_capability": False},
    }
    with pytest.raises(ValueError, match="MUTATION_NOT_AUTHORIZED"):
        verify_no_source_mutation_expansion(
            identifier="disk_bad_block_event_7",
            declared_capabilities={
                "endpoint.alert.history.search", "endpoint.alert.resolve"
            },
            legacy_allowed_capabilities={"service.ticket.note.create"},
            live_catalog=catalog,
        )


def test_missing_live_capability_risk_classification_fails_closed():
    import pytest
    from tools.legacy_json_acceptance_ledger import (
        verify_no_source_mutation_expansion,
    )
    with pytest.raises(ValueError, match="CAPABILITY_RISK_METADATA_MISSING"):
        verify_no_source_mutation_expansion(
            identifier="unreviewed",
            declared_capabilities={"mystery.provider.operate"},
            legacy_allowed_capabilities=set(),
            live_catalog={"mystery.provider.operate": {}},
        )


def test_no_json_artifact_expands_source_write_authority():
    report = build()
    assert all(entry["no_legacy_registry_mutation_authority_expansion"]
               for entry in report["entries"])
    assert all(set(entry["source_declared_write_capabilities"])
               <= set(entry["source_legacy_allowed_write_capabilities"])
               for entry in report["entries"])
    for identifier in ("disk_bad_block_event_7", "post_error_investigation",
                       "vulscan_missing_patch"):
        row = next(x for x in report["entries"] if x["id"] == identifier)
        assert not row["source_declared_write_capabilities"]
        assert "authority" in " ".join(row["unresolved_gaps"]).lower()
