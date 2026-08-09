from __future__ import annotations

from pathlib import Path

import pytest

from tools import provider_secret_lifecycle as lifecycle


def test_check_only_declares_canonical_lifecycle_boundary():
    for action in lifecycle.ACTIONS:
        result = lifecycle._check_only(action, "datto_rmm")
        assert result["status"] == "pass"
        assert result["runtime_authentication"] == "approle"
        assert result["kv_write_semantics"] == "kv_v2_compare_and_set"
        assert result["deactivation_semantics"] == (
            "revoke_runtime_identity_preserve_kv_history"
        )
        assert result["runtime_token_persisted"] is False
        assert result["network_contacted"] is False
        assert result["secret_entered"] is False


def test_create_and_update_are_distinct(monkeypatch):
    spec = lifecycle.base.PROVIDERS["datto_rmm"]
    monkeypatch.setattr(lifecycle.kv, "current_version", lambda *args: 2)
    with pytest.raises(lifecycle.LifecycleError, match="already exists"):
        lifecycle.create_or_update(
            address="http://openbao.invalid",
            admin_token="synthetic",
            provider="datto_rmm",
            action="create",
        )

    monkeypatch.setattr(lifecycle.kv, "current_version", lambda *args: 0)
    with pytest.raises(lifecycle.LifecycleError, match="does not exist"):
        lifecycle.create_or_update(
            address="http://openbao.invalid",
            admin_token="synthetic",
            provider="datto_rmm",
            action="update",
        )
    assert spec["logical_name"] == "datto_rmm.readonly"


def test_deactivate_preserves_kv_history(monkeypatch, tmp_path):
    provider = "datto_rmm"
    original = lifecycle.base.PROVIDERS[provider]
    spec = dict(original)
    spec["credential_dir"] = tmp_path / "datto-rmm-read-approle"
    monkeypatch.setitem(lifecycle.base.PROVIDERS, provider, spec)

    directory = Path(spec["credential_dir"])
    directory.mkdir()
    (directory / "role-id").write_text("synthetic-role\n", encoding="utf-8")
    (directory / "secret-id").write_text("synthetic-secret\n", encoding="utf-8")
    (directory / "credential-metadata.json").write_text(
        '{"secret_id_accessor":"synthetic-accessor"}', encoding="utf-8"
    )

    calls = []

    def fake_request(address, api_path, **kwargs):
        calls.append((api_path, kwargs.get("method")))
        return {}

    monkeypatch.setattr(lifecycle.base, "api_request", fake_request)
    monkeypatch.setattr(lifecycle, "_revoke_secret_id_accessor", lambda **kwargs: None)

    result = lifecycle.deactivate(
        address="http://openbao.invalid",
        admin_token="synthetic",
        provider=provider,
    )

    assert result["runtime_access_active"] is False
    assert result["kv_history_preserved"] is True
    assert result["provider_secret_destroyed"] is False
    assert not directory.exists()
    assert (f"auth/approle/role/{spec['role_name']}", "DELETE") in calls


def test_reactivate_requires_existing_secret(monkeypatch, tmp_path):
    provider = "datto_rmm"
    spec = dict(lifecycle.base.PROVIDERS[provider])
    spec["credential_dir"] = tmp_path / "datto-rmm-read-approle"
    monkeypatch.setitem(lifecycle.base.PROVIDERS, provider, spec)
    monkeypatch.setattr(lifecycle.kv, "current_version", lambda *args: 0)

    with pytest.raises(lifecycle.LifecycleError, match="use create"):
        lifecycle.reactivate(
            address="http://openbao.invalid",
            admin_token="synthetic",
            provider=provider,
        )


def test_rotation_reasserts_policy_before_new_identity(monkeypatch, tmp_path):
    provider = "datto_rmm"
    spec = dict(lifecycle.base.PROVIDERS[provider])
    spec["credential_dir"] = tmp_path / "datto-rmm-read-approle"
    monkeypatch.setitem(lifecycle.base.PROVIDERS, provider, spec)
    directory = Path(spec["credential_dir"])
    directory.mkdir()
    for name, value in {
        "role-id": "role",
        "secret-id": "old-secret",
        "credential-metadata.json": '{"secret_id_accessor":"old-accessor"}',
    }.items():
        (directory / name).write_text(value, encoding="utf-8")

    order = []
    monkeypatch.setattr(
        lifecycle.base,
        "configure_read_approle",
        lambda **kwargs: order.append("configure") or {"credential_dir": str(directory)},
    )
    monkeypatch.setattr(
        lifecycle,
        "_new_secret_id",
        lambda **kwargs: (order.append("new") or "new-secret", "new-accessor"),
    )
    monkeypatch.setattr(
        lifecycle,
        "_write_rotation_metadata",
        lambda provider, accessor: order.append("metadata"),
    )
    monkeypatch.setattr(
        lifecycle,
        "_revoke_secret_id_accessor",
        lambda **kwargs: order.append("revoke-old"),
    )
    monkeypatch.setattr(lifecycle, "_atomic_private_file", lambda *args: order.append("install"))

    result = lifecycle.rotate_identity(
        address="http://openbao.invalid",
        admin_token="synthetic",
        provider=provider,
    )

    assert result["status"] == "pass"
    assert order == ["configure", "new", "install", "metadata", "revoke-old"]
