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
    systemd = tmp_path / "systemd-system"
    systemd.mkdir(exist_ok=True)
    user_units = tmp_path / "systemd-user"
    user_units.mkdir(exist_ok=True)
    monkeypatch.setattr(m, "SYSTEMD_SYSTEM_UNITS", systemd)
    monkeypatch.setattr(m, "SYSTEMD_USER_UNITS", user_units)
    monkeypatch.setattr(m, "POLICY", root_policy)
    monkeypatch.setattr(m, "LEDGER_DIR", store)
    monkeypatch.setattr(m, "ACTIVE", store / "active.json")
    monkeypatch.setattr(m, "ROOT", tmp_path)
    monkeypatch.setattr(m, "_source_policy", lambda sha: source_map[sha])
    monkeypatch.setattr(m, "_reviewed_git_policy", lambda sha: source_map[sha])
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
    assert m.stage_for_candidate(CANDIDATE, BASE) == "STAGED_ALLOWED_ONLY"
    staged = json.loads(policy.read_text())
    assert "jason-openclaw-authority-full-integrity.timer" in staged["allowed_system_units"]
    assert "jason-openclaw-authority-full-integrity.timer" not in staged["required_system_units"]
    assert m.apply_for_candidate(CANDIDATE, BASE) == "APPLIED_REQUIRED_AFTER_HEALTH"
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
    assert m.stage_for_candidate(CANDIDATE, BASE) == "STAGED_ALLOWED_ONLY"
    staged = json.loads(policy.read_text())
    assert "jason-openclaw-authority-full-integrity.timer" in staged["allowed_system_units"]
    assert "jason-openclaw-authority-full-integrity.timer" not in staged["required_system_units"]
    assert m.apply_for_candidate(CANDIDATE, BASE) == "APPLIED_REQUIRED_AFTER_HEALTH"
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
        m.stage_for_candidate(CANDIDATE, BASE)
    assert policy.read_bytes() == original
    assert not m.ACTIVE.exists()
    updated2 = source(new=True)
    updated2["max_stopped_rollback_containers"] = 10000
    configure(monkeypatch, tmp_path / "second", candidate=updated2)
    with pytest.raises(m.MigrationRefused, match="unreviewed non-unit"):
        m.stage_for_candidate(CANDIDATE, BASE)


def test_approval_rejection_happens_before_policy_touch(monkeypatch, tmp_path):
    policy, original, _ = configure(monkeypatch, tmp_path)
    def deny(*_):
        raise m.MigrationRefused("exact owner-reviewed CCC required")
    monkeypatch.setattr(m, "_approval", deny)
    with pytest.raises(m.MigrationRefused, match="CCC"):
        m.stage_for_candidate(CANDIDATE, BASE)
    assert policy.read_bytes() == original
    assert not m.ACTIVE.exists()


def test_unreviewed_addition_and_policy_mismatch_fail_closed(monkeypatch, tmp_path):
    changed = source()
    changed["allowed_system_units"].append("jason-openclaw-authority-full-integrity.service")
    policy, original, _ = configure(monkeypatch, tmp_path, policy=changed)
    with pytest.raises(m.MigrationRefused, match="already present without ledger"):
        m.stage_for_candidate(CANDIDATE, BASE)
    assert policy.read_bytes() == original


def test_rollback_refuses_mismatched_last_known_good(monkeypatch, tmp_path):
    policy, _, _ = configure(monkeypatch, tmp_path)
    assert m.stage_for_candidate(CANDIDATE, BASE) == "STAGED_ALLOWED_ONLY"
    staged = json.loads(policy.read_text())
    assert "jason-openclaw-authority-full-integrity.timer" in staged["allowed_system_units"]
    assert "jason-openclaw-authority-full-integrity.timer" not in staged["required_system_units"]
    assert m.apply_for_candidate(CANDIDATE, BASE) == "APPLIED_REQUIRED_AFTER_HEALTH"
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
    assert reconcile.index("install_release_host_reconciler.py\" --stage-only") < reconcile.index("step_start system_service_activation")
    assert reconcile.index("step_start system_service_activation") < reconcile.index("step_start root_release_transition_install")
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
    monkeypatch.setattr(
        m.subprocess, "check_output",
        lambda *args, **kwargs: b'{"schema_version":"2.0"}',
    )
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
        m.stage_for_candidate(CANDIDATE, BASE)
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
    assert m.stage_for_candidate(CANDIDATE, BASE) == "STAGED_ALLOWED_ONLY"
    staged = json.loads(root_policy.read_text())
    assert "jason-openclaw-authority-full-integrity.timer" in staged["allowed_system_units"]
    assert "jason-openclaw-authority-full-integrity.timer" not in staged["required_system_units"]
    assert m.apply_for_candidate(CANDIDATE, BASE) == "APPLIED_REQUIRED_AFTER_HEALTH"
    worker._verify_root_policy_covers_candidate(CANDIDATE)
    installed = json.loads(root_policy.read_text())
    for field, units in m.APPROVED_DELTA.items():
        assert units.issubset(set(installed[field]))
    assert worker._restore_root_policy_for_target(BASE) == 'ROLLBACK_ALLOWED_STAGE'
    staged = json.loads(root_policy.read_text())
    assert "jason-openclaw-authority-full-integrity.timer" in staged["allowed_system_units"]
    assert "jason-openclaw-authority-full-integrity.timer" not in staged["required_system_units"]
    assert m.complete_rollback(BASE) == 'RESTORED'
    assert root_policy.read_bytes() == original
    assert not m.ACTIVE.exists()
    receipt_path = tmp_path / 'recovery' / 'approved-migrations' / (
        'restored-' + CANDIDATE + '.json')
    assert receipt_path.exists()
    assert json.loads(receipt_path.read_text())['phase'] == 'restored'


def test_preinstall_preview_uses_exact_git_objects_when_candidate_host_dir_absent(monkeypatch, tmp_path):
    reviewed_git_policy = m._reviewed_git_policy
    old = source()
    candidate = source(new=True)
    policy, original, _ = configure(monkeypatch, tmp_path)
    # Explicitly prove that read-only preflight never attempts a host release
    # directory before the reconciler has created it.
    monkeypatch.setattr(m, "_source_policy",
                        lambda _: (_ for _ in ()).throw(
                            AssertionError("candidate immutable directory unavailable")))
    calls = []
    def fake_git(argv, **kwargs):
        calls.append((argv, kwargs))
        assert argv[:6] == [
            "/usr/bin/git", "-c", f"safe.directory={m.MANAGED_GIT}",
            "-C", str(m.MANAGED_GIT), "show",
        ]
        sha = argv[-1].split(":", 1)[0]
        return json.dumps({BASE: old, CANDIDATE: candidate}[sha]).encode()
    # Override fixture policy loader with actual exact Git-object reader.
    monkeypatch.setattr(m.subprocess, "check_output", fake_git)
    monkeypatch.setattr(m, "_reviewed_git_policy", reviewed_git_policy)
    assert m.preview_exact_migration(CANDIDATE, BASE) == "OWNER_CCC_REVIEWED_DELTA_ONLY"
    assert len(calls) == 2
    assert policy.read_bytes() == original
    assert not m.ACTIVE.exists()


def test_reviewed_git_policy_denies_missing_object_and_oversized_payload(monkeypatch):
    from subprocess import CalledProcessError
    monkeypatch.setattr(
        m.subprocess, "check_output",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            CalledProcessError(128, "git show")),
    )
    with pytest.raises(m.MigrationRefused, match="exact-source"):
        m._reviewed_git_policy(CANDIDATE)
    monkeypatch.setattr(m.subprocess, "check_output",
                        lambda *_args, **_kwargs: b"x" * 131073)
    with pytest.raises(m.MigrationRefused, match="too large"):
        m._reviewed_git_policy(CANDIDATE)



def test_rollback_waits_until_both_system_and_user_candidate_units_are_removed(
    monkeypatch, tmp_path
):
    policy, original, _ = configure(monkeypatch, tmp_path)
    assert m.stage_for_candidate(CANDIDATE, BASE) == "STAGED_ALLOWED_ONLY"
    assert m.apply_for_candidate(CANDIDATE, BASE) == "APPLIED_REQUIRED_AFTER_HEALTH"
    systemd = m.SYSTEMD_SYSTEM_UNITS / "jason-openclaw-authority-full-integrity.timer"
    systemd.write_text("[Unit]\nDescription=Simulated installed timer\n")
    assert m.prepare_rollback(BASE) == "ROLLBACK_ALLOWED_STAGE"
    with pytest.raises(m.MigrationRefused, match="system unit still installed"):
        m.complete_rollback(BASE)
    assert m.ACTIVE.is_file()
    assert policy.read_bytes() != original
    systemd.unlink()
    user = m.SYSTEMD_USER_UNITS / "jason-openclaw-recovery-source-bridge.timer"
    user.write_text("[Unit]\nDescription=Simulated installed bridge\n")
    with pytest.raises(m.MigrationRefused, match="user unit still installed"):
        m.complete_rollback(BASE)
    user.unlink()
    assert m.complete_rollback(BASE) == "RESTORED"
    assert policy.read_bytes() == original


def test_interrupted_staging_before_service_start_restores_old_policy(
    monkeypatch, tmp_path
):
    policy, original, _ = configure(monkeypatch, tmp_path)
    assert m.stage_for_candidate(CANDIDATE, BASE) == "STAGED_ALLOWED_ONLY"
    assert m.prepare_rollback(BASE) == "ROLLBACK_ALLOWED_STAGE"
    assert m.complete_rollback(BASE) == "RESTORED"
    assert policy.read_bytes() == original


def test_rollback_stage_is_idempotent_and_does_not_become_required_again(
    monkeypatch, tmp_path
):
    policy, _, _ = configure(monkeypatch, tmp_path)
    assert m.stage_for_candidate(CANDIDATE, BASE) == "STAGED_ALLOWED_ONLY"
    assert m.apply_for_candidate(CANDIDATE, BASE) == "APPLIED_REQUIRED_AFTER_HEALTH"
    assert m.prepare_rollback(BASE) == "ROLLBACK_ALLOWED_STAGE"
    assert m.prepare_rollback(BASE) == "ROLLBACK_ALLOWED_STAGE"
    d = json.loads(policy.read_text())
    assert "jason-openclaw-authority-full-integrity.timer" in d["allowed_system_units"]
    assert "jason-openclaw-authority-full-integrity.timer" not in d["required_system_units"]


@pytest.mark.parametrize(
    ('mode', 'owner', 'group', 'accepted'),
    [
        (0o755, 0, 0, True),
        (0o775, 0, 0, True),  # Actual immutable root:root config directory
        (0o664, 0, 0, True),  # Actual immutable root:root desired-state file
        (0o644, 0, 999, True),  # Non-root group cannot write
        (0o775, 0, 1000, False),  # Non-root group can write
        (0o664, 0, 1000, False),
        (0o777, 0, 0, False),  # World writable even though root group
        (0o666, 0, 0, False),
        (0o775, 1000, 0, False),  # Non-root owner
        (0o664, 1000, 0, False),
    ],
)
def test_immutable_root_group_packaging_modes_are_bounded(
    mode, owner, group, accepted
):
    from types import SimpleNamespace
    import stat
    info = SimpleNamespace(
        st_uid=owner, st_gid=group, st_mode=stat.S_IFREG | mode
    )
    assert m._trusted_immutable_package_metadata(info) is accepted


def test_immutable_file_gate_and_root_private_policy_gate_remain_distinct():
    code = (Path(__file__).resolve().parents[1] /
            'protected_root_policy_migration.py').read_text()
    assert 'not _trusted_immutable_package_metadata(info)' in code
    assert 'not _trusted_immutable_package_metadata(meta)' in code
    # Independently root-protected policy, review ledger and CCC keys must
    # remain mode 0600 even though packaged immutable root:root files are 0664.
    assert 'st.st_mode & 0o077' in code
    assert 'getattr(os, "O_NOFOLLOW", 0)' in code


def test_p0_1993_exact_held_owner_offer_migrates_and_rolls_back_symmetrically(monkeypatch, tmp_path):
    """Old #1974 root declarations stay intact; only the held offer pair is new."""
    prior = source(new=True)
    candidate = {**prior,
                 "required_user_units": prior["required_user_units"] + [
                     "jason-release-approval-only.timer"],
                 "allowed_user_units": prior["allowed_user_units"] + [
                     "jason-release-approval-only.service"]}
    policy, original, _ = configure(monkeypatch, tmp_path,
                                     policy=prior, old=prior, candidate=candidate)
    assert m.preview_exact_migration(CANDIDATE,BASE) == "OWNER_CCC_REVIEWED_DELTA_ONLY"
    assert policy.read_bytes() == original
    assert m.stage_for_candidate(CANDIDATE,BASE) == "STAGED_ALLOWED_ONLY"
    staged = json.loads(policy.read_text())
    assert "jason-release-approval-only.timer" in staged["allowed_user_units"]
    assert "jason-release-approval-only.timer" not in staged["required_user_units"]
    assert "jason-release-approval-only.service" in staged["allowed_user_units"]
    assert m.apply_for_candidate(CANDIDATE,BASE) == "APPLIED_REQUIRED_AFTER_HEALTH"
    final = json.loads(policy.read_text())
    assert "jason-release-approval-only.timer" in final["required_user_units"]
    assert "jason-release-approval-only.service" in final["allowed_user_units"]
    receipt = json.loads(m.ACTIVE.read_text())
    assert receipt["reviewed_delta"] == {
        k: sorted(v) for k,v in m.APPROVED_HELD_OFFER_DELTA.items()
    }
    # The old, previously approved full-integrity system units are untouched.
    assert set(final["required_system_units"]) == set(prior["required_system_units"])
    assert m.prepare_rollback(BASE) == "ROLLBACK_ALLOWED_STAGE"
    rollback_stage = json.loads(policy.read_text())
    assert "jason-release-approval-only.timer" in rollback_stage["allowed_user_units"]
    assert "jason-release-approval-only.timer" not in rollback_stage["required_user_units"]
    # Candidate-only timer/service must have been removed by governed host
    # reconciliation; do not silently restore a policy that would hide them.
    timer=m.SYSTEMD_USER_UNITS/"jason-release-approval-only.timer"
    timer.write_text("reviewed candidate timer")
    with pytest.raises(m.MigrationRefused,match="candidate user unit still installed"):
        m.complete_rollback(BASE)
    timer.unlink()
    assert m.complete_rollback(BASE) == "RESTORED"
    assert policy.read_bytes() == original
    assert not m.ACTIVE.exists()


@pytest.mark.parametrize("invalid", ["union", "unexpected", "missing", "removed"])
def test_p0_1993_rejects_unreviewed_or_mixed_unit_deltas(monkeypatch,tmp_path,invalid):
    prior = source(new=True)
    candidate = {**prior,
                 "required_user_units": prior["required_user_units"] + [
                     "jason-release-approval-only.timer"],
                 "allowed_user_units": prior["allowed_user_units"] + [
                     "jason-release-approval-only.service"]}
    if invalid == "union":
        # A release that combines the historical P0 #1974 additions with a
        # fresh #1993 source delta must be independently reviewed, not matched.
        prior = source()
        candidate = {**source(new=True),
                     "required_user_units": candidate["required_user_units"],
                     "allowed_user_units": source(new=True)["allowed_user_units"] + [
                         "jason-release-approval-only.service"]}
    elif invalid == "unexpected":
        candidate["allowed_user_units"] += ["jason-rogue.service"]
    elif invalid == "missing":
        candidate["allowed_user_units"] = prior["allowed_user_units"]
    else:
        candidate["required_system_units"] = prior["required_system_units"][:-1]
    policy, original, _ = configure(monkeypatch,tmp_path,
                                     policy=prior,old=prior,candidate=candidate)
    with pytest.raises(m.MigrationRefused,match="unapproved desired-state"):
        m.preview_exact_migration(CANDIDATE,BASE)
    assert policy.read_bytes() == original
    assert not m.ACTIVE.exists()


def test_p0_1993_tampered_or_foreign_receipt_never_restores_as_trusted(monkeypatch,tmp_path):
    prior=source(new=True)
    candidate={**prior,
               "required_user_units": prior["required_user_units"] + [
                   "jason-release-approval-only.timer"],
               "allowed_user_units": prior["allowed_user_units"] + [
                   "jason-release-approval-only.service"]}
    policy,original,_=configure(monkeypatch,tmp_path,
                                policy=prior,old=prior,candidate=candidate)
    assert m.stage_for_candidate(CANDIDATE,BASE)=="STAGED_ALLOWED_ONLY"
    receipt=json.loads(m.ACTIVE.read_text())
    receipt["reviewed_delta"]["allowed_user_units"]=["jason-fake.service"]
    m.ACTIVE.write_text(json.dumps(receipt))
    with pytest.raises(m.MigrationRefused,match="unreviewed"):
        m.restore_for_baseline(BASE)
    assert policy.read_bytes() != original


def test_nested_reviewed_root_migration_restores_parent_receipt_exactly(monkeypatch, tmp_path):
    """Historical applied #1974 root policy remains durable under #1993 child."""
    from types import SimpleNamespace
    previous = source()
    first = source(new=True)
    second = {**first,
              "required_user_units": first["required_user_units"] + [
                  "jason-release-approval-only.timer"],
              "allowed_user_units": first["allowed_user_units"] + [
                  "jason-release-approval-only.service"]}
    policy, before, _ = configure(monkeypatch, tmp_path,
                                   policy=previous, old=previous, candidate=first)
    assert m.stage_for_candidate(CANDIDATE, BASE) == "STAGED_ALLOWED_ONLY"
    assert m.apply_for_candidate(CANDIDATE, BASE) == "APPLIED_REQUIRED_AFTER_HEALTH"
    parent_receipt=m.ACTIVE.read_bytes()
    parent_policy=policy.read_bytes()
    CHILD="c"*40
    sources={BASE:previous,CANDIDATE:first,CHILD:second}
    monkeypatch.setattr(m,"_source_policy",lambda sha:sources[sha])
    monkeypatch.setattr(m,"_reviewed_git_policy",lambda sha:sources[sha])
    monkeypatch.setattr(m.subprocess,"run",lambda *args,**kw:SimpleNamespace(returncode=0))
    (tmp_path/"production-control-state.json").write_text(json.dumps({
        "schema_version":"1.0","last_known_good":{"manifest":{"revision":CANDIDATE}}}))
    assert m.preview_exact_migration(CHILD,CANDIDATE)=="OWNER_CCC_REVIEWED_DELTA_ONLY"
    assert m.stage_for_candidate(CHILD,CANDIDATE)=="STAGED_ALLOWED_ONLY"
    child_receipt=json.loads(m.ACTIVE.read_text())
    assert child_receipt["prior_active_receipt_sha256"] == hashlib.sha256(parent_receipt).hexdigest()
    assert m.apply_for_candidate(CHILD,CANDIDATE)=="APPLIED_REQUIRED_AFTER_HEALTH"
    assert m.prepare_rollback(CANDIDATE)=="ROLLBACK_ALLOWED_STAGE"
    # Candidate-only user units must not remain installed at final restoration.
    assert m.complete_rollback(CANDIDATE)=="RESTORED"
    assert policy.read_bytes()==parent_policy
    assert m.ACTIVE.read_bytes()==parent_receipt
    assert (tmp_path/"recovery/approved-migrations"/("restored-"+CHILD+".json")).exists()
    assert before != policy.read_bytes()


@pytest.mark.parametrize("fault",["staged","bad_digest","bad_lineage","already_nested"])
def test_nested_reviewed_root_migration_rejects_untrusted_parent(monkeypatch,tmp_path,fault):
    from types import SimpleNamespace
    previous=source()
    first=source(new=True)
    second={**first,
            "required_user_units":first["required_user_units"]+["jason-release-approval-only.timer"],
            "allowed_user_units":first["allowed_user_units"]+["jason-release-approval-only.service"]}
    policy,_,_=configure(monkeypatch,tmp_path,policy=previous,old=previous,candidate=first)
    assert m.stage_for_candidate(CANDIDATE,BASE)=="STAGED_ALLOWED_ONLY"
    if fault!="staged":
        assert m.apply_for_candidate(CANDIDATE,BASE)=="APPLIED_REQUIRED_AFTER_HEALTH"
    parent=json.loads(m.ACTIVE.read_text())
    if fault=="bad_digest":parent["applied_sha256"]="0"*64
    if fault=="already_nested":parent["prior_active_receipt_base64"]="ZmFrZQ=="
    m.ACTIVE.write_text(json.dumps(parent))
    original=policy.read_bytes()
    CHILD="c"*40
    sources={BASE:previous,CANDIDATE:first,CHILD:second}
    monkeypatch.setattr(m,"_source_policy",lambda sha:sources[sha])
    monkeypatch.setattr(m,"_reviewed_git_policy",lambda sha:sources[sha])
    monkeypatch.setattr(m.subprocess,"run",
                        lambda *args,**kw:SimpleNamespace(
                            returncode=1 if fault=="bad_lineage" else 0))
    (tmp_path/"production-control-state.json").write_text(json.dumps({
        "schema_version":"1.0","last_known_good":{"manifest":{"revision":CANDIDATE}}}))
    with pytest.raises(m.MigrationRefused):
        m.preview_exact_migration(CHILD,CANDIDATE)
    with pytest.raises(m.MigrationRefused):
        m.stage_for_candidate(CHILD,CANDIDATE)
    assert policy.read_bytes()==original



def test_nested_root_rollback_rejects_parent_digest_before_policy_write(monkeypatch,tmp_path):
    from types import SimpleNamespace
    previous=source()
    first=source(new=True)
    second={**first,
            "required_user_units":first["required_user_units"]+["jason-release-approval-only.timer"],
            "allowed_user_units":first["allowed_user_units"]+["jason-release-approval-only.service"]}
    policy,_,_=configure(monkeypatch,tmp_path,policy=previous,old=previous,candidate=first)
    assert m.stage_for_candidate(CANDIDATE,BASE)=="STAGED_ALLOWED_ONLY"
    assert m.apply_for_candidate(CANDIDATE,BASE)=="APPLIED_REQUIRED_AFTER_HEALTH"
    child="c"*40
    sources={BASE:previous,CANDIDATE:first,child:second}
    monkeypatch.setattr(m,"_source_policy",lambda sha:sources[sha])
    monkeypatch.setattr(m,"_reviewed_git_policy",lambda sha:sources[sha])
    monkeypatch.setattr(m.subprocess,"run",lambda *args,**kw:SimpleNamespace(returncode=0))
    (tmp_path/"production-control-state.json").write_text(json.dumps({
        "schema_version":"1.0","last_known_good":{"manifest":{"revision":CANDIDATE}}}))
    assert m.stage_for_candidate(child,CANDIDATE)=="STAGED_ALLOWED_ONLY"
    assert m.apply_for_candidate(child,CANDIDATE)=="APPLIED_REQUIRED_AFTER_HEALTH"
    receipt=json.loads(m.ACTIVE.read_text())
    receipt["prior_active_receipt_sha256"]="0"*64
    m.ACTIVE.write_text(json.dumps(receipt))
    before=policy.read_bytes()
    with pytest.raises(m.MigrationRefused,match="prior root receipt checksum"):
        m.restore_for_baseline(CANDIDATE)
    assert policy.read_bytes()==before
    assert not (tmp_path/"recovery/approved-migrations"/("restored-"+child+".json")).exists()


def _held_pair_with_installed_units(monkeypatch,tmp_path):
    import types
    import pwd
    prior=source(new=True)
    candidate={**prior,
        'required_user_units':prior['required_user_units']+['jason-release-approval-only.timer'],
        'allowed_user_units':prior['allowed_user_units']+['jason-release-approval-only.service']}
    policy,original,_=configure(monkeypatch,tmp_path,policy=prior,old=prior,candidate=candidate)
    m.stage_for_candidate(CANDIDATE,BASE)
    m.apply_for_candidate(CANDIDATE,BASE)
    for name in ('jason-release-approval-only.timer','jason-release-approval-only.service'):
        (m.SYSTEMD_USER_UNITS/name).write_text('reviewed unit')
    monkeypatch.setattr(pwd,'getpwnam',lambda name:types.SimpleNamespace(pw_uid=1000))
    return policy,original


def test_held_offer_rollback_stops_and_removes_pair_before_old_host(monkeypatch,tmp_path):
    import subprocess
    policy,original=_held_pair_with_installed_units(monkeypatch,tmp_path)
    calls=[]
    def run(cmd,**kwargs):
        calls.append(cmd)
        if 'is-active' in cmd:return subprocess.CompletedProcess(cmd,3,stdout='inactive\n',stderr='')
        return subprocess.CompletedProcess(cmd,0,stdout='',stderr='')
    monkeypatch.setattr(m.subprocess,'run',run)
    assert m.prepare_rollback(BASE)=='ROLLBACK_ALLOWED_STAGE'
    assert not list(m.SYSTEMD_USER_UNITS.iterdir())
    assert any('disable' in cmd and '--now' in cmd for cmd in calls)
    assert all('jason-release-manager.timer' not in cmd for cmd in calls)
    assert m.complete_rollback(BASE)=='RESTORED'
    assert policy.read_bytes()==original


def test_held_offer_rollback_stop_failure_retains_files_and_audit(monkeypatch,tmp_path):
    import subprocess
    _held_pair_with_installed_units(monkeypatch,tmp_path)
    def fail(cmd,**kwargs):raise subprocess.CalledProcessError(1,cmd)
    monkeypatch.setattr(m.subprocess,'run',fail)
    with pytest.raises(m.MigrationRefused,match='cleanup failed'):m.prepare_rollback(BASE)
    assert len(list(m.SYSTEMD_USER_UNITS.iterdir()))==2
    assert json.loads(m.ACTIVE.read_text())['phase']=='rollback_prepared'
    with pytest.raises(m.MigrationRefused,match='still installed'):m.complete_rollback(BASE)


def test_held_offer_rollback_wrong_target_never_stops_units(monkeypatch,tmp_path):
    _held_pair_with_installed_units(monkeypatch,tmp_path)
    with patch.object(m.subprocess,'run') as run:
        with pytest.raises(m.MigrationRefused,match='rollback target'):
            m.prepare_rollback('c'*40)
        run.assert_not_called()
    assert len(list(m.SYSTEMD_USER_UNITS.iterdir()))==2


def test_pm_v2_shadow_exact_allowed_service_migrates_and_rolls_back_symmetrically(monkeypatch, tmp_path):
    """PM V2 persistence adds exactly one optional release-owned user service."""
    prior = source(new=True)
    prior["required_user_units"] += ["jason-release-approval-only.timer"]
    prior["allowed_user_units"] += ["jason-release-approval-only.service"]
    candidate = {key: (list(value) if isinstance(value, list) else value) for key, value in prior.items()}
    candidate["allowed_user_units"] = list(prior["allowed_user_units"]) + [
        "jason-pm-v2-shadow.service"
    ]
    policy, original, _ = configure(
        monkeypatch, tmp_path, policy=prior, old=prior, candidate=candidate
    )
    assert m.preview_exact_migration(CANDIDATE, BASE) == "OWNER_CCC_REVIEWED_DELTA_ONLY"
    assert policy.read_bytes() == original
    assert m.stage_for_candidate(CANDIDATE, BASE) == "STAGED_ALLOWED_ONLY"
    staged = json.loads(policy.read_text())
    assert "jason-pm-v2-shadow.service" in staged["allowed_user_units"]
    assert "jason-pm-v2-shadow.service" not in staged["required_user_units"]
    assert m.apply_for_candidate(CANDIDATE, BASE) == "APPLIED_REQUIRED_AFTER_HEALTH"
    final = json.loads(policy.read_text())
    assert "jason-pm-v2-shadow.service" in final["allowed_user_units"]
    receipt = json.loads(m.ACTIVE.read_text())
    assert receipt["reviewed_delta"] == {
        k: sorted(v) for k, v in m.APPROVED_PM_V2_SHADOW_DELTA.items()
    }
    assert m.prepare_rollback(BASE) == "ROLLBACK_ALLOWED_STAGE"
    service = m.SYSTEMD_USER_UNITS / "jason-pm-v2-shadow.service"
    service.write_text("reviewed candidate service")
    with pytest.raises(m.MigrationRefused, match="candidate user unit still installed"):
        m.complete_rollback(BASE)
    service.unlink()
    assert m.complete_rollback(BASE) == "RESTORED"
    assert policy.read_bytes() == original


def test_pm_v2_shadow_policy_plan_rejects_any_extra_unit(monkeypatch, tmp_path):
    prior = source(new=True)
    prior["required_user_units"] += ["jason-release-approval-only.timer"]
    prior["allowed_user_units"] += ["jason-release-approval-only.service"]
    candidate = {key: (list(value) if isinstance(value, list) else value) for key, value in prior.items()}
    candidate["allowed_user_units"] = list(prior["allowed_user_units"]) + [
        "jason-pm-v2-shadow.service", "jason-unreviewed.service"
    ]
    configure(monkeypatch, tmp_path, policy=prior, old=prior, candidate=candidate)
    with pytest.raises(m.MigrationRefused, match="unapproved desired-state"):
        m.preview_exact_migration(CANDIDATE, BASE)


def test_pmv31_exact_provider_health_units_staged_and_rollback_is_byte_exact(monkeypatch, tmp_path):
    old = source()
    candidate = source()
    delta = m.APPROVED_PM_V31_PROVIDER_HEALTH_DELTA
    for key, units in delta.items():
        candidate[key].extend(sorted(units))
    policy, before, _ = configure(monkeypatch, tmp_path, policy=old,
                                  candidate=candidate, old=old)
    assert m.preview_exact_migration(CANDIDATE, BASE) == "OWNER_CCC_REVIEWED_DELTA_ONLY"
    assert policy.read_bytes() == before
    assert m.stage_for_candidate(CANDIDATE, BASE) == "STAGED_ALLOWED_ONLY"
    staged = json.loads(policy.read_text())
    assert set(staged["allowed_system_units"]) == (
        set(old["allowed_system_units"]) | delta["allowed_system_units"])
    assert set(staged["required_system_units"]) == set(old["required_system_units"])
    assert m.apply_for_candidate(CANDIDATE, BASE) == "APPLIED_REQUIRED_AFTER_HEALTH"
    receipt = json.loads(m.ACTIVE.read_text())
    assert receipt["reviewed_delta"] == {k: sorted(v) for k, v in delta.items()}
    assert m.restore_for_baseline(BASE) == "RESTORED"
    assert policy.read_bytes() == before
    assert not m.ACTIVE.exists()


@pytest.mark.parametrize("unexpected", [
    "jason-unknown.service", "jason-isolated-provider-health-extra.timer",
])
def test_pmv31_extra_system_unit_denied_before_root_write(monkeypatch, tmp_path, unexpected):
    old = source()
    candidate = source()
    for key, units in m.APPROVED_PM_V31_PROVIDER_HEALTH_DELTA.items():
        candidate[key].extend(sorted(units))
    candidate["allowed_system_units"].append(unexpected)
    policy, before, _ = configure(monkeypatch, tmp_path, policy=old,
                                  candidate=candidate, old=old)
    with pytest.raises(m.MigrationRefused, match="unapproved desired-state"):
        m.preview_exact_migration(CANDIDATE, BASE)
    with pytest.raises(m.MigrationRefused, match="unapproved desired-state"):
        m.stage_for_candidate(CANDIDATE, BASE)
    assert policy.read_bytes() == before
    assert not m.ACTIVE.exists()


def test_pmv31_combined_with_historical_plan_denied(monkeypatch, tmp_path):
    old = source()
    candidate = source(new=True)
    for key, units in m.APPROVED_PM_V31_PROVIDER_HEALTH_DELTA.items():
        candidate[key].extend(sorted(units))
    policy, before, _ = configure(monkeypatch, tmp_path, policy=old,
                                  candidate=candidate, old=old)
    with pytest.raises(m.MigrationRefused, match="unapproved desired-state"):
        m.stage_for_candidate(CANDIDATE, BASE)
    assert policy.read_bytes() == before
    assert not m.ACTIVE.exists()


def test_pmv31_missing_one_unit_denied(monkeypatch, tmp_path):
    old = source()
    candidate = source()
    candidate["allowed_system_units"].append("jason-isolated-provider-health.service")
    policy, before, _ = configure(monkeypatch, tmp_path, policy=old,
                                  candidate=candidate, old=old)
    with pytest.raises(m.MigrationRefused, match="unapproved desired-state"):
        m.preview_exact_migration(CANDIDATE, BASE)
    assert policy.read_bytes() == before
    assert not m.ACTIVE.exists()


def _three_level_pmv31_chain(monkeypatch, tmp_path):
    """Set up the exact prior plans: #1974, held Teams pair, PMv3.1 pair."""
    import base64
    from types import SimpleNamespace

    baseline = source()
    authority = source(new=True)
    held = {
        **authority,
        "required_user_units": authority["required_user_units"] +
        ["jason-release-approval-only.timer"],
        "allowed_user_units": authority["allowed_user_units"] +
        ["jason-release-approval-only.service"],
    }
    pmv31 = {
        **held,
        "allowed_system_units": held["allowed_system_units"] +
        sorted(m.APPROVED_PM_V31_PROVIDER_HEALTH_DELTA["allowed_system_units"]),
    }
    first = "b" * 40
    second = "c" * 40
    third = "d" * 40
    sources = {BASE: baseline, first: authority, second: held, third: pmv31}
    policy, original, _ = configure(
        monkeypatch, tmp_path, policy=baseline, old=baseline, candidate=authority,
    )
    monkeypatch.setattr(m, "_source_policy", lambda sha: sources[sha])
    monkeypatch.setattr(m, "_reviewed_git_policy", lambda sha: sources[sha])
    monkeypatch.setattr(
        m.subprocess, "run",
        lambda *args, **kw: SimpleNamespace(returncode=0),
    )

    def set_lkg(sha):
        (tmp_path / "production-control-state.json").write_text(json.dumps({
            "schema_version": "1.0",
            "last_known_good": {"manifest": {"revision": sha}},
        }))

    set_lkg(BASE)
    assert m.stage_for_candidate(first, BASE) == "STAGED_ALLOWED_ONLY"
    assert m.apply_for_candidate(first, BASE) == "APPLIED_REQUIRED_AFTER_HEALTH"
    first_bytes = m.ACTIVE.read_bytes()
    first_policy = policy.read_bytes()
    set_lkg(first)
    assert m.stage_for_candidate(second, first) == "STAGED_ALLOWED_ONLY"
    assert m.apply_for_candidate(second, first) == "APPLIED_REQUIRED_AFTER_HEALTH"
    second_bytes = m.ACTIVE.read_bytes()
    second_policy = policy.read_bytes()
    parent = json.loads(second_bytes)
    assert base64.b64decode(parent["prior_active_receipt_base64"]) == first_bytes
    set_lkg(second)
    return policy, original, first_policy, second_policy, first_bytes, second_bytes, (first,second,third), set_lkg


def test_pmv31_reviewed_third_migration_preserves_every_parent_ledger_byte(monkeypatch,tmp_path):
    import base64
    policy,original,first_policy,second_policy,first_bytes,second_bytes,shas,lkg = (
        _three_level_pmv31_chain(monkeypatch,tmp_path))
    first,second,third=shas
    assert m.preview_exact_migration(third, second) == "OWNER_CCC_REVIEWED_DELTA_ONLY"
    assert m.stage_for_candidate(third, second) == "STAGED_ALLOWED_ONLY"
    receipt = json.loads(m.ACTIVE.read_text())
    assert receipt["prior_active_receipt_sha256"] == hashlib.sha256(second_bytes).hexdigest()
    assert base64.b64decode(receipt["prior_active_receipt_base64"]) == second_bytes
    assert m.apply_for_candidate(third, second) == "APPLIED_REQUIRED_AFTER_HEALTH"
    assert m.restore_for_baseline(second) == "RESTORED"
    assert policy.read_bytes() == second_policy
    assert m.ACTIVE.read_bytes() == second_bytes
    lkg(first)
    assert m.restore_for_baseline(first) == "RESTORED"
    assert policy.read_bytes() == first_policy
    assert m.ACTIVE.read_bytes() == first_bytes
    lkg(BASE)
    assert m.restore_for_baseline(BASE) == "RESTORED"
    assert policy.read_bytes() == original
    assert not m.ACTIVE.exists()
    for sha in (first, second, third):
        archived = m.LEDGER_DIR / ("restored-" + sha + ".json")
        assert archived.is_file() and json.loads(archived.read_text())["phase"]=="restored"


@pytest.mark.parametrize("fault",[
    "parent_digest", "grandparent_digest", "grandparent_phase",
    "grandparent_reviewed_delta", "partial_parent", "unexpected_depth",
])
def test_pmv31_rejects_tampered_three_level_ancestors_before_policy_write(
    monkeypatch, tmp_path, fault
):
    import base64
    policy,_,_,second_policy,_,_,shas,_ = (
        _three_level_pmv31_chain(monkeypatch,tmp_path))
    first,second,third = shas
    receipt = json.loads(m.ACTIVE.read_text())
    if fault == "parent_digest":
        receipt["applied_sha256"] = "0" * 64
    elif fault == "partial_parent":
        del receipt["prior_active_receipt_sha256"]
    elif fault == "unexpected_depth":
        # A third predecessor is outside the bounded review.
        inner = json.loads(base64.b64decode(receipt["prior_active_receipt_base64"]))
        inner["prior_active_receipt_base64"] = base64.b64encode(b"{}").decode("ascii")
        inner["prior_active_receipt_sha256"] = hashlib.sha256(b"{}").hexdigest()
        raw = (json.dumps(inner, sort_keys=True, indent=2)+"\n").encode()
        receipt["prior_active_receipt_base64"] = base64.b64encode(raw).decode("ascii")
        receipt["prior_active_receipt_sha256"] = hashlib.sha256(raw).hexdigest()
    else:
        inner = json.loads(base64.b64decode(receipt["prior_active_receipt_base64"]))
        if fault == "grandparent_digest":
            inner["original_sha256"] = "0"*64
        elif fault == "grandparent_phase":
            inner["phase"] = "staged"
        elif fault == "grandparent_reviewed_delta":
            inner["reviewed_delta"]["allowed_system_units"] = ["jason-unknown.service"]
        raw=(json.dumps(inner,sort_keys=True,indent=2)+"\n").encode()
        receipt["prior_active_receipt_base64"]=base64.b64encode(raw).decode("ascii")
        receipt["prior_active_receipt_sha256"]=hashlib.sha256(raw).hexdigest()
    m.ACTIVE.write_text(json.dumps(receipt))
    before = policy.read_bytes()
    with pytest.raises(m.MigrationRefused):
        m.preview_exact_migration(third, second)
    with pytest.raises(m.MigrationRefused):
        m.stage_for_candidate(third, second)
    assert policy.read_bytes() == before == second_policy


@pytest.mark.parametrize("fault", ["parent_digest","grandparent_digest","grandparent_phase"])
def test_pmv31_third_migration_rejects_tamper_on_rollback_without_policy_write(
    monkeypatch, tmp_path, fault,
):
    import base64
    policy,_,_,_,_,_,shas,_=_three_level_pmv31_chain(monkeypatch,tmp_path)
    _,second,third=shas
    assert m.stage_for_candidate(third,second)=="STAGED_ALLOWED_ONLY"
    assert m.apply_for_candidate(third,second)=="APPLIED_REQUIRED_AFTER_HEALTH"
    receipt=json.loads(m.ACTIVE.read_text())
    if fault=="parent_digest":
        receipt["prior_active_receipt_sha256"]="0"*64
    else:
        parent=json.loads(base64.b64decode(receipt["prior_active_receipt_base64"]))
        inner=json.loads(base64.b64decode(parent["prior_active_receipt_base64"]))
        if fault=="grandparent_digest":
            inner["original_sha256"]="0"*64
        else:
            inner["phase"]="staged"
        inner_bytes=(json.dumps(inner,sort_keys=True,indent=2)+"\n").encode()
        parent["prior_active_receipt_base64"]=base64.b64encode(inner_bytes).decode("ascii")
        parent["prior_active_receipt_sha256"]=hashlib.sha256(inner_bytes).hexdigest()
        parent_bytes=(json.dumps(parent,sort_keys=True,indent=2)+"\n").encode()
        receipt["prior_active_receipt_base64"]=base64.b64encode(parent_bytes).decode("ascii")
        receipt["prior_active_receipt_sha256"]=hashlib.sha256(parent_bytes).hexdigest()
    m.ACTIVE.write_text(json.dumps(receipt))
    applied=policy.read_bytes()
    with pytest.raises(m.MigrationRefused):
        m.restore_for_baseline(second)
    assert policy.read_bytes()==applied
    assert not (m.LEDGER_DIR / ("restored-"+third+".json")).exists()



def test_ccc_retirement_stages_old_allowances_then_removes_exact_pair(monkeypatch, tmp_path):
    old = source()
    old["allowed_system_units"].extend(["jason-ccc.timer", "jason-ccc.service"])
    candidate = source()
    policy, original, _ = configure(
        monkeypatch, tmp_path, policy=old, old=old, candidate=candidate,
    )
    assert m.preview_exact_migration(CANDIDATE, BASE) == (
        "OWNER_EXACT_RELEASE_REVIEWED_CCC_RETIREMENT"
    )
    assert policy.read_bytes() == original
    assert m.stage_for_candidate(CANDIDATE, BASE) == "STAGED_ALLOWED_ONLY"
    assert policy.read_bytes() == original
    receipt = json.loads(m.ACTIVE.read_text())
    assert receipt["authorized_by"] == "exact_owner_bound_native_release_ccc_retirement"
    assert receipt["reviewed_delta"] == {
        name: sorted(values) for name, values in m.APPROVED_CCC_RETIREMENT_DELTA.items()
    }
    assert m.apply_for_candidate(CANDIDATE, BASE) == "APPLIED_REQUIRED_AFTER_HEALTH"
    applied = json.loads(policy.read_text())
    assert not set(("jason-ccc.timer", "jason-ccc.service")).intersection(
        applied["allowed_system_units"]
    )
    assert set(applied["allowed_system_units"]) == set(candidate["allowed_system_units"])
    # Native rollback re-admits OLD units before the host reinstalls them.
    assert m.prepare_rollback(BASE) == "ROLLBACK_ALLOWED_STAGE"
    assert policy.read_bytes() == original
    assert m.complete_rollback(BASE) == "RESTORED"
    assert policy.read_bytes() == original
    assert not m.ACTIVE.exists()


@pytest.mark.parametrize("removed", [
    ["jason-ccc.service"], ["jason-ccc.timer"],
    ["jason-ccc.timer", "jason-ccc.service", "jason-openclaw-authority-health.service"],
])
def test_unreviewed_or_partial_ccc_removal_fails_closed(monkeypatch, tmp_path, removed):
    old = source()
    old["allowed_system_units"].extend([
        "jason-ccc.timer", "jason-ccc.service",
    ])
    candidate = source()
    for value in set(old["allowed_system_units"]) - set(removed):
        if value not in candidate["allowed_system_units"]:
            candidate["allowed_system_units"].append(value)
    candidate["allowed_system_units"] = [
        v for v in candidate["allowed_system_units"] if v not in removed
    ]
    policy, before, _ = configure(monkeypatch, tmp_path, policy=old, old=old,
                                  candidate=candidate)
    with pytest.raises(m.MigrationRefused, match="unapproved desired-state unit removal"):
        m.stage_for_candidate(CANDIDATE, BASE)
    assert policy.read_bytes() == before
    assert not m.ACTIVE.exists()


def test_v31_root_migration_uses_exact_owner_transaction_without_ccc(monkeypatch, tmp_path):
    root = tmp_path / "root"
    (root / "records").mkdir(parents=True)
    path = root / "records" / ("release-" + CANDIDATE[:16] + ".json")
    policy = {
        "schema_version": "3.1", "policy_mode": "owner_reviewed",
        "organization_id": "aot", "capability": "release.production.approve",
        "high_impact_review": {
            "owner_exact_sha_required": True,
            "protected_release_gates_unchanged": True,
            "authenticated_entra_owner_decision_required": True,
            "independent_native_release_health_required": True,
        },
    }
    raw = (json.dumps(policy, sort_keys=True) + "\n").encode()
    manifest = {
        "candidate_sha": CANDIDATE,
        "rollback_sha": BASE,
        "mobile_release_approval_policy_digest": "sha256:" + hashlib.sha256(raw).hexdigest(),
    }
    digest_manifest = hashlib.sha256(json.dumps(
        manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode()).hexdigest()
    scope = "c" * 64
    record = {
        "state": "production", "risk_profile": "production_control_core",
        "owner_approval": {
            "approved": True, "candidate_sha": CANDIDATE,
            "source": "explicit_owner_instruction",
            "transaction_binding": {
                "candidate_sha": CANDIDATE, "rollback_sha": BASE,
                "scope_sha256": scope, "manifest_sha256": digest_manifest,
            },
        },
        "manual_scope_review": {
            "candidate_sha": CANDIDATE, "baseline_sha": BASE,
            "scope_sha256": scope,
        },
        "release_manifest": manifest,
    }
    control = {
        "schema_version": "1.0",
        "last_known_good": {"manifest": {"revision": BASE, "complete": True}},
        "circuit_breaker": {"state": "closed"},
    }
    monkeypatch.setattr(m, "ROOT", root)
    monkeypatch.setattr(m, "_root_only", lambda path: Path(path).read_bytes())
    monkeypatch.setattr(m.subprocess, "check_output", lambda *a, **kw: raw)
    def write():
        path.write_text(json.dumps(record))
        (root / "production-control-state.json").write_text(json.dumps(control))
    write()
    # No historical CCC file is present or required.
    m._approval(CANDIDATE, BASE)
    for field, value in (
        ("scope_sha256", "f" * 64),
        ("manifest_sha256", "f" * 64),
        ("rollback_sha", "d" * 40),
    ):
        good = record["owner_approval"]["transaction_binding"][field]
        record["owner_approval"]["transaction_binding"][field] = value
        write()
        with pytest.raises(m.MigrationRefused, match="Owner-bound"):
            m._approval(CANDIDATE, BASE)
        record["owner_approval"]["transaction_binding"][field] = good
    record["owner_approval"]["approved"] = False
    write()
    with pytest.raises(m.MigrationRefused, match="exact owner-approved"):
        m._approval(CANDIDATE, BASE)
    record["owner_approval"]["approved"] = True
    wrong = dict(policy)
    wrong["high_impact_review"] = dict(policy["high_impact_review"])
    wrong["high_impact_review"]["authenticated_entra_owner_decision_required"] = False
    monkeypatch.setattr(
        m.subprocess, "check_output",
        lambda *a, **kw: (json.dumps(wrong, sort_keys=True) + "\n").encode(),
    )
    write()
    with pytest.raises(m.MigrationRefused, match="Owner-bound"):
        m._approval(CANDIDATE, BASE)
    monkeypatch.setattr(m.subprocess, "check_output", lambda *a, **kw: raw)
    control["circuit_breaker"]["state"] = "open"
    write()
    with pytest.raises(m.MigrationRefused, match="breaker"):
        m._approval(CANDIDATE, BASE)
