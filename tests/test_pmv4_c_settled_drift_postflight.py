"""One-use Stage C final native drift is never bypassed, but follows real scans."""
from contextlib import contextmanager
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools import pmv4_c_canonical_resume_root as root


@pytest.fixture
def harness(tmp_path,monkeypatch):
    release=tmp_path/("pmv4-c-resume-"+"b"*40)
    release.mkdir()
    (release/"service-manifest.json").write_text("{}")
    work=tmp_path/"protected"
    work.mkdir()
    freeze=work/"freeze"
    hold=work/"hold"
    freeze.write_bytes(b"freeze")
    hold.write_bytes(b"hold")
    monkeypatch.setattr(root.c,"FREEZE",freeze)
    monkeypatch.setattr(root.c,"HOLD",hold)
    plan={
        "candidate_sha":"b"*40,
        "runtime_image_digest":"sha256:"+"1"*64,
        "mcp_container_id":"unchanged-mcp",
        "mcp_image_digest":"sha256:"+"2"*64,
        "freeze_sha256":root.c.sha(b"freeze"),
        "hold_sha256":root.c.sha(b"hold"),
    }
    monkeypatch.setattr(root,"packet",lambda path:(plan,{}))
    monkeypatch.setattr(root,"release_sources",lambda *_:None)
    monkeypatch.setattr(root,"verify_owner",lambda *a,**kw:"one-use-owner-proof")
    monkeypatch.setattr(root.c,"_audit_rows",lambda _: [
        {"event":"begin","details":{"baseline_at":"2026-11-18T11:00:00Z"}},
        {"event":"activated"}])
    monkeypatch.setattr(root.c,"read_json",lambda _: {})
    monkeypatch.setattr(root.service,"validate_effective_inspect",lambda *a:None)
    container={
        "jason-runtime":{"Image":plan["runtime_image_digest"]},
        "jason-mcp-pilot":{"Id":plan["mcp_container_id"],"Image":plan["mcp_image_digest"]},
        root.c.WORKER:{"Id":"worker", "State":{"Health":{"Status":"healthy"}}},
    }
    monkeypatch.setattr(root.c,"_wait_container",
                        lambda name,**kw:container[name])
    actions=[]
    monkeypatch.setattr(root.c,"_wait_two_scans",
        lambda baseline:(actions.append("two_real_scans") or
            (("scan1",None,None,None,0),("scan2",None,None,None,0))))
    def run(args, **kwargs):
        if args[1].endswith("production_drift_guard.py"):
            actions.append("native_final_drift")
            return SimpleNamespace(returncode=0,stdout='{"status":"pass","problems":[]}')
        if args[1].endswith("production_drift_watchdog.py"):
            actions.append("native_final_watchdog")
            return SimpleNamespace(returncode=0,stdout="pass")
        raise AssertionError("Unexpected run "+str(args))
    monkeypatch.setattr(root.c,"_run",run)
    class Host:
        @contextmanager
        def host_release_transaction(self):
            actions.append("protected_transaction")
            yield
        def _assert_protected_release_state(self):
            actions.append("protected_root_release_check")
    monkeypatch.setattr(root.guard,"IndependentHostGuard",Host)
    monkeypatch.setattr(root.c,"_append",lambda *a:actions.append("audit_"+str(a[2])))
    monkeypatch.setattr(root.c,"_receipt_path",lambda *a:release/"receipt.json")
    monkeypatch.setattr(root,"rollback",lambda *a,**kw:actions.append("safe_rollback"))
    return release/"root-release-plan.json", actions


def test_final_drift_after_genuine_scans_and_before_receipt(harness):
    path, actions=harness
    root.postflight(path)
    assert actions.index("two_real_scans") < actions.index("native_final_drift")
    assert actions.index("native_final_drift") < actions.index("native_final_watchdog")
    assert actions.index("native_final_watchdog") < actions.index("protected_root_release_check")
    assert actions.index("protected_root_release_check") < actions.index("audit_committed")
    assert "safe_rollback" not in actions
    receipt=json.loads((path.parent/"receipt.json").read_text())
    assert receipt["status"]=="postmigration_stage_c_accepted"
    assert receipt["mcp_restarts"]==0
    assert receipt["no_database_relocation"] is True


def test_final_unknown_drift_still_forces_rollback(harness,monkeypatch,capsys):
    path,actions=harness
    def fail_drift(args,**kwargs):
        if args[1].endswith("production_drift_guard.py"):
            actions.append("native_final_drift")
            return SimpleNamespace(returncode=2,stdout=json.dumps({
                "status":"drift_detected","problems":[
                    {"kind":"undeclared_running_container","container":"unexpected",
                     "secret":"must never show"}]}))
        raise AssertionError("watchdog must NOT run when final drift fails")
    monkeypatch.setattr(root.c,"_run",fail_drift)
    with pytest.raises(root.c.StageCRootDenied,match="POSTFLIGHT_FINAL_DRIFT_DENIED"):
        root.postflight(path)
    assert actions[:2]==["two_real_scans","native_final_drift"]
    assert actions[-1]=="safe_rollback"
    assert not (path.parent/"receipt.json").exists()
    err=capsys.readouterr().err
    assert "PMV4_C_FINAL_DRIFT_PROBLEMS=" in err
    assert "undeclared_running_container" in err
    assert "must never show" not in err


def test_final_watchdog_failure_rolls_back_despite_drift_pass(harness,monkeypatch):
    path,actions=harness
    def fail_watchdog(args,**kwargs):
        if args[1].endswith("production_drift_guard.py"):
            actions.append("native_final_drift")
            return SimpleNamespace(returncode=0,stdout='{"status":"pass","problems":[]}')
        actions.append("native_final_watchdog")
        return SimpleNamespace(returncode=2,stdout="failed")
    monkeypatch.setattr(root.c,"_run",fail_watchdog)
    with pytest.raises(root.c.StageCRootDenied,match="POSTFLIGHT_WATCHDOG_FAILED"):
        root.postflight(path)
    assert actions[:3]==["two_real_scans","native_final_drift","native_final_watchdog"]
    assert actions[-1]=="safe_rollback"
    assert not (path.parent/"receipt.json").exists()
