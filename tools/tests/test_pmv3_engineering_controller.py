import importlib.util
import fcntl
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("pmv3_engineering_controller", ROOT / "tools/pmv3_engineering_controller.py")
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")




def idle_integration_queue(**kwargs):
    return {
        "schema_version": "1.0", "status": "idle", "updated_at": "2026-11-03T00:00:00+00:00",
        "train": None, "release_lock": None, "queue": [],
    }


def runner_for(spool, snapshots):
    calls = {"n": 0}
    def runner(argv, **kwargs):
        idx = min(calls["n"], len(snapshots) - 1)
        snap = snapshots[idx]
        calls["n"] += 1
        write(spool / "engineering-pipeline-state.json", snap["pipeline"])
        write(spool / "engineering-supervisor-state.json", snap["supervisor"])
        return subprocess.CompletedProcess(argv, snap.get("return_code", 0))
    return runner, calls


def test_recoverable_work_keeps_running_until_complete(tmp_path):
    spool = tmp_path / "spool"
    snapshots = [
        {
            "pipeline": {
                "status": "degraded", "failed_work_stages": [],
                "failed_control_stages": [],
                "operational_blocker": {"reason": "approved_work_stalled"},
            },
            "supervisor": {
                "status": "degraded", "reason": "internal_recovery_needed",
                "category_counts": {"recoverable_transport": 1},
                "disposition_sha256": "a", "approved_outstanding": 1, "active": 0,
            },
        },
        {
            "pipeline": {"status": "healthy", "failed_work_stages": [], "failed_control_stages": []},
            "supervisor": {
                "status": "healthy", "reason": None, "category_counts": {},
                "disposition_sha256": "b", "approved_outstanding": 0, "active": 0,
            },
        },
    ]
    runner, calls = runner_for(spool, snapshots)
    state = module.controller_run(
        scripts=tmp_path, repo=tmp_path, spool=spool, release_state=tmp_path,
        runner=runner, integration_reconciler=idle_integration_queue, max_passes=4,
    )
    assert state["status"] == "complete"
    assert calls["n"] == 2


def test_external_gate_stops_without_retry(tmp_path):
    spool = tmp_path / "spool"
    runner, calls = runner_for(spool, [{
        "pipeline": {
            "status": "degraded", "failed_work_stages": [], "failed_control_stages": [],
            "operational_blocker": {"reason": "approved_work_stalled"},
        },
        "supervisor": {
            "status": "degraded", "reason": "external_or_governed_gate",
            "category_counts": {"human_authority": 1},
            "disposition_sha256": "a", "approved_outstanding": 1, "active": 0,
        },
    }])
    state = module.controller_run(
        scripts=tmp_path, repo=tmp_path, spool=spool, release_state=tmp_path,
        runner=runner, integration_reconciler=idle_integration_queue, max_passes=4,
    )
    assert state["status"] == "waiting_external"
    assert calls["n"] == 1


def test_unchanged_recoverable_work_is_bounded_not_infinite(tmp_path):
    spool = tmp_path / "spool"
    snap = {
        "pipeline": {
            "status": "degraded", "failed_work_stages": ["development"],
            "failed_control_stages": [],
        },
        "supervisor": {
            "status": "degraded", "reason": "internal_recovery_needed",
            "category_counts": {"recoverable_validation": 1},
            "disposition_sha256": "same", "approved_outstanding": 1, "active": 0,
        },
    }
    runner, calls = runner_for(spool, [snap, snap, snap, snap])
    state = module.controller_run(
        scripts=tmp_path, repo=tmp_path, spool=spool, release_state=tmp_path,
        runner=runner, integration_reconciler=idle_integration_queue, max_passes=6, unchanged_limit=2,
    )
    assert state["status"] == "bounded_stall"
    assert state["reason"] == "recoverable_state_not_advancing"
    assert calls["n"] == 3
    assert module.service_exit_code(state) == 0


def test_control_failure_is_hard_failure(tmp_path):
    spool = tmp_path / "spool"
    runner, calls = runner_for(spool, [{
        "pipeline": {
            "status": "degraded", "failed_work_stages": [],
            "failed_control_stages": ["engineering_supervisor"],
        },
        "supervisor": {"status": "degraded", "reason": "internal_recovery_needed"},
    }])
    state = module.controller_run(
        scripts=tmp_path, repo=tmp_path, spool=spool, release_state=tmp_path,
        runner=runner, integration_reconciler=idle_integration_queue,
    )
    assert state["status"] == "control_failure"
    assert module.service_exit_code(state) == 1


def test_controller_cannot_create_or_import_approval():
    source = (ROOT / "tools/pmv3_engineering_controller.py").read_text(encoding="utf-8")
    lowered = source.casefold()
    assert "record_teams_approval" not in source
    assert "approval_request_id" not in source
    assert "decision=" not in lowered
    assert "channel=" not in lowered
    assert "teams_only_approval" not in source


def test_integration_queue_failure_does_not_stop_development(tmp_path):
    spool = tmp_path / "spool"
    runner, calls = runner_for(spool, [{
        "pipeline": {"status": "healthy", "failed_work_stages": [], "failed_control_stages": []},
        "supervisor": {"status": "healthy", "reason": None, "category_counts": {},
                       "disposition_sha256": "ok", "approved_outstanding": 0, "active": 0},
    }])
    def broken_queue(**kwargs):
        raise RuntimeError("queue unavailable")
    state = module.controller_run(
        scripts=tmp_path, repo=tmp_path, spool=spool, release_state=tmp_path,
        runner=runner, integration_reconciler=broken_queue, max_passes=1,
    )
    assert state["status"] == "complete"
    assert state["integration_queue"]["status"] == "control_failure"
    assert calls["n"] == 1


def test_production_transaction_defers_pmv3_before_pipeline(tmp_path):
    spool = tmp_path / "spool"
    release_state = tmp_path / "release"
    release_state.mkdir()
    lock_path = release_state / "production-transaction.lock"
    lock_path.write_text("{}\n", encoding="utf-8")
    handle = lock_path.open("r+", encoding="utf-8")
    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        def must_not_run(*args, **kwargs):
            raise AssertionError("pipeline must not run during production transaction")
        state = module.controller_run(
            scripts=tmp_path, repo=tmp_path, spool=spool,
            release_state=release_state, runner=must_not_run,
            integration_reconciler=must_not_run, max_passes=3,
        )
    finally:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()
    assert state["status"] == "deferred"
    assert state["reason"] == "production_transaction_active"
    assert state["pass_count"] == 0
    assert module.service_exit_code(state) == 0


def test_free_production_lock_allows_pmv3_pipeline(tmp_path):
    spool = tmp_path / "spool"
    release_state = tmp_path / "release"
    release_state.mkdir()
    (release_state / "production-transaction.lock").write_text("\n", encoding="utf-8")
    runner, calls = runner_for(spool, [{
        "pipeline": {"status": "healthy", "failed_work_stages": [], "failed_control_stages": []},
        "supervisor": {
            "status": "healthy", "reason": None, "category_counts": {},
            "disposition_sha256": "ok", "approved_outstanding": 0, "active": 0,
        },
    }])
    state = module.controller_run(
        scripts=tmp_path, repo=tmp_path, spool=spool,
        release_state=release_state, runner=runner,
        integration_reconciler=idle_integration_queue, max_passes=2,
    )
    assert state["status"] == "complete"
    assert calls["n"] == 1


def test_production_lock_acquired_during_pass_defers_second_queue_reconcile(tmp_path):
    spool = tmp_path / "spool"
    release_state = tmp_path / "release"
    release_state.mkdir()
    lock_path = release_state / "production-transaction.lock"
    lock_path.write_text("{}\n", encoding="utf-8")
    base_runner, calls = runner_for(spool, [{
        "pipeline": {"status": "healthy", "failed_work_stages": [], "failed_control_stages": []},
        "supervisor": {
            "status": "healthy", "reason": None, "category_counts": {},
            "disposition_sha256": "ok", "approved_outstanding": 0, "active": 0,
        },
    }])
    queue_calls = {"n": 0}
    held = []

    def queue_reconciler(**kwargs):
        queue_calls["n"] += 1
        return idle_integration_queue()

    def acquire_production_lock_during_pipeline(argv, **kwargs):
        handle = lock_path.open("r+", encoding="utf-8")
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        held.append(handle)
        return base_runner(argv, **kwargs)

    try:
        state = module.controller_run(
            scripts=tmp_path, repo=tmp_path, spool=spool,
            release_state=release_state,
            runner=acquire_production_lock_during_pipeline,
            integration_reconciler=queue_reconciler,
            max_passes=2,
        )
    finally:
        for handle in held:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()

    assert state["status"] == "deferred"
    assert state["reason"] == "production_transaction_active"
    assert state["pass_count"] == 1
    assert state["passes"][0]["disposition"] == "deferred"
    assert calls["n"] == 1
    assert queue_calls["n"] == 1  # initial read; no post-pass queue mutation


def test_opt_in_controller_recovers_short_contention_and_rechecks_all_boundaries(tmp_path,monkeypatch):
    import threading
    spool=tmp_path/'spool';spool.mkdir()
    lock=tmp_path/'production-transaction.lock';lock.touch(mode=0o600)
    gate=module.release_gate
    monkeypatch.setattr(gate,'INITIAL_BACKOFF_SECONDS',0.01)
    monkeypatch.setattr(gate,'MAX_BACKOFF_SECONDS',0.02)
    monkeypatch.setattr(gate,'RETRY_SECONDS',0.5)
    base_runner,calls=runner_for(spool,[{
        "pipeline":{"status":"healthy","failed_work_stages":[],"failed_control_stages":[]},
        "supervisor":{"status":"healthy","category_counts":{},"disposition_sha256":"ok",
                      "approved_outstanding":0,"active":0},
    }])
    held=[];timers=[];queue_calls=[]
    def brief_lock():
        handle=lock.open('rb')
        fcntl.flock(handle.fileno(),fcntl.LOCK_EX)
        held.append(handle)
        timer=threading.Timer(0.04,lambda:fcntl.flock(handle.fileno(),fcntl.LOCK_UN))
        timers.append(timer);timer.start()
    def reconcile(**kwargs):
        queue_calls.append(1)
        if len(queue_calls)==1:brief_lock()
        return idle_integration_queue(**kwargs)
    def runner(*args,**kwargs):
        result=base_runner(*args,**kwargs)
        brief_lock()
        return result
    brief_lock()
    try:
        state=module.controller_run(scripts=tmp_path,repo=tmp_path,spool=spool,
            release_state=tmp_path,runner=runner,integration_reconciler=reconcile,
            retry_release_contention=True)
        assert state["status"]=="complete"
        assert state["release_gate_status"]=="allowed"
        assert calls["n"]==1 and len(queue_calls)==2
    finally:
        for timer in timers:timer.join()
        for handle in held:handle.close()


def test_opt_in_controller_fails_closed_on_missing_lock_and_pause(tmp_path):
    spool=tmp_path/'spool';spool.mkdir()
    def must_not_run(*args,**kwargs):raise AssertionError('unsafe engineering admission')
    for expected in ('unavailable','paused'):
        if expected=='paused':
            (tmp_path/'production-transaction.lock').touch(mode=0o600)
            (spool/'pmv3-engineering-owner-pause.json').touch(mode=0o600)
        state=module.controller_run(scripts=tmp_path,repo=tmp_path,spool=spool,
            release_state=tmp_path,runner=must_not_run,integration_reconciler=must_not_run,
            retry_release_contention=True)
        assert state["status"]=="deferred" and state["release_gate_status"]==expected
        assert state["pass_count"]==0


def test_unrelated_authority_hold_does_not_mask_critical_internal_work(tmp_path):
    spool = tmp_path / "spool"
    critical = {"reason": "critical_support_stalled", "blocked_count": 1, "unadmitted_count": 0,
                "blocked_items": ["SUPPORT-OPS-054"], "unadmitted_items": []}
    pipeline = {"status": "degraded", "failed_control_stages": [], "failed_work_stages": [],
                "critical_support_blocker": critical}
    supervisor = {"status": "degraded", "reason": "external_or_governed_gate",
                  "category_counts": {"human_authority": 1, "recoverable_source": 100},
                  "support_blocker_routes": {"SUPPORT-OPS-054": {"category": "recoverable_source"}},
                  "unchanged_cycles": 3, "disposition_sha256": "same"}
    runner, calls = runner_for(spool, [{"pipeline": pipeline, "supervisor": supervisor}])
    result = module.controller_run(scripts=tmp_path, repo=tmp_path, spool=spool,
                                   release_state=tmp_path, runner=runner,
                                   integration_reconciler=idle_integration_queue)
    assert result["status"] == "bounded_stall"
    assert result["reason"] == "critical_support_repair_handoff"
    assert calls["n"] == 1
    assert module.service_exit_code(result) == 0
    supervisor["unchanged_cycles"] = 0
    assert module.classify(pipeline, supervisor) == ("recoverable", "critical_support_recoverable")
    supervisor["support_blocker_routes"]["SUPPORT-OPS-054"]["category"] = "human_authority"
    assert module.classify(pipeline, supervisor)[0] == "waiting_external"
    pipeline["failed_work_stages"] = ["development"]
    assert module.classify(pipeline, supervisor) == ("recoverable", "work_stage_failed")
    pipeline["failed_control_stages"] = ["engineering_supervisor"]
    assert module.classify(pipeline, supervisor) == ("control_failure", "control_plane_failure")
