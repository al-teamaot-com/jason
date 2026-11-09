"""Native release policy V5 matches the exact runtime contract, still inert."""
import json
from pathlib import Path

import pytest

from tools.release_manager_host_runner import (
    ReleaseManagerError, _validated_mobile_release_policy,
)

def _policy(tmp_path, *, v5=True):
    source = Path(__file__).resolve().parents[2] / "config" / "mobile-release-approval-policy.json"
    payload = json.loads(source.read_text())
    if v5:
        payload["schema_version"] = "5.0"
        payload["policy_mode"] = "service_requester_regular_owner_teams"
        payload["release_requester_principal_id"] = "svc-jason-release-manager"
    target = tmp_path / "mobile-owner-policy.json"
    target.write_text(json.dumps(payload))
    target.chmod(0o600)
    return target



def test_native_v5_requires_exact_aot_service_requester_and_owner_separation(tmp_path):
    p = _policy(tmp_path)
    result = _validated_mobile_release_policy(p, source_v2_required=True)
    assert result["schema_version"] == "5.0"
    assert result["mode"] == "service_requester_regular_owner_teams"
    assert result["ttl_seconds"] == 900
    assert result["digest"].startswith("sha256:")


def test_native_v4_keeps_original_admin_separated_mode(tmp_path):
    p = _policy(tmp_path, v5=False)
    result = _validated_mobile_release_policy(p, source_v2_required=True)
    assert result["mode"] == "admin_approver_separated"


@pytest.mark.parametrize("update", [
    {"release_requester_principal_id": "person-al"},
    {"policy_mode": "admin_approver_separated"},
    {"allowed_risk_profiles": ["normal"]},
    {"owner_identity_ids": ["someone-else"]},
    {"ttl_seconds": 6000},
])
def test_native_policy_rejects_unreviewed_v5_scope(tmp_path, update):
    p = _policy(tmp_path)
    data = json.loads(p.read_text())
    data.update(update)
    p.write_text(json.dumps(data))
    with pytest.raises(ReleaseManagerError):
        _validated_mobile_release_policy(p, source_v2_required=True)


def test_native_policy_rejects_extra_approval_switch(tmp_path):
    p = _policy(tmp_path)
    data = json.loads(p.read_text())
    data["ignore_teams"] = True
    p.write_text(json.dumps(data))
    with pytest.raises(ReleaseManagerError):
        _validated_mobile_release_policy(p, source_v2_required=True)
