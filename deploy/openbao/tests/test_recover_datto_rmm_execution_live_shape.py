from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "recover-datto-rmm-execution-staging-live-shape.py"
)
SPEC = importlib.util.spec_from_file_location("datto_execution_recovery_live_shape", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


POLICY = '''path "secret/data/connectors/datto-rmm/production/execution" {
  capabilities = ["read"]
}
'''


def test_extracts_live_openbao_data_policy_shape():
    response = {
        "request_id": "redacted",
        "data": {
            "cas_required": False,
            "name": "jason-datto-rmm-execution",
            "policy": POLICY,
            "version": 1,
        },
    }

    assert MODULE.extract_existing_policy_text(response) == POLICY


def test_still_accepts_top_level_policy_shape():
    assert MODULE.extract_existing_policy_text({"policy": POLICY}) == POLICY


def test_still_accepts_nested_rules_compatibility_shape():
    assert MODULE.extract_existing_policy_text({"data": {"rules": POLICY}}) == POLICY


def test_accepts_multiple_identical_representations():
    response = {
        "policy": POLICY,
        "data": {
            "policy": POLICY,
            "rules": POLICY,
        },
    }

    assert MODULE.extract_existing_policy_text(response) == POLICY


def test_rejects_conflicting_live_and_compatibility_representations():
    response = {
        "data": {
            "policy": POLICY,
            "rules": 'path "secret/data/other" { capabilities = ["read"] }',
        }
    }

    with pytest.raises(MODULE.RecoveryError, match="inconsistent"):
        MODULE.extract_existing_policy_text(response)


def test_rejects_missing_policy_text():
    with pytest.raises(MODULE.RecoveryError, match="unavailable"):
        MODULE.extract_existing_policy_text(
            {
                "data": {
                    "name": "jason-datto-rmm-execution",
                    "version": 1,
                }
            }
        )


def test_base_recovery_uses_live_shape_parser(monkeypatch):
    observed = {}

    def fake_request_json(**kwargs):
        observed.update(kwargs)
        return {
            "data": {
                "name": "jason-datto-rmm-execution",
                "policy": POLICY,
                "version": 1,
            }
        }

    monkeypatch.setattr(MODULE.BASE, "request_json", fake_request_json)

    MODULE.BASE.require_existing_policy_matches(
        base_url="http://127.0.0.1:8200",
        token="not-a-real-token",
        policy_name="jason-datto-rmm-execution",
        policy_text=POLICY,
    )

    assert observed["path"] == "sys/policies/acl/jason-datto-rmm-execution"
    assert observed["method"] == "GET"
