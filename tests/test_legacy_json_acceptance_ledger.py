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
    assert report["detailed_candidates"] == 3
    assert report["structural_unaccepted_drafts"] == 16
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
