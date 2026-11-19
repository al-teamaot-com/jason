"""The independently installed root CLI needs its pinned PMv4 sibling module."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from tools import scoped_backport_projection_helper_repair as repair
from tools import scoped_backport_native_host as host
from tools import scoped_backport_root_install as installer


def test_immutable_root_policy_covers_the_missing_import_module():
    assert "tools/pmv4_mcp_projection.py" in installer.FILES
    assert installer.FILES.count("tools/pmv4_mcp_projection.py") == 1
    assert ("native_mcp_projection_sha256" in
            host.ROOT_POLICY_FIELDS)
    assert host.INSTALL_FILES["native_mcp_projection_sha256"] == (
        host.INSTALL_ROOT / "tools/pmv4_mcp_projection.py")
    assert host.INSTALL_FILES["native_deploy_sha256"] == (
        host.INSTALL_ROOT / "tools/deploy_live_container.py")
    assert set(host.ROOT_POLICY_FIELDS) >= set(host.INSTALL_FILES)


def test_standalone_pinned_native_cli_proves_omitted_import_regression(tmp_path):
    # Treat this as a new root installation: NOT the repo's tools directory.
    executable = tmp_path / "tools" / "deploy_live_container.py"
    executable.parent.mkdir()
    executable.write_bytes((installer.REPO / "tools/deploy_live_container.py").read_bytes())
    proc = subprocess.run([sys.executable, "-E", str(executable), "--help"],
                          capture_output=True, text=True, timeout=15)
    assert proc.returncode != 0
    assert "ModuleNotFoundError" in proc.stderr
    assert "pmv4_mcp_projection" in proc.stderr
    # Required companion is installed as its own immutable module.
    proj = executable.parent / "pmv4_mcp_projection.py"
    proj.write_bytes((installer.REPO / "tools/pmv4_mcp_projection.py").read_bytes())
    passing = subprocess.run([sys.executable, "-E", str(executable), "--help"],
                             capture_output=True, text=True, timeout=15)
    assert passing.returncode == 0
    assert "--preflight" in passing.stdout
    assert "--add-readonly-bind" in passing.stdout
    assert passing.stderr == ""


def _previous():
    return {
        "schema_version": "1.0",
        "profile": "governed-scoped-backport-v1",
        "trusted_source_sha": repair.OLD_MAIN,
        "reviewed_ci_sha": repair.OLD_REVIEWED,
        "no_global_owner_elevation": True,
        "native_root_control_supported": True,
        "automatic_rollback_recovery_installed": True,
        "exact_signed_owner_approval_required": True,
        "native_host_sha256": "a"*64,
        "native_deploy_sha256": "b"*64,
        "root_handler_sha256": "c"*64,
        "runtime_protection": {"unmodified": True},
    }


def test_policy_upgrade_changes_only_four_exact_fields():
    before = _previous()
    original = deepcopy(before)
    host_data = b"reviewed native root host source"
    projection = b"reviewed root projection module"
    after = repair.upgrade_policy(
        before, source_sha="1"*40, reviewed_sha="2"*40,
        host=host_data, projection=projection)
    assert before == original
    assert set(after) - set(before) == {"native_mcp_projection_sha256"}
    changes = {k for k in before if before[k] != after[k]}
    assert changes == {
        "trusted_source_sha", "reviewed_ci_sha", "native_host_sha256"}
    assert after["native_mcp_projection_sha256"] == sha256(projection).hexdigest()
    assert after["native_host_sha256"] == sha256(host_data).hexdigest()
    assert after["root_handler_sha256"] == before["root_handler_sha256"]
    assert after["native_deploy_sha256"] == before["native_deploy_sha256"]
    assert after["runtime_protection"] == before["runtime_protection"]


@pytest.mark.parametrize("field,replacement", [
    ("trusted_source_sha", "f"*40),
    ("reviewed_ci_sha", "f"*40),
    ("no_global_owner_elevation", False),
    ("native_root_control_supported", False),
    ("automatic_rollback_recovery_installed", False),
])
def test_replay_or_changed_root_policy_denied(field, replacement):
    previous = _previous()
    previous[field] = replacement
    with pytest.raises(repair.base.DriftCorrectionDenied,
                       match="SCOPED_PROJECTION_PREVIOUS_ROOT_POLICY_NOT_EXACT"):
        repair.upgrade_policy(previous, source_sha="1"*40, reviewed_sha="2"*40,
                              host=b"new host", projection=b"new projection")


def test_duplicate_projection_file_in_root_policy_fails_closed():
    previous = _previous()
    previous["native_mcp_projection_sha256"] = "d"*64
    with pytest.raises(repair.base.DriftCorrectionDenied):
        repair.upgrade_policy(previous, source_sha="1"*40, reviewed_sha="2"*40,
                              host=b"host", projection=b"projection")


def test_production_scope_does_not_include_core_service_changes():
    assert repair.MODULE_PATH == repair.ROOT_DIR / "tools/pmv4_mcp_projection.py"
    assert repair.HOST_PATH == repair.ROOT_DIR / "tools/scoped_backport_native_host.py"
    assert repair.ROOT_POLICY == Path(
        "/etc/jason-owner-release/scoped-backport-installed.json")
    assert repair.PUBLIC == Path(
        "/etc/jason-owner-release/scoped-backport-public-attestation.json")
    assert repair.ROOT_AUDIT.parent == Path("/etc/jason-owner-release")
    assert "APPROVE" in repair.CONFIRM
    assert "GRAPH" not in repair.ACTION
    assert repair.ROOT_DIR.as_posix().startswith("/usr/local/lib/jason/")
    assert not any("pmv4-ticket" in v for v in repair.SCOPE_PATHS)


def test_no_verification_without_clean_exact_sha_and_reviewed_lineage(monkeypatch):
    monkeypatch.setattr(repair, "git", lambda *args: b"a"*40 + b"\n"
                        if args == ("rev-parse", "HEAD") else b"some-file-modified")
    with pytest.raises(repair.base.DriftCorrectionDenied,
                       match="SCOPED_PROJECTION_SOURCE_WORKTREE_DIRTY"):
        repair.source_verified("a"*40, "b"*40)


def test_source_verification_requires_bound_git_origin(monkeypatch):
    source = "a"*40
    def fake_git(*args):
        if args == ("rev-parse", "HEAD"):
            return (source+"\n").encode()
        if args == ("status", "--porcelain"):
            return b""
        if args == ("remote", "get-url", "origin"):
            return b"https://untrusted.example.org/fake"
        pytest.fail("must not read further from unrelated origin")
    monkeypatch.setattr(repair, "git", fake_git)
    with pytest.raises(repair.base.DriftCorrectionDenied,
                       match="SCOPED_PROJECTION_SOURCE_ORIGIN_NOT_AOT"):
        repair.source_verified(source, "b"*40)


def test_untrusted_new_helper_will_not_do_privileged_read(monkeypatch):
    monkeypatch.setattr(repair.os, "geteuid", lambda: 1000)
    monkeypatch.setenv("SUDO_USER", "al")
    monkeypatch.setattr(repair, "source_verified", lambda *a, **kw:
                        pytest.fail("must check root context first"))
    with pytest.raises(repair.base.DriftCorrectionDenied,
                       match="SCOPED_PROJECTION_AUTHENTICATED_LOCAL_SUDO_REQUIRED"):
        repair.inspect(source_sha="a"*40, reviewed_sha="b"*40)


def test_repair_only_validates_direct_one_user_owner_scope():
    # Retain the already-reviewed precise Entra Owner challenge; no generic
    # root actions or provisioned permissions are minted by this helper.
    assert repair.base.owner_sign_in.__module__.endswith(
        "scoped_backport_four_unit_drift_reconcile")
    assert repair.CONFIRM == "APPROVE-SCOPED-BACKPORT-PROJECTION-DEPENDENCY-V1"
    assert repair.ACTION == "INSTALL-SCOPED-BACKPORT-PINNED-PROJECTION-DEPENDENCY-V1"


def test_exact_new_root_module_rollback_rejects_foreign_bytes(monkeypatch, tmp_path):
    path = tmp_path / "module.py"
    path.write_bytes(b"foreign")
    monkeypatch.setattr(repair, "MODULE_PATH", path)
    monkeypatch.setattr(repair.base, "read_root", lambda *a, **kw: b"foreign")
    with pytest.raises(repair.base.DriftCorrectionDenied,
                       match="SCOPED_PROJECTION_FOREIGN_PROJECTION_MODULE_PREVENTS_ROLLBACK"):
        repair.remove_only_reviewed_module(b"expected")
    assert path.exists()


def test_root_module_atomic_creation_rejects_preexisting_symlink(tmp_path, monkeypatch):
    destination = tmp_path / "projection.py"
    destination.symlink_to(tmp_path / "untrusted")
    monkeypatch.setattr(repair, "MODULE_PATH", destination)
    with pytest.raises(repair.base.DriftCorrectionDenied,
                       match="SCOPED_PROJECTION_PROJECTION_MODULE_ALREADY_PRESENT"):
        repair.create_root_module(b"reviewed")


def test_no_permission_promoted_via_imported_root_module():
    # No new writable bind API is introduced. Reuse original module source.
    content = (installer.REPO / "tools/pmv4_mcp_projection.py").read_text()
    assert "EXACT_MOUNTS" in content
    assert "validate_source" in content
    assert "should_omit_existing" in content
