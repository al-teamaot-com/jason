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


def test_protected_readback_distinguishes_current_lkg_previous_and_open_breaker(tmp_path):
    file = tmp_path / "protected-control-state.json"
    file.write_text(__import__("json").dumps({
        "schema_version": "1.0", "updated_at": "2026-11-11T20:24:42+00:00",
        "last_known_good": {
            "manifest": {"revision": "a" * 40,
                         "mobile_release_approval_mode": "owner_reviewed"}
        },
        "previous_last_known_good": {"manifest": {"revision": "b" * 40}},
        "circuit_breaker": {
            "state": "open", "reason": "continuous_production_drift_detected",
            "problem_kinds": ["undeclared_running_container"],
            "revalidated_revision": None,
        },
    }))
    result = migration._control_summary(str(file))
    assert result["status"] == "readable"
    assert result["last_known_good_sha"] == "a" * 40
    assert result["previous_last_known_good_sha"] == "b" * 40
    assert result["breaker_state"] == "open"
    assert result["breaker_revalidated_revision"] is None

    drift = tmp_path / "drift.json"
    drift.write_text(__import__("json").dumps({
        "status": "pass", "observed_at": "2026-11-11T20:33:44+00:00",
        "problems": [],
    }))
    now = migration._drift_summary(str(drift))
    assert now["status"] == "pass"
    assert now["problem_count"] == 0
    # A fresh zero-drift report never changes the root control breaker.
    assert result["breaker_state"] == "open"


def test_invalid_root_lkg_readback_is_not_treated_as_verified(tmp_path):
    file = tmp_path / "bad-control-state.json"
    file.write_text(__import__("json").dumps({
        "last_known_good": {"manifest": {"revision": "a" * 40}},
        "previous_last_known_good": {},
        "circuit_breaker": {"state": "closed"},
    }))
    assert migration._control_summary(str(file))["status"] == "unavailable_or_invalid"
