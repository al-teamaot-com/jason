"""P0 #1974: isolated root host policy/rollback sequencing fault injection.

These tests NEVER execute systemctl or write live protected files. They
validate the existing root worker with controlled fake host and process IO.
"""
from __future__ import annotations

import importlib.util
import json
import stat
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest


SOURCE = Path(__file__).resolve().parents[1] / "release_host_reconcile_worker.py"
spec = importlib.util.spec_from_file_location("root_host_1974_fault_path", SOURCE)
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)

CANDIDATE = "e8caace9791659adfd383a7ff148253c2ac5f424"
BASELINE = "aca94fdc0bfa551162f6ea99d7ddded311786414"
MISSING = (
    "protected root drift policy missing exact candidate unit declarations: "
    "required_system_units:jason-openclaw-authority-full-integrity.timer"
)


def test_missing_root_policy_permits_only_exact_reviewed_read_only_plan(tmp_path):
    reviewed = []
    root_state = {"schema_version": "1.0", "last_known_good": {
        "manifest": {"revision": BASELINE}
    }}
    helper = SimpleNamespace(
        ROOT=tmp_path,
        _root_only=lambda p: json.dumps(root_state).encode(),
        _json=lambda b: json.loads(b),
        preview_exact_migration=lambda target, rollback: (
            reviewed.append((target, rollback)) or "OWNER_CCC_REVIEWED_DELTA_ONLY"
        ),
    )
    with patch.object(
        worker, "_verify_root_policy_covers_candidate",
        side_effect=worker.HostReconcileError(MISSING),
    ), patch.object(worker, "_trusted_root_policy_helper", return_value=helper):
        assert worker._preflight_candidate_root_policy(CANDIDATE) == (
            "OWNER_CCC_REVIEWED_DELTA_ONLY"
        )
    assert reviewed == [(CANDIDATE, BASELINE)]


@pytest.mark.parametrize("failure", [
    "root recovery policy is not root-only mode-0600",
    "exact candidate drift policy schema is invalid",
    "invalid protected drift unit declarations: required_system_units",
])
def test_untrusted_root_policy_never_enters_migration_path(failure):
    with patch.object(worker, "_verify_root_policy_covers_candidate",
                      side_effect=worker.HostReconcileError(failure)), \
         patch.object(worker, "_trusted_root_policy_helper") as loader:
        with pytest.raises(worker.HostReconcileError, match=failure):
            worker._preflight_candidate_root_policy(CANDIDATE)
    loader.assert_not_called()


class _FakeReleaseDir:
    def __init__(self, revision: str):
        self.revision = revision

    def exists(self):
        return True

    def lstat(self):
        return SimpleNamespace(st_uid=0, st_mode=stat.S_IFDIR | 0o755)

    def is_symlink(self):
        return False

    def stat(self):
        return SimpleNamespace(st_uid=0, st_mode=stat.S_IFDIR | 0o755)


class _FakeReleases:
    def __truediv__(self, revision):
        return _FakeReleaseDir(revision)


def _simulate_root_worker(monkeypatch, tmp_path, revision, *, approved, outcome,
                          expires=False, missing_after=False):
    events = []
    results = []
    request = tmp_path / ("release-" + revision[:12] + ".json")
    request.write_text("{}")
    script = tmp_path / "fake-reconcile.sh"
    script.write_text("#!/bin/sh\nexit 0\n")
    real_path = Path

    monkeypatch.setattr(worker, "Path", lambda p:
                        _FakeReleases() if p == "/opt/jason/releases" else real_path(p))
    monkeypatch.setattr(worker, "CURRENT",
                        SimpleNamespace(resolve=lambda:
                                        SimpleNamespace(name=revision)))
    monkeypatch.setattr(worker.os, "chmod", lambda *args: None)
    monkeypatch.setattr(worker, "_read_request", lambda _p: {
        "request_id": request.stem, "source_revision": revision})
    monkeypatch.setattr(worker, "_verify_main",
                        lambda s: events.append(("main", s)))
    monkeypatch.setattr(worker, "_mcp_revision", lambda: revision)
    monkeypatch.setattr(worker, "_restore_root_policy_for_target",
                        lambda s: (events.append(("restore", s)) or
                                   ("ROLLBACK_ALLOWED_STAGE" if revision == BASELINE else
                                    "NO_MIGRATION_ACTIVE")))
    monkeypatch.setattr(worker, "_trusted_root_policy_helper",
                        lambda: SimpleNamespace(complete_rollback=lambda sha:
                            (events.append(("complete_policy", sha)) or "RESTORED")))
    monkeypatch.setattr(worker, "_preflight_candidate_root_policy",
                        lambda s: (events.append(("preflight", s)) or
                                   ("OWNER_CCC_REVIEWED_DELTA_ONLY" if approved else
                                    "ALREADY_COVERED")))
    monkeypatch.setattr(worker, "_candidate_reconcile_script",
                        lambda s: (events.append(("materialize", s)) or script))

    def run(command, **kwargs):
        events.append(("host_script", kwargs.get("timeout")))
        if expires:
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])
        return subprocess.CompletedProcess(command, 0, stdout=outcome)
    monkeypatch.setattr(worker.subprocess, "run", run)

    def verify(s):
        events.append(("root_post_check", s))
        if missing_after:
            raise worker.HostReconcileError("candidate root recovery policy still missing")
    monkeypatch.setattr(worker, "_verify_root_policy_covers_candidate", verify)
    monkeypatch.setattr(worker, "_write_result",
                        lambda *args, **kwargs: results.append(kwargs))
    worker._process(request)
    assert not request.exists()
    assert len(results) == 1
    return events, results[0]


def test_authorized_candidate_install_must_reverify_root_policy_before_success(
    monkeypatch, tmp_path
):
    events, result = _simulate_root_worker(
        monkeypatch, tmp_path, CANDIDATE, approved=True,
        outcome="HOST_RECONCILIATION=PASS", missing_after=False)
    assert result["success"] is True
    assert "ROOT_POLICY_PREFLIGHT=OWNER_CCC_REVIEWED_DELTA_ONLY" in result["detail"]
    assert [name for name, _ in events].index("preflight") < [
        name for name, _ in events].index("host_script") < [
        name for name, _ in events].index("root_post_check")


def test_candidate_install_without_actual_root_migration_is_rejected(
    monkeypatch, tmp_path
):
    events, result = _simulate_root_worker(
        monkeypatch, tmp_path, CANDIDATE, approved=True,
        outcome="HOST_RECONCILIATION=PASS", missing_after=True)
    assert result["success"] is False
    assert "still missing" in result["detail"]
    assert any(name == "root_post_check" for name, _ in events)


def test_baseline_rollback_restores_exact_bytes_only_after_full_health_script(
    monkeypatch, tmp_path
):
    events, result = _simulate_root_worker(
        monkeypatch, tmp_path, BASELINE, approved=False,
        outcome="HOST_RECONCILIATION=PASS", missing_after=False)
    assert result["success"] is True
    assert "ROOT_POLICY_MIGRATION=RESTORED" in result["detail"]
    assert ("host_script", 410) in events
    assert ("complete_policy", BASELINE) in events
    assert [name for name, _ in events].index("host_script") < [name for name, _ in events].index("complete_policy")
    assert [name for name, _ in events].index("restore") < [
        name for name, _ in events].index("host_script")
    assert not any(name == "root_post_check" for name, _ in events)


def test_stalled_legacy_full_health_check_is_not_accepted_as_verified_rollback(
    monkeypatch, tmp_path
):
    events, result = _simulate_root_worker(
        monkeypatch, tmp_path, BASELINE, approved=False, outcome="",
        expires=True)
    assert ("host_script", 410) in events
    assert not any(name == "complete_policy" for name, _ in events)
    assert result["success"] is False
    assert "exceeded 410s" in result["detail"]
    assert not any(name == "root_post_check" for name, _ in events)
