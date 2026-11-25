"""Isolated two-identity/mount test. No production or Host storage allowed."""
import os,sys,json,sqlite3,subprocess,runpy,ctypes
from pathlib import Path
from contextlib import closing
BASE=Path("/tmp/audit-native-root-fixture")
ARC=BASE/"archive-root"
TRUST=Path("/usr/local/lib/jason/audit-journal/trusted")
sys.path.insert(0,str(TRUST/"implementation"))
from orchestrator.segmented_journal import JournalProfile,SegmentedOrchestrationEventStore
from orchestrator.event_store import OrchestrationEvent,SQLiteOrchestrationEventStore
ns=runpy.run_path(str(TRUST/"tools/audit_journal_control.py"))
JournalController=ns["JournalController"];atomic=ns["atomic"]
p=JournalProfile(active=BASE/"data/active.sqlite3",control=BASE/"control",archives=ARC/"orchestration",
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
 elif sys.argv[1] in ("legacy","legacy-write"):
  old=SQLiteOrchestrationEventStore(p.active)
  if sys.argv[1]=="legacy-write":old.append_event(event(sys.argv[2]))
  else:assert {e.event_id for e in old.list_by_execution("test")}==set(sys.argv[2:])
  old.close()
 elif sys.argv[1]=="attack":
  for target in (p.control/"catalog.json",next(p.archives.glob("*.sqlite3"))):
   try:target.write_bytes(b"tamper")
   except PermissionError:continue
   raise AssertionError("writer could modify Root custody")
 elif sys.argv[1]=="view":
  # Simulates the recreated container's recursive parent-directory bind.
  old=SQLiteOrchestrationEventStore(BASE/"view/active.sqlite3")
  assert {e.event_id for e in old.list_by_execution("test")}==set(sys.argv[2:]);old.close()
 store.close();sys.exit(0)

assert os.geteuid()==0 and not Path("/var/run/docker.sock").exists()
assert not Path("/var/lib/jason/authority").exists()
BASE.mkdir(mode=0o755,exist_ok=True)
ARC.mkdir(mode=0o755,exist_ok=True)
assert ARC.stat().st_dev!=BASE.stat().st_dev,"separate test filesystems required"
for name in ("data","control","pending","local","private","view"):
 d=BASE/name;d.mkdir(mode=0o755)
 if name=="private":d.chmod(0o700)
 if name=="data":os.chown(d,1000,1000);d.chmod(0o700)
for name in ("orchestration","work","rollback"):
 d=ARC/name;d.mkdir(mode=0o711 if name=="work" else 0o750);os.chown(d,0,1000)
(BASE/"fixture.json").write_text(json.dumps({"format":ns["FIXTURE"]}))
lock=p.control/"handoff.lock";lock.touch();lock.chmod(0o644)
atomic(p.control/"catalog.json",{"schema_version":"1.0","mode":"legacy","generation":0,
 "epoch":None,"segments":[]},owner=0)
controller=JournalController(p,BASE/"private",ARC/"work",BASE/"local",fixture=False)
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
writer("write","after");writer("read","before","after")
controller.seal_one();writer("attack")
controller.prepare_rollback();controller.recovery().accept_recipe()
identifier=p.catalog()["segments"][0]["id"]
controller.reclaim(identifier)
assert not list(p.pending.iterdir()),"original source must actually be reclaimed"
writer("write","late");controller.finish_rollback()
writer("legacy","before","after","late")
assert p.active.stat().st_dev==ARC.stat().st_dev
writer("legacy-write","after-rollback")
# A fresh recursive directory bind is how recreated container mounts inherit the
# canonical file submount. Its WAL names refer to the same containing directory.
lib=ctypes.CDLL(None,use_errno=True)
lib.mount.argtypes=[ctypes.c_char_p,ctypes.c_char_p,ctypes.c_char_p,ctypes.c_ulong,ctypes.c_void_p]
assert lib.mount(str(BASE/"data").encode(),str(BASE/"view").encode(),None,4096|16384,None)==0
writer("view","before","after","late","after-rollback")
lib.umount2.argtypes=[ctypes.c_char_p,ctypes.c_int]
assert lib.umount2(str(BASE/"view/active.sqlite3").encode(),0)==0
assert lib.umount2(str(BASE/"view").encode(),0)==0
# Reboot model: remove the ephemeral bind, retain the archive file/private
# marker, then run the same recorded-source restoration operation.
assert lib.umount2(str(p.active).encode(),0)==0
assert p.active.stat().st_size==0
controller.recovery().restore_mount()
writer("legacy","before","after","late","after-rollback")
try:controller.transition(initial=True)
except FileExistsError:pass
else:raise AssertionError("one-use cutover authority replayed")
# A Root SQL-helper timeout must not leave its UID1000 descendant holding
# the journal open. This read-only helper is deliberately interrupted at startup.
try:controller._sql("state",{"path":str(p.active)},seconds=0.001)
except subprocess.TimeoutExpired:pass
else:raise AssertionError("startup timeout did not occur")
controller.no_handles(p.active)
bootstrap=runpy.run_path("/bootstrap_fixture.py")
cases=bootstrap["exercise"](BASE,TRUST)
installer_fixture=runpy.run_path("/installer_fixture.py")
parent_admission=installer_fixture["exercise_parents"](BASE,TRUST)
capacity_admission=installer_fixture["exercise_reserve"](BASE,TRUST)
composition=installer_fixture["exercise"](BASE,TRUST)
print(json.dumps({"sql_helper_timeout_group_reaped":True,"root_parent_admission_cases":parent_admission,"root_rollback_capacity_cases":capacity_admission,"root_install_composition_cases":composition,"root_bootstrap_interruption_cases":cases,"test":"isolated-native-root-two-identity","result":"passed",
 "root_custody":True,"writer_uid":1000,"distinct_filesystems":True,"production_mounts":False,
 "all_events_retained":True,"original_source_reclaimed":True,"reboot_mapping_restored":True,
 "recursive_container_bind_verified":True}))
