"""Exact one-use, minimal host recovery for the completed-install stale timer."""
import json
import os
from pathlib import Path
import subprocess
import sys
from contextlib import contextmanager
import pytest

from tools import pmv4_bootstrap_timer_recovery_root as r
from tools import pmv4_bootstrap_timer_recovery_builder as b


def test_exact_scope_never_mutates_other_services_or_containers():
    assert r.ACTION == "pmv4-completed-catalog-bootstrap-timer-supersession-v1"
    assert r.OLD_TIMER == "jason-catalog-root-bootstrap-recovery.timer"
    assert r.SCOPED_TIMER == "jason-catalog-scoped-recovery.timer"
    assert r.WATCHDOG == "jason-production-drift-watchdog.service"
    source=Path(r.__file__).read_text()
    assert 'native_action("disable","--now",OLD_TIMER)' in source
    assert 'native_action("start",WATCHDOG' in source
    assert 'native_action("enable","--now",OLD_TIMER)' in source
    assert "root_revalidate_release_breaker" not in source
    assert "BREAKER_NOT_FORCED_CLOSED" in source
    assert "BREAKER_NOT_FORCED" in source
    for banned in ('docker stop', 'docker restart', 'systemctl mask',
                   'native_action("stop"', 'native_action("disable","--now",SCOPED_TIMER)'):
        assert banned not in source


def test_exact_launcher_requires_human_and_two_root_calls(tmp_path):
    sample=b.launcher(tmp_path, "f"*40, "a"*64)
    path=tmp_path/"launcher.sh"
    path.write_text(sample)
    assert subprocess.run(["bash","-n",str(path)],capture_output=True).returncode==0
    assert "INTERACTIVE_OWNER_TTY_REQUIRED" in sample
    assert "--check-only" in sample
    assert "--execute" in sample
    assert sample.index(' --check-only\n') < sample.index(' --execute\n')
    assert "PRODUCTION_MUTATIONS=false; OWNER_APPROVAL=false" in sample
    assert "TP_SOURCE_SHA" not in sample
    assert "TP_ROOT_SHA256" not in sample


def test_plan_rejects_nonroot_readonly_use(tmp_path):
    with pytest.raises(r.BootstrapTimerRecoveryDenied,match="ISOLATED_ROOT_ONLY"):
        r.packet(tmp_path/"not-authorized.json")


def test_recovery_requires_single_existing_drift_kind(monkeypatch):
    plan={"source_sha":"f"*40,"rollback_sha":"c"*40,
          "freeze_sha256":"a"*64,"old_timer_unit_sha256":"b"*64,
          "scoped_timer_unit_sha256":"d"*64}
    monkeypatch.setattr(r,"protected_ci",lambda *_: None)
    monkeypatch.setattr(r.HOST_LKG.__class__,"resolve",
        lambda path,strict=False: Path("/opt/jason/releases/"+"c"*40))
    monkeypatch.setattr(r,"completed_install",lambda:None)
    monkeypatch.setattr(r,"secure_file",lambda path,**kwargs:
        b"freeze" if path==r.FREEZE else b"unit")
    plan["freeze_sha256"]=r.digest(b"freeze")
    plan["old_timer_unit_sha256"]=r.digest(b"unit")
    plan["scoped_timer_unit_sha256"]=r.digest(b"unit")
    monkeypatch.setattr(r,"systemd_status",
        lambda unit,action: "failed" if unit==r.OLD_SERVICE else
        ("active" if action=="is-active" else "enabled"))
    monkeypatch.setattr(r,"jsonfile",lambda path,**k:
        {"circuit_breaker":{"state":"open",
          "reason":"continuous_production_drift_detected",
          "problem_kinds":["failed_system_unit"]}})
    monkeypatch.setattr(r,"protected_containers",lambda:{"jason-runtime":("one","image","started")})
    monkeypatch.setattr(r,"observed_drift",lambda:{
        "schema_version":"1.0","status":"drift_detected",
        "problems":[{"kind":"failed_system_unit","unit":r.OLD_SERVICE}]})
    assert r.verify(plan)=={"jason-runtime":("one","image","started")}
    monkeypatch.setattr(r,"observed_drift",lambda:{
        "schema_version":"1.0","status":"drift_detected",
        "problems":[{"kind":"failed_system_unit","unit":r.OLD_SERVICE},
                    {"kind":"undeclared_running_container","unit":"rogue"}]})
    with pytest.raises(r.BootstrapTimerRecoveryDenied,match="UNRELATED_PRODUCTION_DRIFT"):
        r.verify(plan)


@pytest.fixture
def isolated(tmp_path,monkeypatch):
    root=tmp_path/"audit"
    monkeypatch.setattr(r,"AUDIT",root)
    original_lstat = Path.lstat
    from types import SimpleNamespace
    def synthetic_root_audit_stat(path):
        original = original_lstat(path)
        if path == root:
            return SimpleNamespace(st_uid=0, st_mode=original.st_mode)
        return original
    monkeypatch.setattr(Path, "lstat", synthetic_root_audit_stat)
    source="a"*40
    plan={"source_sha":source,"rollback_sha":"b"*40,"scope_sha256":"c"*64,
          "freeze_sha256":r.digest(b"freeze")}
    monkeypatch.setattr(r,"packet",lambda p:plan)
    previous={"jason-runtime":("runtime","img","time"),"jason-mcp-pilot":("mcp","img","time")}
    monkeypatch.setattr(r,"verify",lambda p:previous)
    monkeypatch.setattr(r,"authenticated_owner",lambda p:"real-verified-oid-synthetic")
    monkeypatch.setattr(r.os,"isatty",lambda _:True)
    @contextmanager
    def fake_locks():
        yield
    monkeypatch.setattr(r,"native_locks",fake_locks)
    monkeypatch.setattr(r,"protected_containers",lambda:previous)
    monkeypatch.setattr(r,"secure_file",lambda path,**kwargs:b"freeze")
    monkeypatch.setattr(r.HOST_LKG.__class__,"resolve",
        lambda path,strict=False:Path("/opt/jason/releases/"+"b"*40))
    state={"boot":True,"watchdog":False,"fail":False}
    calls=[]
    def action(*args,**kw):
        calls.append(args)
        if args[:3]==("disable","--now",r.OLD_TIMER):
            state["boot"]=False
        if args[:3]==("enable","--now",r.OLD_TIMER):
            state["boot"]=True
        if args[:2]==("start",r.WATCHDOG) and state["fail"]:
            raise RuntimeError("synthetic_watchdog_failure")
    monkeypatch.setattr(r,"native_action",action)
    def status(unit,op):
        if unit==r.SCOPED_TIMER:return "active" if op=="is-active" else "enabled"
        if unit==r.OLD_TIMER:
            return ("active" if state["boot"] else "inactive") if op=="is-active" else ("enabled" if state["boot"] else "disabled")
        return "failed"
    monkeypatch.setattr(r,"systemd_status",status)
    monkeypatch.setattr(r,"observed_drift",lambda:{"status":"pass","problems":[]})
    return root,plan,state,calls


def test_oneuse_rollback_never_restarts_core(isolated,tmp_path):
    root,plan,state,calls=isolated
    r.execute(tmp_path/"plan.json")
    assert state["boot"] is False
    assert (root/(plan["source_sha"]+"-attempt.json")).is_file()
    assert (root/(plan["source_sha"]+"-accepted.json")).is_file()
    assert ("disable","--now",r.OLD_TIMER) in calls
    assert ("start",r.WATCHDOG) in calls
    assert not any(c[0] in ("restart","stop") for c in calls)
    with pytest.raises(r.BootstrapTimerRecoveryDenied,match="OWNER_ACTION_ALREADY_CONSUMED"):
        r.execute(tmp_path/"plan.json")


def test_failed_watchdog_restores_only_original_timer(isolated,monkeypatch,tmp_path):
    root,plan,state,calls=isolated
    state["fail"]=True
    with pytest.raises(RuntimeError,match="synthetic_watchdog_failure"):
        r.execute(tmp_path/"plan.json")
    assert state["boot"] is True
    assert (root/(plan["source_sha"]+"-rollback.json")).is_file()
    assert json.loads((root/(plan["source_sha"]+"-rollback.json")).read_text())["timer_rollback_verified"] is True
    assert not (root/(plan["source_sha"]+"-accepted.json")).exists()


def test_never_claims_breaker_closed():
    source=Path(r.__file__).read_text()
    assert "root_revalidate_release_breaker" not in source
    assert "circuit_breaker']={'state':'closed'" not in source
    assert "BREAKER_NOT_FORCED_CLOSED" in source


def test_plan_source_binding_fails_with_changed_scope():
    unsigned={"schema_version":"1.0","action":r.ACTION,"source_sha":"f"*40,
              "production_mutations":["disable_completed_bootstrap_recovery_timer"]}
    expected=r.digest(r.canonical(unsigned))
    unsigned["production_mutations"].append("restart_jason_runtime")
    assert r.digest(r.canonical(unsigned))!=expected


def test_original_finished_install_receipt_and_owner_identity_are_authoritative(tmp_path,monkeypatch):
    sha=r.SOURCE_SHA
    rollback="b"*40
    freeze=b"frozen-original-marker"
    bootstrap_source=b"trusted-original-bootstrap-source"
    install={
        "source_sha":sha,"rollback_source_sha":rollback,
        "installation_scope_sha256":"a"*64,
        "install_plan_sha256":"b"*64,
        "freeze_sha256":r.digest(freeze),
        "root_policy_after_separate_approval":{"source_sha":sha,"scope":"catalog-only"},
    }
    trust={
        "protected_source_sha":sha,
        "install_scope_sha256":install["installation_scope_sha256"],
        "plan_sha256":install["install_plan_sha256"],
        "bootstrap_sha256":r.digest(bootstrap_source),
    }
    journal={
        "schema_version":"1.0","action":"catalog_root_install_only_v1",
        "source_sha":sha,
        "plan_sha256":install["install_plan_sha256"],
        "scope_sha256":install["installation_scope_sha256"],
        "rollback_source_sha":rollback,
        "approval_id":"catalog-root-owner-"+"c"*32,
        "verified_owner_oid":"real-entra-owner-oid",
        "verified_token_sha256":"d"*64,
        "status":"exact_catalog_root_install_verified",
    }
    files={
        r.INSTALL_PLAN:install,
        r.BOOTSTRAP_TRUST:trust,
        r.INSTALLED_POLICY:install["root_policy_after_separate_approval"],
    }
    audit=r.ROOT_JOURNALS/("release-"+sha[:16]+".json")
    files[audit]=journal
    monkeypatch.setattr(r,"jsonfile",lambda path,**kw:files[path])
    monkeypatch.setattr(r,"secure_file",
        lambda path,**kw:freeze if path==r.FREEZE else bootstrap_source)
    root_path=tmp_path / ("b"*40)
    root_path.mkdir()
    monkeypatch.setattr(r,"HOST_LKG",root_path)
    r.completed_install()
    journal["verified_token_sha256"]="wrong"
    with pytest.raises(r.BootstrapTimerRecoveryDenied,match="ORIGINAL_ROOT_INSTALL_NOT_ACCEPTED"):
        r.completed_install()
    journal["verified_token_sha256"]="d"*64
    journal["status"]="catalog_root_rollback_unverified"
    with pytest.raises(r.BootstrapTimerRecoveryDenied,match="ORIGINAL_ROOT_INSTALL_NOT_ACCEPTED"):
        r.completed_install()
    journal["status"]="exact_catalog_root_install_verified"
    trust["protected_source_sha"]="0"*40
    with pytest.raises(r.BootstrapTimerRecoveryDenied,match="ORIGINAL_ROOT_TRUST_SOURCE_CHANGED"):
        r.completed_install()


def test_unauthorized_timer_and_breaker_mutations_not_exposed():
    with pytest.raises(r.BootstrapTimerRecoveryDenied,match="SYSTEMD_READ_SCOPE_INVALID"):
        r.systemd_status("jason-runtime.service","is-active")
    with pytest.raises(r.BootstrapTimerRecoveryDenied,match="SYSTEMD_READ_SCOPE_INVALID"):
        r.systemd_status(r.OLD_TIMER,"stop")
