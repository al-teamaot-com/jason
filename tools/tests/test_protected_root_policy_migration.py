"""P0 #1974: root-owned exact-delta migration / symmetric rollback."""
from __future__ import annotations

import importlib.util
import json
import hashlib
from pathlib import Path
from unittest.mock import patch

import pytest

S = Path(__file__).resolve().parents[1] / "protected_root_policy_migration.py"
spec = importlib.util.spec_from_file_location("tested_root_policy_migration_1974", S)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
BASE = "a" * 40
CANDIDATE = "b" * 40


def source(*, new=False):
    base = {
        "schema_version": "1.0",
        "required_system_units": ["jason-openclaw-authority-health.timer"],
        "allowed_system_units": ["jason-openclaw-authority-health.service"],
        "required_user_units": ["jason-support-repair-worker.timer"],
        "allowed_user_units": ["jason-support-repair-worker.service"],
        "required_containers": ["jason-runtime"],
        "max_stopped_rollback_containers": 20,
    }
    if new:
        for field, units in m.APPROVED_DELTA.items():
            base[field] += sorted(units)
    return base


def configure(monkeypatch, tmp_path, *, policy=None, candidate=None, old=None):
    policy = policy or source()
    candidate = candidate or source(new=True)
    old = old or source()
    recovery = tmp_path / "recovery"
    recovery.mkdir(parents=True)
    store = recovery / "approved-migrations"
    store.mkdir(mode=0o700)
    root_policy = recovery / "production-desired-state.json"
    before = (json.dumps(policy, sort_keys=True) + "\n").encode()
    root_policy.write_bytes(before)
    source_map = {BASE: old, CANDIDATE: candidate}
    state = tmp_path / "production-control-state.json"
    state.write_text(json.dumps({"schema_version": "1.0",
                                 "last_known_good": {"manifest": {"revision": BASE}}}))
    monkeypatch.setattr(m, "POLICY", root_policy)
    monkeypatch.setattr(m, "LEDGER_DIR", store)
    monkeypatch.setattr(m, "ACTIVE", store / "active.json")
    monkeypatch.setattr(m, "ROOT", tmp_path)
    monkeypatch.setattr(m, "_source_policy", lambda sha: source_map[sha])
    monkeypatch.setattr(m, "_approval", lambda candidate_sha, rollback_sha: None)
    monkeypatch.setattr(m, "_require_root", lambda: None)
    monkeypatch.setattr(m, "_root_only", lambda p: Path(p).read_bytes())
    monkeypatch.setattr(m.os, "fchown", lambda *a, **kw: None)
    monkeypatch.setattr(m.os, "geteuid", lambda: 0)
    monkeypatch.setattr(m, "_ledger_dir", lambda: None)
    return root_policy, before, store


def test_reviewed_exact_four_declarations_and_original_root_extras_preserved(monkeypatch, tmp_path):
    previous = source()
    previous["allowed_system_units"] += ["jason-release-control-readback.service"]
    policy, original, _ = configure(monkeypatch, tmp_path, policy=previous)
    assert m.apply_for_candidate(CANDIDATE, BASE) == "APPLIED"
    after = json.loads(policy.read_text())
    for field, entries in m.APPROVED_DELTA.items():
        assert set(after[field]) == set(previous[field]) | entries
    assert "jason-release-control-readback.service" in after["allowed_system_units"]
    assert m.ACTIVE.is_file()
    record = json.loads(m.ACTIVE.read_text())
    assert record["phase"] == "applied"
    assert record["original_sha256"] == hashlib.sha256(original).hexdigest()
    assert m.apply_for_candidate(CANDIDATE, BASE) == "ALREADY_APPLIED"
    assert m.restore_for_baseline(BASE) == "RESTORED"
    assert policy.read_bytes() == original
    assert not m.ACTIVE.exists()
    receipt = tmp_path / "recovery/approved-migrations" / ("restored-" + CANDIDATE + ".json")
    assert receipt.exists() and json.loads(receipt.read_text())["phase"] == "restored"


def test_wrong_rollback_or_tampered_protected_policy_does_not_restore(monkeypatch, tmp_path):
    policy, before, _ = configure(monkeypatch, tmp_path)
    assert m.apply_for_candidate(CANDIDATE, BASE) == "APPLIED"
    with pytest.raises(m.MigrationRefused, match="rollback target"):
        m.restore_for_baseline("c" * 40)
    changed = json.loads(policy.read_text())
    changed["allowed_user_units"].append("jason-unknown.service")
    policy.write_text(json.dumps(changed))
    with pytest.raises(m.MigrationRefused, match="changed outside migration"):
        m.restore_for_baseline(BASE)
    assert policy.read_bytes() != before
    assert m.ACTIVE.exists()


def test_source_policy_scope_change_or_missing_declarations_rejected(monkeypatch, tmp_path):
    updated = source(new=True)
    updated["required_system_units"].remove("jason-openclaw-authority-full-integrity.timer")
    policy, original, _ = configure(monkeypatch, tmp_path, candidate=updated)
    with pytest.raises(m.MigrationRefused, match="unapproved desired-state"):
        m.apply_for_candidate(CANDIDATE, BASE)
    assert policy.read_bytes() == original
    assert not m.ACTIVE.exists()
    updated2 = source(new=True)
    updated2["max_stopped_rollback_containers"] = 10000
    configure(monkeypatch, tmp_path / "second", candidate=updated2)
    with pytest.raises(m.MigrationRefused, match="unreviewed non-unit"):
        m.apply_for_candidate(CANDIDATE, BASE)


def test_approval_rejection_happens_before_policy_touch(monkeypatch, tmp_path):
    policy, original, _ = configure(monkeypatch, tmp_path)
    def deny(*_):
        raise m.MigrationRefused("exact owner-reviewed CCC required")
    monkeypatch.setattr(m, "_approval", deny)
    with pytest.raises(m.MigrationRefused, match="CCC"):
        m.apply_for_candidate(CANDIDATE, BASE)
    assert policy.read_bytes() == original
    assert not m.ACTIVE.exists()


def test_unreviewed_addition_and_policy_mismatch_fail_closed(monkeypatch, tmp_path):
    changed = source()
    changed["allowed_system_units"].append("jason-openclaw-authority-full-integrity.service")
    policy, original, _ = configure(monkeypatch, tmp_path, policy=changed)
    with pytest.raises(m.MigrationRefused, match="already in root overlay"):
        m.apply_for_candidate(CANDIDATE, BASE)
    assert policy.read_bytes() == original


def test_rollback_refuses_mismatched_last_known_good(monkeypatch, tmp_path):
    policy, _, _ = configure(monkeypatch, tmp_path)
    assert m.apply_for_candidate(CANDIDATE, BASE) == "APPLIED"
    state = tmp_path / "production-control-state.json"
    state.write_text(json.dumps({"schema_version": "1.0",
                                 "last_known_good": {"manifest": {"revision": "c" * 40}}}))
    with pytest.raises(m.MigrationRefused, match="LKG"):
        m.restore_for_baseline(BASE)
    assert m.ACTIVE.exists()


def test_installers_and_root_worker_stage_then_restore_in_safe_order():
    root = Path(__file__).resolve().parents[2]
    reconcile = (root / "tools/reconcile_production_host_services.sh").read_text()
    installer = (root / "tools/install_release_host_reconciler.py").read_text()
    transition = (root / "tools/install_release_control_transition.py").read_text()
    worker = (root / "tools/release_host_reconcile_worker.py").read_text()
    assert reconcile.index("install_release_host_reconciler.py") < reconcile.index(
        "install_release_control_transition.py")
    assert "protected_root_policy_migration.py" in installer
    assert "migration.apply_for_candidate(candidate,baseline)" in transition
    assert "_restore_root_policy_for_target(source_revision)" in worker
    assert worker.index("_restore_root_policy_for_target(source_revision)", worker.index("def _process(")) < worker.index("_candidate_reconcile_script(source_revision)", worker.index("def _process("))
