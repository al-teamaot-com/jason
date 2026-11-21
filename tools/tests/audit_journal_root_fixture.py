"""Isolated two-identity test. Never run against host/production storage."""
import os,sys,json,sqlite3,subprocess,runpy
from pathlib import Path
from dataclasses import replace
BASE=Path("/tmp/audit-native-root-fixture")
TRUST=Path("/usr/local/lib/jason/audit-journal/trusted")
sys.path.insert(0,str(TRUST/"implementation"))
from orchestrator.segmented_journal import JournalProfile,SegmentedOrchestrationEventStore
from orchestrator.event_store import OrchestrationEvent,SQLiteOrchestrationEventStore
ns=runpy.run_path(str(TRUST/"tools/audit_journal_control.py"))
JournalController=ns["JournalController"];atomic=ns["atomic"]
p=JournalProfile(active=BASE/"data/active.sqlite3",control=BASE/"control",archives=BASE/"archive",
    pending=BASE/"pending",custody_uid=0,writer_uid=1000,fixture=True)

def event(identifier):
 return OrchestrationEvent(event_id=identifier,event_type="fixture.observer",execution_id="test",
 correlation_id="test",organization_id="fixture",principal_id="fixture",
 capability_name="fixture.read",stage="observed",payload={"fixture":True})

if len(sys.argv)>1:
 store=SegmentedOrchestrationEventStore(p)
 if sys.argv[1]=="write":store.append_event(event(sys.argv[2]))
 elif sys.argv[1]=="read":
  assert {e.event_id for e in store.list_by_execution("test")}==set(sys.argv[2:])
 elif sys.argv[1]=="legacy":
  old=SQLiteOrchestrationEventStore(p.active)
  assert {e.event_id for e in old.list_by_execution("test")}==set(sys.argv[2:]);old.close()
 elif sys.argv[1]=="attack":
  for target in (p.control/"catalog.json",next(p.archives.glob("*.sqlite3"))):
   try:target.write_bytes(b"tamper")
   except PermissionError:continue
   raise AssertionError("writer could modify Root custody")
 store.close();sys.exit(0)

assert os.geteuid()==0 and not Path("/var/run/docker.sock").exists()
BASE.mkdir(mode=0o755)
for name in ("data","control","archive","pending","work","local","private"):
 d=BASE/name;d.mkdir(mode=0o711 if name in ("work","local") else 0o755)
 if name=="private":d.chmod(0o700)
 if name=="data":os.chown(d,1000,1000);d.chmod(0o700)
(BASE/"fixture.json").write_text(json.dumps({"format":ns["FIXTURE"]}))
lock=p.control/"handoff.lock";lock.touch();lock.chmod(0o644)
atomic(p.control/"catalog.json",{"schema_version":"1.0","mode":"legacy","generation":0,
 "epoch":None,"segments":[]},owner=0)
controller=JournalController(p,BASE/"private",BASE/"work",BASE/"local",fixture=False)
atomic(BASE/"private/adoption.json",{"fixture":True,"production_authority":False},mode=0o400,owner=0)
controller._sql("create_active",{"target":str(p.active),"epoch":"fixture-initial"})
def writer(*args):
 subprocess.run(["/usr/sbin/runuser","-u","al","--","/usr/bin/python3","-I","-B",
                 __file__,*args],check=True,timeout=60)
writer("write","before")
def initial_fault(at):
 if at=="initial_claim":raise RuntimeError("fixture_power_loss_after_one_use_claim")
controller.fault=initial_fault
try:controller.transition(initial=True)
except RuntimeError as exc:assert str(exc)=="fixture_power_loss_after_one_use_claim"
else:raise AssertionError("fault did not run")
controller.fault=lambda _:None
assert controller.recover()["status"]=="transition_recovered"
writer("write","after")
writer("read","before","after");controller.seal_one()
writer("attack");controller.prepare_rollback()
writer("write","late");controller.finish_rollback();writer("legacy","before","after","late")
try:controller.transition(initial=True)
except FileExistsError:pass
else:raise AssertionError("one-use cutover authority replayed")
writer("legacy","before","after","late")
print(json.dumps({"test":"isolated-native-root-two-identity","result":"passed",
 "root_custody":True,"writer_uid":1000,"production_mounts":False,"all_events_retained":True}))
