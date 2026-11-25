"""Provider-free tests of the exact successor scope and native rollback ordering."""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from tools import pmv4_e_engineering_manager_install as m


def plan():
    return {
        "action":"REPAIR-EXACT-PMV4-ENGINEERING-PIPELINE-CONTRACT",
        "policy":{"candidate_sha":"a"*40,"rollback_sha":m.LKG},
        "predecessor_candidate_sha":m.PIPELINE_BASELINE,
        "queue_cutover":False,"provider_writes":False,"production_authority":False,
        "freeze_or_hold_change":False,"runtime_or_mcp_restart_allowed":False,
        "rollback_authorized":True,"temporary_timer_stops":list(m.TIMERS),
        "resume_after_verified_cutover":True,
        "restore_pause_on_failed_scheduled_acceptance":True,
        "restore_pause_on_completed_work_stage_failure":True,
    }


@pytest.mark.parametrize("key,value",[
    ("queue_cutover",True),("provider_writes",True),("production_authority",True),
    ("freeze_or_hold_change",True),("runtime_or_mcp_restart_allowed",True),
    ("rollback_authorized",False),("temporary_timer_stops",["foreign.timer"]),
    ("resume_after_verified_cutover",False),
    ("restore_pause_on_completed_work_stage_failure",False),
    ("predecessor_candidate_sha","0"*40),
])
def test_scope_rejects_authority_and_target_expansion(key,value):
    p=plan()
    assert m.pipeline_scope_sha(p)==m.digest(m.canon(p))
    p[key]=value
    with pytest.raises(PermissionError):m.pipeline_scope_sha(p)


def test_unapproved_scope_never_reaches_owner_or_mutation():
    a=object.__new__(m.PipelineSuccessor)
    a.n={"owner":Mock()}
    with pytest.raises(PermissionError,match="EXACT_SCOPE"):
        a.apply(plan(),"0"*64)
    a.n["owner"].assert_not_called()


def test_native_existing_receipt_and_stage_inventory_are_mandatory():
    from tools import pmv4_e_engineering_manager_guard as g
    a=object.__new__(m.PipelineSuccessor)
    a.g={"ARTIFACTS":g.ARTIFACTS,"PIPELINE_ARTIFACTS":g.PIPELINE_ARTIFACTS}
    a.release=m.ROOT/"releases"/("a"*40)/"tools"
    targets=a.approved_targets()
    assert {m.PIPELINE_UNIT,m.PIPELINE_PROGRAM,m.MANAGER_GUARD,m.RECEIPT,m.PAUSE,
            a.release.parent/"predecessor.json"}.issubset(targets)
    assert {p.name for p in targets if p.parent==a.release}==set(g.ARTIFACTS)|set(g.PIPELINE_ARTIFACTS)
    assert m.POLICY not in targets and m.ENV not in targets
    assert not any(p.name in ("production-deployment-freeze","auto-promotion-incident-hold",
                               "production-control-state.json") for p in targets)


def test_quiesce_never_treats_running_or_failed_service_as_ready(monkeypatch):
    a=object.__new__(m.PipelineSuccessor)
    a.properties=lambda n,user: {"ActiveState":"failed","MainPID":"0"}
    monkeypatch.setattr(m.time,"sleep",lambda _:None)
    with pytest.raises(PermissionError,match="NOT_QUIESCENT"):
        a.quiesce((m.SERVICES[0],),1)
    a.quiesce((m.SERVICES[0],),1,rollback=True)
    a.properties=lambda n,user: {"ActiveState":"activating","MainPID":"123"}
    with pytest.raises(PermissionError,match="NOT_QUIESCENT"):
        a.quiesce((m.SERVICES[0],),1,rollback=True)


def test_durable_scope_guard_and_full_stage_acceptance_are_present():
    source=Path(m.__file__).read_text()
    assert 'self.actor = self.n["owner"](plan)' in source
    assert 'self.persist()' in source
    assert 'self.namespace_probe()' in source
    assert 'self.native_revalidation()' in source
    assert 'all(x.get("status")=="succeeded" for x in pipeline["stages"].values())' in source
    assert 'PIPELINE_SCHEDULED_WATCHDOG_ACCEPTANCE_PENDING' in source
    assert 'self.restore()' in source
