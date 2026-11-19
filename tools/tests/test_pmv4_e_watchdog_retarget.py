"""Watchdog cannot reanimate PMv3 after exact authenticated Stage E cutover."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import importlib.util
import json
import os
import stat

import pytest


ROOT=Path(__file__).resolve().parents[2]
SPEC=importlib.util.spec_from_file_location(
    "pmv4_e_watchdog_source",ROOT/"tools/jason_self_heal_watchdog.py")
m=importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(m)


@pytest.fixture
def probe(tmp_path,monkeypatch):
    marker=tmp_path/"accepted.json"
    guard=tmp_path/"exact-root-guard.py"
    marker.write_text("{}")
    guard.write_text("source-only fake guard")
    marker.chmod(0o444)
    guard.chmod(0o444)
    monkeypatch.setattr(m,"PMV4_E_MARKER",marker)
    monkeypatch.setattr(m,"PMV4_E_GUARD",guard)
    source=Path.lstat
    attrs={marker,guard}
    def owned(candidate):
        real=source(candidate)
        if candidate in attrs:
            return SimpleNamespace(
                st_mode=real.st_mode,st_uid=0,st_gid=0,
                st_nlink=real.st_nlink,st_size=real.st_size)
        return real
    monkeypatch.setattr(Path,"lstat",owned)
    lock=tmp_path/"production-transaction.lock"
    lock.touch(mode=0o600)
    lock.chmod(0o600)
    monkeypatch.setattr(m,"PRODUCTION_TRANSACTION_LOCK",lock)
    return marker,guard,lock


def approval_stdout():
    return json.dumps({
        "status":"accepted_for_one_configured_service",
        "role":"engineering",
        "unit":"jason-pmv4-engineering.timer",
        "production_changes_performed":False,
        "owner_authority_issued":False,
    })


def test_absent_cutover_keeps_old_engineering_target(probe,monkeypatch):
    marker,_,_=probe
    marker.unlink()
    requested=[]
    def fake_run(argv,**kw):
        requested.append(argv)
        return SimpleNamespace(returncode=0,stdout="",stderr="")
    monkeypatch.setattr(m,"run",fake_run)
    assert m.pmv4_e_controlplane_mode()=="legacy"
    assert m.request_engineering_worker()=="requested"
    assert requested==[[
        "systemctl","--user","start","--no-block",
        "jason-support-repair-worker.service",
    ]]


def test_accepted_root_guard_retargets_engineering_under_same_lock(probe,monkeypatch):
    marker,guard,lock=probe
    requested=[]
    def fake_run(argv,**kw):
        requested.append(argv)
        if argv[0]=="/usr/bin/python3":
            return SimpleNamespace(returncode=0,stdout=approval_stdout(),stderr="")
        return SimpleNamespace(returncode=0,stdout="",stderr="")
    monkeypatch.setattr(m,"run",fake_run)
    assert m.pmv4_e_controlplane_mode()=="replacement"
    requested.clear()
    assert m.request_engineering_worker()=="requested"
    assert requested[0]==[
        "/usr/bin/python3","-I","-B",str(guard),
        "--mode","engineering",
    ]
    assert requested[1]==[
        "systemctl","--user","start","--no-block",
        "jason-pmv4-engineering.service",
    ]


def test_untrusted_root_marker_never_falls_back_to_old_worker(probe,monkeypatch):
    marker,guard,lock=probe
    marker.chmod(0o666)
    requested=[]
    monkeypatch.setattr(m,"run",lambda args,**kw:requested.append(args))
    assert m.pmv4_e_controlplane_mode()=="denied"
    assert m.request_engineering_worker()=="deferred_pmv4_e_root_acceptance_invalid"
    assert requested==[]


def test_invalid_root_guard_never_reactivates_legacy(probe,monkeypatch):
    _,guard,_=probe
    guard.chmod(0o666)
    requested=[]
    monkeypatch.setattr(m,"run",lambda args,**kw:requested.append(args))
    assert m.pmv4_e_controlplane_mode()=="denied"
    assert m.request_engineering_worker()=="deferred_pmv4_e_root_acceptance_invalid"
    assert requested==[]


def test_guard_denial_is_not_automatic_legacy_fallback(probe,monkeypatch):
    requests=[]
    def fake_run(argv,**kw):
        requests.append(argv)
        return SimpleNamespace(returncode=255,stdout="denied",stderr="")
    monkeypatch.setattr(m,"run",fake_run)
    assert m.pmv4_e_controlplane_mode()=="denied"
    assert m.request_engineering_worker()=="deferred_pmv4_e_root_acceptance_invalid"
    assert len(requests)==2
    assert all(x[0]=="/usr/bin/python3" for x in requests)


@pytest.mark.parametrize("payload",[
    {"status":"accepted_for_one_configured_service","role":"engineering",
     "unit":"jason-support-repair-worker.timer",
     "production_changes_performed":False,"owner_authority_issued":False},
    {"status":"accepted_for_one_configured_service","role":"release-approval",
     "unit":"jason-pmv4-engineering.timer",
     "production_changes_performed":False,"owner_authority_issued":False},
    {"status":"accepted_for_one_configured_service","role":"engineering",
     "unit":"jason-pmv4-engineering.timer",
     "production_changes_performed":True,"owner_authority_issued":False},
])
def test_spoofed_success_output_is_not_authority(probe,monkeypatch,payload):
    monkeypatch.setattr(m,"run",lambda *a,**kw:SimpleNamespace(
        returncode=0,stdout=json.dumps(payload),stderr=""))
    assert m.pmv4_e_controlplane_mode()=="denied"


def test_invalid_acceptance_production_convergence_fails_before_other_probes(
    probe,monkeypatch,
):
    monkeypatch.setattr(m,"run",lambda *a,**kw:SimpleNamespace(
        returncode=255,stdout="",stderr=""))
    monkeypatch.setattr(m,"_container_source_revision",
                        lambda name:(_ for _ in ()).throw(
                            AssertionError("no revision or provider probe")))
    problems,evidence=m.production_convergence_failures()
    assert problems==["production_convergence_pmv4_e_acceptance_invalid"]
    assert evidence["pmv4_e_controlplane_mode"]=="denied"


def test_replacement_production_convergence_expects_only_new_timer(probe,monkeypatch,tmp_path):
    revision="a"*40
    releases=tmp_path/"releases"
    release=releases/revision
    release.mkdir(parents=True)
    monkeypatch.setattr(m,"pmv4_e_controlplane_mode",lambda:"replacement")
    monkeypatch.setattr(m,"_container_source_revision",lambda name:revision)
    problems,evidence=m.production_convergence_failures(
        releases_root=releases,verify_scheduled_surfaces=False)
    # Unavailable source prevents a false success.
    assert "production_convergence_release_source_missing" not in problems
    assert "production_convergence_release_manager_source_drift" in problems
    assert evidence["pmv4_e_controlplane_mode"]=="replacement"


def test_source_preserves_existing_release_mutex_and_no_disruptive_change():
    content=Path(m.__file__).read_text()
    assert "with non_disruptive_release_guard() as admitted:" in content
    assert "if control_mode==\"denied\":" in content
    assert "jason-pmv4-engineering.service" in content
    assert "PMV4_E_ROOT_RECONCILE_PATH" in content
    assert "os.chown(" not in content.split("def pmv4_e_controlplane_mode",1)[1].split("def atomic_json",1)[0]


def test_root_accepted_controlplane_can_run_new_source_with_pinned_old_images():
    baseline="a"*40
    new_control="b"*40
    assert m.choose_pmv4_e_convergence_source(
        mode="replacement",runtime_revision=baseline,mcp_revision=baseline,
        accepted={"candidate_sha":new_control,"rollback_sha":baseline},
    )==new_control


@pytest.mark.parametrize("case",[
    ("legacy","a"*40,"a"*40,None,"a"*40),
    ("legacy","a"*40,"b"*40,None,None),
    ("replacement","a"*40,"a"*40,None,None),
    ("replacement","a"*40,"b"*40,
     {"candidate_sha":"b"*40,"rollback_sha":"a"*40},None),
    ("replacement","a"*40,"a"*40,
     {"candidate_sha":"a"*40,"rollback_sha":"a"*40},None),
    ("replacement","a"*40,"a"*40,
     {"candidate_sha":"b"*40,"rollback_sha":"c"*40},None),
    ("replacement","a"*40,"a"*40,
     {"candidate_sha":"invalid","rollback_sha":"a"*40},None),
    ("denied","a"*40,"a"*40,
     {"candidate_sha":"b"*40,"rollback_sha":"a"*40},None),
])
def test_dual_source_never_weakens_legacy_or_accepts_bad_root_marker(
        case):
    mode,runtime,mcp,accepted,result=case
    assert m.choose_pmv4_e_convergence_source(
        mode=mode,runtime_revision=runtime,mcp_revision=mcp,
        accepted=accepted)==result


def test_marker_identity_requires_actual_pinned_root_accepted_schema(
        probe,monkeypatch):
    marker,guard,lock=probe
    receipt={
        "action":"pmv4-e-oneowner-six-unit-replacement-and-retirement-v1",
        "state":"accepted","source_sha":"b"*40,
        "source_rollback_sha":"a"*40,
    }
    marker.chmod(0o600)
    marker.write_text(json.dumps(receipt))
    marker.chmod(0o444)
    assert m.pmv4_e_accepted_source_identity()=={
        "candidate_sha":"b"*40,"rollback_sha":"a"*40,
    }
    receipt["source_rollback_sha"]="b"*40
    marker.chmod(0o600)
    marker.write_text(json.dumps(receipt))
    marker.chmod(0o444)
    assert m.pmv4_e_accepted_source_identity() is None
