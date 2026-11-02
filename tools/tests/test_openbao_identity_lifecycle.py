from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "openbao_identity_lifecycle.py"
spec = importlib.util.spec_from_file_location("openbao_identity_lifecycle", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def private(path: Path, value: str, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value + "\n", encoding="utf-8")
    os.chmod(path, mode)


def configure_tmp(monkeypatch, tmp_path: Path):
    source_a = tmp_path / "autotask"
    source_d = tmp_path / "dnsfilter"
    staged = tmp_path / "runtime" / "autotask" / "secret_id"
    mcp_staged = tmp_path / "mcp-runtime" / "autotask" / "secret-id"
    for root, role, secret in (
        (source_a, "role-a", "old-a"),
        (source_d, "role-d", "old-d"),
    ):
        private(root / "role-id", role)
        private(root / "secret-id", secret)
    private(staged, "old-a", 0o400)
    private(mcp_staged, "old-a", 0o600)
    monkeypatch.setattr(module.os, "geteuid", lambda: 0)
    monkeypatch.setattr(module, "ROOT_UID", os.getuid())
    monkeypatch.setattr(module, "ROOT_GID", os.getgid())
    monkeypatch.setattr(module, "STATE_ROOT", tmp_path / "state")
    monkeypatch.setattr(module, "ROLE_MAP", tmp_path / "state" / "role-map.json")
    monkeypatch.setattr(module, "LIFECYCLE_CREDENTIAL_DIR", tmp_path / "lifecycle")
    monkeypatch.setattr(
        module,
        "PROFILES",
        {
            "autotask_read": module.IdentityProfile("autotask_read", source_a, (staged, mcp_staged)),
            "dnsfilter": module.IdentityProfile("dnsfilter", source_d),
        },
    )
    return source_a, source_d, staged


def test_policy_contains_only_exact_approle_identity_paths():
    text = module.lifecycle_policy_text(
        {"autotask_read": "jason-autotask-read", "dnsfilter": "jason-dnsfilter-read"}
    )
    assert "secret/data/" not in text
    assert "sys/policies" not in text
    assert "auth/approle/role/jason-autotask-read/secret-id" in text
    assert "auth/approle/role/jason-dnsfilter-read/secret-id-accessor/destroy" in text
    assert 'path "auth/token/revoke-self"' in text


def test_discovery_matches_protected_role_id_without_exposing_value(monkeypatch, tmp_path):
    monkeypatch.setattr(module, "ROOT_UID", os.getuid())
    monkeypatch.setattr(module, "ROOT_GID", os.getgid())
    source = tmp_path / "provider"
    private(source / "role-id", "role-id-secret-value")
    private(source / "secret-id", "secret")
    profile = module.IdentityProfile("p", source)
    monkeypatch.setattr(module, "_list_approle_names", lambda token: ["one", "two"])

    def fake_api(path, **kwargs):
        return {"data": {"role_id": "role-id-secret-value" if "/two/" in path else "other"}}

    monkeypatch.setattr(module, "_api", fake_api)
    assert module.discover_role_name("admin-token", profile) == "two"


def test_bootstrap_builds_exact_policy_and_stores_no_provider_secret_values(monkeypatch, tmp_path):
    configure_tmp(monkeypatch, tmp_path)
    monkeypatch.setattr(
        module,
        "discover_role_name",
        lambda token, profile: "jason-autotask-read" if profile.provider == "autotask_read" else "jason-dnsfilter-read",
    )
    calls = []

    def fake_api(path, **kwargs):
        calls.append((path, kwargs))
        if path.endswith("/role-id"):
            return {"data": {"role_id": "lifecycle-role-id"}}
        if path.endswith("/secret-id") and "identity-lifecycle" in path:
            return {"data": {"secret_id": "lifecycle-secret-id", "secret_id_accessor": "accessor-life"}}
        return {}

    monkeypatch.setattr(module, "_api", fake_api)
    result = module.bootstrap("admin-token")
    assert result["status"] == "pass"
    assert result["provider_api_credentials_changed"] is False
    policy_call = next(x for x in calls if x[0].startswith("sys/policies/acl/"))
    policy = policy_call[1]["payload"]["policy"]
    assert "secret/data/" not in policy
    assert "jason-autotask-read" in policy and "jason-dnsfilter-read" in policy
    role_map = json.loads(module.ROLE_MAP.read_text())
    assert role_map["roles"] == {
        "autotask_read": "jason-autotask-read",
        "dnsfilter": "jason-dnsfilter-read",
    }
    serialized = json.dumps(role_map)
    assert "lifecycle-secret-id" not in serialized
    assert "lifecycle-role-id" not in serialized


def test_rotation_installs_new_before_revoking_old_and_marks_runtime_refresh(monkeypatch, tmp_path):
    source_a, source_d, staged = configure_tmp(monkeypatch, tmp_path)
    private(module.LIFECYCLE_CREDENTIAL_DIR / "role-id", "life-role")
    private(module.LIFECYCLE_CREDENTIAL_DIR / "secret-id", "life-secret")
    module._write_root_json(
        module.ROLE_MAP,
        {
            "schema_version": "1.0",
            "roles": {"autotask_read": "jason-autotask-read", "dnsfilter": "jason-dnsfilter-read"},
        },
    )
    monkeypatch.setattr(module, "_login_lifecycle", lambda: "short-token")
    monkeypatch.setattr(module, "_revoke_token", lambda token: None)
    order = []

    real_write = module._write_private_like

    def tracking_write(path, value, *args, **kwargs):
        order.append(("write", str(path)))
        return real_write(path, value, *args, **kwargs)

    monkeypatch.setattr(module, "_write_private_like", tracking_write)

    def fake_api(path, **kwargs):
        if path.endswith("/secret-id/lookup"):
            return {"data": {"secret_id_accessor": "old-accessor"}}
        if path.endswith("/secret-id"):
            return {"data": {"secret_id": "new-secret", "secret_id_accessor": "new-accessor"}}
        if path.endswith("/secret-id-accessor/destroy"):
            order.append(("revoke", kwargs["payload"]["secret_id_accessor"]))
            return {}
        return {}

    monkeypatch.setattr(module, "_api", fake_api)
    result = module.rotate("autotask_read")
    assert result["runtime_refresh_required"] is True
    assert result["provider_api_credentials_changed"] is False
    assert (source_a / "secret-id").read_text().strip() == "new-secret"
    assert staged.read_text().strip() == "new-secret"
    mcp_projection = module.PROFILES["autotask_read"].secret_id_projections[1]
    assert mcp_projection.read_text().strip() == "new-secret"
    assert result["secret_id_projection_count"] == 2
    assert order[-1] == ("revoke", "old-accessor")
    assert [x[0] for x in order[:3]] == ["write", "write", "write"]


def test_rotation_rejects_unknown_provider(monkeypatch, tmp_path):
    configure_tmp(monkeypatch, tmp_path)
    with pytest.raises(module.IdentityLifecycleError, match="not approved"):
        module.rotate("unknown")


def test_bootstrap_from_init_revokes_and_removes_initial_token(monkeypatch, tmp_path):
    configure_tmp(monkeypatch, tmp_path)
    init = tmp_path / 'init.json'
    init.write_text(json.dumps({'root_token': 'initial-admin-token', 'unseal_keys_b64': ['share-a', 'share-b']}) + '\n')
    os.chmod(init, 0o600)
    monkeypatch.setattr(module, 'INIT_FILE', init)
    monkeypatch.setattr(module, 'bootstrap', lambda token: {
        'status': 'pass', 'providers': ['autotask_read', 'dnsfilter'],
        'secret_values_printed': False,
    })
    revoked = []
    monkeypatch.setattr(module.base, 'revoke_admin_token', lambda address, token: revoked.append((address, token)))
    result = module.bootstrap_from_init(init)
    assert result['initial_admin_token_revoked'] is True
    assert result['initial_admin_token_removed_from_init'] is True
    assert revoked == [(module.ADDRESS, 'initial-admin-token')]
    rewritten = json.loads(init.read_text())
    assert rewritten['root_token'] == ''
    assert rewritten['unseal_keys_b64'] == ['share-a', 'share-b']
    assert 'initial-admin-token' not in json.dumps(result)


def test_bootstrap_from_init_without_token_fails_closed(monkeypatch, tmp_path):
    configure_tmp(monkeypatch, tmp_path)
    init = tmp_path / 'init.json'
    init.write_text(json.dumps({'root_token': '', 'unseal_keys_b64': ['share-a']}) + '\n')
    os.chmod(init, 0o600)
    with pytest.raises(module.IdentityLifecycleError, match='no usable'):
        module.bootstrap_from_init(init)


def test_release_recovery_requires_signed_teams_record_and_rotates_both(monkeypatch, tmp_path):
    configure_tmp(monkeypatch, tmp_path)
    sha = "a" * 40
    release_dir = tmp_path / sha
    release_dir.mkdir()
    current = tmp_path / "current"
    current.symlink_to(release_dir, target_is_directory=True)
    records = tmp_path / "records"
    records.mkdir()
    release_id = "release-" + sha[:16]
    record = {
        "release_id": release_id,
        "state": "production",
        "risk_profile": "production_control_core",
        "release_candidate": {"candidate_sha": sha},
        "changed_files": [
            "tools/openbao_identity_lifecycle.py",
            "tools/openbao_identity_lifecycle_worker.py",
            "tools/install_openbao_identity_lifecycle.py",
            "tools/reconcile_production_host_services.sh",
            "tools/release_manager_host_runner.py",
        ],
        "owner_approval": {
            "approved": True,
            "candidate_sha": sha,
            "source": "authenticated_mobile_teams_owner:relapproval-" + "c" * 32,
        },
        "open_breaker_recovery": {
            "profile_id": "provider_identity_and_authority_recovery",
        },
    }
    (records / (release_id + ".json")).write_text(json.dumps(record))
    monkeypatch.setattr(module, "CURRENT_RELEASE", current)
    monkeypatch.setattr(module, "RELEASE_RECORDS", records)
    monkeypatch.setattr(module, "bootstrap_from_init", lambda: {"status": "pass"})
    rotated = []
    monkeypatch.setattr(module, "rotate", lambda provider: rotated.append(provider) or {
        "new_identity_installed": True,
    })
    result = module.recover_approved_release(sha)
    assert result["status"] == "pass"
    assert rotated == ["autotask_read", "dnsfilter"]

    denied = json.loads(json.dumps(record))
    denied["owner_approval"]["source"] = "explicit_owner_instruction"
    (records / (release_id + ".json")).write_text(json.dumps(denied))
    with pytest.raises(module.IdentityLifecycleError, match="uniquely proven"):
        module.recover_approved_release(sha)
