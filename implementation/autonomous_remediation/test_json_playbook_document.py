import pytest

from .playbook_document import PlaybookValidationError, validate_playbook_document
from .playbook_runtime import JsonPlaybookInterpreter


def sample():
    return {
        "schema_version": 1,
        "playbook": {
            "id": "sample_service_repair",
            "name": "Sample Service Repair",
            "version": "1.0.0",
            "lifecycle": "pilot",
            "target_type": "endpoint",
        },
        "trigger": {"provider": "autotask", "match": {"title_contains": ["Sample"]}},
        "scope": {"direct_provider_access": False},
        "expected_state": {"service": "running"},
        "state_model": {"entry_step": "check_service"},
        "steps": [
            {
                "id": "check_service",
                "type": "diagnostic",
                "capability": "endpoint.service.read",
                "arguments": {"service": "Example"},
                "next": "service_state",
            },
            {
                "id": "service_state",
                "type": "decision",
                "branches": [{
                    "when": {"fact": "service_running", "operator": "eq", "value": True},
                    "next": "verify_service",
                }],
                "default": "start_service",
            },
            {
                "id": "start_service",
                "type": "remediation",
                "capability": "endpoint.service.start",
                "arguments": {"service": "Example"},
                "approval_classification": "non_destructive",
                "approval_required": False,
                "verification_step": "verify_service",
                "retry": {"max_attempts": 1},
            },
            {
                "id": "verify_service",
                "type": "verification",
                "capability": "endpoint.service.read",
                "arguments": {"service": "Example"},
                "next": "complete",
            },
            {"id": "complete", "type": "complete"},
        ],
        "verification": {
            "authoritative_source": "endpoint.service.read",
            "success_condition": "service_running=true",
        },
        "completion": {"terminal_disposition": "Complete"},
        "autonomy": {
            "activation": "shadow",
            "allowed_capabilities": [
                "endpoint.service.read",
                "endpoint.service.start",
            ],
        },
    }


def test_valid_document_is_canonical_and_fingerprinted():
    document = validate_playbook_document(sample())
    assert document.playbook_id == "sample_service_repair"
    assert document.version == "1.0.0"
    assert len(document.fingerprint) == 64
    assert document.capabilities == ("endpoint.service.read", "endpoint.service.start")


def test_disruptive_step_requires_explicit_approval():
    payload = sample()
    payload["steps"][2]["approval_classification"] = "disruptive"
    with pytest.raises(PlaybookValidationError) as caught:
        validate_playbook_document(payload)
    assert "start_service:DISRUPTIVE_APPROVAL_REQUIRED" in caught.value.errors


def test_inline_shell_is_rejected():
    payload = sample()
    payload["steps"][0]["powershell"] = "Get-Service"
    with pytest.raises(PlaybookValidationError) as caught:
        validate_playbook_document(payload)
    assert any("INLINE_EXECUTION_FORBIDDEN:powershell" in item for item in caught.value.errors)


def test_graph_targets_must_exist():
    payload = sample()
    payload["steps"][0]["next"] = "missing"
    with pytest.raises(PlaybookValidationError) as caught:
        validate_playbook_document(payload)
    assert "check_service:TARGET_NOT_FOUND:missing" in caught.value.errors


def test_interpreter_resolves_deterministic_decision_without_execution():
    document = validate_playbook_document(sample())
    runtime = JsonPlaybookInterpreter(document)
    instruction = runtime.instruction(step_id="service_state", facts={"service_running": False})
    assert instruction.step_id == "start_service"
    assert instruction.capability == "endpoint.service.start"
    assert instruction.approval_classification == "non_destructive"


def test_capability_first_binds_prior_governed_facts_without_execution():
    payload = sample()
    payload["steps"][0]["arguments"] = {
        "service": {"$fact": "service_name"},
        "scope": {"ticket_id": {"$fact": "ticket_id"}},
    }
    runtime = JsonPlaybookInterpreter(validate_playbook_document(payload))
    instruction = runtime.instruction(
        facts={"service_name": "Spooler", "ticket_id": 12345},
    )
    assert instruction.capability == "endpoint.service.read"
    assert instruction.arguments == {
        "service": "Spooler", "scope": {"ticket_id": 12345},
    }
    assert payload["steps"][0]["arguments"]["service"] == {"$fact": "service_name"}


def test_capability_first_missing_fact_fails_closed():
    payload = sample()
    payload["steps"][0]["arguments"] = {"ticket_id": {"$fact": "ticket_id"}}
    runtime = JsonPlaybookInterpreter(validate_playbook_document(payload))
    with pytest.raises(KeyError, match="PLAYBOOK_REQUIRED_FACT_MISSING"):
        runtime.instruction(facts={})


def test_capability_first_rejects_mixed_expression_reference():
    payload = sample()
    payload["steps"][0]["arguments"] = {
        "ticket_id": {"$fact": "ticket_id", "default": 5},
    }
    runtime = JsonPlaybookInterpreter(validate_playbook_document(payload))
    with pytest.raises(ValueError, match="PLAYBOOK_FACT_REFERENCE_INVALID"):
        runtime.instruction(facts={"ticket_id": 7})


def test_capability_first_never_executes_provider_operation():
    payload = sample()
    payload["steps"][0]["arguments"] = {"ticket_id": {"$fact": "ticket_id"}}
    runtime = JsonPlaybookInterpreter(validate_playbook_document(payload))
    first = runtime.instruction(facts={"ticket_id": 7})
    second = runtime.instruction(facts={"ticket_id": 7})
    assert first == second
    assert runtime.next_step(first.step_id) == "service_state"
