"""Synthetic no-production tests for the bounded interrupted-ticket-core rescue."""
import copy,json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
import pytest
from tools import audit_journal_ticket_core_rescue as r
from tools import audit_journal_container_release as m
from tools.tests.test_audit_journal_release_plan import before as example_before


def container_from_spec(body,cid,status):
    c={
        "Id":cid,"Image":body["Image"],
        "Config":copy.deepcopy({k:v for k,v in body.items()
                               if k not in ("HostConfig","NetworkingConfig","Image")}),
        "HostConfig":copy.deepcopy(body["HostConfig"]),
        "NetworkSettings":{"Networks":copy.deepcopy(body["NetworkingConfig"]["EndpointsConfig"])},
        "Mounts":[{"Destination":x["Target"],"Type":x["Type"],
                   "Source":x["Source"],"RW":not x.get("ReadOnly",False)}
                  for x in body["HostConfig"].get("Mounts",[])],
        "State":{"Status":status,"Running":status=="running",
                 "Health":{"Status":"healthy"} if status=="running" else {}},
    }
    return c


@pytest.fixture
def context(monkeypatch):
    before={}
    for idx,role in enumerate((r.ROLE,"jason-runtime","jason-mcp-pilot")):
        base=example_before(role)
        base["Id"]=str(idx+1)*64
        base["State"]={"Running":True}
        base["HostConfig"]["OomKillDisable"]=None
        before[role]=base
    origin=before[r.ROLE]
    original_spec=m.exact_original_configuration(origin)
    current=container_from_spec(original_spec,"4"*64,"created")
    current["HostConfig"]["OomKillDisable"]=False
    old=copy.deepcopy(origin)
    old["Name"]="/"+r.BACKUP_BEFORE
    old["State"]={"Running":False,"Status":"exited"}
    dormant=container_from_spec(m.planned_configuration(origin,r.OLD_CANDIDATE),
                                "5"*64,"created")
    dormant["HostConfig"]["OomKillDisable"]=False
    dormant["Name"]="/"+r.BACKUP_FAILED
    other={
        role:container_from_spec(m.exact_original_configuration(before[role]),
                                 before[role]["Id"],"running")
        for role in ("jason-runtime","jason-mcp-pilot")
    }
    rows={r.ROLE:current,r.BACKUP_BEFORE:old,r.BACKUP_FAILED:dormant,**other}
    class FakeEngine:
        calls=[]
        fail_after_start=False
        fail_before_start=False
        def __init__(self):pass
        def inspect(self,name):
            return copy.deepcopy(rows[name])
        def lookup(self,name,required=False):
            return copy.deepcopy(rows[name])
        def call(self,method,path,body=None,**kwargs):
            self.calls.append((method,path))
            if method!="POST" or path!="/containers/"+rows[r.ROLE]["Id"]+"/start":
                raise AssertionError("unexpected provider action: "+path)
            if self.fail_before_start:
                raise OSError("transport failure")
            rows[r.ROLE]["State"]={"Status":"running","Running":True,"Health":{"Status":"healthy"}}
            if self.fail_after_start:
                raise OSError("response lost")
            return {}
    FakeEngine.calls=[]
    fake_impl=SimpleNamespace(ROLES=m.ROLES,DockerEngine=FakeEngine,
                              configuration_matches=m.configuration_matches,
                              planned_configuration=m.planned_configuration,
                              exact_original_configuration=m.exact_original_configuration)
    scope={"policy":{"candidate_sha":r.OLD_CANDIDATE,
                     "rollback_sha":r.ROLLBACK_SHA},"source_sha256":{}}
    monkeypatch.setattr(r,"RECENT_SCOPE",r.digest(scope))
    plan={"candidate_sha":r.OLD_CANDIDATE,"scope_sha256":r.RECENT_SCOPE,
          "scope":scope,"owner_oid":r.OWNER,
          "producer_before_sha256":r.digest(before),
          "independently_verified_entra_owner":True}
    journal={"started_at":"2026-11-24T11:58:00+00:00",
             "recovery_started_at":"2026-11-24T11:58:10+00:00",
             "scope_sha256":r.RECENT_SCOPE,"steps":{
        "install:"+r.ROLE:{"before_id":origin["Id"],"backup":r.BACKUP_BEFORE},
        "restore:"+r.ROLE:{"before_id":dormant["Id"],"backup":r.BACKUP_FAILED},
    }}
    adoption={"scope_sha256":r.RECENT_SCOPE,"owner_oid":r.OWNER,
              "independently_verified_entra_owner":True}
    policy={"candidate_sha":r.OLD_CANDIDATE,"enabled":True,
            "trusted_source_sha256":{}}
    catalog={"mode":"legacy","generation":0,"epoch":None,"segments":[]}
    latest_grant={
        "action":"FRESH-AUTHORIZED-RECOVERY-OF-EXPIRED-DAILY-AUDIT-JOURNAL",
        "candidate_sha":r.LAST_FRESH_SOURCE,"installed_candidate_sha":r.OLD_CANDIDATE,
        "scope_sha256":r.RECENT_SCOPE,"owner_oid":r.OWNER,
        "independently_verified_entra_owner":True,
        "one_use":True,"old_approval_reused":False,
        "new_execution_claim":True,
    }
    data={
        r.LAST_FRESH_GRANT:latest_grant,
        r.PRIVATE/"release-plan.json":plan,
        r.PRIVATE/"release-journal.json":journal,
        r.PRIVATE/"producer-before.json":before,
        r.PRIVATE/"adoption.json":adoption,
        r.POLICY:policy,
        r.CONTROL/"catalog.json":catalog,
    }
    class FakeTx:
        @staticmethod
        def raw_file(path,mode):
            assert path in data,str(path)
            return r.canon(data[path])
    tx=FakeTx()
    class FakeI:
        @staticmethod
        def command(argv):
            name=argv[2]
            if name.endswith(".service"):
                return "ActiveState=failed\nMainPID=0\nResult=exit-code\nUnitFileState=enabled"
            return "ActiveState=inactive\nUnitFileState=disabled"
    modules={"audit_journal_container_release":fake_impl,
             "audit_journal_install_transaction":tx}
    I=FakeI()
    candidate="a"*40
    payload={
        "tools/audit_journal_ticket_core_rescue.py":b"exact-reviewed-rescue",
        "tools/audit_journal_container_release.py":b"exact-reviewed-matcher",
    }
    return SimpleNamespace(rows=rows,engine=FakeEngine,modules=modules,
                           tx=tx,previous=data,I=I,candidate=candidate,
                           payload=payload,original=original_spec)


def probe(t):
    return r.preflight(t.I,None,t.modules,None,t.candidate,t.payload,production=False)


def test_no_production_preflight_binds_only_exact_existing_created_original(context):
    scope,evidence=probe(context)
    assert scope["action"]==r.ACTION
    assert scope["ticket_core_current_created_id"]==context.rows[r.ROLE]["Id"]
    assert scope["scope_excludes_docker_create_rename_remove"] is True
    assert scope["scope_excludes_systemd_service_restart"] is True
    assert scope["scope_excludes_all_database_changes"] is True
    assert scope["immutable_prior_approval_reused"] is False
    assert "start" in scope["one_exact_docker_action"]
    assert evidence["prior_scope_sha256"]==r.RECENT_SCOPE
    assert context.engine.calls==[]


@pytest.mark.parametrize("change",[
    ("current_status","running"),
    ("current_image","sha256:"+"0"*64),
    ("current_security",True),
    ("current_oom",None),
    ("current_mount",True),
    ("dormant_id","7"*64),
    ("before_id","8"*64),
    ("runtime_running",False),
    ("journal_outcome","rolled_back"),
    ("journal_extra_step",True),
    ("catalog_mode","segmented"),
    ("owner",False),
    ("prior_owner_grant",False),
])
def test_preflight_rejects_unapproved_or_changed_state(context,change):
    key,value=change
    if key=="current_status":
        context.rows[r.ROLE]["State"]["Status"]=value
    elif key=="current_image":
        context.rows[r.ROLE]["Image"]=value
    elif key=="current_security":
        context.rows[r.ROLE]["HostConfig"]["Privileged"]=value
    elif key=="current_oom":
        context.rows[r.ROLE]["HostConfig"]["OomKillDisable"]=value
    elif key=="current_mount":
        context.rows[r.ROLE]["Mounts"][0]["RW"]=value
    elif key=="dormant_id":
        context.rows[r.BACKUP_FAILED]["Id"]=value
    elif key=="before_id":
        context.rows[r.BACKUP_BEFORE]["Id"]=value
    elif key=="runtime_running":
        context.rows["jason-runtime"]["State"]["Running"]=value
    elif key=="journal_outcome":
        context.previous[r.PRIVATE/"release-journal.json"]["outcome"]=value
    elif key=="journal_extra_step":
        context.previous[r.PRIVATE/"release-journal.json"]["steps"]["unreviewed"]={}
    elif key=="catalog_mode":
        context.previous[r.CONTROL/"catalog.json"]["mode"]=value
    elif key=="owner":
        context.previous[r.PRIVATE/"adoption.json"]["independently_verified_entra_owner"]=value
    elif key=="prior_owner_grant":
        context.previous[r.LAST_FRESH_GRANT]["independently_verified_entra_owner"]=value
    with pytest.raises((PermissionError,KeyError)):
        probe(context)
    assert context.engine.calls==[]


def test_exact_owner_is_required_before_docker_start(monkeypatch,tmp_path,context):
    scope,_=probe(context)
    monkeypatch.setattr(r.os,"geteuid",lambda:0)
    monkeypatch.setattr(r,"preflight",lambda *args,**kwargs:(scope,{}))
    monkeypatch.setattr(r,"root_dir",lambda path:None)
    monkeypatch.setattr(r.os,"chown",lambda *args:None)
    monkeypatch.setattr(r,"ROOT",tmp_path/"rescue")
    context.tx.sync=lambda path:None
    context.tx.atomic=lambda path,content,mode:path.write_bytes(content)
    monkeypatch.setattr(r,"scope_original",lambda *args:context.original)
    @contextmanager
    def locks():yield
    auth={"locks":locks,"owner":lambda scope:"NOT_LICENSED_OWNER"}
    with pytest.raises(PermissionError,match="INDEPENDENT_LICENSED_OWNER_REQUIRED"):
        r.execute(context.I,None,context.modules,None,auth,context.candidate,context.payload)
    assert context.engine.calls==[]
    assert not r.ROOT.exists()


def test_one_approved_exact_start_is_idempotent_only_via_verified_receipt(
        monkeypatch,tmp_path,context):
    scope,_=probe(context)
    monkeypatch.setattr(r.os,"geteuid",lambda:0)
    monkeypatch.setattr(r,"preflight",lambda *args,**kwargs:(scope,{}))
    monkeypatch.setattr(r,"root_dir",lambda path:None)
    monkeypatch.setattr(r.os,"chown",lambda *args:None)
    monkeypatch.setattr(r,"ROOT",tmp_path/"rescue")
    context.tx.sync=lambda path:None
    context.tx.atomic=lambda path,content,mode:path.write_bytes(content)
    monkeypatch.setattr(r,"scope_original",lambda *args:context.original)
    @contextmanager
    def locks():yield
    prompts=[]
    def owner(plan):
        prompts.append(plan)
        assert plan["action"]==r.ACTION
        assert plan["policy"]["candidate_sha"]==context.candidate
        assert plan["one_exact_docker_action"].endswith("/start")
        return r.OWNER
    auth={"locks":locks,"owner":owner}
    r.execute(context.I,None,context.modules,None,auth,context.candidate,context.payload)
    assert len(prompts)==1
    assert len(context.engine.calls)==1
    assert context.engine.calls[0][0]=="POST"
    assert context.rows[r.ROLE]["State"]["Running"] is True
    assert context.rows[r.BACKUP_BEFORE]["State"]["Running"] is False
    assert (r.ROOT/context.candidate/"authorization.json").exists()
    result=json.loads((r.ROOT/context.candidate/"result.json").read_text())
    assert result["status"]=="ticket_core_running_verified"
    assert result["audit_journal_release_not_restarted"] is True
    assert result["audit_journal_rollback_not_closed"] is True


def test_ambiguous_provider_failure_writes_evidence_without_retry(
        monkeypatch,tmp_path,context):
    scope,_=probe(context)
    monkeypatch.setattr(r.os,"geteuid",lambda:0)
    monkeypatch.setattr(r,"preflight",lambda *args,**kwargs:(scope,{}))
    monkeypatch.setattr(r,"root_dir",lambda path:None)
    monkeypatch.setattr(r.os,"chown",lambda *args:None)
    monkeypatch.setattr(r,"ROOT",tmp_path/"rescue")
    context.tx.sync=lambda path:None
    context.tx.atomic=lambda path,content,mode:path.write_bytes(content)
    monkeypatch.setattr(r,"scope_original",lambda *args:context.original)
    @contextmanager
    def locks():yield
    auth={"locks":locks,"owner":lambda scope:r.OWNER}
    context.engine.fail_before_start=True
    with pytest.raises(OSError):
        r.execute(context.I,None,context.modules,None,auth,context.candidate,context.payload)
    assert len(context.engine.calls)==1
    result=json.loads((r.ROOT/context.candidate/"result.json").read_text())
    assert result["status"]=="needs_governed_human_reconciliation"
    assert result["no_second_write_attempted"] is True
