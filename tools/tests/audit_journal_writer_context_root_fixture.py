"""Required PAM-session denial under the journal capability/NNP boundary."""
import json,os,resource,runpy,sqlite3,subprocess,sys
from pathlib import Path
from types import SimpleNamespace
BASE=Path("/tmp/audit-writer-context")
TRUST=Path("/usr/local/lib/jason/audit-journal/trusted")
ENTRY=TRUST/"tools/audit_journal_control.py"
sys.path[:0]=[str(TRUST),str(TRUST/"implementation")]
from orchestrator.event_store import _SCHEMA
from orchestrator.segmented_journal import JournalProfile
assert os.geteuid()==0 and not Path("/var/run/docker.sock").exists()
assert not Path("/var/lib/jason/authority").exists()
status=dict(line.split(":",1) for line in Path("/proc/self/status").read_text().splitlines() if ":" in line)
assert status["NoNewPrivs"].strip()=="1"
assert int(status["CapBnd"].strip(),16)&(1<<24)==0  # CAP_SYS_RESOURCE stays absent.
resource.setrlimit(resource.RLIMIT_NOFILE,(524288,524288))
# Only a private container tmpfs is writable here; never change Host PAM.
assert os.path.ismount("/etc/pam.d")
Path("/etc/pam.d/runuser").write_bytes(Path("/writer-pam.conf").read_bytes())
Path("/etc/pam.d/runuser").chmod(0o644)
BASE.mkdir(mode=0o755)
for name,mode,uid,gid in (("data",0o700,1000,1000),("private",0o700,0,0),
 ("work",0o711,0,0),("local",0o711,0,0),("control",0o755,0,0),("archives",0o750,0,1000),("pending",0o750,0,1000)):
 p=BASE/name;p.mkdir(mode=mode);os.chown(p,uid,gid);p.chmod(mode)
active=BASE/"data/active.sqlite3"
db=sqlite3.connect(active);db.executescript(_SCHEMA);db.close();os.chown(active,1000,1000);active.chmod(0o600)
loader='import runpy,sys;sys.path.insert(0,sys.argv[1]);p=sys.argv[2];sys.argv=[p,*sys.argv[3:]];runpy.run_path(p,run_name="__main__")'
argv=["/usr/bin/python3","-I","-B","-c",loader,str(TRUST/"implementation"),str(ENTRY),
 "--sql-operation","state","--sql-arguments",json.dumps({"path":str(active)})]
failed=subprocess.run(["/usr/sbin/runuser","-u","al","--",*argv],capture_output=True,text=True,timeout=15)
assert failed.returncode!=0 and "session" in failed.stderr.lower(),failed.stderr
ns=runpy.run_path(str(ENTRY),run_name="writer_context_fixture")
p=JournalProfile(active=active,control=BASE/"control",archives=BASE/"archives",pending=BASE/"pending",fixture=True)
c=ns["JournalController"](p,BASE/"private",BASE/"work",BASE/"local",fixture=False)
state=c._sql("state",{"path":str(active)},seconds=15)
assert state["watermark"]==0 and state["epoch"] is None
probe='import json,os;from pathlib import Path;s=dict(x.split(":",1) for x in Path("/proc/self/status").read_text().splitlines() if ":" in x);print(json.dumps({"uids":os.getresuid(),"gids":os.getresgid(),"groups":os.getgroups(),"nnp":s["NoNewPrivs"].strip(),"cap":s["CapEff"].strip(),"home":os.environ.get("HOME")}))'
identity=subprocess.run(["/usr/bin/python3","-I","-B","-c",probe],capture_output=True,text=True,check=True,timeout=15,**c.writer_identity())
identity=json.loads(identity.stdout)
assert identity["uids"]==[1000]*3 and identity["gids"]==[1000]*3 and identity["groups"]==[]
assert identity["nnp"]=="1" and int(identity["cap"],16)==0 and identity["home"]=="/home/al"
c._sql("barrier",{"path":str(active),"enabled":True,"block_invoking":True},seconds=15)
db=sqlite3.connect(active);assert db.execute("SELECT count(*) FROM sqlite_master WHERE type='trigger'").fetchone()[0]==2;db.close()
c._sql("barrier",{"path":str(active),"enabled":False},seconds=15)
db=sqlite3.connect(active);assert db.execute("SELECT count(*) FROM sqlite_master WHERE type='trigger'").fetchone()[0]==0;db.close()
print(json.dumps({"test":"isolated-hardened-writer-context","result":"passed","pam_login_handoff_denied":True,
 "fixed_uid_helper_succeeded":True,"writer_uid":1000,"writer_gid":1000,"supplementary_groups_empty":True,
 "no_new_privs":True,"cap_sys_resource_added":False,"writer_effective_capabilities":0,
 "actual_sql_read_and_barrier_recovery_verified":True,"provider_contacted":False,"production_mounts":False}))
