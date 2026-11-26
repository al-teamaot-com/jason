"""Independent isolated synthetic read-only pilot acceptance.

The pilot is intentionally *not* a legacy replacement, production deployment
or live-provider shadow run. Every acceptance case uses the existing PMv4
JSON registry/interpreter with a fake governed, client-scoped read port.
"""
from datetime import datetime, timezone
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from implementation.autonomous_remediation.playbook_document import (
    validate_playbook_document)
from implementation.autonomous_remediation.playbook_store import SQLitePlaybookRegistry
from implementation.autonomous_remediation.json_shadow_integration import (
    GovernedJsonShadowIntegration, SQLiteJsonShadowState)
from implementation.autonomous_remediation.json_shadow_facts import (
    reduce_daily_drmm_alert)
from tests.test_json_governed_shadow_integration import (
    FakeGovernedObserve, NOW, READS)

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / "docs/playbooks/json/migration/candidates/drmm_recent_alert_readonly_shadow_pilot.v1.json"
SCHEMA = ROOT / "docs/playbooks/json/playbook-v1.schema.json"


def build(tmp_path, *, case):
    payload = json.loads(CANDIDATE.read_text())
    Draft202012Validator(json.loads(SCHEMA.read_text())).validate(payload)
    doc = validate_playbook_document(payload)
    registry = SQLitePlaybookRegistry(tmp_path / "existing-json-registry.sqlite3")
    draft = registry.stage(payload, actor="synthetic-readonly-pilot")
    assert draft.state == "draft"
    assert registry.generation() == 1
    assert registry.active(doc.playbook_id) is None
    registry.close()
    registry = SQLitePlaybookRegistry(tmp_path / "existing-json-registry.sqlite3")
    assert registry.get(doc.playbook_id, doc.version).document.fingerprint == doc.fingerprint
    assert registry.active(doc.playbook_id) is None
    registry.close()
    state = SQLiteJsonShadowState(tmp_path / "read-only-run-state.sqlite3")
    reads = FakeGovernedObserve(case=case)
    runner = GovernedJsonShadowIntegration(
        document=doc, state=state, read_port=reads,
        read_capabilities=READS,
        normalize=lambda capability, result, facts: reduce_daily_drmm_alert(
            capability, result, facts, at=NOW),
        clock=lambda: NOW,
    )
    return runner, reads, state


@pytest.mark.parametrize("case,terminal,read_count", [
    ("unsupported", "unsupported_class", 1),
    ("old", "outside_window", 1),
    ("offline", "waiting_offline", 2),
    ("active", "active_detections", 4),
    ("healthy", "healthy_observed", 4),
])
def test_deterministic_read_only_terminal_and_zero_mutations(
    tmp_path, case, terminal, read_count,
):
    runner, reads, state = build(tmp_path, case=case)
    kwargs = {
        "run_id": "synthetic-readonly-acceptance",
        "client_id": "company-1", "target_id": "alert-1",
        "trusted_seed": {"client_id": "company-1", "target_id": "alert-1"},
    }
    first = runner.run(**kwargs)
    assert first.status == "completed_readonly"
    assert first.step_id == terminal
    assert len(reads.calls) == read_count
    assert reads.mutations == []
    assert all("NO_MUTATION_IN_SHADOW" != e.get("result") for e in first.history)
    assert all(e["type"] not in ("remediation", "document") for e in first.history)
    assert first.history[-1] == {"step_id": terminal, "type": "complete"}
    assert runner.run(**kwargs) == first
    assert len(reads.calls) == read_count
    assert runner.document.payload["migration"]["accepted_as_legacy_replacement"] is False
    state.close()


@pytest.mark.parametrize("case", ["ambiguous", "identity_mismatch"])
def test_fail_closed_identity_and_duplicate_alert(tmp_path, case):
    runner, reads, state = build(tmp_path, case=case)
    result = runner.run(
        run_id="synthetic-readonly-acceptance", client_id="company-1",
        target_id="alert-1",
        trusted_seed={"client_id": "company-1", "target_id": "alert-1"},
    )
    assert result.status == "failed_closed"
    assert reads.mutations == []
    state.close()


def test_isolated_registry_draft_does_not_issue_authority(tmp_path):
    payload = json.loads(CANDIDATE.read_text())
    registry = SQLitePlaybookRegistry(tmp_path / "draft-only.sqlite3")
    first = registry.stage(payload, actor="synthetic-only")
    assert first.state == "draft"
    assert registry.generation() == 1
    assert registry.active(payload["playbook"]["id"]) is None
    assert [row["event_type"] for row in registry.lifecycle_events()] == ["staged"]
    registry.close()


def test_read_only_pilot_rejects_declared_mutation_capabilities():
    payload = json.loads(CANDIDATE.read_text())
    assert all(step["type"] in {
        "diagnostic", "verification", "decision", "complete",
    } for step in payload["steps"])
    assert set(payload["autonomy"]["allowed_capabilities"]).isdisjoint({
        "endpoint.alert.resolve", "service.ticket.update",
        "service.ticket.note.create", "automation.component.execute",
    })
    assert payload["scope"]["direct_provider_access"] is False
    assert payload["autonomy"]["activation"] == "shadow"
