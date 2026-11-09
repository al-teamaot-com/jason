"""Native release policy V5 matches the exact runtime contract, still inert."""
import json

import pytest

from tools.release_manager_host_runner import (
    ReleaseManagerError, _validated_mobile_release_policy,
)
from implementation.runtime_service.tests.test_v5_service_originated_owner_release import v5
from implementation.runtime_service.tests.test_admin_separated_release_roles import separated_policy_file


def test_native_v5_requires_exact_aot_service_requester_and_owner_separation(tmp_path):
    p = v5(tmp_path)
    result = _validated_mobile_release_policy(p, source_v2_required=True)
    assert result["schema_version"] == "5.0"
    assert result["mode"] == "service_requester_regular_owner_teams"
    assert result["ttl_seconds"] == 600
    assert result["digest"].startswith("sha256:")


def test_native_v4_keeps_original_admin_separated_mode(tmp_path):
    p = separated_policy_file(tmp_path)
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
    p = v5(tmp_path)
    data = json.loads(p.read_text())
    data.update(update)
    p.write_text(json.dumps(data))
    with pytest.raises(ReleaseManagerError):
        _validated_mobile_release_policy(p, source_v2_required=True)


def test_native_policy_rejects_extra_approval_switch(tmp_path):
    p = v5(tmp_path)
    data = json.loads(p.read_text())
    data["ignore_teams"] = True
    p.write_text(json.dumps(data))
    with pytest.raises(ReleaseManagerError):
        _validated_mobile_release_policy(p, source_v2_required=True)
