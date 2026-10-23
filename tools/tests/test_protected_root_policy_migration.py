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
    assert m.preview_exact_migration(CANDIDATE, BASE) == "OWNER_CCC_REVIEWED_DELTA_ONLY"
    assert policy.read_bytes() == original
    assert not m.ACTIVE.exists()
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


def test_reviewed_migration_preview_is_read_only_and_fails_without_authority(monkeypatch, tmp_path):
    policy, original, _ = configure(monkeypatch, tmp_path)
    assert m.preview_exact_migration(CANDIDATE, BASE) == "OWNER_CCC_REVIEWED_DELTA_ONLY"
    assert policy.read_bytes() == original
    assert not m.ACTIVE.exists()
    def deny(*args):
        raise m.MigrationRefused("exact Owner CCC review missing")
    monkeypatch.setattr(m, "_approval", deny)
    with pytest.raises(m.MigrationRefused, match="Owner"):
        m.preview_exact_migration(CANDIDATE, BASE)
    assert policy.read_bytes() == original
    assert not m.ACTIVE.exists()

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
    assert installer.index('ROOT / "tools" / "protected_root_policy_migration.py"') < installer.index('ROOT / "tools" / "release_host_reconcile_worker.py"')
    assert "migration.apply_for_candidate(candidate,baseline)" in transition
    assert "_restore_root_policy_for_target(source_revision)" in worker
    assert worker.index("_restore_root_policy_for_target(source_revision)", worker.index("def _process(")) < worker.index("_candidate_reconcile_script(source_revision)", worker.index("def _process("))


def test_exact_owner_approval_and_ccc_reviewer_are_checked(monkeypatch, tmp_path):
    root = tmp_path / "release-manager"
    (root / "records").mkdir(parents=True)
    ccc = tmp_path / "material-review.json"
    ctrl = root / "production-control-state.json"
    release = root / "records" / ("release-" + CANDIDATE[:16] + ".json")
    record = {
        "state": "production",
        "risk_profile": "production_control_core",
        "owner_approval": {"approved": True, "candidate_sha": CANDIDATE},
        "release_manifest": {"candidate_sha": CANDIDATE, "rollback_sha": BASE},
    }
    review = {"source_revision": CANDIDATE, "status": "approved",
              "recorded_by": "person-al"}
    control = {"schema_version": "1.0", "last_known_good": {
        "manifest": {"revision": BASE, "complete": True}},
        "circuit_breaker": {"state": "closed"}}
    monkeypatch.setattr(m, "ROOT", root)
    monkeypatch.setattr(m, "CCC_REVIEW", ccc)
    monkeypatch.setattr(m, "_root_only", lambda p: Path(p).read_bytes())
    def write():
        release.write_text(json.dumps(record))
        ccc.write_text(json.dumps(review))
        ctrl.write_text(json.dumps(control))
    write()
    m._approval(CANDIDATE, BASE)
    record["owner_approval"]["approved"] = False
    write()
    with pytest.raises(m.MigrationRefused, match="exact owner-approved"):
        m._approval(CANDIDATE, BASE)
    record["owner_approval"]["approved"] = True
    review["recorded_by"] = "some-other-person"
    write()
    with pytest.raises(m.MigrationRefused, match="exact owner-reviewed CCC"):
        m._approval(CANDIDATE, BASE)
    review["recorded_by"] = "person-al"
    control["circuit_breaker"]["state"] = "open"
    write()
    with pytest.raises(m.MigrationRefused, match="breaker"):
        m._approval(CANDIDATE, BASE)


def test_crash_before_policy_write_can_be_recovered_without_false_success(monkeypatch, tmp_path):
    policy, original, _ = configure(monkeypatch, tmp_path)
    real_atomic = m._atomic
    attempts = []
    def fail_on_policy(path, data):
        attempts.append(Path(path))
        if Path(path) == policy:
            raise OSError("injected atomic policy write failure")
        return real_atomic(path, data)
    monkeypatch.setattr(m, "_atomic", fail_on_policy)
    with pytest.raises(OSError, match="injected"):
        m.apply_for_candidate(CANDIDATE, BASE)
    assert policy.read_bytes() == original
    receipt = json.loads(m.ACTIVE.read_text())
    assert receipt["phase"] == "prepared"
    monkeypatch.setattr(m, "_atomic", real_atomic)
    assert m.restore_for_baseline(BASE) == "RESTORED"
    assert policy.read_bytes() == original
    assert not m.ACTIVE.exists()


def test_real_temporary_policy_full_forward_and_downgrade_roundtrip(monkeypatch, tmp_path):
    import importlib.util
    repo_root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("release_worker_roundtrip",
        repo_root / "release_host_reconcile_worker.py")
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)
    root_policy, original, _ = configure(monkeypatch, tmp_path)
    monkeypatch.setattr(worker, '_trusted_root_policy_helper', lambda: m)
    monkeypatch.setattr(worker, '_protected_root_drift_policy',
                        lambda: json.loads(root_policy.read_text()))
    monkeypatch.setattr(worker.subprocess, 'check_output',
                        lambda *args, **kwargs: json.dumps(source(new=True)))
    assert worker._preflight_candidate_root_policy(CANDIDATE) == (
        "OWNER_CCC_REVIEWED_DELTA_ONLY")
    assert root_policy.read_bytes() == original
    assert not m.ACTIVE.exists()
    assert m.apply_for_candidate(CANDIDATE, BASE) == 'APPLIED'
    worker._verify_root_policy_covers_candidate(CANDIDATE)
    installed = json.loads(root_policy.read_text())
    for field, units in m.APPROVED_DELTA.items():
        assert units.issubset(set(installed[field]))
    assert worker._restore_root_policy_for_target(BASE) == 'RESTORED'
    assert root_policy.read_bytes() == original
    assert not m.ACTIVE.exists()
    receipt_path = tmp_path / 'recovery' / 'approved-migrations' / (
        'restored-' + CANDIDATE + '.json')
    assert receipt_path.exists()
    assert json.loads(receipt_path.read_text())['phase'] == 'restored'
