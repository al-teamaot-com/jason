"""Full fail-closed tests for two-trigger atomic legacy admission restoration."""
from contextlib import contextmanager
from pathlib import Path
import json,os,sqlite3,subprocess,sys
import pytest
from tools import audit_journal_legacy_admission_rescue as a
from tools.tests.test_audit_journal_ticket_core_rescue import context as core_context

@pytest.fixture
def t(monkeypatch):
    # Reuse deterministic full producer before-image and intentionally
    # incomplete interrupted-release fixture from the ticket-core recovery.
    c=core_context.__wrapped__(monkeypatch)
    prior_core=c.previous
    prior_core[a.PRIVATE/"release-plan.json"]["scope"]["policy"]={
        "candidate_sha":a.OLD,"rollback_sha":a.ROLLBACK}
    scope=prior_core[a.PRIVATE/"release-plan.json"]["scope"]
    monkeypatch.setattr(a,"OLD_SCOPE",a.digest(scope))
    plan=prior_core[a.PRIVATE/"release-plan.json"]
    plan["scope_sha256"]=a.OLD_SCOPE
    plan["owner_oid"]=a.OWNER
    journal=prior_core[a.PRIVATE/"release-journal.json"]
    journal["scope_sha256"]=a.OLD_SCOPE
    prior_core[a.PRIVATE/"adoption.json"]["scope_sha256"]=a.OLD_SCOPE
    prior_core[a.PRIVATE/"producer-before.json"][a.CANDIDATE_ROLE]["State"]={"Running":True}
    original=prior_core[a.PRIVATE/"producer-before.json"]
    plan["producer_before_sha256"]=a.digest(original)
    monkeypatch.setattr(a,"PINNED_ID",c.rows[a.CANDIDATE_ROLE]["Id"])
    prior_core[a.PRIOR_RESCUE/"authorization.json"]={
        "candidate_sha":a.RESCUE,
        "action":"RESTORE-EXACT-PMV4-TICKET-CORE-AFTER-AUDIT-ROLLBACK",
        "scope_sha256":a.RESCUE_SCOPE,"owner_oid":a.OWNER,
        "independently_verified_entra_owner":True,
        "one_use":True,"old_approval_reused":False,
    }
    prior_core[a.PRIOR_RESCUE/"result.json"]={
        "status":"ticket_core_running_verified","scope_sha256":a.RESCUE_SCOPE,
        "restored_container_id":a.PINNED_ID,
    }
    c.rows[a.CANDIDATE_ROLE]["State"]={
        "Status":"running","Running":True,"Health":{"Status":"healthy"}}
    before={n:["orchestration_events",h] for n,h in a.EXPECTED_TRIGGER_SHA.items()}
    calls=[]
    def sql(mode):
        calls.append(mode)
        if mode=="read":return {"operation":"read","before":before,"after":before,"writer_uid":1000}
        if mode=="clear":return {"operation":"clear","before":before,"after":{},
                                 "writer_uid":1000,"only_exact_two_ddl_drops":True}
    monkeypatch.setattr(a,"sql",sql)
    c.sql_calls=calls
    c.payload["tools/audit_journal_legacy_admission_rescue.py"]=b"reviewed-safe-source"
    return c

def check(t):
    return a.preflight(t.I,None,t.modules,None,t.candidate,t.payload,production=False)

def test_readonly_root_preflight_exact_old_authority_and_two_triggers(t):
    scope=check(t)
    assert scope["action"]==a.ACTION
    assert scope["exact_installed_legacy_trigger_sha256"]==a.EXPECTED_TRIGGER_SHA
    assert scope["one_use"] is True and scope["standing_authority"] is False
    assert scope["release_service_restart_excluded"] is True
    assert scope["native_breaker_reset_excluded"] is True
    assert scope["failed_journal_receipt_unchanged"] is True
    assert t.sql_calls==["read"]

@pytest.mark.parametrize("what",[
    "altered_original_plan","journal_finished","journal_unknown_step",
    "missing_prior_owner_receipt","wrong_owner","ticket_core_not_running",
    "ticket_core_changed_security","catalog_migrated","unknown_trigger",
    "prior_rescue_result_not_success",
])
def test_unapproved_or_changed_prior_evidence_denied(monkeypatch,t,what):
    data=t.previous
    if what=="altered_original_plan":
        data[a.PRIVATE/"release-plan.json"]["candidate_sha"]="0"*40
    elif what=="journal_finished":
        data[a.PRIVATE/"release-journal.json"]["outcome"]="rolled_back"
    elif what=="journal_unknown_step":
        data[a.PRIVATE/"release-journal.json"]["steps"]["unreviewed"]={}
    elif what=="missing_prior_owner_receipt":
        data[a.PRIOR_RESCUE/"authorization.json"]["independently_verified_entra_owner"]=False
    elif what=="wrong_owner":
        data[a.PRIVATE/"adoption.json"]["owner_oid"]="WRONG"
    elif what=="ticket_core_not_running":
        t.rows[a.CANDIDATE_ROLE]["State"]["Running"]=False
    elif what=="ticket_core_changed_security":
        t.rows[a.CANDIDATE_ROLE]["HostConfig"]["Privileged"]=True
    elif what=="catalog_migrated":
        data[a.CONTROL/"catalog.json"]["mode"]="segmented"
    elif what=="unknown_trigger":
        real={n:["orchestration_events",h] for n,h in a.EXPECTED_TRIGGER_SHA.items()}
        real["audit_journal_maintenance_other"]=["orchestration_events","0"*64]
        monkeypatch.setattr(a,"sql",lambda mode:{"operation":mode,"before":real,"after":real})
    elif what=="prior_rescue_result_not_success":
        data[a.PRIOR_RESCUE/"result.json"]["status"]="not_complete"
    with pytest.raises(PermissionError):
        check(t)

def ci_sqlite_fixture_program():
    # Production must run as Jason's fixed writer UID/GID 1000. GitHub-hosted
    # disposable SQLite runners use arbitrary UIDs; change ONLY the assertion
    # in this test's in-memory copy. Never loosen production SQL_PROGRAM.
    guard="assert os.geteuid()==1000 and os.getegid()==1000 and len(sys.argv)==3"
    assert a.SQL_PROGRAM.count(guard)==1
    assert "DROP TRIGGER audit_journal_maintenance_admission" in a.SQL_PROGRAM
    assert "DROP TRIGGER audit_journal_maintenance_invoking" in a.SQL_PROGRAM
    return a.SQL_PROGRAM.replace(
        guard,
        "assert os.geteuid()=="+str(os.geteuid())+
        " and os.getegid()=="+str(os.getegid())+
        " and len(sys.argv)==3",
    )


def test_real_sqlite_atomic_dual_drop_never_modifies_data_rows(tmp_path):
    dbpath=tmp_path/"audit.sqlite3"
    db=sqlite3.connect(dbpath)
    db.execute("CREATE TABLE orchestration_events (id INTEGER PRIMARY KEY, event_type TEXT)")
    db.executemany("INSERT INTO orchestration_events(id,event_type) VALUES(?,?)",
                   [(1,"orchestration.request.received"),(2,"orchestration.capability.invoking")])
    for name,event in (("audit_journal_maintenance_admission","orchestration.request.received"),
                       ("audit_journal_maintenance_invoking","orchestration.capability.invoking")):
        db.execute("CREATE TRIGGER "+name+"\nBEFORE INSERT ON orchestration_events\n"
                   "WHEN NEW.event_type = '"+event+"'\n"
                   "BEGIN SELECT RAISE(ABORT,'JASON_AUDIT_JOURNAL_MAINTENANCE'); END")
    db.commit();db.close()
    def child(mode):
        out=subprocess.run([sys.executable,"-I","-B","-c",ci_sqlite_fixture_program(),mode,str(dbpath)],
                           capture_output=True,text=True,timeout=12)
        assert out.returncode==0,out.stderr
        return json.loads(out.stdout)
    before=child("read")
    assert before["before"]=={n:["orchestration_events",h] for n,h in a.EXPECTED_TRIGGER_SHA.items()}
    drop=child("clear")
    assert drop["before"]==before["before"] and drop["after"]=={}
    assert child("read")["after"]=={}
    db=sqlite3.connect(dbpath)
    assert db.execute("SELECT count(*) FROM orchestration_events").fetchone()==(2,)
    db.execute("INSERT INTO orchestration_events VALUES(3,'orchestration.request.received')")
    assert db.execute("SELECT count(*) FROM orchestration_events").fetchone()==(3,)
    db.close()

def test_ambiguous_or_changed_ddl_refuses_execution(tmp_path):
    dbpath=tmp_path/"audit.sqlite3"
    db=sqlite3.connect(dbpath)
    db.execute("CREATE TABLE orchestration_events (event_type TEXT)")
    db.execute("CREATE TRIGGER audit_journal_maintenance_admission BEFORE INSERT ON orchestration_events BEGIN SELECT RAISE(ABORT,'UNKNOWN'); END")
    db.commit();db.close()
    out=subprocess.run([sys.executable,"-I","-B","-c",ci_sqlite_fixture_program(),"clear",str(dbpath)],
                       capture_output=True,text=True,timeout=12)
    assert out.returncode!=0
    db=sqlite3.connect(dbpath)
    assert db.execute("SELECT name FROM sqlite_master WHERE type='trigger'").fetchone()[0]=="audit_journal_maintenance_admission"
    db.close()

def test_new_owner_approval_required_before_any_sql_write(monkeypatch,t):
    scope=check(t)
    @contextmanager
    def locks():yield
    monkeypatch.setattr(a.os,"geteuid",lambda:0)
    monkeypatch.setattr(a,"preflight",lambda *args,**kwargs:scope)
    with pytest.raises(PermissionError,match="EXACT_LICENSED_OWNER_REQUIRED"):
        a.execute(t.I,None,t.modules,None,{"locks":locks,"owner":lambda _: "wrong-owner"},
                  t.candidate,t.payload)
    assert "clear" not in t.sql_calls
