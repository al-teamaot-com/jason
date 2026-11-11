"""Read-only PMv4 exact migration source attestations and fail-closed CI."""
from __future__ import annotations

from pathlib import Path

import pytest

from tools import pmv4_migration_evidence as migration


def _fake_call(*, missing: str | None = None, bad_path: bool = False,
               failed: bool = False):
    def fake(argv):
        if "pr" in argv and "view" in argv:
            return {
                "headRefOid": "f" * 40, "state": "OPEN", "isDraft": True,
                "baseRefName": "main",
                "files": [{"path": "../prod/secrets"} if bad_path
                          else {"path": "tools/pmv4_release.py"}],
            }
        if "pr" in argv and "checks" in argv:
            return [
                {"name": item, "bucket": "fail" if failed and item == "runtime-service"
                    else "pass"}
                for item in migration.REQUIRED_SOURCE_CHECKS if item != missing
            ]
        raise RuntimeError("Unexpected query")
    return fake


def test_exact_ci_and_source_scope_when_all_required_checks_green(monkeypatch):
    monkeypatch.setattr(migration, "_call", _fake_call())
    result = migration._github_pr(2438)
    assert result["source_sha"] == "f" * 40
    assert result["required_source_checks_present"]
    assert result["preproduction_checks_green"] is True
    assert result["scope_files"] == ["tools/pmv4_release.py"]
    assert len(result["scope_sha256"]) == 64


def test_missing_required_check_is_not_mislabelled_green(monkeypatch):
    monkeypatch.setattr(migration, "_call", _fake_call(missing="runtime-service"))
    result = migration._github_pr(2438)
    assert result["ci"]["pass"] > 0
    assert result["required_source_checks_present"] is False
    assert result["preproduction_checks_green"] is False


def test_failed_required_check_denies_ready(monkeypatch):
    monkeypatch.setattr(migration, "_call", _fake_call(failed=True))
    result = migration._github_pr(2438)
    assert result["preproduction_checks_green"] is False
    assert result["ci"]["fail"] == 1


def test_path_traversal_scope_denied(monkeypatch):
    monkeypatch.setattr(migration, "_call", _fake_call(bad_path=True))
    with pytest.raises(migration.MigrationEvidenceDenied, match="SCOPE_UNTRUSTED"):
        migration._github_pr(2438)


def test_missing_or_protected_control_state_reports_uncertainty(tmp_path):
    result = migration._file_status("protected-control", str(tmp_path / "missing"))
    assert result["status"] == "absent_or_untrusted"
    # No fake success when file is inaccessible; a generated report must
    # still be a PREPRODUCTION packet, never an Owner release grant.
    file = tmp_path / "owner-pause.json"
    file.write_text("not-sensitive-test")
    result = migration._file_status("owner-pause", str(file))
    assert result["status"] == "readable"
    assert len(result["sha256"]) == 64


def test_invalid_digest_or_source_label_rejected(monkeypatch):
    monkeypatch.setattr(migration, "_call", lambda args: [{
        "Id": "sha256:invalid",
        "Config": {"Labels": {"com.teamaot.jason.source_revision": "a" * 40}},
    }])
    with pytest.raises(migration.MigrationEvidenceDenied, match="IMAGE_PROVENANCE"):
        migration._image("jason-runtime:production")
