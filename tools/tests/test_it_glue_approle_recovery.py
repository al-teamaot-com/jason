"""Failure-first source tests for one-provider root-mediated IT Glue AppRole repair."""
import hmac
import json
import os
import stat
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tools import it_glue_approle_recovery as m


ROLE = m.SecretFile(Path("/protected/role-id"), "role-private-id", 0o600, 0, 0)
OLD = m.SecretFile(Path("/protected/secret-id"), "old-private-id", 0o600, 0, 0)


class Api:
    def __init__(self, *, old_valid=False, new_valid=True, new_kv_valid=True,
                 role_matches=True, fail_create=False):
        self.calls = []
        self.old_valid = old_valid
        self.new_valid = new_valid
        self.new_kv_valid = new_kv_valid
        self.role_matches = role_matches
        self.fail_create = fail_create
        self.tokens = {}

    def __call__(self, path, *, method, token=None, payload=None, allow_empty=False):
        self.calls.append((path, method, token, payload))
        if path.endswith("/role-id"):
            return {"data": {"role_id": ROLE.value if self.role_matches else "different-role"}}
        if path.endswith("/secret-id"):
            if self.fail_create:
                raise RuntimeError("provider failure with SECRET-NEVER-LOG")
            return {"data": {"secret_id": "new-private-id",
                             "secret_id_accessor": "new-accessor"}}
        if path == "auth/approle/login":
            sid = payload["secret_id"]
            if sid == "old-private-id" and self.old_valid:
                self.tokens["old"] = "token-old"
                return {"auth": {"client_token": "token-old"}}
            if sid == "new-private-id" and self.new_valid:
                self.tokens["new"] = "token-new"
                return {"auth": {"client_token": "token-new"}}
            raise RuntimeError("HTTP 403 SECRET-NEVER-LOG")
        if path == m.API_SECRET:
            if token == "token-new" and not self.new_kv_valid:
                raise RuntimeError("KV policy denied")
            return {"data": {"data": {"api_key": "ITG.test-key-never-exposed"}}}
        if path.endswith("/secret-id-accessor/destroy"):
            assert payload["secret_id_accessor"] == "new-accessor"
            return {}
        if path == "auth/token/revoke-self":
            return {}
        raise AssertionError((path, method))


def test_role_mismatch_denied_before_creation(monkeypatch):
    api = Api(role_matches=False)
    with pytest.raises(m.ItGlueIdentityError, match="ROLE_ID_MISMATCH"):
        m.rotate_once(api, admin_token="admin-token", role=ROLE, old=OLD)
    assert len(api.calls) == 1


def test_already_valid_does_not_rotate(monkeypatch):
    api = Api(old_valid=True)
    monkeypatch.setattr(m, "_write_private", lambda *_: pytest.fail("must not write"))
    result = m.rotate_once(api, admin_token="admin-token", role=ROLE, old=OLD)
    assert result["status"] == "already_valid"
    assert result["secret_id_rotated"] is False
    assert not any(p.endswith("/secret-id") for p, *_ in api.calls)


def test_new_secret_logged_in_and_kv_read_before_root_source_mutation(monkeypatch):
    api = Api()
    calls = []
    monkeypatch.setattr(m, "_write_private",
                        lambda original, replacement: calls.append(("write", replacement)))
    monkeypatch.setattr(m, "_protected",
                        lambda _: m.SecretFile(OLD.path, "new-private-id", 0o600, 0, 0))
    result = m.rotate_once(api, admin_token="admin-token", role=ROLE, old=OLD)
    assert result["status"] == "source_rotated"
    assert result["openbao_login_and_kv_verified"]
    assert result["provider_api_key_changed"] is False
    assert result["old_identity_revocation_deferred"] is True
    assert calls == [("write", "new-private-id")]
    assert any(p == m.API_SECRET and token == "token-new" for p, _, token, _ in api.calls)
    assert api.calls.index(next(c for c in api.calls if c[0] == m.API_SECRET and c[2] == "token-new")) < len(api.calls)
    assert not any(p.endswith("/secret-id-accessor/destroy") for p, *_ in api.calls)
    assert "old-private-id" not in json.dumps(result)
    assert "new-private-id" not in json.dumps(result)
    assert "ITG.test-key-never-exposed" not in json.dumps(result)


@pytest.mark.parametrize("overrides", [{"new_valid": False}, {"new_kv_valid": False},
                                       {"fail_create": True}])
def test_new_identity_denied_never_replaces_protected_source(monkeypatch, overrides):
    api = Api(**overrides)
    monkeypatch.setattr(m, "_write_private", lambda *_: pytest.fail("must not replace"))
    with pytest.raises(m.ItGlueIdentityError):
        m.rotate_once(api, admin_token="admin-token", role=ROLE, old=OLD)
    if not overrides.get("fail_create"):
        assert any(p.endswith("/secret-id-accessor/destroy") for p, *_ in api.calls)


def test_provider_error_is_sanitized_without_credential_content():
    api = Api(fail_create=True)
    with pytest.raises(m.ItGlueIdentityError) as exc:
        m.rotate_once(api, admin_token="admin-token", role=ROLE, old=OLD)
    assert "SECRET-NEVER-LOG" not in str(exc.value)


def test_root_guards_block_user_execute_and_uninstalled_code(monkeypatch):
    monkeypatch.setattr(m.os, "geteuid", lambda: 1000)
    with pytest.raises(m.ItGlueIdentityError, match="LOCAL_ROOT"):
        m._verify_installed_source("a" * 40)


def test_source_private_files_symlink_and_group_other_permissions_fail(tmp_path):
    secret = tmp_path / "real"
    secret.write_text("private-role-id")
    os.chmod(secret, 0o644)
    target = tmp_path / "alias"
    target.symlink_to(secret)
    with pytest.raises(OSError):
        m._protected(target)
    if os.geteuid() == 0:
        with pytest.raises(m.ItGlueIdentityError, match="permissions"):
            m._protected(secret)


def test_exact_provider_no_caller_controlled_targets():
    assert m.PROVIDER == "it_glue.readonly"
    assert m.ROLE == "jason-itglue-read"
    assert m.API_SECRET == "secret/data/connectors/it-glue/production/read-only"
    assert not hasattr(m, "provision_write_api_key")
    assert "read-only" in str(m.SOURCE_DIR).replace("itglue-read", "read-only")


def test_apply_needs_real_local_owner_and_exact_reference(monkeypatch, capsys):
    monkeypatch.setattr(m, "_verify_installed_source", lambda _: Path("/valid-record"))
    monkeypatch.setattr(m, "_protected", lambda p: ROLE if p.name == "role-id" else OLD)
    monkeypatch.delenv("SUDO_USER", raising=False)
    assert m.main(["--source-sha", "a" * 40, "--apply",
                   "--approval-reference", "valid-approval-20261112"]) == 1
    assert "LOCAL_OWNER_AND_EXACT_APPROVAL_REQUIRED" in capsys.readouterr().err


def test_no_root_operations_from_normal_check(monkeypatch, capsys):
    monkeypatch.setattr(m, "_verify_installed_source", lambda _: Path("/valid-record"))
    monkeypatch.setattr(m, "_protected", lambda p: ROLE if p.name == "role-id" else OLD)
    assert m.main(["--source-sha", "a" * 40, "--check-only"]) == 0
    assert "credential_values_exposed" in capsys.readouterr().out
