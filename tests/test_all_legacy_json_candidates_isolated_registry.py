"""All nineteen exact source candidates: isolated draft-only registry acceptance.

Exercises the *existing* PMv4 immutable JSON registry, interpreter, and
source/legacy write authority contract with no production component or
provider access. It is NOT a claim of full legacy behavior parity.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

import pytest

from implementation.autonomous_remediation.playbook_document import (
    validate_playbook_document,
)
from implementation.autonomous_remediation.playbook_runtime import JsonPlaybookInterpreter
from implementation.autonomous_remediation.playbook_store import SQLitePlaybookRegistry
from tools.legacy_json_acceptance_ledger import ROOT, build


CASES = tuple(build()["entries"])


@pytest.mark.parametrize("record", CASES, ids=lambda x:x["id"])
def test_source_schema_graph_semantics_capability_and_no_shadow_authority(record):
    document = json.loads((ROOT / record["json_source_path"]).read_text())
    parsed = validate_playbook_document(document)
    assert parsed.playbook_id == record["id"]
    assert parsed.fingerprint == record["json_fingerprint"]
    assert document["scope"]["direct_provider_access"] is False
    assert parsed.autonomy_activation == "shadow"
    assert document["migration"]["production_activation_authorized"] is False
    assert document["migration"].get("accepted_for_execution", False) is False
    steps = {step["id"]: step for step in document["steps"]}
    interpreter = JsonPlaybookInterpreter(parsed)
    for step in document["steps"]:
        if step["type"] == "remediation":
            assert step["approval_required"] is True
            assert step["capability"] in record["source_legacy_allowed_write_capabilities"]
            assert step["verification_step"] in steps
            assert 1 <= step["retry"]["max_attempts"] <= 10
        if step["type"] == "decision":
            try:
                default = interpreter.instruction(step_id=step["id"], facts={})
            except KeyError as exc:
                assert "PLAYBOOK_REQUIRED_FACT_MISSING" in str(exc)
            else:
                assert default.step_id in steps
                assert default.step_type != "remediation"
    assert not record["full_legacy_parity_pass"]
    assert not record["isolated_live_provider_shadow_pass"]


def test_all_19_versions_stage_exactly_once_in_private_draft_registry_and_survive_restart(tmp_path):
    path = tmp_path / "isolated-draft-only-registry.sqlite3"
    store = SQLitePlaybookRegistry(path)
    seen = {}
    try:
        for record in CASES:
            document = json.loads((ROOT / record["json_source_path"]).read_text())
            entry = store.stage(document, actor="isolated-source-acceptance-only")
            assert entry.state == "draft"
            assert entry.document.fingerprint == record["json_fingerprint"]
            seen[record["id"]] = entry.document
        assert store.generation() == 19
        assert len(store.lifecycle_events()) == 19
        assert all(row["event_type"] == "staged" for row in store.lifecycle_events())
        assert store.active_snapshot()[1] == ()
        for record in CASES:
            document = json.loads((ROOT / record["json_source_path"]).read_text())
            store.stage(document, actor="isolated-source-acceptance-only")
        assert store.generation() == 19
    finally:
        store.close()
    reopened = SQLitePlaybookRegistry(path, read_only=True)
    try:
        assert reopened.generation() == 19
        assert reopened.active_snapshot()[1] == ()
        assert len(reopened.list_all()) == 19
        for record in CASES:
            entry = reopened.get(record["id"], record["json_version"])
            assert entry.state == "draft"
            assert entry.document.fingerprint == record["json_fingerprint"]
    finally:
        reopened.close()


@pytest.mark.parametrize("record", CASES, ids=lambda x:x["id"])
def test_mutating_source_cannot_dispatch_from_unbound_default_interpreter(record):
    raw = json.loads((ROOT / record["json_source_path"]).read_text())
    j = JsonPlaybookInterpreter(validate_playbook_document(raw))
    actions = [s for s in raw["steps"] if s["type"] == "remediation"]
    assert all(s["approval_classification"] in {
        "modifying", "disruptive", "non_destructive", "read_only"
    } for s in actions)
    for step in actions:
        with pytest.raises(KeyError, match="PLAYBOOK_REQUIRED_FACT_MISSING"):
            j.instruction(step_id=step["id"], facts={})


def test_source_acceptance_reconciliation_is_complete_but_zero_fully_accepted():
    report = build()
    assert report["verified_inventory"] == report["canonical_json_source_artifacts"] == 19
    assert report["detailed_candidates"] == 19
    assert report["structural_unaccepted_drafts"] == 0
    assert report["fully_accepted_migrations"] == 0
    assert all(entry["unresolved_gaps"] for entry in report["entries"])
    assert all(entry["no_legacy_registry_mutation_authority_expansion"]
               for entry in report["entries"])
    assert all(not entry["production_json_activated"]
               and not entry["legacy_retired"]
               for entry in report["entries"])
