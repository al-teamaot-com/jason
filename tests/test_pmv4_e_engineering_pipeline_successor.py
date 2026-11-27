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
    # Test the actual authorization call below rather than its spelling.
    assert 'self.actor = self.n["owner"](' in source
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


def closed_loop_plan():
    p = source_integration_plan()
    p.update(predecessor_candidate_sha=m.CLOSED_LOOP_BASELINE,
             worker_replacements=sorted(m.CLOSED_LOOP_WORKERS),
             engineering_progress_detector_required=True,
             closed_loop_source_review={
                 "scope_commit":"7"*40,"scope_parent":"8"*40,
                 "excluded_source_paths":["docs/unrelated.md"],
             })
    return p


@pytest.mark.parametrize("key,value", [
    ("worker_replacements",["jason_self_heal_watchdog.py"]),
    ("production_authority",True),
    ("provider_writes",True),
    ("runtime_or_mcp_restart_allowed",True),
    ("freeze_or_hold_change",True),
    ("engineering_progress_detector_required",False),
    ("required_scheduled_cycles",1),
    ("closed_loop_source_review",None),
    ("closed_loop_source_review",{"scope_commit":"7"*40,"scope_parent":"8"*40,
                                  "excluded_source_paths":["tools/engineering_supervisor.py"]}),
])
def test_closed_loop_scope_rejects_expansion_and_missing_evidence(key,value):
    p=closed_loop_plan()
    assert m.pipeline_scope_sha(p)==m.digest(m.canon(p))
    p[key]=value
    with pytest.raises(PermissionError):
        m.pipeline_scope_sha(p)


def test_closed_loop_targets_preserve_existing_manager_and_pin_resolver():
    from tools import pmv4_e_engineering_manager_guard as g
    a=object.__new__(m.PipelineSuccessor)
    a.predecessor=m.CLOSED_LOOP_BASELINE
    a.changed_workers=m.CLOSED_LOOP_WORKERS
    a.g={"ARTIFACTS":g.ARTIFACTS,"PIPELINE_ARTIFACTS":g.PIPELINE_ARTIFACTS}
    a.release=m.ROOT/"releases"/("a"*40)/"tools"
    targets=a.approved_targets()
    assert {m.LIB/name for name in m.CLOSED_LOOP_WORKERS} <= targets
    assert {x.name for x in targets if x.parent==a.release} == (
        set(g.ARTIFACTS)|set(g.CLOSED_LOOP_PIPELINE_ARTIFACTS))
    assert not any(x in targets for x in (m.POLICY,m.ENV))
    assert not any(x.name in ("production-deployment-freeze","auto-promotion-incident-hold",
                              "production-control-state.json") for x in targets)


def test_closed_loop_requires_accepted_independent_source_predecessor(tmp_path):
    a=object.__new__(m.PipelineSuccessor)
    a.n={"read":lambda p,*args:p.read_bytes()}
    activation={"at":"2026-11-26T19:00:00+00:00","scope_sha256":"1"*64}
    accepted={"status":"scheduled_engineering_acceptance_verified","scope_sha256":"1"*64,
              "evidence":{"two_distinct_scheduled_cycles_verified":True,
                          "todo_identity_quarantined":True,
                          "production_authority":False,
                          "bounded_release_retry_policy_verified":True}}
    path=tmp_path/"scheduled-acceptance.json"
    path.write_bytes(m.canon(accepted))
    with pytest.raises(PermissionError,match="PREDECESSOR_SOURCE_POLICY_NOT_ACCEPTED"):
        a.verify_closed_loop_predecessor(tmp_path,activation)
    accepted["evidence"]["independent_source_policy_verified"]=True
    path.write_bytes(m.canon(accepted))
    a.verify_closed_loop_predecessor(tmp_path,activation)


def test_closed_loop_exact_git_scope_and_intervening_changes(tmp_path,monkeypatch):
    import subprocess
    repo=tmp_path/"repo"
    repo.mkdir()
    def git(*args):
        return subprocess.check_output(["git","-C",str(repo),*args],stderr=subprocess.PIPE)
    git("init","-q")
    git("config","user.name","Isolated Test")
    git("config","user.email","test@example.invalid")
    def commit(message, changes):
        for name,body in changes.items():
            path=repo/name
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(body)
        git("add","--all")
        git("commit","-qm",message)
        return git("rev-parse","HEAD").decode().strip()
    baseline=commit("base",{"tools/pmv4_e_engineering_manager_install.py":"old",
                            "tools/engineering_supervisor.py":"old",
                            "tools/pmv3_integration_queue.py":"old"})
    monkeypatch.setattr(m,"CLOSED_LOOP_BASELINE",baseline)
    scope={"tools/pmv4_e_engineering_manager_install.py","tools/engineering_supervisor.py"}
    monkeypatch.setattr(m,"CLOSED_LOOP_SCOPE_FILES",scope)
    monkeypatch.setattr(m,"CLOSED_LOOP_PROTECTED_PATHS",scope|{"tools/pmv3_integration_queue.py"})
    parent=commit("independent source only",{"docs/unrelated.md":"one"})
    anchor=commit("exact scoped source",{
        "tools/pmv4_e_engineering_manager_install.py":"new",
        "tools/engineering_supervisor.py":"new"})
    candidate=commit("additional source only",{"docs/other.md":"two"})
    assert m.review_closed_loop_delta(git,candidate)=={
        "scope_commit":anchor,"scope_parent":parent,
        "excluded_source_paths":["docs/other.md","docs/unrelated.md"]}
    changed=commit("protected control change",{"tools/pmv3_integration_queue.py":"new"})
    with pytest.raises(PermissionError,match="INTERVENING_PROTECTED_SOURCE_CHANGE"):
        m.review_closed_loop_delta(git,changed)
    reverted=commit("revert protected control",{"tools/pmv3_integration_queue.py":"old"})
    with pytest.raises(PermissionError,match="INTERVENING_PROTECTED_SOURCE_CHANGE"):
        m.review_closed_loop_delta(git,reverted)


def breaker_custody_plan():
    p = source_integration_plan()
    p.update(predecessor_candidate_sha=m.BREAKER_CUSTODY_BASELINE,
             worker_replacements=sorted(m.BREAKER_CUSTODY_WORKERS),
             engineering_progress_detector_required=True,
             breaker_custody_source_review={
                 "scope_commit":"7"*40,"scope_parent":"8"*40,
                 "excluded_source_paths":["docs/roadmaps/Project-Jason-TODO-and-Future-Ideas.md"],
             },
             breaker_policy_source=dict(m.BREAKER_POLICY_SOURCE))
    return p


@pytest.mark.parametrize("key,value", [
    ("worker_replacements",["release_manager_host_runner.py"]),
    ("provider_writes",True), ("production_authority",True),
    ("freeze_or_hold_change",True), ("runtime_or_mcp_restart_allowed",True),
    ("engineering_progress_detector_required",False),
    ("required_scheduled_cycles",1),
    ("breaker_policy_source",{"repository":"/tmp/untrusted","revision":"0"*40}),
    ("breaker_custody_source_review",{"scope_commit":"7"*40,"scope_parent":"8"*40,
                                    "excluded_source_paths":["tools/pmv3_integration_queue.py"]}),
])
def test_breaker_custody_scope_preserves_existing_authority(key,value):
    p=breaker_custody_plan()
    assert m.pipeline_scope_sha(p)==m.digest(m.canon(p))
    p[key]=value
    with pytest.raises(PermissionError):
        m.pipeline_scope_sha(p)


def test_breaker_custody_only_replaces_pipeline_and_preserves_resolver_pin():
    from tools import pmv4_e_engineering_manager_guard as g
    a=object.__new__(m.PipelineSuccessor)
    a.predecessor=m.BREAKER_CUSTODY_BASELINE
    a.changed_workers=m.BREAKER_CUSTODY_WORKERS
    a.g={"ARTIFACTS":g.ARTIFACTS,"PIPELINE_ARTIFACTS":g.PIPELINE_ARTIFACTS}
    a.release=m.ROOT/"releases"/("a"*40)/"tools"
    targets=a.approved_targets()
    assert {p.name for p in targets if p.parent==m.LIB}=={"engineering_pipeline.py"}
    assert {x.name for x in targets if x.parent==a.release} == (
        set(g.ARTIFACTS)|set(g.CLOSED_LOOP_PIPELINE_ARTIFACTS))
    assert m.POLICY not in targets and m.ENV not in targets


@pytest.mark.parametrize("fault", ["wrong_repo","wrong_revision","stale","open","pending","missing","failed"])
def test_breaker_scheduled_route_requires_fresh_native_ledger(fault):
    pipeline={"started_at":"2026-11-27T06:00:00+00:00",
              "finished_at":"2026-11-27T06:01:00+00:00",
              "stages":{"release_breaker_recovery":{
                  "status":"succeeded","policy_repository":m.BREAKER_POLICY_SOURCE["repository"]}}}
    ledger={"observed_at":"2026-11-27T06:01:00.100000+00:00",
            "status":"already_closed","lkg_revision":m.LKG,
            "breaker_state":"closed","next_action":"none"}
    assert m.verify_scheduled_breaker_policy_route(pipeline,ledger)==m.BREAKER_POLICY_SOURCE
    if fault=="wrong_repo":pipeline["stages"]["release_breaker_recovery"]["policy_repository"]="/tmp/other"
    elif fault=="wrong_revision":ledger["lkg_revision"]="0"*40
    elif fault=="stale":ledger["observed_at"]="2026-11-27T05:59:59+00:00"
    elif fault=="open":ledger["breaker_state"]="open"
    elif fault=="pending":ledger["status"]="pending_root_verification"
    elif fault=="failed":pipeline["stages"]["release_breaker_recovery"]["status"]="failed"
    else:ledger.pop("observed_at")
    with pytest.raises(PermissionError,match="SCHEDULED_POLICY_ROUTE_NOT_VERIFIED"):
        m.verify_scheduled_breaker_policy_route(pipeline,ledger)

def watchdog_recovery_plan():
    p=breaker_custody_plan()
    p.pop("breaker_custody_source_review",None)
    p.update(predecessor_candidate_sha=m.WATCHDOG_RECOVERY_BASELINE,
             worker_replacements=sorted(m.WATCHDOG_RECOVERY_WORKERS),
             failed_unit_reset_scope=list(m.SERVICES),
             precutover_exact_faults=list(m.WATCHDOG_RECOVERY_FAULTS),
             derived_reporter_exit2_only={"unit":m.DRIFT_REPORTER_UNIT,
                                         "pins":m.DRIFT_REPORTER_PINS,
                                         "properties":m.DRIFT_REPORTER_EXIT2},
             local_reasoning_runtime_activation=False)
    return p


@pytest.mark.parametrize("key,value", [
    ("failed_unit_reset_scope",["jason-runtime.service"]),
    ("failed_unit_reset_scope",list(m.SERVICES)+["extra.service"]),
    ("precutover_exact_faults",[]),
    ("derived_reporter_exit2_only",{}),
    ("local_reasoning_runtime_activation",True),
    ("runtime_or_mcp_restart_allowed",True),
    ("production_authority",True),
    ("provider_writes",True),
    ("freeze_or_hold_change",True),
    ("worker_replacements",["jason_self_heal_watchdog.py"]),
])
def test_watchdog_recovery_exact_scope_denies_expansion(key,value):
    p=watchdog_recovery_plan()
    assert len(m.pipeline_scope_sha(p))==64
    p[key]=value
    with pytest.raises(PermissionError):m.pipeline_scope_sha(p)


def test_failed_manager_preflight_rejects_unrelated_duplicate_or_stale_drift():
    from copy import deepcopy
    from datetime import datetime,timezone,timedelta
    control={"circuit_breaker":{"state":"open","source":"production_drift_watchdog",
             "reason":"continuous_production_drift_detected","problem_count":2,
             "problem_kinds":["failed_system_unit"]}}
    drift={"status":"drift_detected","problems":deepcopy(m.WATCHDOG_RECOVERY_FAULTS),
           "observed_at":datetime.now(timezone.utc).isoformat()}
    assert m.verify_failed_manager_drift(control,drift,deepcopy(drift))==m.WATCHDOG_RECOVERY_FAULTS
    for changed in ([],drift["problems"]+[{"kind":"failed_system_unit","state":"failed","unit":"openbao.service"}],
                    [drift["problems"][0]]*2):
        bad={**drift,"problems":changed}
        with pytest.raises(PermissionError):m.verify_failed_manager_drift(control,drift,bad)
    bad={**drift,"observed_at":(datetime.now(timezone.utc)-timedelta(minutes=10)).isoformat()}
    with pytest.raises(PermissionError):m.verify_failed_manager_drift(control,bad,drift)
    bad=deepcopy(control);bad["circuit_breaker"]["reason"]="manual_hold"
    with pytest.raises(PermissionError):m.verify_failed_manager_drift(bad,drift,drift)


def test_watchdog_recovery_root_target_set_excludes_runtime_and_other_units():
    from tools import pmv4_e_engineering_manager_guard as g
    a=object.__new__(m.PipelineSuccessor)
    a.predecessor=m.WATCHDOG_RECOVERY_BASELINE
    a.changed_workers=m.WATCHDOG_RECOVERY_WORKERS
    a.g={"ARTIFACTS":g.ARTIFACTS,"PIPELINE_ARTIFACTS":g.PIPELINE_ARTIFACTS}
    a.release=m.ROOT/"releases"/("f"*40)/"tools"
    targets=a.approved_targets()
    assert all(m.LIB/name in targets for name in m.WATCHDOG_RECOVERY_WORKERS)
    assert m.MANAGER_GUARD in targets and m.RECEIPT in targets
    assert m.POLICY not in targets and m.ENV not in targets
    assert all(not str(x).startswith("/opt/jason/") for x in targets)
    assert not any(x.name in {"jason-runtime.service","jason-pmv4-ticket-core.service"} for x in targets)


def test_failed_manager_reporter_exit2_is_only_a_verified_derived_observation():
    from copy import deepcopy
    from datetime import datetime,timezone
    control={"circuit_breaker":{"state":"open","source":"production_drift_watchdog",
             "reason":"continuous_production_drift_detected","problem_count":2,
             "problem_kinds":["failed_system_unit"]}}
    drift={"status":"drift_detected","problems":deepcopy(m.WATCHDOG_RECOVERY_FAULTS),
           "observed_at":datetime.now(timezone.utc).isoformat()}
    evaluated={**drift,"problems":[*drift["problems"],m.DRIFT_REPORTER_FAULT]}
    assert m.verify_failed_manager_drift(control,drift,evaluated,
        reporter=m.DRIFT_REPORTER_EXIT2)==m.WATCHDOG_RECOVERY_FAULTS
    for key,value in (("ExecMainStatus","1"),("MainPID","123"),
                      ("Result","timeout"),("DropInPaths","/tmp/foreign")):
        with pytest.raises(PermissionError):
            m.verify_failed_manager_drift(control,drift,evaluated,
                reporter={**m.DRIFT_REPORTER_EXIT2,key:value})
    with pytest.raises(PermissionError):
        m.verify_failed_manager_drift(control,drift,evaluated)
    with pytest.raises(PermissionError):
        m.verify_failed_manager_drift(control,evaluated,evaluated,
            reporter=m.DRIFT_REPORTER_EXIT2)
    with pytest.raises(PermissionError):
        m.verify_failed_manager_drift(control,drift,
            {**evaluated,"problems":[*evaluated["problems"],m.DRIFT_REPORTER_FAULT]},
            reporter=m.DRIFT_REPORTER_EXIT2)


def normal_manager_plan():
    p = breaker_custody_plan()
    p.pop("breaker_custody_source_review")
    p.update(predecessor_candidate_sha=m.NORMAL_MANAGER_BASELINE,
             worker_replacements=sorted(m.NORMAL_MANAGER_WORKERS),
             normal_manager_source_review={
                 "baseline":m.NORMAL_MANAGER_BASELINE,
                 "candidate":p["policy"]["candidate_sha"],
                 "reviewed_source_paths":sorted(m.NORMAL_MANAGER_SCOPE_FILES),
                 "excluded_source_paths":["docs/operations/unrelated.md"],
             },
             normal_manager_stage_targets=sorted(map(str,m.NORMAL_MANAGER_STAGE_FILES)),
             normal_mode_activation=False)
    return p


@pytest.mark.parametrize("key,value", [
    ("freeze_or_hold_change",True),
    ("provider_writes",True),
    ("production_authority",True),
    ("runtime_or_mcp_restart_allowed",True),
    ("normal_mode_activation",True),
    ("normal_manager_stage_targets",["/etc/sudoers"]),
    ("normal_manager_source_review",None),
    ("worker_replacements",["foreign.py"]),
    ("required_scheduled_cycles",1),
])
def test_normal_manager_stage_scope_keeps_production_authority_unchanged(key,value):
    p=normal_manager_plan()
    assert len(m.pipeline_scope_sha(p))==64
    p[key]=value
    with pytest.raises(PermissionError):
        m.pipeline_scope_sha(p)


def test_normal_manager_exact_targets_preserve_legacy_root_guard_and_application():
    from tools import pmv4_e_engineering_manager_guard as g
    a=object.__new__(m.PipelineSuccessor)
    a.predecessor=m.NORMAL_MANAGER_BASELINE
    a.changed_workers=m.NORMAL_MANAGER_WORKERS
    a.g={"ARTIFACTS":g.ARTIFACTS,"PIPELINE_ARTIFACTS":g.PIPELINE_ARTIFACTS}
    a.release=m.ROOT/"releases"/("f"*40)/"tools"
    targets=a.approved_targets()
    assert set(m.NORMAL_MANAGER_STAGE_FILES)<=targets
    assert all(m.LIB/name in targets for name in m.NORMAL_MANAGER_WORKERS)
    assert m.RECEIPT in targets and m.MANAGER_GUARD in targets
    assert m.POLICY not in targets and m.ENV not in targets
    assert not any(str(p).startswith("/opt/jason/") for p in targets)
    assert not any(p.name in ("production-deployment-freeze","auto-promotion-incident-hold",
                             "production-freeze-retirement.json","jason-runtime.service",
                             "jason-pmv4-ticket-core.service") for p in targets)


def test_normal_manager_source_projection_records_exclusions_and_denies_protected_drift():
    candidate="a"*40
    paths=set(m.NORMAL_MANAGER_SCOPE_FILES)|{"docs/operations/unrelated.md"}
    def git(*args):
        if args[0]=="merge-base":
            assert args==("merge-base","--is-ancestor",m.NORMAL_MANAGER_BASELINE,candidate)
            return b""
        assert args==("diff","--no-renames","--name-only",m.NORMAL_MANAGER_BASELINE,candidate)
        return "\n".join(sorted(paths)).encode()
    row=m.review_normal_manager_delta(git,candidate)
    assert row["excluded_source_paths"]==["docs/operations/unrelated.md"]
    assert row["reviewed_source_paths"]==sorted(m.NORMAL_MANAGER_SCOPE_FILES)
    paths.add("config/release-manager-policy.json")
    with pytest.raises(PermissionError,match="UNREVIEWED_PROTECTED_SOURCE"):
        m.review_normal_manager_delta(git,candidate)
    paths.remove("config/release-manager-policy.json")
    paths.remove("tools/pmv4_e_engineering_manager_install.py")
    with pytest.raises(PermissionError,match="DELTA_INCOMPLETE"):
        m.review_normal_manager_delta(git,candidate)


def test_legacy_successor_passes_exact_scope_to_existing_authenticator():
    a=object.__new__(m.PipelineSuccessor)
    p=plan()
    # Stop at the existing authenticator; no locks or production methods run.
    a.n={"owner":Mock(side_effect=PermissionError("test authorization denied")),
         "locks":Mock(side_effect=AssertionError("unexpected mutation"))}
    with pytest.raises(PermissionError,match="test authorization denied"):
        a.apply(p,m.pipeline_scope_sha(p))
    a.n["owner"].assert_called_once_with(p)
    a.n["locks"].assert_not_called()


@pytest.mark.parametrize("reason",sorted(m.PIPELINE_HEALTH_DENIAL_REASONS))
def test_independent_health_denial_reason_preserved(reason):
    with pytest.raises(PermissionError,match="PIPELINE_NATIVE_CORE_HEALTH:"+reason):
        m.verify_pipeline_native_core_health({
            "verified":False,"reason":reason,"production_authority":False})


@pytest.mark.parametrize("invalid",[
    None, [], {}, {"verified":1,"production_authority":False,"production_revision":m.LKG},
    {"verified":True,"production_authority":0,"production_revision":m.LKG},
    {"verified":True,"production_authority":True,"production_revision":m.LKG},
    {"verified":True,"production_authority":False,"production_revision":"0"*40},
    {"verified":False,"reason":"native_readback_live_core_and_authority_verified"},
    {"verified":False,"reason":["unrecognized"]},
])
def test_health_diagnostics_never_turn_denial_into_acceptance(invalid):
    with pytest.raises(PermissionError,match="PIPELINE_NATIVE_CORE_HEALTH"):
        m.verify_pipeline_native_core_health(invalid)


def test_health_diagnostic_does_not_echo_arbitrary_child_output():
    with pytest.raises(PermissionError,match="invalid_or_unrecognized_result") as caught:
        m.verify_pipeline_native_core_health({"verified":False,"reason":"fixture-private-output"})
    assert "fixture-private-output" not in str(caught.value)


def test_exact_native_health_still_requires_original_three_conditions():
    assert m.verify_pipeline_native_core_health({
        "verified":True,"production_authority":False,"production_revision":m.LKG}) is None



def test_normal_manager_stage_images_bind_reader_custody():
    from tools import owner_approved_development_worker as worker
    code = {rel: (m.REPO / rel).read_bytes()
            for rel in m.NORMAL_MANAGER_STAGE_FILES.values()}
    images = m.normal_manager_stage_images(code)
    assert set(images) == set(m.NORMAL_MANAGER_STAGE_FILES)
    raw, uid, gid, mode = images[worker.NATIVE_HEALTH_GUARD]
    assert (uid, gid, mode) == (0, 0, 0o444)
    assert m.digest(raw) == worker.NATIVE_HEALTH_GUARD_SHA256
    for path, value in images.items():
        if path != worker.NATIVE_HEALTH_GUARD:
            assert value[1:] == (0, 0, 0o644)


def normal_rollback_plan():
    p = normal_manager_plan()
    p["normal_retirement"] = {
        "action":"RETIRE-EXACT-GLOBAL-PRODUCTION-FREEZE",
        "candidate_sha":p["policy"]["candidate_sha"],
        "provider_writes":False, "standing_authority":False,
        "rollback_authorized":True,
        "configuration_after":{"schema_version":"1.0","production_freeze":False},
        "installation_targets":["fixture-retirement-target"],
    }
    return p


@pytest.mark.parametrize("mutation", [
    "foreign_candidate","wrong_approval","wrong_receipt","wrong_rollback",
    "same_candidate","missing_retirement","different_predecessor"
])
def test_rollback_predecessor_scope_rejects_unrelated_authority(mutation):
    p = normal_rollback_plan()
    p["normal_manager_rollback_predecessor"] = dict(m.NORMAL_MANAGER_ROLLBACK_EVIDENCE)
    assert m.pipeline_scope_sha(p) == m.digest(m.canon(p))
    if mutation == "foreign_candidate":
        p["normal_manager_rollback_predecessor"]["failed_candidate_sha"] = "e"*40
    elif mutation in ("wrong_approval","wrong_receipt","wrong_rollback"):
        p["normal_manager_rollback_predecessor"][mutation[6:]+"_sha256"] = "0"*64
    elif mutation == "same_candidate":
        p["policy"]["candidate_sha"] = m.NORMAL_MANAGER_ROLLBACK_EVIDENCE["failed_candidate_sha"]
        p["normal_manager_source_review"]["candidate"] = p["policy"]["candidate_sha"]
        p["normal_retirement"]["candidate_sha"] = p["policy"]["candidate_sha"]
    elif mutation == "missing_retirement":
        del p["normal_retirement"]
    else:
        p["predecessor_candidate_sha"] = m.PIPELINE_BASELINE
    with pytest.raises(PermissionError,match="NORMAL_MANAGER_ROLLBACK_SCOPE_INVALID"):
        m.pipeline_scope_sha(p)


@pytest.fixture
def normal_rollback_history(tmp_path, monkeypatch):
    """Synthetic immutable records and snapshots; no production paths touched."""
    import os
    from tools import production_freeze_retirement as retirement
    failed = "b"*40
    root = tmp_path/"manager"
    state = tmp_path/"state"
    history = state/failed
    history.mkdir(parents=True,mode=0o700)
    pause = m.image(b"fixture rollback pause",1000,0o600)
    monkeypatch.setattr(m,"ROOT",root)
    monkeypatch.setattr(m,"STATE",state)
    monkeypatch.setitem(m.OLD,m.PAUSE,(1000,0o600,m.digest(pause[0])))
    a = object.__new__(m.PipelineSuccessor)
    a.predecessor = m.NORMAL_MANAGER_BASELINE
    a.candidate = "a"*40
    a.retirement_requested = True
    a.release = root/"releases"/a.candidate/"tools"
    a.g = {"validate_receipt":lambda row:row}
    a.retirement_helper = lambda:{"owner_scope":retirement.owner_scope}
    restored = root/"fixture-native-guard"
    a.approved_targets = lambda:{m.PAUSE,m.RECEIPT,restored,a.release/"fixture.py"}
    before = {m.PAUSE:None,m.RECEIPT:m.image(b"predecessor receipt",0,0o444),
              restored:None,root/"releases"/failed/"tools"/"fixture.py":None}
    after = {p:m.image(b"fixture successor",0,0o444)
             for p in before if p!=m.RECEIPT}
    after[m.PAUSE] = pause
    scope = normal_rollback_plan()
    scope["policy"]["candidate_sha"] = failed
    scope["normal_manager_source_review"]["candidate"] = failed
    scope["normal_retirement"]["candidate_sha"] = failed
    scope["installation_targets"] = sorted(map(str,before))
    scope["before"] = {str(p):m.describe(v) for p,v in before.items()}
    scope["after"] = {str(p):m.describe(v) for p,v in after.items()}
    sha = m.pipeline_scope_sha(scope)
    approval = {"scope":scope,"scope_sha256":sha,"owner_action":scope["normal_retirement"]["action"],
                "owner_scope_sha256":m.digest(m.canon(retirement.owner_scope(scope))),
                "before_images":m.encode(before),"after_images":m.encode(after)}
    raw = m.canon(approval)
    receipt = m.canon({"candidate_sha":failed,"scope_sha256":sha,
                      "approval_sha256":m.digest(raw),
                      "predecessor_candidate_sha":a.predecessor})
    rollback = m.canon({"status":"predecessor_restored_engineering_paused",
                       "scope_sha256":sha,"production_authority":False})
    records = {"approval.json":raw,"receipt-image.json":receipt,"rollback.json":rollback}
    for name,data in records.items():
        p=history/name
        p.write_bytes(data)
        p.chmod(0o400)
    pins = {"failed_candidate_sha":failed,"approval_sha256":m.digest(raw),
            "receipt_sha256":m.digest(receipt),"rollback_sha256":m.digest(rollback)}
    monkeypatch.setattr(m,"NORMAL_MANAGER_ROLLBACK_EVIDENCE",pins)
    # Only the synthetic history directory is assigned test root metadata.
    real_lstat = Path.lstat
    def lstat(path,*args,**kwargs):
        row=real_lstat(path,*args,**kwargs)
        if path==history:
            values=list(row)
            values[4]=values[5]=0
            return os.stat_result(values)
        return row
    monkeypatch.setattr(Path,"lstat",lstat)
    def read(path,uid,mode,maximum=2_000_000):
        assert path.parent==history and uid==0 and mode==0o400
        return path.read_bytes()
    a.n={"read":read}
    snapshots=dict(before)
    snapshots[m.PAUSE]=pause
    monkeypatch.setattr(m,"snapshot",snapshots.get)
    return a,history,snapshots,pins,restored


def test_exact_rollback_evidence_is_read_only(normal_rollback_history):
    a,history,snapshots,pins,_=normal_rollback_history
    before=dict(snapshots)
    records={p:p.read_bytes() for p in history.iterdir()}
    assert a.verify_normal_manager_rollback_predecessor()==pins
    assert snapshots==before
    assert {p:p.read_bytes() for p in history.iterdir()}==records


@pytest.mark.parametrize("mutation",["foreign_pause","missing_pause","live_file",
                                     "foreign_record","changed_record","same_candidate",
                                     "unrelated_request","wrong_predecessor"])
def test_rollback_evidence_fails_closed(normal_rollback_history,mutation):
    a,history,snapshots,pins,restored=normal_rollback_history
    if mutation=="foreign_pause":
        snapshots[m.PAUSE]=m.image(b"foreign pause",1000,0o600)
    elif mutation=="missing_pause":
        snapshots[m.PAUSE]=None
    elif mutation=="live_file":
        snapshots[restored]=m.image(b"unexpected file",0,0o444)
    elif mutation=="foreign_record":
        (history/"activation.json").touch()
    elif mutation=="changed_record":
        path=history/"rollback.json"
        path.chmod(0o600)
        path.write_bytes(b"changed")
    elif mutation=="same_candidate":
        a.candidate=pins["failed_candidate_sha"]
    elif mutation=="unrelated_request":
        a.retirement_requested=False
    else:
        a.predecessor=m.PIPELINE_BASELINE
    with pytest.raises(PermissionError,match="NORMAL_MANAGER_ROLLBACK"):
        a.verify_normal_manager_rollback_predecessor()


def test_recovery_proof_remains_inside_new_authenticated_scope():
    from tools import production_freeze_retirement as retirement
    p=normal_rollback_plan()
    p["normal_manager_rollback_predecessor"]=dict(m.NORMAL_MANAGER_ROLLBACK_EVIDENCE)
    a=object.__new__(m.PipelineSuccessor)
    a.retirement_helper=lambda:{"owner_scope":retirement.owner_scope}
    a.n={"owner":Mock(side_effect=PermissionError("fixture authorization denied")),
         "locks":Mock(side_effect=AssertionError("mutation before authentication"))}
    p["installation_targets"]=["fixture-preparation-target"]
    exact=retirement.owner_scope(p)
    with pytest.raises(PermissionError,match="fixture authorization denied"):
        a.apply(p,m.digest(m.canon(exact)))
    a.n["owner"].assert_called_once_with(exact)
    a.n["locks"].assert_not_called()


def test_readback_wait_uses_only_existing_publisher(monkeypatch):
    from datetime import datetime,timezone,timedelta
    a=object.__new__(m.PipelineSuccessor)
    def row(age):
        return m.canon({"schema_version":"1.0","status":"pass","problems":[],
                       "observed_at":(datetime.now(timezone.utc)-timedelta(seconds=age)).isoformat()})
    read=Mock(side_effect=[row(110),row(65),row(25)])
    a.p={"read":read}
    sleep=Mock()
    monkeypatch.setattr(m.time,"sleep",sleep)
    a.wait_for_fresh_pipeline_readback(attempts=4)
    assert read.call_count==3
    assert sleep.call_count==2
    assert all(c.args==(m.MANAGER/"protected-readback/production-drift.json",1000,0o600)
               for c in read.call_args_list)


@pytest.mark.parametrize("fault",["stale","drift","future"])
def test_readback_wait_does_not_accept_failed_or_missing_fresh_evidence(monkeypatch,fault):
    from datetime import datetime,timezone,timedelta
    a=object.__new__(m.PipelineSuccessor)
    a.p={"read":Mock(return_value=m.canon({
        "schema_version":"1.0","status":"drift_detected" if fault=="drift" else "pass",
        "problems":[] if fault!="drift" else [{"kind":"fixture_drift"}],
        "observed_at":(datetime.now(timezone.utc)-timedelta(seconds=-30 if fault=="future" else 180)).isoformat()
    }))}
    monkeypatch.setattr(m.time,"sleep",lambda _:None)
    with pytest.raises(PermissionError,match="PIPELINE_(FRESH_READBACK_UNAVAILABLE|READBACK_NOT_CLEAN|READBACK_TIME_INVALID)"):
        a.wait_for_fresh_pipeline_readback(attempts=2)
