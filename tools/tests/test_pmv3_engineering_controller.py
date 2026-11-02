import importlib.util
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


def test_credit_probe_is_bounded_by_durable_cooldown(tmp_path):
    spool = tmp_path / "spool"
    calls = []
    def runner(argv, **kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 4)
    first = module.maybe_run_credit_probe(
        spool=spool, runner=runner, cooldown_seconds=900,
    )
    second = module.maybe_run_credit_probe(
        spool=spool, runner=runner, cooldown_seconds=900,
    )
    assert first["status"] == "unavailable"
    assert second["status"] == "cooldown"
    assert len(calls) == 1
    assert calls[0][:3] == ["docker", "exec", "jason-runtime"]


def test_verified_credit_probe_keeps_pmv3_running_for_worker_readmission(tmp_path):
    spool = tmp_path / "spool"
    pipeline_calls = {"n": 0}
    probe_calls = {"n": 0}
    snapshots = [
        {
            "pipeline": {
                "status": "degraded", "failed_work_stages": [],
                "failed_control_stages": [],
                "operational_blocker": {"reason": "approved_work_stalled"},
            },
            "supervisor": {
                "status": "degraded", "reason": "internal_recovery_needed",
                "category_counts": {"recoverable_credit": 1},
                "disposition_sha256": "credit-blocked",
                "approved_outstanding": 1, "active": 0,
            },
        },
        {
            "pipeline": {"status": "healthy", "failed_work_stages": [], "failed_control_stages": []},
            "supervisor": {
                "status": "healthy", "reason": None, "category_counts": {},
                "disposition_sha256": "resumed",
                "approved_outstanding": 0, "active": 0,
            },
        },
    ]
    def runner(argv, **kwargs):
        if argv and argv[0] == "docker":
            probe_calls["n"] += 1
            return subprocess.CompletedProcess(argv, 0)
        idx = min(pipeline_calls["n"], len(snapshots) - 1)
        snap = snapshots[idx]
        pipeline_calls["n"] += 1
        write(spool / "engineering-pipeline-state.json", snap["pipeline"])
        write(spool / "engineering-supervisor-state.json", snap["supervisor"])
        return subprocess.CompletedProcess(argv, 0)
    state = module.controller_run(
        scripts=tmp_path, repo=tmp_path, spool=spool, release_state=tmp_path,
        runner=runner, max_passes=3,
    )
    assert probe_calls["n"] == 1
    assert pipeline_calls["n"] == 2
    assert state["status"] == "complete"
    assert state["passes"][0]["credit_probe"]["status"] == "verified"
