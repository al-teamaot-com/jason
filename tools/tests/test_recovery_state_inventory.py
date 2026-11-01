from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]


def load(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def test_recovery_state_inventory_schema_and_document_are_valid():
    schema = load("config/schemas/recovery-state-inventory.schema.json")
    inventory = load("config/recovery-state-inventory.v1.json")
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(inventory)


def test_critical_authority_audit_and_workflow_state_are_full_recovery_required():
    inventory = load("config/recovery-state-inventory.v1.json")
    by_name = {item["state_class"]: item for item in inventory["classes"]}
    for name in (
        "authority-and-identity",
        "audit-and-orchestration",
        "workflow-state",
        "provider-client-mappings",
    ):
        assert by_name[name]["full_recovery_export"] is True
        assert by_name[name]["recovery_action"] == "restore"


def test_secret_state_never_enters_portable_deployment_export():
    inventory = load("config/recovery-state-inventory.v1.json")
    for item in inventory["classes"]:
        if item["contains_secrets"]:
            assert item["portable_deployment_export"] is False


def test_cache_transient_and_host_identity_are_not_blindly_restored():
    inventory = load("config/recovery-state-inventory.v1.json")
    by_name = {item["state_class"]: item for item in inventory["classes"]}
    assert by_name["model-and-download-cache"]["recovery_action"] == "reconstruct"
    assert by_name["ephemeral-runtime-state"]["recovery_action"] == "discard"
    assert by_name["host-bound-identity"]["recovery_action"] == "reenroll"
    assert by_name["host-bound-identity"]["machine_bound"] is True
