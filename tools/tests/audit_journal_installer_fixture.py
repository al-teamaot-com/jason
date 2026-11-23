"""Composition of installer files/rollback in an isolated Root filesystem.

Parent-directory admission uses real isolated UID0/UID1000 filesystem metadata.
Owner issuer, remaining live admission, Docker daemon and systemd do not run.
The installation component receives synthetic paths and source bytes.
"""
from datetime import datetime,timezone
from pathlib import Path
from types import ModuleType
from hashlib import sha256
import json,os,stat,sys

def load(path,name):
 module=ModuleType(name);module.__file__=str(path)
 exec(compile(path.read_bytes(),str(path),"exec"),module.__dict__);return module

def exercise(base,trust):
 sys.path.insert(0,str(trust))
 total=0
 for scenario in ("queued","fail-before-queue","power-loss-before-queue"):
  install=load(trust/"tools/audit_journal_install.py","fixture_install")
  s=load(trust/"tools/audit_journal_release_scope.py","fixture_scope")
  root=base/("install-composition-"+scenario);root.mkdir(mode=0o755)
  archive=root/"archive";archive.mkdir();os.chown(archive,1000,984);archive.chmod(0o2770)
  record=root/"record";record.mkdir(mode=0o700);systemd=root/"systemd";systemd.mkdir()
  shared=root/"shared";shared.mkdir();active=shared/"orchestration-events.sqlite3"
  active.write_bytes(b"untouched-canonical");os.chown(active,1000,1000);active.chmod(0o600)
  identity=(active.stat().st_dev,active.stat().st_ino)
  desired=root/"desired.json"
  original=json.dumps({"required_system_units":[],"allowed_system_units":[],"rollback_container_prefixes":[],"max_stopped_rollback_containers":21}).encode()
  desired.write_bytes(original);desired.chmod(0o600)
  s.BASE=root/"library";s.PRIVATE=root/"data/private";s.CONTROL=root/"data/control"
  s.POLICY=root/"policy.json";s.ACTIVE=active;s.ARCHIVE=archive;s.PROFILE=root/"run/profile.json";s.DESIRED=desired
  s.SOURCES=("tools/fixture.py",);s.NATIVE={"tools/fixture-health.py":"health.py"}
  install.RECORD=record;install.SYSTEMD=systemd
  candidate="a"*40;scope={"action":s.ACTION,"policy":{"candidate_sha":candidate,"rollback_sha":s.ROLLBACK},
   "source_sha256":{"tools/fixture.py":sha256(b"reviewed").hexdigest()}}
  stamp=datetime.now(timezone.utc).isoformat()
  proof={"action":s.ACTION,"owner_oid":s.OWNER,"independently_verified_entra_owner":True,
         "approved_at":stamp,"claimed_at":stamp,"scope":scope,"scope_sha256":s.digest(scope)}
  (record/"approval.json").write_bytes(install.canonical(proof));(record/"approval.json").chmod(0o400)
  payload={"tools/fixture.py":b"reviewed","tools/fixture-health.py":b"reviewed-health"}
  for name in (*s.UNITS,*install.OVERRIDES):payload["infrastructure/jason-audit-journal/"+name]=b"[Unit]\nDescription=fixture\n"
  before={"fixture":{"State":{"StartedAt":stamp}}};after=s.desired_after(json.loads(original))
  fired=[]
  def command(args,**kwargs):
   if scenario!="queued" and args==["/usr/bin/systemctl","daemon-reload"] and not fired:
    fired.append(True)
    if scenario=="fail-before-queue":raise RuntimeError("fixture-command-failure")
    raise SystemExit("fixture-power-loss")
   return ""
  install.command=command
  try:install.install(s,payload,scope,before,original,after,s.OWNER,{},None)
  except RuntimeError:
   assert scenario=="fail-before-queue"
   assert not s.BASE.exists() and not s.PRIVATE.parent.exists() and desired.read_bytes()==original
   assert not list(systemd.iterdir()) and archive.stat().st_uid==1000
   assert stat.S_IMODE(archive.stat().st_mode)==0o2770
  except SystemExit:
   assert scenario=="power-loss-before-queue"
   install.install(s,payload,scope,before,original,after,s.OWNER,{},None)
  else:assert scenario=="queued"
  if scenario!="fail-before-queue":
   assert stat.S_IMODE((s.PRIVATE/"producer-before.json").stat().st_mode)==0o400
   assert stat.S_IMODE((s.BASE/"trusted/tools/fixture.py").stat().st_mode)==0o444
   assert all(stat.S_IMODE((systemd/unit).stat().st_mode)==0o644 for unit in s.UNITS)
   assert json.loads((record/"transaction.json").read_bytes())["outcome"]=="queued"
   assert archive.stat().st_uid==0 and stat.S_IMODE(archive.stat().st_mode)==0o755
   assert json.loads(desired.read_bytes())["max_stopped_rollback_containers"]==27
  assert active.read_bytes()==b"untouched-canonical" and (active.stat().st_dev,active.stat().st_ino)==identity
  total+=1
 return total


def exercise_parents(base,trust):
 """Actual preflight parent phase with the unchanged native directory guard."""
 install=load(trust/"tools/audit_journal_install.py","fixture_parent_install")
 native=load(trust/"tools/pmv4_e_operational_closure.py","fixture_parent_guard")
 root=base/"parent-admission";root.mkdir(mode=0o755)
 roots=("/usr/local/lib/jason","/etc/jason-owner-release","/etc/systemd/system", "/var/lib","/srv","/srv/jason")
 mapping={Path(n):root/n.lstrip("/") for n in roots}
 for p in mapping.values():
  p.mkdir(mode=0o755,parents=True,exist_ok=True);os.chown(p,0,0);p.chmod(0o755)
 service=Path("/var/lib/jason");mapping[service]=root/"var/lib/jason"
 mapping[service].mkdir(mode=0o750);os.chown(mapping[service],1000,1000);mapping[service].chmod(0o750)
 class ReachedDataAdmission(Exception):pass
 reached=[]
 def stop(_):
  reached.append(True);raise ReachedDataAdmission
 install.capacity=stop
 def guard(path,uid,mode=None):native.directory(mapping[path],uid,mode)
 def invoke():install.inspect(None,None,None,"a"*40,{}, {"directory":guard})
 def metadata():return {str(p):(p.lstat().st_uid,p.lstat().st_gid,stat.S_IMODE(p.lstat().st_mode)) for p in mapping.values()}
 before=metadata()
 try:invoke()
 except ReachedDataAdmission:pass
 else:raise AssertionError("parent admission did not reach data phase")
 assert reached==[True] and metadata()==before
 total=1
 cases=[(service,*bad) for bad in ((0,0,0o750,False),(1001,1000,0o750,False),(1000,984,0o750,False),
       (1000,1000,0o770,False),(1000,1000,0o752,False),(1000,1000,0o755,False),(1000,1000,0o750,True))]
 cases.extend((Path(name),*bad) for name in roots for bad in ((1000,1000,0o755,False),
       (0,1000,0o755,False),(0,0,0o775,False),(0,0,0o755,True)))
 for name,uid,gid,mode,link in cases:
  path=mapping[name];original=path.lstat();saved=(original.st_uid,original.st_gid,stat.S_IMODE(original.st_mode))
  backing=path.with_name(path.name+".fixture-original")
  reached.clear()
  try:
   if link:path.rename(backing);path.symlink_to(backing)
   else:os.chown(path,uid,gid);path.chmod(mode)
   try:invoke()
   except native.ClosureDenied:pass
   else:raise AssertionError("unsafe parent custody accepted")
   assert reached==[]
   total+=1
  finally:
   if link:path.unlink();backing.rename(path)
   else:os.chown(path,saved[0],saved[1]);path.chmod(saved[2])
 assert metadata()==before
 return total


def exercise_reserve(base,trust):
 """Root-private before-policy, native population and exact six-slot reserve."""
 install=load(trust/"tools/audit_journal_install.py","fixture_capacity_install")
 s=load(trust/"tools/audit_journal_release_scope.py","fixture_capacity_scope")
 root=base/"rollback-capacity";root.mkdir(mode=0o700)
 path=root/"before.json"
 before={"schema_version":"1.0","required_system_units":[],"allowed_system_units":[],
  "rollback_container_prefixes":["jason-runtime-rollback-","jason-mcp-pilot-rollback-",
   "jason-mcp-rollback-","jason-teams-gateway-rollback-"],"max_stopped_rollback_containers":21}
 original=install.canonical(before);path.write_bytes(original);path.chmod(0o600)
 assert path.stat().st_uid==path.stat().st_gid==0 and stat.S_IMODE(path.stat().st_mode)==0o600
 names=[]
 def command(argv,**kwargs):
  assert argv==["/usr/bin/docker","ps","-a","--filter","status=exited","--format","{{.Names}}"]
  return "\n".join(names)
 install.command=command
 total=0
 for count in (0,20,21,22,27):
  names[:]=["jason-runtime-rollback-fixture-"+str(i) for i in range(count)]+[
   "jason-pmv4-shadow-gateway","jason-mcp-signer-recovery-prior"]
  try:after,facts=install.recovery_capacity(s,json.loads(install.read(path)))
  except PermissionError as exc:
   assert count>21 and str(exc)=="JOURNAL_INSTALL_STOPPED_CONTAINER_BASELINE_CAPACITY"
  else:
   assert count<=21 and after["max_stopped_rollback_containers"]==27
   assert facts["existing_count"]==count and len(facts["existing_names"])==count
   assert facts["reserved_slots"]==6 and facts["cleanup_allowed"] is False
  assert path.read_bytes()==original;total+=1
 for limit in (20,22,27,200,True,21.0,"21",None):
  changed={**before,"max_stopped_rollback_containers":limit}
  try:install.recovery_capacity(s,changed)
  except PermissionError as exc:assert str(exc)=="AUDIT_REVIEWED_ROLLBACK_BASELINE_REQUIRED"
  else:raise AssertionError("unreviewed rollback baseline accepted")
  assert path.read_bytes()==original;total+=1
 names[:]=["jason-runtime-rollback-fixture-"+str(i) for i in range(21)]+[
  "jason-pmv4-ticket-core-rollback-audit-before-"+"a"*12]
 try:install.recovery_capacity(s,before)
 except PermissionError as exc:assert str(exc)=="JOURNAL_INSTALL_STOPPED_CONTAINER_BASELINE_CAPACITY"
 else:raise AssertionError("preexisting ticket recovery escaped the capacity gate")
 assert path.read_bytes()==original
 return total+1
