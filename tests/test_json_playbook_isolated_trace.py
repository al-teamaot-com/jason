"""Synthetic-only isolated acceptance traces; no provider interaction."""
import json
from pathlib import Path

import pytest

from implementation.autonomous_remediation.playbook_document import validate_playbook_document
from tools.json_playbook_isolated_trace import trace_synthetic

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "docs/playbooks/json/migration"
CANDIDATES = BASE / "candidates"
FIXTURES = BASE / "fixtures"


def load_case(playbook_id: str, case: str):
    doc = validate_playbook_document(json.loads(
        (CANDIDATES / (playbook_id + ".v1.json")).read_text()))
    facts = json.loads((FIXTURES / f"{playbook_id}-{case}.json").read_text())
    return doc, facts


@pytest.mark.parametrize("playbook_id,case,expected_terminal,write_intents", [
    ("unsupported_readonly_triage_note", "positive", "documented", ["service.ticket.note.create"]),
    ("unsupported_readonly_triage_note", "no_promotion", "blocked", []),
    ("unsupported_triage_human_review", "positive", "handoff_complete", ["service.ticket.update"]),
    ("unsupported_triage_human_review", "human_owned", "blocked", []),
    ("drmm_recent_alert_reconciliation", "healthy", "ticket_reconciled",
     ["endpoint.alert.resolve", "service.ticket.note.create", "service.ticket.update"]),
    ("drmm_recent_alert_reconciliation", "active_detection", "skip_no_mutation", []),
])
def test_isolated_fixture_traces_never_execute(playbook_id, case, expected_terminal, write_intents):
    document, facts = load_case(playbook_id, case)
    trace = trace_synthetic(document, facts=facts)
    assert trace["terminal_step"] == expected_terminal
    assert trace["provider_calls"] == 0
    assert trace["provider_mutations"] == 0
    assert trace["authority_granted"] is False
    assert trace["operational_acceptance"] is False
    assert trace["mode"] == "synthetic_shadow_trace"
    assert trace["fingerprint"] == document.fingerprint
    intents = [
        record["capability"] for record in trace["instructions"]
        if record["step_type"] == "remediation"
    ]
    assert intents == write_intents
    assert all(record["execution_status"] == "proposed_only_no_provider_call"
               for record in trace["instructions"])
    assert trace == trace_synthetic(document, facts=facts)


def test_isolated_trace_rejects_autonomous_activation():
    document, facts = load_case("unsupported_readonly_triage_note", "positive")
    payload = json.loads(document.canonical_json)
    payload["autonomy"]["activation"] = "autonomous"
    activated = validate_playbook_document(payload)
    with pytest.raises(PermissionError, match="MIGRATION_SHADOW_ONLY"):
        trace_synthetic(activated, facts=facts)


def test_isolated_trace_rejects_direct_provider_access():
    document, facts = load_case("unsupported_readonly_triage_note", "positive")
    payload = json.loads(document.canonical_json)
    payload["scope"]["direct_provider_access"] = True
    bypass = validate_playbook_document(payload)
    with pytest.raises(PermissionError, match="MIGRATION_DIRECT_PROVIDER_ACCESS_FORBIDDEN"):
        trace_synthetic(bypass, facts=facts)


def test_isolated_trace_requires_all_argument_facts():
    document, facts = load_case("unsupported_readonly_triage_note", "positive")
    facts.pop("note_body")
    with pytest.raises(KeyError, match="PLAYBOOK_REQUIRED_FACT_MISSING"):
        trace_synthetic(document, facts=facts)


def test_isolated_trace_bounded_step_limit():
    document, facts = load_case("drmm_recent_alert_reconciliation", "healthy")
    with pytest.raises(RuntimeError, match="MIGRATION_SHADOW_TRACE_STEP_LIMIT"):
        trace_synthetic(document, facts=facts, max_steps=1)
