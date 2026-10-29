"""Read-only acceptance tests for draft JSON v1 playbook conversions.

These tests never open a provider connector, stage a document, or activate an
execution authority. They validate canonical structure, original-source
integrity, and deterministic Windows Time shadow classification only.
"""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha1
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[3]
IMPLEMENTATION = ROOT / "implementation"
if str(IMPLEMENTATION) not in sys.path:
    sys.path.insert(0, str(IMPLEMENTATION))

from autonomous_remediation.playbook_document import (  # noqa: E402
    PlaybookValidationError,
    validate_playbook_document,
)
from autonomous_remediation.playbook_runtime import JsonPlaybookInterpreter  # noqa: E402

REGISTRY_PATH = ROOT / "implementation" / "autonomous_remediation" / "playbook_registry.json"
CANDIDATES = ROOT / "docs" / "playbooks" / "json" / "candidates"
# Round 1 client questions were added to protected main after the 16-document
# snapshot. They have a separate approval/activation lifecycle and must not
# silently receive a JSON conversion or be counted as converted.
POST_SNAPSHOT_UNMIGRATED_IDS = frozenset({"client_information_request"})


def _source_registry():
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def _all_candidates():
    entries = _source_registry()["playbooks"]
    by_id = {entry["id"]: entry for entry in entries}
    assert len(by_id) == len(entries), "Duplicate playbook identity in source registry"
    assert POST_SNAPSHOT_UNMIGRATED_IDS <= by_id.keys()
    converted_entries = [
        entry for entry in entries if entry["id"] not in POST_SNAPSHOT_UNMIGRATED_IDS
    ]
    assert len(converted_entries) == 16, "Conversion scope drift requires an explicit new review"
    expected_names = {
        f"{entry['id']}-{entry['version']}-jsonpreview.json"
        for entry in converted_entries
    }
    actual_names = {path.name for path in CANDIDATES.glob("*-jsonpreview.json")}
    assert actual_names == expected_names, "Unexpected or missing JSON migration candidate"
    for entry in converted_entries:
        path = CANDIDATES / f"{entry['id']}-{entry['version']}-jsonpreview.json"
        yield entry, json.loads(path.read_text(encoding="utf-8"))


def test_new_client_question_is_not_silently_migrated():
    source = {entry["id"]: entry for entry in _source_registry()["playbooks"]}
    new_entry = source["client_information_request"]
    assert new_entry["version"] == "1.0.0"
    assert new_entry["lifecycle"] == "pilot"
    assert new_entry["autonomy"]["activation"] == "shadow"
    assert not (CANDIDATES / "client_information_request-1.0.0-jsonpreview.json").exists()


def _source_sha1(content):
    encoded = content.encode("utf-8")
    return sha1(b"blob " + str(len(encoded)).encode("ascii") + bytes([0]) + encoded).hexdigest()


def test_all_16_candidates_pass_canonical_validator_and_have_no_execution_authority():
    ids = set()
    for entry, payload in _all_candidates():
        doc = validate_playbook_document(payload, known_capabilities=set())
        assert doc.playbook_id == entry["id"]
        assert doc.version == entry["version"] + "-jsonpreview"
        assert doc.lifecycle == "pilot"
        assert doc.capabilities == ()
        assert doc.autonomy_activation == "disabled"
        assert payload["scope"]["direct_provider_access"] is False
        assert payload["migration"]["production_replacement_allowed"] is False
        assert payload["autonomy"]["allowed_capabilities"] == []
        assert all(step["type"] in {"decision", "human_review"} for step in payload["steps"])
        assert all("capability" not in step for step in payload["steps"])
        assert doc.fingerprint == validate_playbook_document(payload).fingerprint
        ids.add(doc.playbook_id)
    assert len(ids) == 16


def test_original_legacy_sources_reconstruct_exactly_from_json_drafts():
    for entry, payload in _all_candidates():
        source = payload["source_document"]
        full_text = source["prelude_markdown"] + "".join(
            section["heading_markdown"] + section["body_markdown"]
            for section in source["sections"]
        )
        original = ROOT / source["path"]
        assert original.is_file(), entry["id"]
        assert full_text == original.read_text(encoding="utf-8"), entry["id"]
        assert _source_sha1(full_text) == source["source_blob_sha"], entry["id"]


def test_source_version_conflict_is_explicit_not_silently_promoted():
    entry, payload = next(
        (entry, payload) for entry, payload in _all_candidates()
        if entry["id"] == "backupiq_endpoint_backup"
    )
    assert entry["version"] == "1.2.0"
    assert payload["playbook"]["documented_version"] == "1.3.0"
    assert payload["migration"]["source_version_discrepancy"] is True
    assert payload["autonomy"]["activation"] == "disabled"


def test_missing_sections_are_recorded_without_fabricating_policy():
    expected = {
        "dns_agent_diagnostic": {"23"},
        "drmm_recent_alert_reconciliation": {"20", "21", "22", "23"},
        "low_disk_space": {"23"},
        "post_error_investigation": {"23"},
        "security_log_self_heal": {"23"},
        "vulscan_multi_device_split": {"23"},
    }
    for entry, payload in _all_candidates():
        sections = payload["procedure"]["source_section_inventory"]
        assert len(sections) == 23
        missing = {item["section_key"] for item in sections if not item["present"]}
        assert missing == expected.get(entry["id"], set()), entry["id"]


def _windows_time_preview():
    return next(payload for entry, payload in _all_candidates()
                if entry["id"] == "windows_time_source")


@pytest.mark.parametrize("fixture_index", range(15))
def test_windows_time_shadow_classification_has_no_side_effects(fixture_index):
    payload = _windows_time_preview()
    cases = payload["shadow_fixtures"]["cases"]
    assert len(cases) == 15
    selected = cases[fixture_index]
    facts = dict(payload["shadow_fixtures"]["base_facts"])
    facts.update(selected["overrides"])
    doc = validate_playbook_document(payload, known_capabilities=set())
    instruction = JsonPlaybookInterpreter(doc).instruction(facts=facts)
    assert instruction.step_id == selected["expected_terminal"], selected["name"]
    assert instruction.step_type == "human_review"
    assert instruction.terminal is True
    assert instruction.capability is None
    assert instruction.arguments == {}
    assert instruction.approval_required is False


def test_windows_time_no_evidence_fails_closed():
    doc = validate_playbook_document(_windows_time_preview(), known_capabilities=set())
    instruction = JsonPlaybookInterpreter(doc).instruction(facts={})
    assert instruction.step_id == "review_identity_blocked"
    assert instruction.capability is None
    assert instruction.terminal is True


def test_runtime_validator_rejects_inline_powershell_in_draft():
    payload = deepcopy(_windows_time_preview())
    payload["steps"][0]["powershell"] = "Restart-Service W32Time"
    with pytest.raises(PlaybookValidationError) as exc:
        validate_playbook_document(payload, known_capabilities=set())
    assert any("INLINE_EXECUTION_FORBIDDEN:powershell" in error for error in exc.value.errors)


def test_windows_time_preview_does_not_depend_on_live_client_evidence():
    payload = _windows_time_preview()
    assert payload["migration"]["operational_state_binding_verified"] is False
    assert payload["scope"]["simulation_only"] is True
    assert payload["scope"]["never_resolve_live_alert"] is True
    assert payload["scope"]["never_modify_windows_time"] is True
    assert payload["scope"]["never_close_autotask_ticket"] is True
