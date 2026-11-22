"""Composition of installer files/rollback in an isolated Root filesystem.

No admission, Owner issuer, Docker daemon or systemd call runs in this fixture.
Only the filesystem component receives synthetic paths and source bytes.
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
  original=json.dumps({"required_system_units":[],"allowed_system_units":[],"rollback_container_prefixes":[]}).encode()
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
  assert active.read_bytes()==b"untouched-canonical" and (active.stat().st_dev,active.stat().st_ino)==identity
  total+=1
 return total
