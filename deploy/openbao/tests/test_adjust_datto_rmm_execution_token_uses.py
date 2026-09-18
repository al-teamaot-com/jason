from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "adjust-datto-rmm-execution-token-uses.py"
)
SPEC = importlib.util.spec_from_file_location("datto_execution_token_uses", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def role_data(token_num_uses: int) -> dict[str, object]:
    return {
        "bind_secret_id": True,
        "secret_id_ttl": 7776000,
        "secret_id_num_uses": 0,
        "token_policies": ["jason-datto-rmm-execution"],
        "token_no_default_policy": True,
        "token_ttl": 300,
        "token_max_ttl": 300,
        "token_explicit_max_ttl": 300,
        "token_num_uses": token_num_uses,
        "token_type": "service",
    }


def test_accepts_two_use_approved_state():
    assert MODULE.validate_role_data(
        role_data(2),
        allowed_token_uses={2},
    ) == 2


def test_accepts_transient_three_use_state_during_repair():
    assert MODULE.validate_role_data(
        role_data(3),
        allowed_token_uses={2, 3},
    ) == 3


def test_rejects_unapproved_token_use_budget():
    with pytest.raises(MODULE.AdjustmentError, match="use budget"):
        MODULE.validate_role_data(
            role_data(4),
            allowed_token_uses={2, 3},
        )


def test_rejects_policy_binding_drift():
    data = role_data(2)
    data["token_policies"] = ["default"]
    with pytest.raises(MODULE.AdjustmentError, match="policy binding"):
        MODULE.validate_role_data(data, allowed_token_uses={2, 3})


def test_rejects_ttl_drift():
    data = role_data(2)
    data["token_ttl"] = 600
    with pytest.raises(MODULE.AdjustmentError, match="token_ttl"):
        MODULE.validate_role_data(data, allowed_token_uses={2, 3})


def test_desired_role_payload_restores_approved_two_use_budget():
    payload = MODULE.desired_role_payload()
    assert payload["token_num_uses"] == 2
    assert payload["token_policies"] == ["jason-datto-rmm-execution"]
    assert payload["token_no_default_policy"] is True
    assert payload["token_ttl"] == "5m"
    assert payload["token_max_ttl"] == "5m"
    assert payload["token_explicit_max_ttl"] == "5m"
    assert payload["secret_id_num_uses"] == 0
    assert payload["token_type"] == "service"


def test_legacy_policy_is_accepted_only_as_repair_predecessor():
    assert MODULE.validate_policy_transition(MODULE.LEGACY_POLICY) == "legacy_missing_self_revoke"


def test_approved_policy_requires_execution_read_and_self_revoke_only():
    assert MODULE.validate_policy_transition(MODULE.APPROVED_POLICY) == "approved"
    normalized = MODULE.normalize_policy(MODULE.APPROVED_POLICY)
    assert 'path "secret/data/connectors/datto-rmm/production/execution" {' in normalized
    assert 'capabilities = ["read"]' in normalized
    assert 'path "auth/token/revoke-self" {' in normalized
    assert 'capabilities = ["update"]' in normalized


def test_policy_with_extra_authority_is_rejected():
    expanded = MODULE.APPROVED_POLICY + '''
path "secret/data/connectors/datto-rmm/production/read-only" {
  capabilities = ["read"]
}
'''
    with pytest.raises(MODULE.AdjustmentError, match="repair boundary"):
        MODULE.validate_policy_transition(expanded)


def test_policy_missing_execution_read_is_rejected():
    incomplete = '''
path "auth/token/revoke-self" {
  capabilities = ["update"]
}
'''
    with pytest.raises(MODULE.AdjustmentError, match="repair boundary"):
        MODULE.validate_policy_transition(incomplete)


def test_extract_policy_text_accepts_live_data_policy_shape():
    response = {"data": {"policy": MODULE.APPROVED_POLICY}}
    assert MODULE.validate_policy_transition(MODULE.extract_policy_text(response)) == "approved"


def test_extract_policy_text_rejects_inconsistent_shapes():
    response = {
        "policy": MODULE.APPROVED_POLICY,
        "data": {"rules": MODULE.LEGACY_POLICY},
    }
    with pytest.raises(MODULE.AdjustmentError, match="inconsistent"):
        MODULE.extract_policy_text(response)
