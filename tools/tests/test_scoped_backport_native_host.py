"""Native root host cannot be called from source or forged approval context."""
from pathlib import Path
import json

import pytest

from tools import scoped_backport_native_host as native
from tools.scoped_backport_release import ScopedBackportDenied, ENV


@pytest.fixture
def not_root_install(monkeypatch):
    # Even if an unprivileged caller simulates root UID, the actual source
    # path is not the attested installed root path. No production mutation.
    monkeypatch.setattr(native.os, "geteuid", lambda: 0)
    return native.NativeScopedBackportHost()


def test_native_root_host_requires_exact_install_path(not_root_install):
    with pytest.raises(ScopedBackportDenied, match="IMMUTABLE_ROOT_INSTALL_REQUIRED"):
        not_root_install.enforce_installed_root_trust()


@pytest.mark.parametrize("method,args", [
    ("freshly_validate_live_scope", ({},)),
    ("record_intent", ({}, {})),
    ("consume_owner_proof", ("owner-mcp-" + "a" * 32,)),
    ("promote_exact", ("jason-runtime", "sha256:" + "b" * 64,
                       "c" * 40, ENV, native.GROUP_BIND_DESTINATIONS)),
    ("restore_pair_exact", ({},)),
    ("record_outcome", ({}, "production_pair_verified")),
    ("open_breaker", ("SCOPED_BACKPORT_TEST_ONLY",)),
])
def test_privileged_methods_refuse_uninstalled_source(not_root_install, method, args):
    not_root_install.policy = {"simulated": True}
    with pytest.raises(ScopedBackportDenied, match="IMMUTABLE_ROOT_INSTALL_REQUIRED"):
        getattr(not_root_install, method)(*args)


def test_frozen_transaction_cannot_start_without_root(not_root_install):
    not_root_install.policy = {"simulated": True}
    with pytest.raises(ScopedBackportDenied, match="IMMUTABLE_ROOT_INSTALL_REQUIRED"):
        with not_root_install.frozen_transaction({}, {}):
            pytest.fail("would mutate a production freeze")


def test_root_release_lock_cannot_be_acquired_without_root(not_root_install):
    not_root_install.policy = {"simulated": True}
    with pytest.raises(ScopedBackportDenied):
        with not_root_install.release_lock({}):
            pytest.fail("would lock native production manager")


def test_symlink_and_untrusted_modes_are_denied(tmp_path):
    target = tmp_path / "protected.json"
    target.write_text('{"schema_version":"1.0"}')
    target.chmod(0o644)
    other = tmp_path / "link.json"
    other.symlink_to(target)
    with pytest.raises(ScopedBackportDenied, match="ROOT_FILE_MISSING_OR_SYMLINK"):
        native.exact_file(other, uid=0)
    with pytest.raises(ScopedBackportDenied, match="ROOT_FILE_METADATA_MISMATCH"):
        native.exact_file(target, uid=0, mode=0o600)


def test_docker_target_allowlist_blocks_foreign_container_before_docker(monkeypatch):
    monkeypatch.setattr(native, "run", lambda *args, **kwargs:
                        pytest.fail("must not call Docker for unreviewed names"))
    with pytest.raises(ScopedBackportDenied, match="UNKNOWN_DOCKER_TARGET"):
        native.inspect("jason-autotask-ticket-core")


def test_duplicate_environment_variable_is_denied():
    c = {"Config": {"Env": ["JASON_M365_GROUP_ADMIN_PROFILE=off",
                            "JASON_M365_GROUP_ADMIN_PROFILE=on"]}}
    with pytest.raises(ScopedBackportDenied, match="DUPLICATE_PROTECTED_ENV_SETTING"):
        native.env(c, "JASON_M365_GROUP_ADMIN_PROFILE")


def test_label_disagreement_is_denied():
    c = {"Config": {"Labels": {
        "org.opencontainers.image.revision": "a" * 40,
        "com.teamaot.jason.source_revision": "b" * 40,
    }}}
    with pytest.raises(ScopedBackportDenied, match="CONTAINER_SOURCE_LABEL_DRIFT"):
        native.source(c)


def test_absent_root_trust_signer_path_is_a_nonfatal_source_import():
    # Import is read-only, and static constant references no private key.
    assert native.TRUST_KEY.as_posix().startswith("/etc/jason-owner-release/")
    assert "private" not in native.TRUST_KEY.name


def test_exact_sudo_permission_receipt_target_is_read_only():
    assert native.ROOT_RECEIPT.as_posix().startswith("/var/lib/jason/authority/")
    assert native.ROOT_RECEIPT.name.endswith(".json")


def test_no_root_worker_or_recovery_modules_installed_on_host():
    # Test in source CI checks only that installation is not claimed by module.
    assert native.INSTALLED != Path(__file__).resolve()
    assert native.INSTALLED.parent.name == "tools"
