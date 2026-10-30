"""Bounded auto-revalidation orchestration: no root writes or false PASS."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


MODULE = Path(__file__).resolve().parents[1] / "release_breaker_recovery_manager.py"
spec = importlib.util.spec_from_file_location("release_breaker_recovery_manager", MODULE)
recovery = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = recovery
spec.loader.exec_module(recovery)
NOW = datetime(2026, 10, 19, 14, 0, tzinfo=timezone.utc)
SHA = "a" * 40
POLICY = json.loads(
    (Path(__file__).resolve().parents[2] /
     "config/release-breaker-self-recovery-policy.json").read_text()
)


def evidence(*, source=recovery.OPEN_SOURCE, reason=recovery.OPEN_REASON, revision=SHA):
    control = {
        "schema_version": "1.0",
        "circuit_breaker": {
            "state": "open",
            "source": source, "reason": reason,
            "opened_at": (NOW - timedelta(minutes=8)).isoformat(),
        },
        "last_known_good": {"manifest": {
            "revision": revision, "complete": True,
            "runtime_image_id": "sha256:" + "b" * 64,
            "mcp_image_id": "sha256:" + "c" * 64,
        }},
    }
    drift = {
        "schema_version": "1.0", "status": "pass", "problems": [],
        "observed_at": NOW.isoformat(),
    }
    return control, drift


def ready(control=None, drift=None):
    control, drift = (control, drift) if control is not None else evidence()
    state = {}
    for seconds in (0, 20, 40):
        at = NOW + timedelta(seconds=seconds)
        drift["observed_at"] = at.isoformat()
        state = recovery.decision(control, drift, state, POLICY, at)
    return state


def test_requires_three_distinct_root_observations_not_three_reads_of_one():
    control, drift = evidence()
    result = recovery.decision(control, drift, {}, POLICY, NOW)
    assert result["next_action"] == "accumulate_distinct_root_drift_passes"
    assert len(result["clean_observations"]) == 1
    for step in (5, 15, 24):
        result = recovery.decision(control, drift, result, POLICY, NOW + timedelta(seconds=step))
        assert len(result["clean_observations"]) == 1
        assert result["status"] == "blocked"
    assert ready()["status"] == "ready_for_governed_request"


@pytest.mark.parametrize("case", [
    "nonwatchdog", "release_failure", "still_dirty", "stale", "preopen",
    "future", "disabled", "early", "wrong_revision", "incomplete",
])
def test_nonqualified_states_never_request_root(case):
    control, drift = evidence()
    policy = dict(POLICY)
    time = NOW
    if case == "nonwatchdog":
        control["circuit_breaker"]["source"] = "release_manager"
    elif case == "release_failure":
        control["circuit_breaker"]["reason"] = "rollback_failed"
    elif case == "still_dirty":
        drift["status"], drift["problems"] = "drift", [{"kind":"failed_unit"}]
    elif case == "stale":
        drift["observed_at"] = (NOW-timedelta(minutes=4)).isoformat()
    elif case == "preopen":
        drift["observed_at"] = (NOW-timedelta(minutes=9)).isoformat()
    elif case == "future":
        drift["observed_at"] = (NOW+timedelta(hours=1)).isoformat()
    elif case == "disabled":
        policy["enabled"] = False
    elif case == "early":
        control["circuit_breaker"]["opened_at"] = (NOW-timedelta(seconds=12)).isoformat()
    elif case == "wrong_revision":
        control["last_known_good"]["manifest"]["revision"] = "bad"
    elif case == "incomplete":
        control["last_known_good"]["manifest"]["complete"] = False
    if case in {"wrong_revision","incomplete"}:
        with pytest.raises(ValueError, match="last-known-good"):
            recovery.decision(control,drift,{},policy,time)
    else:
        result=recovery.decision(control,drift,{},policy,time)
        assert result["status"] != "ready_for_governed_request"


def test_intermittent_failed_drift_clears_observations():
    control, drift = evidence()
    first = recovery.decision(control,drift,{},POLICY,NOW)
    drift["status"],drift["problems"] = "fail",[{"kind":"user_unit"}]
    failed = recovery.decision(control,drift,first,POLICY,NOW+timedelta(seconds=20))
    assert failed["clean_observations"] == []
    drift["status"],drift["problems"] = "pass",[]
    drift["observed_at"]=(NOW+timedelta(seconds=40)).isoformat()
    fresh=recovery.decision(control,drift,failed,POLICY,NOW+timedelta(seconds=40))
    assert len(fresh["clean_observations"])==1


def test_attempt_budget_survives_repeated_scheduler_runs_and_pending_root_result():
    control, drift = evidence()
    first=ready(control,drift)
    assert first["status"]=="ready_for_governed_request"
    first["attempts"].append({
        "requested_at":(NOW+timedelta(seconds=40)).isoformat(),
        "revision":SHA, "result":"root_revalidation_rejected",
    })
    drift["observed_at"]=(NOW+timedelta(seconds=70)).isoformat()
    too_soon=recovery.decision(control,drift,first,POLICY,NOW+timedelta(seconds=70))
    assert too_soon["next_action"]=="wait_for_next_bounded_attempt"
    drift["observed_at"]=(NOW+timedelta(seconds=360)).isoformat()
    later=recovery.decision(control,drift,too_soon,POLICY,NOW+timedelta(seconds=360))
    assert later["status"]=="ready_for_governed_request"
    later["attempts"].append({
        "requested_at":(NOW+timedelta(seconds=360)).isoformat(),
        "revision":SHA, "result":"root_revalidation_rejected",
    })
    exhausted=recovery.decision(control,drift,later,POLICY,NOW+timedelta(seconds=380))
    assert exhausted["next_action"]=="operator_review_recovery_attempt_budget_exhausted"
    assert len(exhausted["attempts"]) == 2


def test_corrupt_or_ambiguous_tracker_cannot_reset_used_authority():
    control,drift=evidence()
    for attempts in ("not an array", [{"requested_at":"bad", "revision":SHA}]*5,
                     [{"requested_at":"bad", "revision":"b"*40}]):
        previous=ready(control,drift)
        previous["attempts"]=attempts
        with pytest.raises(ValueError,match="history"):
            recovery.decision(control,drift,previous,POLICY,NOW+timedelta(seconds=60))


def test_breaker_identity_change_resets_samples_and_budget_but_not_existing_breaker():
    control,drift=evidence()
    prior=ready(control,drift)
    prior["attempts"]=[{"requested_at":NOW.isoformat(),"revision":SHA}]
    next_control,next_drift=evidence()
    next_control["circuit_breaker"]["opened_at"]=(NOW-timedelta(minutes=2)).isoformat()
    fresh=recovery.decision(next_control,next_drift,prior,POLICY,NOW)
    assert fresh["status"]=="blocked"
    assert len(fresh["clean_observations"])==1
    assert fresh["attempts"]==[]


def test_closed_breaker_never_calls_any_root_transition():
    control,drift=evidence()
    control["circuit_breaker"]["state"]="closed"
    result=recovery.decision(control,drift,{},POLICY,NOW)
    assert result["status"]=="already_closed"
    assert result["next_action"]=="none"


def test_pinned_policy_rejects_untrusted_branch_and_invalid_bounds(tmp_path):
    repo=tmp_path/"repo";repo.mkdir()
    (repo/"config").mkdir()
    source=Path(__file__).resolve().parents[2]/recovery.POLICY_PATH
    policy_file=repo/recovery.POLICY_PATH
    policy_file.write_text(source.read_text())
    def git(*args):
        return subprocess.run(["git",*args],cwd=repo,text=True,
                              capture_output=True,check=True).stdout.strip()
    git("init","-b","main")
    git("config","user.name","Test")
    git("config","user.email","fixture@example.invalid")
    git("add",".");git("commit","-m","fixture")
    head=git("rev-parse","HEAD")
    assert recovery.load_pinned_policy(repo,head)==POLICY
    with pytest.raises(ValueError,match="differs from LKG"):
        recovery.load_pinned_policy(repo,"b"*40)
    policy=dict(POLICY);policy["minimum_distinct_clean_observations"]=1
    policy_file.write_text(json.dumps(policy))
    git("add",".");git("commit","-m","invalid pinned policy")
    with pytest.raises(ValueError,match="policy bound"):
        recovery.load_pinned_policy(repo,git("rev-parse","HEAD"))


def test_main_persists_permit_before_authorized_root_call_and_checks_closeout(tmp_path, monkeypatch):
    repo=tmp_path/"repo";repo.mkdir();(repo/"config").mkdir()
    (repo/recovery.POLICY_PATH).write_text((Path(__file__).resolve().parents[2]/recovery.POLICY_PATH).read_text())
    def git(*args):
        return subprocess.run(["git",*args],cwd=repo,capture_output=True,text=True,check=True).stdout.strip()
    git("init","-b","main");git("config","user.name","Fixture")
    git("config","user.email","fixture@example.invalid")
    git("add",".");git("commit","-m","fixture")
    sha=git("rev-parse","HEAD")
    root=tmp_path/"release"/"protected-readback";root.mkdir(parents=True)
    control,drift=evidence(revision=sha)
    control_path=root/"production-control-state.json"
    drift_path=root/"production-drift.json"
    control_path.write_text(json.dumps(control))
    drift_path.write_text(json.dumps(drift))
    spool=tmp_path/"spool";spool.mkdir()
    track=spool/"release-breaker-recovery-state.json"
    calls=[]
    def native(state_root,revision):
        calls.append(revision)
        persisted=json.loads(track.read_text())
        assert persisted["status"]=="pending_root_verification"
        assert len(persisted["attempts"])==1
        value=json.loads(control_path.read_text())
        value["circuit_breaker"]={"state":"closed","revalidated_revision":sha}
        control_path.write_text(json.dumps(value))
        return value
    monkeypatch.setattr(recovery,"native_revalidation_preflight",lambda *args: None)
    monkeypatch.setattr(recovery,"native_root_transition",native)
    monkeypatch.setattr(recovery,"transaction_busy",lambda path: False)
    monkeypatch.setattr(sys,"argv",["recovery","--repo",str(repo),
                                   "--spool",str(spool),"--release-state",str(root.parent)])
    for i,seconds in enumerate((0,20,40)):
        at=NOW+timedelta(seconds=seconds)
        drift_path.write_text(json.dumps({**drift,"observed_at":at.isoformat()}))
        monkeypatch.setattr(recovery,"utcnow",lambda at=at: at)
        assert recovery.main()==0
    state=json.loads(track.read_text())
    assert state["status"]=="root_verified_closed"
    assert state["attempts"][0]["result"]=="root_verified_closed"
    assert len(calls)==1 and calls[0]==sha
    assert track.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize(('detail', 'expected'), [
    ('governed root release transition rejected: ValueError: immutable last-known-good mismatch: runtime_image_id',
     'root_lkg_fingerprint_mismatch'),
    ('governed root release transition rejected: ValueError: production drift is not clean',
     'root_independent_drift_not_clean'),
    ('governed root release transition rejected: ValueError: independent production drift refresh did not pass',
     'root_drift_refresh_failed'),
    ('governed root release transition rejected: PermissionError: root-only mode-0600 file required',
     'root_protected_file_invalid'),
    ('governed root release transition rejected: PermissionError: invalid requester ownership',
     'root_request_ownership_rejected'),
    ('governed root release transition rejected: ValueError: root-owned drift evidence is stale',
     'root_drift_stale'),
    ('protected release-state snapshot stale: production-control-state.json',
     'protected_readback_stale'),
    ('governed root transition result timed out', 'root_transition_result_timeout'),
    ('root-governed breaker transition succeeded but readback did not converge',
     'root_closeout_readback_not_converged'),
    ('production circuit breaker is open; authoritative health revalidation failed: timer inactive',
     'production_manifest_precheck_failed'),
    ('governed root release transition rejected: UnknownNewFailure /tokens/must-not-persist',
     'root_transition_rejected_other'),
    ('unknown secret JWT=not-allowed path=/etc/secure', 'unclassified_root_revalidation_failure'),
])
def test_revalidation_failure_classification_is_whitelisted(detail, expected):
    category = recovery.classify_root_revalidation_error(RuntimeError(detail))
    assert category == expected
    assert detail not in category
    assert 'secret' not in category and 'JWT' not in category


def test_root_rejection_does_not_replay_same_permit_or_claim_pass(tmp_path, monkeypatch):
    repo=tmp_path/"repo";repo.mkdir();(repo/"config").mkdir()
    (repo/recovery.POLICY_PATH).write_text((Path(__file__).resolve().parents[2]/recovery.POLICY_PATH).read_text())
    def git(*args):
        return subprocess.run(["git",*args],cwd=repo,capture_output=True,text=True,check=True).stdout.strip()
    git("init","-b","main");git("config","user.name","Fixture")
    git("config","user.email","fixture@example.invalid")
    git("add",".");git("commit","-m","fixture")
    sha=git("rev-parse","HEAD")
    root=tmp_path/"release"/"protected-readback";root.mkdir(parents=True)
    control,drift=evidence(revision=sha)
    (root/"production-control-state.json").write_text(json.dumps(control))
    spool=tmp_path/"spool";spool.mkdir()
    track=spool/"release-breaker-recovery-state.json"
    calls=[]
    def reject(*args):
        calls.append(True)
        assert json.loads(track.read_text())["attempts"]
        raise RuntimeError(
            "governed root release transition rejected: "
            "ValueError: immutable last-known-good mismatch: runtime_image_id; SECRET=DONT_STORE"
        )
    monkeypatch.setattr(recovery,"native_revalidation_preflight",lambda *args: None)
    monkeypatch.setattr(recovery,"native_root_transition",reject)
    monkeypatch.setattr(recovery,"transaction_busy",lambda path: False)
    monkeypatch.setattr(sys,"argv",["recovery","--repo",str(repo),
                                   "--spool",str(spool),"--release-state",str(root.parent)])
    for seconds in (0,20,40,50):
        at=NOW+timedelta(seconds=seconds)
        (root/"production-drift.json").write_text(json.dumps({**drift,"observed_at":at.isoformat()}))
        monkeypatch.setattr(recovery,"utcnow",lambda at=at: at)
        assert recovery.main()==0
    result=json.loads(track.read_text())
    assert len(calls)==1
    assert result["status"]=="blocked"
    assert result["attempts"][0]["result"]=="root_revalidation_rejected"
    assert result["attempts"][0]["failure_class"]=="root_lkg_fingerprint_mismatch"
    assert "SECRET" not in track.read_text()
    assert result["last_revalidation_attempt"]["failure_class"]=="root_lkg_fingerprint_mismatch"
    assert result["next_action"]=="wait_for_next_bounded_attempt"


def test_recovery_stage_defers_to_existing_live_production_transaction(monkeypatch,tmp_path):
    repo=tmp_path/"repo";repo.mkdir();(repo/"config").mkdir()
    source=Path(__file__).resolve().parents[2]/recovery.POLICY_PATH
    (repo/recovery.POLICY_PATH).write_text(source.read_text())
    def git(*args):
        return subprocess.run(["git",*args],cwd=repo,check=True,
                              text=True,capture_output=True).stdout.strip()
    git("init","-b","main");git("config","user.name","Fixture")
    git("config","user.email","test@example.invalid");git("add",".");git("commit","-m","fixture")
    sha=git("rev-parse","HEAD")
    root=tmp_path/"release"/"protected-readback";root.mkdir(parents=True)
    control,drift=evidence(revision=sha)
    (root/"production-control-state.json").write_text(json.dumps(control))
    (root/"production-drift.json").write_text(json.dumps(drift))
    spool=tmp_path/"spool";spool.mkdir()
    prior=ready(control,drift)
    track=spool/"release-breaker-recovery-state.json"
    prior["attempts"]=[]
    track.write_text(json.dumps(prior))
    monkeypatch.setattr(recovery,"transaction_busy",lambda path: True)
    monkeypatch.setattr(recovery,"native_root_transition",lambda *args: pytest.fail("must not request root while transaction active"))
    monkeypatch.setattr(sys,"argv",["recovery","--repo",str(repo),
                                   "--spool",str(spool),"--release-state",str(root.parent)])
    at=NOW+timedelta(seconds=60)
    (root/"production-drift.json").write_text(json.dumps({**drift,"observed_at":at.isoformat()}))
    monkeypatch.setattr(recovery,"utcnow",lambda:at)
    assert recovery.main()==0
    result=json.loads(track.read_text())
    assert result["next_action"]=="wait_for_existing_production_transaction"
    assert result["attempts"]==[]


def test_temporary_release_source_mismatch_is_visible_hold_not_failed_user_unit(tmp_path,monkeypatch):
    repo=tmp_path/"repo";repo.mkdir();(repo/"config").mkdir()
    source=Path(__file__).resolve().parents[2]/recovery.POLICY_PATH
    (repo/recovery.POLICY_PATH).write_text(source.read_text())
    def git(*args):
        return subprocess.run(["git",*args],cwd=repo,check=True,
                              text=True,capture_output=True).stdout.strip()
    git("init","-b","main");git("config","user.name","Fixture")
    git("config","user.email","test@example.invalid");git("add",".");git("commit","-m","fixture")
    root=tmp_path/"release"/"protected-readback";root.mkdir(parents=True)
    control,drift=evidence(revision="f"*40)
    (root/"production-control-state.json").write_text(json.dumps(control))
    (root/"production-drift.json").write_text(json.dumps(drift))
    spool=tmp_path/"spool";spool.mkdir()
    monkeypatch.setattr(sys,"argv",["recovery","--repo",str(repo),
                                   "--spool",str(spool),"--release-state",str(root.parent)])
    monkeypatch.setattr(recovery,"utcnow",lambda:NOW)
    monkeypatch.setattr(recovery,"native_root_transition",
                        lambda *args: pytest.fail("root must not be called on mismatched LKG"))
    assert recovery.main()==0
    assert not (spool/"release-breaker-recovery-state.json").exists()


def test_closed_precommissioned_breaker_never_creates_failed_worker_unit(tmp_path, monkeypatch):
    """No LKG yet on a new install is safe if the protected breaker is closed."""
    repo=tmp_path/"repo";repo.mkdir()
    root=tmp_path/"release"/"protected-readback";root.mkdir(parents=True)
    (root/"production-control-state.json").write_text(json.dumps({
        "schema_version":"1.0","circuit_breaker":{"state":"closed"},
        "last_known_good":None,
    }))
    (root/"production-drift.json").write_text(json.dumps({
        "schema_version":"1.0","status":"pass","problems":[],
        "observed_at":NOW.isoformat(),
    }))
    spool=tmp_path/"spool";spool.mkdir()
    monkeypatch.setattr(recovery,"utcnow",lambda:NOW)
    monkeypatch.setattr(recovery,"native_root_transition",
                        lambda *args:pytest.fail("closed breaker must not request root"))
    monkeypatch.setattr(recovery,"load_pinned_policy",
                        lambda *args:pytest.fail("closed breaker does not need policy"))
    monkeypatch.setattr(sys,"argv",["recovery","--repo",str(repo),
                                   "--spool",str(spool),"--release-state",str(root.parent)])
    assert recovery.main()==0
    tracker=json.loads((spool/"release-breaker-recovery-state.json").read_text())
    assert tracker["status"]=="already_closed"
    assert tracker["next_action"]=="none"


def test_closed_breaker_preserves_recovery_attempt_receipt(tmp_path, monkeypatch):
    repo=tmp_path/"repo";repo.mkdir()
    root=tmp_path/"release"/"protected-readback";root.mkdir(parents=True)
    (root/"production-control-state.json").write_text(json.dumps({
        "schema_version":"1.0","circuit_breaker":{
            "state":"closed","reason":"root_verified_revalidate",
            "revalidated_revision":SHA},
        "last_known_good":{"manifest":{"revision":SHA,"complete":True}},
    }))
    (root/"production-drift.json").write_text(json.dumps({
        "schema_version":"1.0","status":"pass","problems":[],
        "observed_at":NOW.isoformat(),
    }))
    spool=tmp_path/"spool";spool.mkdir()
    receipt={"revision":SHA,"requested_at":NOW.isoformat(),
             "result":"root_verified_closed"}
    (spool/"release-breaker-recovery-state.json").write_text(json.dumps({
        "schema_version":"1.0","last_revalidation_attempt":receipt,
    }))
    monkeypatch.setattr(sys,"argv",["recovery","--repo",str(repo),
                                   "--spool",str(spool),"--release-state",str(root.parent)])
    monkeypatch.setattr(recovery,"utcnow",lambda:NOW)
    assert recovery.main()==0
    data=json.loads((spool/"release-breaker-recovery-state.json").read_text())
    assert data["last_revalidation_attempt"]==receipt
    assert data["status"]=="already_closed"


def test_preflight_failure_is_not_a_governed_root_attempt(tmp_path, monkeypatch):
    """A local manifest failure must not exhaust root retry authority."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "config").mkdir()
    source = Path(__file__).resolve().parents[2] / recovery.POLICY_PATH
    (repo / recovery.POLICY_PATH).write_text(source.read_text())
    def git(*args):
        return subprocess.run(
            ["git", *args], cwd=repo, capture_output=True, text=True, check=True
        ).stdout.strip()
    git("init", "-b", "main")
    git("config", "user.name", "Fixture")
    git("config", "user.email", "fixture@example.invalid")
    git("add", ".")
    git("commit", "-m", "fixture")
    sha = git("rev-parse", "HEAD")
    state_root = tmp_path / "release"
    protected = state_root / "protected-readback"
    protected.mkdir(parents=True)
    control, drift = evidence(revision=sha)
    (protected / "production-control-state.json").write_text(json.dumps(control))
    drift_file = protected / "production-drift.json"
    spool = tmp_path / "spool"
    spool.mkdir()
    tracker = spool / "release-breaker-recovery-state.json"
    monkeypatch.setattr(recovery, "transaction_busy", lambda path: False)
    monkeypatch.setattr(
        recovery, "native_root_transition",
        lambda *args: pytest.fail("preflight must not request root"))
    def fail_preflight(*args):
        raise recovery.NativePreflightError("production_manifest_precheck_failed")
    monkeypatch.setattr(recovery, "native_revalidation_preflight", fail_preflight)
    monkeypatch.setattr(sys, "argv", [
        "recovery", "--repo", str(repo), "--spool", str(spool),
        "--release-state", str(state_root),
    ])
    for seconds in (0, 20, 40, 60):
        moment = NOW + timedelta(seconds=seconds)
        drift_file.write_text(json.dumps({**drift, "observed_at": moment.isoformat()}))
        monkeypatch.setattr(recovery, "utcnow", lambda moment=moment: moment)
        assert recovery.main() == 0
    state = json.loads(tracker.read_text())
    assert state["attempts"] == []
    assert state["status"] == "blocked"
    assert state["next_action"] == "reconcile_read_only_preflight"
    assert state["last_preflight_failure"]["failure_class"] == (
        "production_manifest_precheck_failed"
    )
    assert tracker.stat().st_mode & 0o777 == 0o600


def test_preflight_rejects_stale_root_snapshot_without_root_contact(tmp_path):
    root = tmp_path / "release"
    protected = root / "protected-readback"
    protected.mkdir(parents=True)
    payload, _ = evidence()
    target = protected / "production-control-state.json"
    target.write_text(json.dumps(payload))
    os.utime(target, (1, 1))
    with pytest.raises(recovery.NativePreflightError) as failure:
        recovery.native_revalidation_preflight(root, SHA)
    assert failure.value.code == "protected_readback_unavailable_or_stale"


def test_original_attempt_budget_stays_exhausted_even_if_preflight_would_pass():
    control, drift = evidence()
    previous = ready(control, drift)
    previous["attempts"] = [
        {"requested_at": (NOW + timedelta(seconds=i * 300)).isoformat(),
         "revision": SHA, "result": "root_revalidation_rejected"}
        for i in range(2)
    ]
    drift["observed_at"] = (NOW + timedelta(seconds=900)).isoformat()
    state = recovery.decision(
        control, drift, previous, POLICY, NOW + timedelta(seconds=900))
    assert state["status"] == "blocked"
    assert state["next_action"] == "operator_review_recovery_attempt_budget_exhausted"
    assert len(state["attempts"]) == 2
