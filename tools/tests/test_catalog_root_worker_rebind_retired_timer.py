"""Root rebind must accept only an auditable, Owner-verified supersession of the obsolete timer."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import pytest

ROOT = Path(__file__).resolve().parents[1] / "catalog_root_worker_rebind_once.py"
spec = importlib.util.spec_from_file_location("catalog_root_rebind_retired_test", ROOT)
assert spec and spec.loader
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


@pytest.fixture
def receipt(tmp_path, monkeypatch):
    root = tmp_path / "root"
    root.mkdir()
    sha = "a" * 40
    current = "b" * 40
    consent = "exact-owner-approval-123"
    scope = "f" * 64
    accepted = {
        "schema_version": "1.0",
        "status": "completed_bootstrap_timer_superseded",
        "action": m.RETIREMENT_ACTION,
        "source_sha": sha,
        "scope_sha256": scope,
        "approval_id": consent,
        "drift": "pass",
        "scoped_recovery_timer_active": True,
        "breaker_force_closed": False,
        "production_freeze_changed": False,
        "protected_containers_restarted": 0,
    }
    attempt = {
        "status": "owner_consumed_before_mutation",
        "action": m.RETIREMENT_ACTION,
        "source_sha": sha,
        "scope_sha256": scope,
        "approval_id": consent,
        "owner_oid": "d8707b77-f0b3-41ec-9b06-2647efbd1ac5",
    }
    (root / (sha + "-accepted.json")).write_text(json.dumps(accepted))
    (root / (sha + "-attempt.json")).write_text(json.dumps(attempt))
    monkeypatch.setattr(m, "RETIREMENT_AUDIT", root)
    monkeypatch.setattr(m, "root_directory", lambda *args: None)
    monkeypatch.setattr(m, "file", lambda path, **kwargs: Path(path).read_bytes())
    state = {"timer_active": "inactive", "timer_enabled": "disabled",
             "ancestor_rc": 0}
    def fake_run(argv, **kwargs):
        if argv[0] == "runuser" and "merge-base" in argv:
            return subprocess.CompletedProcess(argv, state["ancestor_rc"], "", "")
        if argv[:2] == ("systemctl", "is-active"):
            return subprocess.CompletedProcess(argv, 3, state["timer_active"], "")
        if argv[:2] == ("systemctl", "is-enabled"):
            return subprocess.CompletedProcess(argv, 1, state["timer_enabled"], "")
        raise AssertionError(argv)
    monkeypatch.setattr(m.subprocess, "run", fake_run)
    return root, sha, current, consent, accepted, attempt, state


def test_valid_prior_authenticated_timer_retirement_permits_rebind(receipt):
    _, _, current, consent, _, _, _ = receipt
    assert m.verify_accepted_bootstrap_retirement(current) == consent


def test_rejects_absent_owner_identity(receipt):
    root, sha, current, _, _, attempt, _ = receipt
    attempt["owner_oid"] = ""
    (root / (sha + "-attempt.json")).write_text(json.dumps(attempt))
    with pytest.raises(PermissionError, match="TIMER_RETIREMENT_OWNER_AUDIT_INVALID"):
        m.verify_accepted_bootstrap_retirement(current)


def test_rejects_nonancestor_retirement_source(receipt):
    _, _, current, _, _, _, state = receipt
    state["ancestor_rc"] = 1
    with pytest.raises(PermissionError, match="TIMER_RETIREMENT_SOURCE_NOT_ANCESTOR"):
        m.verify_accepted_bootstrap_retirement(current)


@pytest.mark.parametrize("key,value", [
    ("timer_active", "active"), ("timer_enabled", "enabled"),
])
def test_rejects_reactivated_bootstrap_timer(receipt, key, value):
    _, _, current, _, _, _, state = receipt
    state[key] = value
    with pytest.raises(PermissionError, match="SUPERSEDED_BOOTSTRAP_TIMER_REACTIVATED"):
        m.verify_accepted_bootstrap_retirement(current)


def test_rejects_multiple_conflicting_root_receipts(receipt):
    root, _, current, _, accepted, _, _ = receipt
    (root / ("c" * 40 + "-accepted.json")).write_text(json.dumps(accepted))
    with pytest.raises(PermissionError, match="COMPLETED_TIMER_RETIREMENT_RECEIPT_REQUIRED"):
        m.verify_accepted_bootstrap_retirement(current)
