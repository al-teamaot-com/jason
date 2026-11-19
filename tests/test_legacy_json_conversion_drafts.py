"""All 16 structural conversion drafts: validated, but intentionally unaccepted."""
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from implementation.autonomous_remediation.playbook_document import validate_playbook_document
from implementation.autonomous_remediation.playbook_runtime import JsonPlaybookInterpreter
from implementation.autonomous_remediation.playbook_store import SQLitePlaybookRegistry
from tools.legacy_json_conversion_drafts import (
    ALREADY_DETAILED, WORKFLOWS, OUTPUT, ROOT, build, publish,
)


@pytest.fixture(scope="module")
def docs():
    return build()


def test_unconverted_population_is_complete_and_unique(docs):
    registry = json.loads(
        (ROOT / "implementation/autonomous_remediation/playbook_registry.json").read_text())
    enabled = {item["id"] for item in registry["playbooks"] if item["enabled"]}
    assert enabled == ALREADY_DETAILED | set(docs)
    assert len(docs) == 11
    assert not (ALREADY_DETAILED & set(docs))


@pytest.mark.parametrize("playbook_id", sorted(WORKFLOWS))
def test_schema_semantic_source_hash_and_actual_capability_catalog(docs, playbook_id):
    payload = docs[playbook_id]
    schema = json.loads(
        (ROOT / "docs/playbooks/json/playbook-v1.schema.json").read_text())
    catalog = json.loads(
        (ROOT / "docs/playbooks/json/migration/live-capability-snapshot-20261119.json").read_text())
    known = {x["name"] for x in catalog["items"] if x["lifecycle"] == "active"}
    Draft202012Validator(schema).validate(payload)
    validated = validate_playbook_document(payload, known_capabilities=known)
    assert validated.playbook_id == playbook_id
    assert len(validated.fingerprint) == 64
    assert validated.autonomy_activation == "shadow"
    assert payload["scope"]["direct_provider_access"] is False
    assert payload["migration"]["source_conversion"] == "structural_partial_not_accepted"
    assert payload["migration"]["accepted_for_execution"] is False
    assert payload["migration"]["missing_or_unimplemented_parity"]
    assert payload["migration"]["production_activation_authorized"] is False
    source = ROOT / payload["playbook"]["source"]
    source_sha = __import__("hashlib").sha256(source.read_bytes()).hexdigest()
    assert source_sha == payload["migration"]["legacy_source_sha256"]
    assert all(step.get("approval_required") is True
               for step in payload["steps"] if step["type"] == "remediation")


@pytest.mark.parametrize("playbook_id", sorted(WORKFLOWS))
def test_initial_and_negative_safety_gates_block_untrusted_facts(docs, playbook_id):
    interpreter = JsonPlaybookInterpreter(validate_playbook_document(docs[playbook_id]))
    entry = interpreter._steps["read_target"]
    if entry.get("arguments"):
        try:
            instruction = interpreter.instruction(facts={})
        except KeyError as exc:
            assert "PLAYBOOK_REQUIRED_FACT_MISSING" in str(exc)
        else:
            assert instruction.step_type == "diagnostic"
            assert instruction.capability == "management.alert.search"
    assert interpreter.instruction(step_id="scope_gate", facts={}).step_id == "human_review"
    assert interpreter.instruction(
        step_id="scope_gate", facts={"authoritative_same_client_scope_proven": False}
    ).step_id == "human_review"
    assert interpreter.instruction(
        step_id="classification_gate", facts={}
    ).step_id == "human_review"
    if WORKFLOWS[playbook_id]["action"]:
        assert interpreter.instruction(
            step_id="exact_authority_gate", facts={}
        ).step_id == "human_review"


@pytest.mark.parametrize("playbook_id", sorted(WORKFLOWS))
def test_positive_intents_are_approval_bound_not_executed(docs, playbook_id):
    interpreter = JsonPlaybookInterpreter(validate_playbook_document(docs[playbook_id]))
    choice = WORKFLOWS[playbook_id]
    clean = interpreter.instruction(
        step_id="classification_gate",
        facts={"verified_legacy_disposition": choice["clean"],
               "authoritative_healthy_state_proven": True},
    )
    assert clean.step_id == "read_only_complete"
    action = interpreter.instruction(
        step_id="classification_gate",
        facts={
            "verified_legacy_disposition": choice["repair"],
            "exact_owner_promotion_verified": True,
            "server_action_arguments_exact_and_authorized": True,
            "server_verified_exact_action_arguments": {
                "synthetic": "NO_PROVIDER_EXECUTION"
            },
        },
    )
    if choice["action"] is None:
        assert action.step_id == "human_review"
        assert action.terminal is True
    else:
        assert action.step_id == "propose_approved_action"
        assert action.capability == choice["action"]
        assert action.approval_required is True
        assert action.arguments == {"synthetic": "NO_PROVIDER_EXECUTION"}
        assert action.approval_classification == "modifying"
    denied = interpreter.instruction(
        step_id="classification_gate",
        facts={"verified_legacy_disposition": choice["repair"],
               "exact_owner_promotion_verified": False},
    )
    assert denied.step_id == "human_review"


@pytest.mark.parametrize("playbook_id", sorted(WORKFLOWS))
def test_wait_is_bounded_and_leads_to_review_not_duplicate_action(docs, playbook_id):
    interpreter = JsonPlaybookInterpreter(validate_playbook_document(docs[playbook_id]))
    wait = interpreter.instruction(
        step_id="classification_gate",
        facts={"verified_legacy_disposition": WORKFLOWS[playbook_id]["wait"]},
    )
    assert wait.step_id == "wait_for_source"
    assert wait.step_type == "wait"
    assert interpreter._steps[wait.step_id]["seconds"] == 3600
    assert interpreter.next_step(wait.step_id) == "bounded_wait_terminal"
    assert interpreter.instruction(
        step_id="bounded_wait_terminal", facts={}).terminal is True


def test_all_drafts_stage_as_immutable_inactive_versions_in_existing_registry(tmp_path, docs):
    store = SQLitePlaybookRegistry(tmp_path / "all-source-draft-registry.sqlite3")
    for identifier, item in docs.items():
        staged = store.stage(item, actor="source-only-inventory-test")
        assert staged.state == "draft"
        assert store.active(identifier) is None
    assert store.generation() == 11
    assert len(store.lifecycle_events()) == 11
    store.close()
    reopened = SQLitePlaybookRegistry(tmp_path / "all-source-draft-registry.sqlite3")
    assert reopened.generation() == 11
    assert len(reopened.list_all()) == 11
    assert reopened.active_snapshot()[1] == ()
    reopened.close()


def test_source_draft_generation_deterministic(docs):
    before = {
        filename.name: __import__("hashlib").sha256(filename.read_bytes()).hexdigest()
        for filename in OUTPUT.glob("*.json")
    }
    publish()
    after = {
        filename.name: __import__("hashlib").sha256(filename.read_bytes()).hexdigest()
        for filename in OUTPUT.glob("*.json")
    }
    assert before == after
    assert len(after) == len(docs) == 11
