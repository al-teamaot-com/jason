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


def todo_plan():
    p=plan()
    p.update(predecessor_candidate_sha=m.TODO_CONFLICT_BASELINE,
             worker_replacements=sorted(m.TODO_CONFLICT_WORKERS),
             required_scheduled_cycles=2,
             quarantine_existing_todo_identity="TODO-OPS-013",
             conflicted_issues=[1459,1500],preserve_existing_issue_authority=True)
    return p


@pytest.mark.parametrize("key,value",[
    ("worker_replacements",["owner_approved_development_worker.py"]),
    ("required_scheduled_cycles",1),
    ("quarantine_existing_todo_identity","TODO-OPS-999"),
    ("conflicted_issues",[1500]),
    ("preserve_existing_issue_authority",False),
])
def test_todo_scope_cannot_expand_worker_or_approval_authority(key,value):
    p=todo_plan()
    assert m.pipeline_scope_sha(p)==m.digest(m.canon(p))
    p[key]=value
    with pytest.raises(PermissionError):m.pipeline_scope_sha(p)


def test_todo_successor_targets_existing_pipeline_without_new_authority():
    from tools import pmv4_e_engineering_manager_guard as g
    a=object.__new__(m.PipelineSuccessor)
    a.predecessor=m.TODO_CONFLICT_BASELINE
    a.changed_workers=m.TODO_CONFLICT_WORKERS
    a.g={"ARTIFACTS":g.ARTIFACTS,"PIPELINE_ARTIFACTS":g.PIPELINE_ARTIFACTS}
    a.release=m.ROOT/"releases"/("a"*40)/"tools"
    paths=a.approved_targets()
    assert {p.name for p in paths if p.parent==m.LIB}==set(m.TODO_CONFLICT_WORKERS)|{m.PIPELINE_PROGRAM.name}
    assert m.POLICY not in paths and m.ENV not in paths
    assert not any(p.name in ("production-deployment-freeze","auto-promotion-incident-hold",
                              "owner_approved_development_worker.py") and p.parent==m.LIB for p in paths)


def todo_cycle_fixture(tmp_path,monkeypatch):
    from contextlib import nullcontext
    from datetime import datetime,timezone
    a=object.__new__(m.PipelineSuccessor)
    a.predecessor=m.TODO_CONFLICT_BASELINE
    a.directory=tmp_path
    data={}
    def read(p,*args):
        if p.parent==tmp_path: return p.read_bytes()
        return m.canon(data[p.name])
    def write(p,raw,mode):
        assert mode==0o400 and not p.exists()
        p.write_bytes(raw)
    a.n={"locks":nullcontext,"read":read,"write":write}
    a.p={"read":read}
    a.command=Mock(return_value=b"ENGINEERING_STAGE_END name=todo_intake status=succeeded\n")
    monkeypatch.setattr(m,"snapshot",lambda p:None)
    def cycle(n):
        minute=5*n
        start=datetime(2026,11,25,19,minute,tzinfo=timezone.utc)
        finish=start.replace(second=20)
        data["todo-intake-state.json"]={
            "observed_at":start.replace(second=5).isoformat(),
            "identity_conflicts":{"TODO-OPS-013":{"status":"quarantined",
                 "issue_numbers":[1459,1500],"new_work_authorized":False}}}
        data["engineering-supervisor-state.json"]={
            "observed_at":start.replace(second=15).isoformat(),
            "items":[{"id":"TODO-OPS-013","lane":"todo_identity","category":"human_authority"}]}
        c={"started_at":start.isoformat(),"finished_at":finish.isoformat()}
        p={"started_at":start.replace(second=1).isoformat(),"finished_at":finish.isoformat()}
        return c,p,start
    return a,data,cycle


def test_todo_native_acceptance_requires_distinct_cycles(tmp_path,monkeypatch):
    a,data,cycle=todo_cycle_fixture(tmp_path,monkeypatch)
    sha=m.pipeline_scope_sha(todo_plan())
    args=cycle(1)
    assert not a.record_scheduled_acceptance(sha,{"production_authority":False},*args)
    assert (tmp_path/"scheduled-cycle-1.json").exists()
    assert not (tmp_path/"scheduled-acceptance.json").exists()
    assert not a.record_scheduled_acceptance(sha,{"production_authority":False},*args)
    assert a.record_scheduled_acceptance(sha,{"production_authority":False},*cycle(2))
    result=json.loads((tmp_path/"scheduled-acceptance.json").read_text())
    assert result["evidence"]["two_distinct_scheduled_cycles_verified"] is True
    assert result["evidence"]["second_cycle_sha256"]==m.digest((tmp_path/"scheduled-cycle-2.json").read_bytes())


def test_todo_native_acceptance_rejects_expanded_authority_and_stale_evidence(tmp_path,monkeypatch):
    a,data,cycle=todo_cycle_fixture(tmp_path,monkeypatch)
    args=cycle(1)
    sha=m.pipeline_scope_sha(todo_plan())
    data["todo-intake-state.json"]["identity_conflicts"]["TODO-OPS-013"]["new_work_authorized"]=True
    with pytest.raises(PermissionError,match="QUARANTINE_NOT_VERIFIED"):
        a.record_scheduled_acceptance(sha,{},*args)
    args=cycle(1)
    data["todo-intake-state.json"]["observed_at"]="2026-10-01T00:00:00+00:00"
    with pytest.raises(PermissionError,match="QUARANTINE_NOT_VERIFIED"):
        a.record_scheduled_acceptance(sha,{},*args)
    assert not (tmp_path/"scheduled-cycle-1.json").exists()


def test_todo_native_acceptance_never_hides_intervening_failure(tmp_path,monkeypatch):
    a,data,cycle=todo_cycle_fixture(tmp_path,monkeypatch)
    sha=m.pipeline_scope_sha(todo_plan())
    assert not a.record_scheduled_acceptance(sha,{},*cycle(1))
    a.command.return_value=b"ENGINEERING_STAGE_END name=todo_intake status=failed\nENGINEERING_STAGE_END name=todo_intake status=succeeded\n"
    with pytest.raises(PermissionError,match="INTERVENING_FAILURE"):
        a.record_scheduled_acceptance(sha,{},*cycle(2))
    assert not (tmp_path/"scheduled-acceptance.json").exists()


def release_retry_plan():
    p=todo_plan()
    p.update(predecessor_candidate_sha=m.RELEASE_RETRY_BASELINE,
             worker_replacements=sorted(m.RELEASE_RETRY_WORKERS),
             release_gate_retry_budget_seconds=20,
             retry_only_on_contention=True,legacy_release_guard_immediate=True,
             preserve_predecessor_acceptance_requirements=True,
             supersede_pending_only_before_first_worker_execution=True)
    return p


@pytest.mark.parametrize("key,value",[
    ("release_gate_retry_budget_seconds",21),
    ("retry_only_on_contention",False),
    ("legacy_release_guard_immediate",False),
    ("preserve_predecessor_acceptance_requirements",False),
    ("supersede_pending_only_before_first_worker_execution",False),
    ("required_scheduled_cycles",1),
])
def test_retry_scope_preserves_exact_predecessor_authority_and_bounds(key,value):
    p=release_retry_plan()
    assert m.pipeline_scope_sha(p)==m.digest(m.canon(p))
    p[key]=value
    with pytest.raises(PermissionError):m.pipeline_scope_sha(p)


def test_retry_predecessor_requires_no_new_execution_or_verified_acceptance(tmp_path):
    a=object.__new__(m.PipelineSuccessor)
    a.n={"read":lambda p,*args:p.read_bytes()}
    state={"started_at":"2026-11-25T19:35:00+00:00","finished_at":"2026-11-25T19:50:00+00:00"}
    a.p={"read":lambda p,*args:m.canon(state)}
    a.properties=lambda *args:{"ActiveState":"inactive","MainPID":"0"}
    a.systemctl=lambda *args:(
        b"Result=exec-condition\nExecMainStartTimestamp=\n"
        b"ExecCondition={ path=/usr/bin/python3 ; argv[]=pmv4_e_unit_admission.py ; status=0 }\n"
        b"ExecCondition={ path=/usr/bin/python3 ; argv[]=manager_guard.py ; status=0 }\n"
        b"ExecCondition={ path=/usr/bin/python3 ; argv[]=pmv3_worker_release_gate.py ; status=1 }\n")
    activation={"at":"2026-11-25T20:19:00+00:00","scope_sha256":"1"*64}
    a.verify_retry_predecessor(tmp_path,activation,require_gate_skip=True)
    state["started_at"]="2026-11-25T20:20:00+00:00"
    with pytest.raises(PermissionError,match="ALREADY_EXECUTED"):
        a.verify_retry_predecessor(tmp_path,activation,require_gate_skip=False)
    accepted={"status":"scheduled_engineering_acceptance_verified","scope_sha256":"1"*64,
              "evidence":{"two_distinct_scheduled_cycles_verified":True,
                          "todo_identity_quarantined":True,"production_authority":False}}
    (tmp_path/"scheduled-acceptance.json").write_bytes(m.canon(accepted))
    a.verify_retry_predecessor(tmp_path,activation,require_gate_skip=True)
    (tmp_path/"activation-rollback.json").touch()
    with pytest.raises(PermissionError,match="ROLLED_BACK"):
        a.verify_retry_predecessor(tmp_path,activation,require_gate_skip=True)


def test_retry_successor_retains_two_cycle_quarantine_acceptance(tmp_path,monkeypatch):
    a,data,cycle=todo_cycle_fixture(tmp_path,monkeypatch)
    a.predecessor=m.RELEASE_RETRY_BASELINE
    sha=m.pipeline_scope_sha(release_retry_plan())
    first,pipeline,at=cycle(1)
    with pytest.raises(PermissionError,match="CONTROLLER_ADMISSION_NOT_VERIFIED"):
        a.record_scheduled_acceptance(sha,{},first,pipeline,at)
    first["release_gate_status"]="allowed"
    assert not a.record_scheduled_acceptance(sha,{},first,pipeline,at)
    second,pipeline,at=cycle(2)
    second["release_gate_status"]="allowed"
    assert a.record_scheduled_acceptance(sha,{},second,pipeline,at)
    evidence=json.loads((tmp_path/"scheduled-acceptance.json").read_text())["evidence"]
    assert evidence["bounded_release_retry_policy_verified"] is True
    assert evidence["two_distinct_scheduled_cycles_verified"] is True
    assert evidence["todo_identity_quarantined"] is True


def source_integration_plan():
    p=todo_plan()
    p.update(predecessor_candidate_sha=m.SOURCE_INTEGRATION_BASELINE,
             worker_replacements=sorted(m.SOURCE_INTEGRATION_WORKERS),
             source_integration_policy="independent_source_v1",
             production_transaction_mutex_preserved=True,
             exact_native_release_records_unchanged=True,
             source_merges_not_rolled_back=True,
             release_gate_retry_budget_seconds=20)
    return p


@pytest.mark.parametrize("key,value",[
    ("worker_replacements",["pmv3_integration_queue.py","release_manager_host_runner.py"]),
    ("source_integration_policy","unknown"),
    ("production_transaction_mutex_preserved",False),
    ("exact_native_release_records_unchanged",False),
    ("source_merges_not_rolled_back",False),
    ("required_scheduled_cycles",1),
    ("release_gate_retry_budget_seconds",21),
    ("production_authority",True),
])
def test_source_integration_scope_denies_authority_or_policy_expansion(key,value):
    p=source_integration_plan()
    assert m.pipeline_scope_sha(p)==m.digest(m.canon(p))
    p[key]=value
    with pytest.raises(PermissionError):m.pipeline_scope_sha(p)


def test_source_integration_requires_completed_retry_predecessor(tmp_path):
    a=object.__new__(m.PipelineSuccessor)
    a.n={"read":lambda p,*args:p.read_bytes()}
    activation={"at":"2026-11-25T20:19:00+00:00","scope_sha256":"1"*64}
    with pytest.raises(PermissionError,match="PREDECESSOR_NOT_ACCEPTED"):
        a.verify_source_integration_predecessor(tmp_path,activation)
    accepted={"status":"scheduled_engineering_acceptance_verified","scope_sha256":"1"*64,
        "evidence":{"two_distinct_scheduled_cycles_verified":True,
                    "todo_identity_quarantined":True,"production_authority":False}}
    (tmp_path/"scheduled-acceptance.json").write_bytes(m.canon(accepted))
    with pytest.raises(PermissionError,match="PREDECESSOR_RETRY_NOT_VERIFIED"):
        a.verify_source_integration_predecessor(tmp_path,activation)
    accepted["evidence"]["bounded_release_retry_policy_verified"]=True
    (tmp_path/"scheduled-acceptance.json").write_bytes(m.canon(accepted))
    a.verify_source_integration_predecessor(tmp_path,activation)


def test_source_integration_native_cycles_require_policy_and_unchanged_production(tmp_path,monkeypatch):
    a,data,cycle=todo_cycle_fixture(tmp_path,monkeypatch)
    a.predecessor=m.SOURCE_INTEGRATION_BASELINE
    sha=m.pipeline_scope_sha(source_integration_plan())
    def evidence(n):
        c,p,at=cycle(n)
        c["release_gate_status"]="allowed"
        q={"integration_policy":"independent_source_v1","production_authority":False,
           "release_lock":None,"status":"source_backlog","main_sha":"2"*40,
           "updated_at":c["finished_at"],"source_backlog":{
             "main_sha":"2"*40,"verified_production_sha":m.LKG,
             "pending_production_review":True,"production_authority":False}}
        data["pmv3-integration-queue-state.json"]=q
        c["integration_queue"]={k:q[k] for k in ("status","integration_policy","production_authority")}
        return c,p,at
    first,pipeline,at=evidence(1)
    data["pmv3-integration-queue-state.json"]["source_backlog"]["verified_production_sha"]="3"*40
    with pytest.raises(PermissionError,match="SCHEDULED_POLICY_NOT_VERIFIED"):
        a.record_scheduled_acceptance(sha,{},first,pipeline,at)
    assert not a.record_scheduled_acceptance(sha,{},*evidence(1))
    assert a.record_scheduled_acceptance(sha,{},*evidence(2))
    result=json.loads((tmp_path/"scheduled-acceptance.json").read_text())["evidence"]
    assert result["independent_source_policy_verified"] is True
    assert result["native_production_unchanged"] is True
    assert result["two_distinct_scheduled_cycles_verified"] is True


@pytest.fixture
def reviewed_metadata():
    old = {"revision":"a"*40,"status":"ci_passed","workflow":"Validate Jason",
           "workflow_run_id":"100","workflow_url":"https://github.com/al-teamaot-com/jason/actions/runs/100",
           "observed_at":"2026-11-25T17:47:15+00:00"}
    new = dict(old, revision="b"*40, workflow_run_id="101",
               workflow_url="https://github.com/al-teamaot-com/jason/actions/runs/101",
               observed_at="2026-11-26T05:00:09+00:00")
    def doc(v):
        return {"schema_version":"1.0","production":{"revision":m.LKG},
                "validated_source":v}
    def markdown(v):
        return ("# State\n\n## Latest validated source\n\n"
                "- Revision: `"+v["revision"]+"`\n"
                "- Status: `ci_passed`\n- Workflow: `Validate Jason`\n"
                "- Workflow run: `"+v["workflow_run_id"]+"`\n"
                "- Observed: `"+v["observed_at"]+"`\n\n"
                "## Latest production alignment\n\nUnchanged\n")
    return doc(old), doc(new), markdown(old), markdown(new)


@pytest.mark.parametrize("fault", [None, "extra_path", "one_record", "other_baseline",
                                    "production", "markdown", "bad_url", "symlink"])
def test_reviewed_source_delta_metadata_only(reviewed_metadata, fault):
    old, new, old_md, new_md = reviewed_metadata
    baseline = m.SOURCE_INTEGRATION_BASELINE
    candidate = "c"*40
    changed = set(m.SOURCE_INTEGRATION_SCOPE_FILES) | m.SOURCE_METADATA_PATHS
    if fault == "extra_path": changed.add("tools/foreign.py")
    if fault == "one_record": changed.remove("docs/control/AUTOMATED-CHANGE-STATE.md")
    if fault == "other_baseline": baseline = m.RELEASE_RETRY_BASELINE
    if fault == "production": new["production"]["revision"] = candidate
    if fault == "markdown": new_md += "Unreviewed text\n"
    if fault == "bad_url": new["validated_source"]["workflow_url"] = "https://invalid.example/"
    def git(*args):
        if args[0] == "diff": return "\n".join(sorted(changed)).encode()
        if args[0] == "ls-tree":
            mode = "120000" if fault == "symlink" and args[1] == candidate else "100644"
            return (mode + " blob " + "d"*40 + "\t" + args[-1]+"\n").encode()
        if args[0] == "show":
            rev, path = args[1].split(":", 1)
            if path.endswith(".json"):
                return json.dumps(old if rev == baseline else new).encode()
            return (old_md if rev == baseline else new_md).encode()
        raise AssertionError(args)
    if fault is None:
        m.reviewed_source_delta(git, baseline, candidate, m.SOURCE_INTEGRATION_SCOPE_FILES)
    else:
        with pytest.raises(PermissionError):
            m.reviewed_source_delta(git, baseline, candidate, m.SOURCE_INTEGRATION_SCOPE_FILES)


def test_metadata_exception_does_not_remove_exact_current_main_ci_gate():
    import inspect
    source = inspect.getsource(m.source_review)
    assert "ci[\"protected_main\"] == candidate" in source
    assert "ci[\"required_ci_passed\"] is True" in source
    assert "CURRENT_MAIN_CI_NOT_EXACT" in source
    assert "reviewed_source_delta(git, baseline, candidate, source_files)" in source
