"""Exact source declaration cannot be overridden by an arbitrary Entra admin."""
import json
from pathlib import Path
import pytest
from tools.jason_owner_auth_profile import EXPECTED, declared_jason_owner_profile


def policy(tmp_path, **changes):
    path = tmp_path / "config" / "jason-owner-authorization-profile.json"
    path.parent.mkdir(parents=True)
    obj = {**EXPECTED, "enabled": True, **changes}
    path.write_text(json.dumps(obj))
    return path


def test_source_exact_licensed_owner_profile_enabled(tmp_path):
    policy(tmp_path)
    assert declared_jason_owner_profile(tmp_path) == "jason-owner-v1"


def test_source_explicit_disable(tmp_path):
    policy(tmp_path, enabled=False)
    assert declared_jason_owner_profile(tmp_path) == ""


@pytest.mark.parametrize("changes", [
    {"jason_owner_object_id": "c848022d-e13b-4457-84b0-e2f5c00dcaf6"},
    {"microsoft_admin_jason_owner_authority": True},
    {"jason_owner_identity": "person-al"},
    {"microsoft_tenant_id": "22222222-2222-2222-2222-222222222222"},
    {"approval_per_exact_action": False},
    {"preserve_production_freeze": False},
    {"enabled": "true"},
    {"unreviewed_wildcard": "*"},
])
def test_source_modified_or_unsafe_profile_rejected(tmp_path, changes):
    policy(tmp_path, **changes)
    with pytest.raises(ValueError):
        declared_jason_owner_profile(tmp_path)


def test_missing_policy_does_not_enable_new_owner(tmp_path):
    assert declared_jason_owner_profile(tmp_path) == ""


def test_symlink_denied(tmp_path):
    original = policy(tmp_path)
    target = tmp_path / "data.json"
    original.rename(target)
    original.symlink_to(target)
    with pytest.raises(ValueError, match="INVALID_PATH"):
        declared_jason_owner_profile(tmp_path)


def test_source_declares_licensed_owner_not_microsoft_admin():
    assert declared_jason_owner_profile(Path(__file__).resolve().parents[2]) == "jason-owner-v1"
    assert EXPECTED["microsoft_admin_jason_owner_authority"] is False
