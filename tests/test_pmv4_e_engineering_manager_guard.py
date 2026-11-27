"""No production operations; prove exact receipt, topology, and routing rules."""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import pytest

from tools import pmv4_e_engineering_manager_guard as g
from tools import release_manager_host_runner as runner
from tools import jason_self_heal_watchdog as wd


def receipt():
    return {"schema_version": "1.0", "action": g.ACTION, "status": "accepted",
            "candidate_sha": "a"*40, "rollback_sha": g.LKG,
            "scope_sha256": "b"*64, "approval_sha256": "c"*64,
            "stage_e_sha256": g.STAGE_E_SHA256, "parallel_result_sha256": g.PARALLEL_RESULT,
            "effective_policy_sha256": "d"*64, "guard_sha256": "e"*64,
            "unit_sha256": {x: "f"*64 for x in g.UNITS},
            "artifact_sha256": {x: pin or "f"*64 for x,pin in g.ARTIFACTS.items()},
            "accepted_at": datetime.now(timezone.utc).isoformat()}


def test_exact_receipt_only():
    r = receipt()
    assert g.validate_receipt(r) == r
    for field, bad in (("action", "other"), ("rollback_sha", "0"*40),
                       ("stage_e_sha256", "0"*64), ("parallel_result_sha256", "0"*64),
                       ("approval_sha256", ""), ("candidate_sha", g.LKG)):
        candidate = deepcopy(r); candidate[field] = bad
        with pytest.raises(g.Denied):
            g.validate_receipt(candidate)
    r["artifact_sha256"]["owner_approved_development_worker.py"] = "0"*64
    with pytest.raises(g.Denied):
        g.validate_receipt(r)


def topology():
    old = {x: {"LoadState": "not-found", "ActiveState": "inactive",
               "FragmentPath": "", "DropInPaths": "", "MainPID": "0"} for x in g.UNITS}
    new = {x: {"LoadState": "loaded", "FragmentPath": "/etc/systemd/system/"+x,
               "DropInPaths": "", "ActiveState": "active" if x in g.TIMERS else "inactive",
               "UnitFileState": "enabled" if x in g.TIMERS else "static",
               "User": "al", "Group": "al", "NoNewPrivileges": "yes", "PrivateTmp": "yes",
               "ProtectSystem": "strict", "ProtectHome": "read-only"} for x in g.UNITS}
    return old, new


def test_retired_old_and_exact_new_topology():
    old,new = topology()
    g.verify_topology(lambda n, user: (old if user else new)[n])
    for target, name, key, bad in (
        (old,g.TIMERS[0],"ActiveState","active"), (old,g.SERVICES[0],"LoadState","loaded"),
        (new,g.TIMERS[1],"UnitFileState","disabled"), (new,g.SERVICES[0],"User","root"),
        (new,g.SERVICES[1],"ProtectSystem","no"), (new,g.SERVICES[0],"DropInPaths","/unexpected"),
    ):
        before = target[name][key]; target[name][key] = bad
        with pytest.raises(g.Denied):
            g.verify_topology(lambda n, user: (old if user else new)[n])
        target[name][key] = before


def test_actual_service_context_required():
    for unit in g.SERVICES:
        g.verify_service_context("0::/system.slice/"+unit+"\n")
    for data in ("0::/user.slice/user-1000.slice/"+g.SERVICES[0],
                 "0::/system.slice/other.service", ""):
        with pytest.raises(g.Denied):
            g.verify_service_context(data)


def test_manifest_routes_only_accepted_timers_and_retains_names(monkeypatch):
    monkeypatch.setattr(runner, "pmv4_e_scheduling_mode", lambda: "replacement")
    monkeypatch.setattr(runner, "accepted_engineering_manager_routing",
                        lambda: {"system_timers": list(g.TIMERS)})
    calls = []
    required = set(runner.PMV4_E_USER_TIMERS + runner.SYSTEM_CONTROL_TIMERS + runner.PMV4_E_ROOT_TRIGGERS)
    def active(name, *, user):
        calls.append((name, user))
        if name in g.TIMERS: return not user
        return name in required
    monkeypatch.setattr(runner, "unit_active", active)
    out = runner.scheduled_control_alignment()
    assert all(out[x] == "active" for x in required)
    assert all((x,True) in calls and (x,False) in calls for x in g.TIMERS)
    monkeypatch.setattr(runner, "unit_active", lambda name,user: name in required)
    with pytest.raises(runner.ReleaseManagerError, match="retired user"):
        runner.scheduled_control_alignment()


def test_watchdog_does_not_gain_system_start_authority(monkeypatch):
    monkeypatch.setattr(wd, "pmv4_e_controlplane_mode", lambda: "replacement")
    monkeypatch.setattr(wd, "accepted_engineering_manager_routing",
                        lambda: {"system_timers": list(g.TIMERS)})
    monkeypatch.setattr(wd, "run", lambda *a,**kw: pytest.fail("unexpected systemd mutation"))
    assert wd.request_engineering_worker() == "queued_for_verified_system_engineering_timer"
    def denied(): raise PermissionError("invalid")
    monkeypatch.setattr(wd, "accepted_engineering_manager_routing", denied)
    assert wd.request_engineering_worker() == "deferred_engineering_manager_successor_invalid"


def test_pipeline_successor_binds_complete_stage_inventory_and_predecessor():
    r = receipt()
    r.update(schema_version="1.1", action=g.PIPELINE_ACTION,
             predecessor_candidate_sha="1"*40, predecessor_receipt_sha256="2"*64,
             engineering_source_sha=g.PIPELINE_SOURCE_SHA,
             pipeline_artifact_sha256={name:"3"*64 for name in g.PIPELINE_ARTIFACTS})
    assert g.validate_receipt(r) == r
    for key,value in (
        ("action",g.ACTION), ("predecessor_candidate_sha",r["candidate_sha"]),
        ("predecessor_receipt_sha256","not-a-digest"),
        ("engineering_source_sha","0"*40), ("pipeline_artifact_sha256",{}),
    ):
        bad=deepcopy(r);bad[key]=value
        with pytest.raises(g.Denied):g.validate_receipt(bad)


def test_pipeline_unit_covers_exact_runtime_write_roots():
    from tools import pmv4_e_engineering_manager_relocation as m
    root=Path(__file__).resolve().parents[1]
    unit=(root/m.TARGET/m.SERVICE).read_text()
    line=next(x for x in unit.splitlines() if x.startswith("ReadWritePaths="))
    assert set(line.split("=",1)[1].split()) == set(g.PIPELINE_WRITES)
    assert "ProtectSystem=strict" in unit and "ProtectHome=read-only" in unit
    assert "/var/lib/jason/openclaw" not in g.PIPELINE_WRITES
    assert "/home/al/jason-worktrees" not in g.PIPELINE_WRITES


def test_closed_loop_receipt_requires_exact_resolver_pin_and_preserves_old_receipts():
    old = receipt()
    old.update(schema_version="1.1", action=g.PIPELINE_ACTION,
               predecessor_candidate_sha="1"*40, predecessor_receipt_sha256="2"*64,
               engineering_source_sha=g.PIPELINE_SOURCE_SHA,
               pipeline_artifact_sha256={name:"3"*64 for name in g.PIPELINE_ARTIFACTS})
    assert g.validate_receipt(old) == old
    new = deepcopy(old)
    new["predecessor_candidate_sha"] = g.CLOSED_LOOP_PREDECESSOR
    with pytest.raises(g.Denied):
        g.validate_receipt(new)
    new["pipeline_artifact_sha256"]["issue_resolution_engine.py"] = "4"*64
    assert g.validate_receipt(new) == new
    for name in ("foreign.py", "jason_self_heal_watchdog.py"):
        bad = deepcopy(new)
        bad["pipeline_artifact_sha256"][name] = "5"*64
        with pytest.raises(g.Denied):
            g.validate_receipt(bad)
    bad = deepcopy(old)
    bad["pipeline_artifact_sha256"]["issue_resolution_engine.py"] = "4"*64
    with pytest.raises(g.Denied):
        g.validate_receipt(bad)


def test_breaker_custody_successor_keeps_the_complete_closed_loop_inventory():
    row = receipt()
    row.update(schema_version="1.1", action=g.PIPELINE_ACTION,
               predecessor_candidate_sha=g.BREAKER_CUSTODY_PREDECESSOR,
               predecessor_receipt_sha256="2"*64,
               engineering_source_sha=g.PIPELINE_SOURCE_SHA,
               pipeline_artifact_sha256={name:"3"*64 for name in g.CLOSED_LOOP_PIPELINE_ARTIFACTS})
    assert g.validate_receipt(row) == row
    for name in ("issue_resolution_engine.py", "release_breaker_recovery_manager.py"):
        bad = deepcopy(row)
        del bad["pipeline_artifact_sha256"][name]
        with pytest.raises(g.Denied):
            g.validate_receipt(bad)

def test_watchdog_diagnostic_admission_never_asserts_failed_peer_healthy():
    old,new = topology()
    query=lambda n,user:(old if user else new)[n]
    peer=g.SERVICES[0]
    new[peer].update(ActiveState="failed",MainPID="0")
    # Ordinary status and engineering retain exact fail-closed semantics.
    with pytest.raises(g.Denied,match="NOT_OPERATIONAL"):
        g.verify_topology(query)
    assert g.verify_topology(query,diagnostic_watchdog=True)==peer
    for key,bad in (("MainPID","123"),("ProtectSystem","no"),
                    ("User","root"),("DropInPaths","/foreign")):
        before=new[peer].get(key);new[peer][key]=bad
        with pytest.raises(g.Denied):
            g.verify_topology(query,diagnostic_watchdog=True)
        new[peer][key]=before
    new[g.SERVICES[1]].update(ActiveState="failed",MainPID="0")
    with pytest.raises(g.Denied):
        g.verify_topology(query,diagnostic_watchdog=True)

def test_failed_manager_attestation_requires_both_quiescent_exact_units():
    old,new=topology()
    query=lambda n,user:(old if user else new)[n]
    for service in g.SERVICES:
        new[service].update(ActiveState="failed",MainPID="0")
    assert g.verify_topology(query,attest_failed_pair=True)==tuple(sorted(g.SERVICES))
    with pytest.raises(g.Denied):
        g.verify_topology(query)
    for key,value in (("MainPID","123"),("DropInPaths","/unknown"),("ProtectHome","no"),("ActiveState","inactive")):
        prior=new[g.SERVICES[0]][key]
        new[g.SERVICES[0]][key]=value
        with pytest.raises(g.Denied):
            g.verify_topology(query,attest_failed_pair=True)
        new[g.SERVICES[0]][key]=prior


def test_local_reasoning_worker_pin_only_changes_for_exact_new_successor():
    r=receipt()
    r.update(schema_version="1.1",action=g.PIPELINE_ACTION,
             predecessor_candidate_sha=g.WATCHDOG_RECOVERY_PREDECESSOR,
             predecessor_receipt_sha256="2"*64,engineering_source_sha=g.PIPELINE_SOURCE_SHA,
             pipeline_artifact_sha256={name:"3"*64 for name in g.CLOSED_LOOP_PIPELINE_ARTIFACTS})
    r["artifact_sha256"]["owner_approved_development_worker.py"]=g.LOCAL_REASONING_OWNER_WORKER_SHA256
    assert g.validate_receipt(r)==r
    wrong=deepcopy(r);wrong["artifact_sha256"]["owner_approved_development_worker.py"]=g.ARTIFACTS["owner_approved_development_worker.py"]
    with pytest.raises(g.Denied):g.validate_receipt(wrong)
    wrong=deepcopy(r);wrong["predecessor_candidate_sha"]=g.BREAKER_CUSTODY_PREDECESSOR
    with pytest.raises(g.Denied):g.validate_receipt(wrong)
