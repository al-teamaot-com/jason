from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "recover-datto-rmm-execution-staging.py"
)
SPEC = importlib.util.spec_from_file_location("datto_execution_recovery", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


POLICY = '''path "secret/data/connectors/datto-rmm/production/execution" {
  capabilities = ["read"]
}
'''


def test_extracts_actual_openbao_top_level_policy_shape():
    response = {
        "name": "jason-datto-rmm-execution",
        "policy": POLICY,
    }

    assert MODULE.extract_existing_policy_text(response) == POLICY


def test_accepts_legacy_nested_rules_shape_as_compatibility_fallback():
    response = {"data": {"rules": POLICY}}

    assert MODULE.extract_existing_policy_text(response) == POLICY


def test_rejects_inconsistent_dual_policy_shapes():
    response = {
        "policy": POLICY,
        "data": {"rules": 'path "secret/data/other" { capabilities = ["read"] }'},
    }

    with pytest.raises(MODULE.RecoveryError, match="inconsistent"):
        MODULE.extract_existing_policy_text(response)


def test_rejects_missing_policy_text():
    with pytest.raises(MODULE.RecoveryError, match="unavailable"):
        MODULE.extract_existing_policy_text({"name": "jason-datto-rmm-execution"})


def test_require_existing_policy_matches_actual_openbao_shape(monkeypatch):
    def fake_request_json(**kwargs):
        assert kwargs["path"] == "sys/policies/acl/jason-datto-rmm-execution"
        assert kwargs["method"] == "GET"
        return {
            "name": "jason-datto-rmm-execution",
            "policy": POLICY,
        }

    monkeypatch.setattr(MODULE, "request_json", fake_request_json)

    MODULE.require_existing_policy_matches(
        base_url="http://127.0.0.1:8200",
        token="not-a-real-token",
        policy_name="jason-datto-rmm-execution",
        policy_text=POLICY,
    )


def test_require_existing_policy_matches_fails_closed_on_drift(monkeypatch):
    def fake_request_json(**kwargs):
        return {
            "name": "jason-datto-rmm-execution",
            "policy": 'path "secret/data/other" { capabilities = ["read"] }',
        }

    monkeypatch.setattr(MODULE, "request_json", fake_request_json)

    with pytest.raises(MODULE.RecoveryError, match="does not match"):
        MODULE.require_existing_policy_matches(
            base_url="http://127.0.0.1:8200",
            token="not-a-real-token",
            policy_name="jason-datto-rmm-execution",
            policy_text=POLICY,
        )
