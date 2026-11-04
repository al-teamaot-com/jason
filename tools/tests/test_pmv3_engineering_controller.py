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
        runner=runner, max_passes=4,
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
        runner=runner, max_passes=4,
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
        runner=runner, max_passes=6, unchanged_limit=2,
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
        runner=runner,
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
    assert "teams_only_approval" in source


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
            release_state=release_state, runner=must_not_run, max_passes=3,
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
        release_state=release_state, runner=runner, max_passes=2,
    )
    assert state["status"] == "complete"
    assert calls["n"] == 1



def test_unclassified_triage_does_not_falsely_retrigger_recovery():
    pipeline = {
        "status": "degraded", "failed_work_stages": [],
        "failed_control_stages": [],
        "operational_blocker": {"reason": "approved_work_stalled"},
    }
    supervisor = {"status": "degraded", "category_counts": {"needs_triage": 9}}
    disposition, reason = module.classify(pipeline, supervisor)
    assert disposition == "waiting_external"
    assert reason == "approved_work_stalled_external"


def test_governed_repair_handoff_stops_repeated_pipeline_passes(tmp_path):
    spool = tmp_path / "spool"
    runner, calls = runner_for(spool, [{
        "pipeline": {
            "status": "degraded", "failed_work_stages": [],
            "failed_control_stages": [],
            "operational_blocker": {"reason": "approved_work_stalled"},
        },
        "supervisor": {
            "status": "degraded", "reason": "external_or_governed_gate",
            "category_counts": {"governed_repair_handoff": 1},
            "disposition_sha256": "handoff", "approved_outstanding": 1, "active": 0,
        },
    }])
    result = module.controller_run(
        scripts=tmp_path, repo=tmp_path, spool=spool,
        release_state=tmp_path, runner=runner, max_passes=4,
    )
    assert result["status"] == "waiting_external"
    assert calls["n"] == 1
    assert module.service_exit_code(result) == 0
