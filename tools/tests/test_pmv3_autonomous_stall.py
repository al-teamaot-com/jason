"""Independent PMV3 no-progress regressions.

The tests intentionally live outside the queue controller's existing test file:
PR #2280 extends that file with production-lock gating tests, and separate
test ownership keeps later governed source integration conflict-free.
"""
from __future__ import annotations

import importlib.util
import inspect
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "pmv3_engineering_controller_autonomous_stall_test",
    ROOT / "tools" / "pmv3_engineering_controller.py",
)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def runner_for(spool: Path, snapshots):
    calls = {"n": 0}

    def runner(argv, **kwargs):
        index = min(calls["n"], len(snapshots) - 1)
        data = snapshots[index]
        calls["n"] += 1
        spool.mkdir(parents=True, exist_ok=True)
        (spool / "engineering-pipeline-state.json").write_text(
            json.dumps(data["pipeline"]), encoding="utf-8",
        )
        (spool / "engineering-supervisor-state.json").write_text(
            json.dumps(data["supervisor"]), encoding="utf-8",
        )
        return subprocess.CompletedProcess(argv, data.get("return_code", 0))
    return runner, calls


def controller_run_with_bounded_queue(**kwargs):
    # After queue PR #2280 is integrated, prevent real provider access in
    # this deterministic regression. Before #2280, the queue does not exist.
    if "integration_reconciler" in inspect.signature(module.controller_run).parameters:
        kwargs["integration_reconciler"] = (
            lambda **_: module.integration_queue.empty_state()
        )
    return module.controller_run(**kwargs)


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
    result = controller_run_with_bounded_queue(
        scripts=tmp_path, repo=tmp_path, spool=spool,
        release_state=tmp_path, runner=runner, max_passes=4,
    )
    assert result["status"] == "waiting_external"
    assert calls["n"] == 1
    assert module.service_exit_code(result) == 0
