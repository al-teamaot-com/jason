"""PMv4 E cutover root preflight negative and positive synthetic proof tests."""
from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest

from tools import pmv4_e_root_cutover_preflight as gate


def good():
    return {
        "uid":0,"root_cda1":"verified","root_canary":"verified",
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


def test_root_collect_never_forges_other_authority_evidence(tmp_path,monkeypatch):
    from tools import pmv4_e_root_receipt_readback as historical
    from tools import pmv4_e_canary_acceptance_readback as canary
    monkeypatch.setattr(gate.os,"geteuid",lambda:0)
    monkeypatch.setattr(historical,"inspect",lambda:{"status":"pre_retirement_root_acceptance_verified"})
    monkeypatch.setattr(canary,"inspect",lambda:{"status":"native_providerfree_canary_accepted_and_removed"})
    monkeypatch.setattr(gate,"MARKER",tmp_path/"absent-marker")
    calls=[]
    def run(cmd,**kwargs):
        calls.append(tuple(cmd))
        return SimpleNamespace(returncode=0,stdout="active\n")
    result=gate.collect(runner=run)
    assert len(calls)==len(gate.OLD_USER|gate.NEW_USER|gate.PRESERVE_USER)+len(
        gate.OLD_ROOT|gate.NEW_ROOT|gate.PRESERVE_ROOT)
    assert all("is-active" in c for c in calls)
    assert result["source_policy_valid"] is False
    assert result["breaker"]=="unknown"
    with pytest.raises(gate.RootPreflightDenied):
        gate.evaluate(result)


def test_source_module_no_mutation_apis():
    from pathlib import Path
    s=(Path(__file__).resolve().parents[2]/"tools/pmv4_e_root_cutover_preflight.py").read_text()
    for forbidden in ("subprocess.Popen(","os.system(","systemctl start",
                      "systemctl stop","systemctl disable","docker restart",
                      "os.replace(","requests.post("):
        assert forbidden not in s
