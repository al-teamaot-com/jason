"""Scoped native root installer requires exact Owner identity and immutable Git."""
from pathlib import Path

import pytest

from tools import scoped_backport_root_install as ins


def test_scope_and_installer_paths_are_only_new_components():
    assert ins.INSTALL_ROOT.as_posix().startswith("/usr/local/lib/jason/")
    assert ins.ROOT_POLICY.as_posix().startswith("/etc/jason-owner-release/")
    assert all(x.startswith("tools/scoped_backport_")
               or x == "tools/deploy_live_container.py"
               or x.startswith("implementation/kernel/")
               for x in ins.FILES)
    assert len(ins.UNITS) == 4
    assert all(x.startswith("jason-scoped-backport-") for x in ins.UNITS)
    assert "jason-runtime" not in ins.UNITS


def test_installer_requires_exact_protected_main_sha(monkeypatch):
    source = "1" * 40
    def fake_git(*args):
        if args == ("rev-parse", "HEAD"):
            return (source + "\n").encode()
        if args == ("status", "--porcelain"):
            return b""
        if args == ("ls-remote", "origin", "refs/heads/main"):
            return (("2" * 40) + "\trefs/heads/main\n").encode()
        pytest.fail("must not read other blobs from unapproved commit")
    monkeypatch.setattr(ins, "git", fake_git)
    with pytest.raises(ins.ScopedInstallDenied, match="INSTALL_SOURCE_NOT_LATEST_PROTECTED_MAIN"):
        ins.source_tree(source, "a" * 40)


def test_installer_refuses_dirty_source_before_reading_any_blob(monkeypatch):
    source = "1" * 40
    def fake_git(*args):
        if args == ("rev-parse", "HEAD"):
            return (source + "\n").encode()
        if args == ("status", "--porcelain"):
            return b" M tools/scoped_backport_root_install.py\n"
        pytest.fail("must not read other blobs from dirty source")
    monkeypatch.setattr(ins, "git", fake_git)
    with pytest.raises(ins.ScopedInstallDenied, match="INSTALL_SOURCE_NOT_CLEAN_EXACT_SHA"):
        ins.source_tree(source, "a" * 40)


def test_local_approval_is_not_sudo_permission(monkeypatch):
    evidence = {"install_scope_sha256": "a" * 64}
    monkeypatch.setattr(ins.os, "geteuid", lambda: 1000)
    monkeypatch.setenv("SUDO_USER", "al")
    with pytest.raises(ins.ScopedInstallDenied,
                       match="INSTALL_AUTHENTICATED_EXACT_OWNER_SCOPE_REQUIRED"):
        ins.install("b" * 40, "a" * 40, evidence, exact_scope="a" * 64)


def test_exact_approval_scope_required_before_source_or_owner_oauth(monkeypatch):
    evidence = {"install_scope_sha256": "a" * 64}
    monkeypatch.setattr(ins.os, "geteuid", lambda: 0)
    monkeypatch.setenv("SUDO_USER", "al")
    monkeypatch.setattr(ins, "preflight",
                        lambda sha: pytest.fail("no preflight after invalid scope"))
    with pytest.raises(ins.ScopedInstallDenied,
                       match="INSTALL_AUTHENTICATED_EXACT_OWNER_SCOPE_REQUIRED"):
        ins.install("b" * 40, "a" * 40, evidence, exact_scope="c" * 64)


def test_existing_root_install_is_never_treated_as_idempotent(monkeypatch):
    source = "1" * 40
    monkeypatch.setattr(ins, "source_tree", lambda sha, reviewed: {"test": b"raw"})
    monkeypatch.setattr(ins, "INSTALL_ROOT", Path(__file__).resolve().parent)
    with pytest.raises(ins.ScopedInstallDenied,
                       match="INSTALL_EXISTING_ROOT_CONTROL_REQUIRES_REVIEW"):
        ins.preflight(source, "a" * 40)


def test_protected_root_read_requires_authenticated_local_session(monkeypatch):
    monkeypatch.setattr(ins.os, "geteuid", lambda: 1000)
    monkeypatch.setenv("SUDO_USER", "al")
    with pytest.raises(ins.ScopedInstallDenied, match="INSTALL_AUTHENTICATED_LOCAL_ROOT_REQUIRED"):
        ins.protected_root_controls({"frozen_sha256": "a" * 64})


def test_private_signer_is_not_collected_by_install_source():
    assert all("private_key" not in k for k in ins.FILES)
    assert all("private_key" not in k for k in ins.UNITS)


def test_reviewed_ci_blob_must_equal_protected_main_before_code_is_trusted(monkeypatch):
    source = "1" * 40
    reviewed = "2" * 40
    first = ins.FILES[0]
    def fake_git(*args):
        if args == ("rev-parse", "HEAD"):
            return (source + "\n").encode()
        if args == ("status", "--porcelain"):
            return b""
        if args == ("ls-remote", "origin", "refs/heads/main"):
            return (source + "\trefs/heads/main\n").encode()
        if args == ("show", source + ":" + first):
            return b"reviewed bytes"
        if args == ("show", reviewed + ":" + first):
            return b"different bytes"
        pytest.fail("must reject before trusting any further input")
    monkeypatch.setattr(ins, "git", fake_git)
    with pytest.raises(ins.ScopedInstallDenied, match="REVIEWED_CI_TO_MAIN_SOURCE_DRIFT"):
        ins.source_tree(source, reviewed)


def test_reviewed_ci_required_checks_must_all_pass(monkeypatch):
    from io import BytesIO
    import json
    expected = ("repository-hygiene", "documentation",
                "governed-security-regressions", "runtime-service",
                "GitGuardian Security Checks")
    def response(fail=None):
        checks = [{"name": name, "status": "completed",
                   "conclusion": "failure" if name == fail else "success", "id": i}
                  for i, name in enumerate(expected, 1)]
        class Reply:
            def __enter__(self): return BytesIO(json.dumps({"check_runs": checks}).encode())
            def __exit__(self, *args): return None
        return Reply()
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **kw: response())
    ins.required_github_checks("a" * 40)
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **kw: response("GitGuardian Security Checks"))
    with pytest.raises(ins.ScopedInstallDenied, match="INSTALL_REQUIRED_CI_NOT_GREEN"):
        ins.required_github_checks("a" * 40)


def test_root_policy_exactly_matches_native_host_schema():
    from tools import scoped_backport_native_host as host
    assert "reviewed_ci_sha" in host.ROOT_POLICY_FIELDS
    assert host.ROOT_POLICY_FIELDS >= {
        "trusted_source_sha", "reviewed_ci_sha", "root_handler_sha256",
        "root_recovery_sha256", "automatic_rollback_recovery_installed",
        "exact_signed_owner_approval_required"}
