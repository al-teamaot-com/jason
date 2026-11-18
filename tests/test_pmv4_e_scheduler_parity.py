"""Real existing durable engine scheduler, isolated from production/providers."""
from __future__ import annotations

from hashlib import sha256
import fcntl
import json
from pathlib import Path
import os
import subprocess
import sys
from types import SimpleNamespace

import pytest

from tools import pmv4_e_scheduler_parity as stage
from tools import pmv3_work_engine as existing


SOURCE=Path(__file__).resolve().parents[1]/"config/production-desired-state.json"


def create_state(tmp_path,*,action="read_engineering_inventory",
                 idempotent=True,approval_required=False):
    state_path=tmp_path/"existing-work-state.json"
    lock_path=tmp_path/"scheduler.lock"
    state=existing.empty_state()
    item=existing.make_item("PMV4-E-SIM-001",action,
        idempotent=idempotent,approval_required=approval_required,
        approval_request_id="approved-specific-release" if approval_required else "")
    assert existing.admit(state,item)
    existing.atomic_write(state_path,state)
    return state_path,lock_path


def tick(path,lock,action="read_engineering_inventory",handler=None):
    handler=handler or (lambda item,key:
        existing.Outcome(status="complete",receipt="read-evidence-"+key))
    return stage.isolated_preproduction_tick(
        path,lock,handlers={action:handler},facts={})


def test_exact_six_legacy_to_six_replacement_source_only_delta():
    source=stage.read_source_policy(SOURCE)
    result=stage.plan_exact_unit_delta(source)
    assert set(result["retire_user_units"])==stage.USER_LEGACY
    assert set(result["retire_system_units"])==stage.ROOT_LEGACY
    assert set(result["add_user_units"])==stage.USER_REPLACEMENT
    assert set(result["add_system_units"])==stage.ROOT_REPLACEMENT
    candidate=result["candidate_policy"]
    for key in ("required_user_units","required_system_units"):
        before=set(source[key]);after=set(candidate[key])
        assert len(before)==len(after)
        assert (before & stage.CONTINUITY_USER) == (after & stage.CONTINUITY_USER)
        assert (before & stage.CONTINUITY_ROOT) == (after & stage.CONTINUITY_ROOT)
    for k in ("required_containers","allowed_running_containers",
              "max_stopped_rollback_containers",
              "rollback_container_prefixes","forbidden_execution_prefixes"):
        assert source[k]==candidate[k]
    assert result["prior_policy_sha256"]==sha256(stage.canon(source)).hexdigest()
    assert result["candidate_policy_sha256"]==sha256(stage.canon(candidate)).hexdigest()
    assert result["owner_approval_issued"] is False
    assert result["parity_accepted"] is False
    assert result["production_mutations"] is False
    assert result["retirement_authorized"] is False
    assert result["core_mcp_restarts"]==0


def test_source_policy_never_preemptively_removes_required_legacy():
    original=stage.read_source_policy(SOURCE)
    bad=dict(original)
    bad["required_user_units"]=sorted(
        set(bad["required_user_units"])-{"jason-release-manager.timer"})
    with pytest.raises(stage.PMv4SchedulingDenied,match="LEGACY_SOURCE_UNIT_SET_NOT_FOUND"):
        stage.plan_exact_unit_delta(bad)


def test_critical_security_monitor_removal_denied():
    original=stage.read_source_policy(SOURCE)
    bad=dict(original)
    bad["required_system_units"]=sorted(
        set(bad["required_system_units"])-
        {"jason-production-drift-watchdog.timer"})
    with pytest.raises(stage.PMv4SchedulingDenied,match="SAFETY_UNDECLARED"):
        stage.plan_exact_unit_delta(bad)


def test_durable_existing_engine_claim_and_receipt_are_not_replayed(tmp_path):
    state,lock=create_state(tmp_path)
    calls=[]
    def approved_read(item,key):
        calls.append((item["id"],key))
        return existing.Outcome(status="complete",receipt="accepted-"+key)
    one=tick(state,lock,handler=approved_read)
    two=tick(state,lock,handler=approved_read)
    assert one["metrics"]["completed"]==1
    assert two["metrics"]["completed"]==1
    assert one["receipts"]==two["receipts"]==1
    assert len(calls)==1
    assert two["cycle"]==one["cycle"]+1
    assert two["provider_calls"]==two["production_mutations"]==0
    assert two["release_promotions"]==two["owner_approvals_issued"]==0


def test_interrupted_idempotent_claim_resumes_after_process_restarts(tmp_path):
    state,lock=create_state(tmp_path)
    class Crash(BaseException):
        pass
    def killed_after_checkpoint(item,key):
        raise Crash()
    with pytest.raises(Crash):
        tick(state,lock,handler=killed_after_checkpoint)
    persisted=existing.load_state(state)
    assert persisted["items"]["PMV4-E-SIM-001"]["phase"]=="running"
    assert persisted["cycle"]==1
    code=f"""
from tools import pmv4_e_scheduler_parity as stage
from tools import pmv3_work_engine as e
from pathlib import Path
result=stage.isolated_preproduction_tick(
 Path({str(state)!r}),Path({str(lock)!r}),
 handlers={{"read_engineering_inventory":lambda i,k:e.Outcome(status="complete",receipt="recovered-"+k)}})
assert result["metrics"]["completed"]==1
print("NEW_PROCESS_RECOVERY=PASS",result["receipts"])
"""
    res=subprocess.run([sys.executable,"-B","-c",code],
        cwd=str(SOURCE.parents[1]),capture_output=True,text=True,timeout=15,
        env={**os.environ,"PYTHONPATH":str(SOURCE.parents[1])})
    assert res.returncode==0,res.stderr
    assert "NEW_PROCESS_RECOVERY=PASS" in res.stdout
    assert existing.load_state(state)["items"]["PMV4-E-SIM-001"]["phase"]=="complete"


def test_interrupted_non_idempotent_never_replays_unknown_outcome(tmp_path):
    state,lock=create_state(tmp_path,idempotent=False)
    class Crash(BaseException):
        pass
    with pytest.raises(Crash):
        tick(state,lock,handler=lambda *_:(_ for _ in ()).throw(Crash()))
    executed=[]
    tick(state,lock,handler=lambda item,key:(
        executed.append(key),existing.Outcome(status="complete"))[1])
    item=existing.load_state(state)["items"]["PMV4-E-SIM-001"]
    assert item["phase"]=="waiting"
    assert item["reason"]=="indeterminate_execution_requires_reconciliation"
    assert not executed


def test_no_signed_exact_owner_approval_means_no_release_claim(tmp_path):
    state,lock=create_state(tmp_path,action="read_release_approval_offer",
                            approval_required=True)
    count=[]
    result=tick(state,lock,action="read_release_approval_offer",
        handler=lambda item,key:(
            count.append(key),existing.Outcome(status="complete"))[1])
    assert result["receipts"]==0
    assert result["owner_approvals_issued"]==0
    assert existing.load_state(state)["items"]["PMV4-E-SIM-001"]["phase"]=="runnable"
    assert count==[]


def test_missing_work_adapter_blocks_not_invokes_provider(tmp_path):
    state,lock=create_state(tmp_path,action="read_engineering_inventory")
    result=stage.isolated_preproduction_tick(
        state,lock,handlers={},facts={})
    assert result["metrics"]["blocked"]==1
    item=existing.load_state(state)["items"]["PMV4-E-SIM-001"]
    assert item["last_outcome"]["reason"]=="missing_trusted_preproduction_adapter"


@pytest.mark.parametrize("action",[
    "provider.autotask.ticket.write","docker_restart",
    "pmv3_release_manager_promote","source_code_exec",
    "start_legacy_timer","disable_root_drift",
])
def test_unknown_or_provider_actions_not_registered(tmp_path,action):
    state,lock=create_state(tmp_path,action=action)
    with pytest.raises(stage.PMv4SchedulingDenied,match="UNREVIEWED_SCHEDULER_ADAPTER"):
        stage.isolated_preproduction_tick(
            state,lock,handlers={action:lambda *_:None})
    assert existing.load_state(state)["cycle"]==0


def test_two_concurrent_timer_claims_use_one_shared_inode(tmp_path):
    state,lock=create_state(tmp_path)
    with stage.readonly_isolated_lock(lock):
        with pytest.raises(stage.PMv4SchedulingDenied,match="CONCURRENT_SCHEDULER_CLAIM"):
            tick(state,lock)
        assert existing.load_state(state)["cycle"]==0
    done=tick(state,lock)
    assert done["metrics"]["completed"]==1


def test_lock_and_state_must_be_disposable_not_protected_production(tmp_path):
    state,lock=create_state(tmp_path)
    with pytest.raises(stage.PMv4SchedulingDenied,match="TEST_ONLY"):
        stage.isolated_preproduction_tick(
            Path("/var/lib/jason/openclaw/release-manager/current.json"),lock,
            handlers={})
    with pytest.raises(stage.PMv4SchedulingDenied,match="TEST_ONLY"):
        stage.isolated_preproduction_tick(
            state,Path("/var/lib/jason/pmv4-e.lock"),handlers={})


def test_unknown_outcome_fails_before_falsely_completing(tmp_path):
    state,lock=create_state(tmp_path)
    with pytest.raises(stage.PMv4SchedulingDenied,match="TEST_HANDLER_UNTRUSTED"):
        tick(state,lock,handler=lambda *_:existing.Outcome(status="executed"))
    assert existing.load_state(state)["items"]["PMV4-E-SIM-001"]["phase"]=="running"


def test_no_actual_production_install_or_retirement_in_scheduler_source():
    code=Path(stage.__file__).read_text()
    assert "systemctl stop" not in code
    assert "systemctl disable" not in code
    assert "docker compose up" not in code
    assert "subprocess.run(" not in code
    assert "provider_api_key" not in code
    assert '"retirement_authorized":False' in code
    assert '"production_mutations":False' in code
