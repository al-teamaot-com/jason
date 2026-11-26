"""PMv4 E cutover root preflight negative and positive synthetic proof tests."""
from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest

from tools import pmv4_e_root_cutover_preflight as gate


def healthy_native():
    return {name:{"id":name,"image":"sha256:"+"a"*64,"started_at":"2026-11-20T00:00:00Z",
                  "running":True,"health":"healthy"} for name in gate.NATIVE_PROTECTED}


def good():
    return {
        "uid":0,"native_protected":healthy_native(),"root_cda1":"verified","root_canary":"verified",
        "source_policy_valid":True,"root_policy_valid":True,
        "marker_absent":True,"breaker":"closed","freeze":"unchanged",
        "ticket_unique_owner":True,"scan_fresh":True,"duplicate_items":0,
        "user_active_old":{u:True for u in gate.OLD_USER},
        "root_active_old":{u:True for u in gate.OLD_ROOT},
        "user_active_new":{u:False for u in gate.NEW_USER},
        "root_active_new":{u:False for u in gate.NEW_ROOT},
        "user_monitoring":{u:True for u in gate.PRESERVE_USER},
        "root_monitoring":{u:True for u in gate.PRESERVE_ROOT},
    }


def test_all_six_old_and_six_new_with_proven_root_evidence_pass_source_gate():
    r=gate.evaluate(good())
    assert r["status"]=="read_only_root_preflight_source_conditions_passed"
    assert r["production_mutations"] is False
    assert r["owner_release_authorized"] is False
    assert r["pmv3_retirement_authorized"] is False
    assert (r["legacy_triggers_verified"],r["replacement_triggers_verified_inert"])==(6,6)


@pytest.mark.parametrize("key,bad",[
    ("uid",1000),("root_cda1","unknown"),("root_canary","unknown"),
    ("source_policy_valid",False),("root_policy_valid",False),
    ("marker_absent",False),("breaker","open"),("freeze","changed"),
    ("ticket_unique_owner",False),("scan_fresh",False),
    ("duplicate_items",2),
])
def test_missing_or_invalid_protected_proof_blocks(key,bad):
    x=good()
    x[key]=bad
    with pytest.raises(gate.RootPreflightDenied):
        gate.evaluate(x)


@pytest.mark.parametrize("key",[
    "user_active_old","root_active_old","user_active_new",
    "root_active_new","user_monitoring","root_monitoring",
])
def test_missing_one_trigger_or_monitoring_proof_blocks(key):
    x=good()
    name=next(iter(x[key]))
    x[key].pop(name)
    with pytest.raises(gate.RootPreflightDenied):
        gate.evaluate(x)


def test_old_timer_inactive_blocks():
    x=good()
    x["user_active_old"][next(iter(gate.OLD_USER))]=False
    with pytest.raises(gate.RootPreflightDenied):
        gate.evaluate(x)


def test_new_timer_already_active_blocks():
    x=good()
    x["root_active_new"][next(iter(gate.NEW_ROOT))]=True
    with pytest.raises(gate.RootPreflightDenied):
        gate.evaluate(x)


def test_nonroot_collect_fails_before_any_host_command(monkeypatch):
    monkeypatch.setattr(gate.os,"geteuid",lambda:1000)
    def fail(*a,**kw):
        pytest.fail("host read was attempted under wrong uid")
    with pytest.raises(gate.RootPreflightDenied,match="ROOT_ONLY"):
        gate.collect(runner=fail)


def test_root_collect_never_forges_ticket_ownership(tmp_path,monkeypatch):
    from tools import pmv4_e_root_receipt_readback as historical
    from tools import pmv4_e_canary_acceptance_readback as canary
    from tools import pmv4_e_retirement_readiness as retirement
    from tools import pmv4_e_ticket_owner_readback as ownerproof
    monkeypatch.setattr(gate.os,"geteuid",lambda:0)
    monkeypatch.setattr(historical,"inspect",lambda:{"status":"pre_retirement_root_acceptance_verified"})
    monkeypatch.setattr(canary,"inspect",lambda:{"status":"native_providerfree_canary_accepted_and_removed"})
    monkeypatch.setattr(gate,"_root_evidence",lambda **kw:{"root_cda1":"verified",
        "root_canary":"verified","root_policy_valid":True,
        "source_policy_valid":True,"breaker":"closed","freeze":"unchanged"})
    monkeypatch.setattr(retirement,"scan_summary",lambda:{"status":"fresh","duplicate_items":0})
    monkeypatch.setattr(ownerproof,"inspect",lambda **kw:{"status":
        "live_external_ticket_core_exclusive_owner_verified","unique_owner":True,
        "exclusive_owner_count":1,"lock_inode":123,"lock_owner_pid":550,
        "container_init_pid":501})
    monkeypatch.setattr(gate,"MARKER",tmp_path/"absent-marker")
    monkeypatch.setattr(gate,"live_native_protected",lambda **kwargs:healthy_native())
    calls=[]
    def run(cmd,**kwargs):
        calls.append(tuple(cmd))
        return SimpleNamespace(returncode=0,stdout="active\n")
    result=gate.collect(runner=run)
    assert len(calls)==len(gate.OLD_USER|gate.NEW_USER|gate.PRESERVE_USER)+len(
        gate.OLD_ROOT|gate.NEW_ROOT|gate.PRESERVE_ROOT)
    assert all("is-active" in c for c in calls)
    assert result["root_policy_valid"] is True
    assert result["ticket_unique_owner"] is True
    assert result["ticket_owner_evidence"]["lock_owner_pid"]==550
    with pytest.raises(gate.RootPreflightDenied,match="UNIT_STATE_MISMATCH"):
        gate.evaluate(result)


def test_root_evidence_rejects_fake_historical_receipts():
    with pytest.raises(gate.RootPreflightDenied,match="C_D_A1_ROOT_RECEIPT_UNVERIFIED"):
        gate._root_evidence(historical={"status":"arbitrary"},
                            canary={"status":"native_providerfree_canary_accepted_and_removed"})


def test_root_evidence_rejects_fake_canary_without_absence_checks():
    h={"status":"pre_retirement_root_acceptance_verified",
       "stage_c_root_acceptance_verified":True,
       "stage_d_root_acceptance_verified":True,
       "a1_root_acceptance_verified":True}
    with pytest.raises(gate.RootPreflightDenied,match="NATIVE_CANARY_UNVERIFIED"):
        gate._root_evidence(historical=h,canary={"status":"native_providerfree_canary_accepted_and_removed"})


def test_source_module_no_mutation_apis():
    from pathlib import Path
    s=(Path(__file__).resolve().parents[2]/"tools/pmv4_e_root_cutover_preflight.py").read_text()
    for forbidden in ("subprocess.Popen(","os.system(","systemctl start",
                      "systemctl stop","systemctl disable","docker restart",
                      "os.replace(","requests.post("):
        assert forbidden not in s


@pytest.mark.skipif(__import__("os").geteuid()!=0,reason="isolated privileged CI only")
def test_root_only_file_readback_permission_boundary(tmp_path):
    import os,json
    protected=tmp_path/"root-policy.json"
    protected.write_text(json.dumps({"schema_version":"1.0"}))
    protected.chmod(0o600)
    assert protected.stat().st_uid==0
    assert gate._root_json(protected)=={"schema_version":"1.0"}
    protected.chmod(0o666)
    with pytest.raises(gate.RootPreflightDenied):
        gate._root_json(protected)
    protected.chmod(0o600)
    link=tmp_path/"link.json"
    link.symlink_to(protected)
    with pytest.raises(gate.RootPreflightDenied):
        gate._root_json(link)


@pytest.mark.skipif(__import__("os").geteuid()!=0,reason="isolated privileged CI only")
def test_root_readback_recognizes_exact_service_user_owned_records(tmp_path):
    import os,json
    protected=tmp_path/"control.json"
    protected.write_text(json.dumps({"circuit_breaker":{"state":"closed"}}))
    protected.chmod(0o600)
    os.chown(protected,1000,1000)
    assert gate._root_json(protected,allowed_uid=1000)["circuit_breaker"]["state"]=="closed"
    with pytest.raises(gate.RootPreflightDenied):
        gate._root_json(protected,allowed_uid=0)



def test_root_collect_rejects_unverified_live_kernel_owner(monkeypatch):
    from tools import pmv4_e_root_receipt_readback as historical
    from tools import pmv4_e_canary_acceptance_readback as canary
    from tools import pmv4_e_retirement_readiness as retirement
    from tools import pmv4_e_ticket_owner_readback as ownerproof
    monkeypatch.setattr(gate.os,"geteuid",lambda:0)
    monkeypatch.setattr(historical,"inspect",lambda:{"status":"pre_retirement_root_acceptance_verified"})
    monkeypatch.setattr(canary,"inspect",lambda:{"status":"native_providerfree_canary_accepted_and_removed"})
    monkeypatch.setattr(gate,"_root_evidence",lambda **kw:{"root_cda1":"verified",
        "root_canary":"verified","root_policy_valid":True,
        "source_policy_valid":True,"breaker":"closed","freeze":"unchanged"})
    monkeypatch.setattr(retirement,"scan_summary",lambda:{"status":"fresh","duplicate_items":0})
    monkeypatch.setattr(ownerproof,"inspect",lambda **kw:{"status":"unverified","unique_owner":False})
    monkeypatch.setattr(gate,"live_native_protected",lambda **kwargs:healthy_native())
    with pytest.raises(gate.RootPreflightDenied,match="CURRENT_TICKET_DISPATCH_OWNER_UNVERIFIED"):
        gate.collect(runner=lambda *a,**kw:SimpleNamespace(
            returncode=0,stdout="inactive\\n"))


@pytest.mark.parametrize("user,units",[
    (True,gate.NEW_USER),(False,gate.NEW_ROOT),
])
def test_actual_systemd_notfound_is_inert_for_only_reviewed_new_units(user,units):
    """Observed live Jason 2026-11-19: is-active exit=4 text='inactive'."""
    seen=[]
    def runner(argv,**kwargs):
        seen.append(argv)
        return SimpleNamespace(returncode=4,stdout="inactive\n",stderr="")
    for unit in units:
        assert gate._active(unit,user=user,runner=runner) is False
    assert len(seen)==len(units)


@pytest.mark.parametrize("user,units",[
    (True,gate.OLD_USER),(False,gate.OLD_ROOT),
    (True,gate.PRESERVE_USER),(False,gate.PRESERVE_ROOT),
])
def test_no_notfound_exception_for_required_legacy_or_monitoring(user,units):
    def runner(argv,**kwargs):
        return SimpleNamespace(returncode=4,stdout="inactive\n",stderr="")
    for unit in units:
        with pytest.raises(gate.RootPreflightDenied,
                           match="SYSTEMD_READBACK_UNAVAILABLE"):
            gate._active(unit,user=user,runner=runner)


def test_unknown_or_active_status_for_notfound_new_unit_is_denied():
    unit=next(iter(gate.NEW_ROOT))
    for out in ("unknown\n","active\n","failed\n","not-found\n",""):
        def runner(argv,**kwargs):
            return SimpleNamespace(returncode=4,stdout=out,stderr="")
        with pytest.raises(gate.RootPreflightDenied,
                           match="NEW_TRIGGER_ABSENCE_AMBIGUOUS"):
            gate._active(unit,user=False,runner=runner)


def test_notfound_new_unit_nonfour_failure_code_denied():
    unit=next(iter(gate.NEW_USER))
    for code in (1,2,5,127):
        def runner(argv,**kwargs):
            return SimpleNamespace(returncode=code,stdout="inactive\n",stderr="")
        with pytest.raises(gate.RootPreflightDenied,
                           match="SYSTEMD_READBACK_UNAVAILABLE"):
            gate._active(unit,user=True,runner=runner)


def test_canary_freeze_readback_accepts_exact_service_user_owned_file(tmp_path,monkeypatch):
    import hashlib,os
    from tools import pmv4_e_canary_acceptance_readback as canary
    freeze=tmp_path/"production-deployment-freeze"
    raw=b"frozen-production-state\n"
    freeze.write_bytes(raw)
    freeze.chmod(0o600)
    monkeypatch.setattr(canary,"FREEZE_PATH",freeze)
    monkeypatch.setattr(canary,"FREEZE_UID",freeze.stat().st_uid)
    monkeypatch.setattr(canary,"FREEZE_GID",freeze.stat().st_gid)
    monkeypatch.setattr(canary,"root_data",lambda path,**kwargs:b"protected-policy")
    monkeypatch.setattr(canary,"ACTIVE",tmp_path/"absent-active-pointer")
    def runner(*args,**kwargs):
        return SimpleNamespace(returncode=0,stdout="",stderr="")
    result=canary.probe_clean_host(
        runner=runner,expected_freeze_sha=hashlib.sha256(raw).hexdigest(),
        expected_policy_sha=hashlib.sha256(b"protected-policy").hexdigest())
    assert result["freeze_sha256"]==hashlib.sha256(raw).hexdigest()


@pytest.mark.parametrize("field,value",[
    ("st_uid",2000),("st_gid",2000),("st_mode",0o100640),
    ("st_mode",0o120777),("st_nlink",2),("st_size",0),
])
def test_canary_freeze_metadata_rejects_wrong_identity_or_mode(field,value):
    from types import SimpleNamespace
    from tools import pmv4_e_canary_acceptance_readback as canary
    metadata={"st_mode":0o100600,"st_uid":1000,"st_gid":1000,
              "st_nlink":1,"st_size":10}
    metadata[field]=value
    with pytest.raises(canary.CanaryAcceptanceDenied,
                       match="SERVICE_FILE_UNTRUSTED"):
        canary.validate_service_file_meta(
            SimpleNamespace(**metadata),path_name="production-deployment-freeze")


@pytest.mark.parametrize("health",["unhealthy","starting"])
def test_shadow_unhealthy_denies_even_with_verified_historical_receipts(health):
    evidence=good()
    evidence["native_protected"]["jason-pmv4-shadow-gateway"]["health"]=health
    with pytest.raises(gate.RootPreflightDenied,match="NATIVE_PROTECTED_UNHEALTHY:jason-pmv4-shadow-gateway"):
        gate.evaluate(evidence)


def test_missing_native_live_snapshot_cannot_pass_historical_preflight():
    evidence=good();evidence.pop("native_protected")
    with pytest.raises(gate.RootPreflightDenied,match="SNAPSHOT_INCOMPLETE"):
        gate.evaluate(evidence)


def test_live_native_health_reads_only_exact_original_protected_containers():
    import json
    calls=[]
    def run(cmd,**kwargs):
        calls.append(cmd);name=cmd[-1]
        assert cmd==["/usr/bin/docker","inspect","--type","container",name]
        return SimpleNamespace(returncode=0,stdout=json.dumps([{
            "Id":name,"Image":"sha256:"+"a"*64,
            "State":{"Running":True,"StartedAt":"2026-11-20T00:00:00Z"}}]))
    result=gate.live_native_protected(runner=run)
    assert set(result)==set(gate.NATIVE_PROTECTED)
    assert len(calls)==5 and all(row["health"]=="none" for row in result.values())


def test_live_native_health_rejects_non_container_or_malformed_docker_response():
    with pytest.raises(gate.RootPreflightDenied):
        gate.live_native_protected(runner=lambda *a,**k:SimpleNamespace(returncode=0,stdout="{}"))
