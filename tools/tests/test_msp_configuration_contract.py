from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]


def load(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def test_msp_configuration_schema_is_valid_and_example_conforms():
    schema = load("config/schemas/msp-configuration.schema.json")
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(
        load("config/examples/msp-configuration.example.json")
    )


def test_msp_policy_schema_is_valid_and_example_conforms():
    schema = load("config/schemas/msp-policy.schema.json")
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(
        load("config/examples/msp-policy.example.json")
    )


def test_production_policy_cannot_disable_owner_approval():
    schema = load("config/schemas/msp-policy.schema.json")
    candidate = load("config/examples/msp-policy.example.json")
    candidate["production"]["explicit_owner_approval_required"] = False
    assert tuple(Draft202012Validator(schema).iter_errors(candidate))
