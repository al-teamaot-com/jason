"""Synthetic Owner issuer/systemd; real Root files, transactions and power loss."""
import json,os,sys
from pathlib import Path
from types import SimpleNamespace
from datetime import datetime,timezone
from hashlib import sha256
TRUST=Path("/usr/local/lib/jason/audit-journal/trusted")
sys.path[:0]=[str(TRUST),str(TRUST/"implementation")]
from tools import audit_journal_pre_cutover_repair as r
from tools import audit_journal_install as install
from tools.audit_journal_install_transaction import InstallTransaction as NativeTransaction
BASE=Path("/tmp/context-repair-root-fixture")
assert os.geteuid()==0 and not Path("/var/run/docker.sock").exists()
assert not Path("/var/lib/jason/governed-ticket-shared/orchestration-events.sqlite3").exists()
BASE.mkdir(mode=0o755)
total=0
for scenario in ("queued","failure-before-queue","power-loss","tamper","queued-resume","native-failure"):
 root=BASE/scenario;root.mkdir();owner=root/"owner";owner.mkdir(mode=0o700)
 original_bootstrap=owner/"original-bootstrap";original_bootstrap.mkdir(mode=0o700)
 sentinel=original_bootstrap/"approval.json";sentinel.write_bytes(b"original immutable Owner approval");sentinel.chmod(0o400)
 original_approval=sha256(sentinel.read_bytes()).hexdigest()
 r.ROOT=owner/"context-repairs"
 private=root/"private";private.mkdir(mode=0o700);base=root/"library";base.mkdir()
 lock=private/"maintenance.lock";lock.touch();lock.chmod(0o600)
 source=base/"trusted/tools/fixture.py";source.parent.mkdir(parents=True);source.write_bytes(b"old-code");source.chmod(0o444)
 profile=root/"profile.json";control=root/"control";control.mkdir()
 public=lambda candidate:{"schema_version":"1.0","component_source_sha":candidate}
 old_profile=r.canon(public(r.OLD))
 for p in (profile,control/"profile.json"):p.write_bytes(old_profile);p.chmod(0o444)
 old_policy={"candidate_sha":r.OLD,"trusted_source_sha256":{"tools/fixture.py":r.digest(b"old-code")},
  "public_profile":public(r.OLD),"profile_sha256":r.digest(old_profile)}
 policy=root/"policy.json";policy.write_bytes(r.canon(old_policy));policy.chmod(0o600)
 desired=root/"desired.json";desired.write_bytes(b'{"limit":27}');desired.chmod(0o600)
 active=root/"active.sqlite3";active.write_bytes(b"canonical-not-cut-over");os.chown(active,1000,1000);active.chmod(0o600)
 identity=(active.stat().st_dev,active.stat().st_ino)
 catalog=control/"catalog.json";catalog.write_bytes(r.canon({"mode":"legacy","generation":0,"epoch":None,"segments":[]}));catalog.chmod(0o444)
 before={"jason-runtime":{"Id":"a"*64,"Image":"sha256:"+"b"*64,"State":{"StartedAt":"2026-11-18T00:00:00Z","Running":True}}}
 originals={n:r.canon({"original":n}) for n in r.PRIVATE_NAMES}
 originals["producer-before.json"]=r.canon(before)
 originals["release-journal.json"]=r.canon({"steps":{},"scope_sha256":r.OLD_SCOPE,"recovery_started_at":"2026-11-23T14:18:07+00:00"})
 for n,raw in originals.items():p=private/n;p.write_bytes(raw);p.chmod(0o400)
 candidate="b"*40;payload={"tools/fixture.py":b"new-code","tools/audit_journal_install.py":b"frozen-installer-fixture"}
 scope={"action":"ADOPT-EXACT-DAILY-AUDIT-JOURNAL","policy":{"candidate_sha":candidate,"rollback_sha":"d"*40},
  "source_sha256":{"tools/fixture.py":r.digest(b"new-code")},"source_dataset_identity":{"device":identity[0],"inode":identity[1]},
  "protected_peer_before":{},"desired_state_initial_sha256":r.digest(b'{"limit":27,"timer":"allowed"}'),
  "desired_state_after_sha256":r.digest(desired.read_bytes()),"desired_state_before_sha256":r.digest(desired.read_bytes()),"pre_cutover_context_repair":{"previous_scope_sha256":r.OLD_SCOPE,"catalog_before_sha256":r.digest(catalog.read_bytes())}}
 s=SimpleNamespace(BASE=base,PRIVATE=private,CONTROL=control,POLICY=policy,PROFILE=profile,DESIRED=desired,
  ACTIVE=active,PROTECTED={},digest=lambda value:r.digest(r.canon(value)),protected_peer_inventory=lambda:{},
  desired_initial=lambda value:{"limit":27,"timer":"allowed"},desired_after=lambda value:{"limit":27},
  ACTION=scope["action"],OWNER="bee80bdc-ffb0-4c50-b453-c09d4d411f5f",ROLLBACK="d"*40,public_profile=public)
 engine=SimpleNamespace(DockerEngine=lambda:SimpleNamespace(inspect=lambda role:before[role]),
  exact_original_configuration=lambda row:{"Image":row["Image"]})
 modules={"audit_journal_release_scope":s,"audit_journal_container_release":engine}
 unit={"state":"failed","enabled":True};fired=[];commands=[]
 def command(argv,**kwargs):
  commands.append(argv)
  assert argv[0]=="/usr/bin/systemctl" and "docker" not in " ".join(argv)
  if argv[1]=="show":return "ActiveState="+unit["state"]+"\nSubState="+unit["state"]+"\nMainPID=0\nUnitFileState="+("enabled" if unit["enabled"] else "disabled")
  if argv[1]=="disable":unit["enabled"]=False;return ""
  if argv[1]=="reset-failed":
   if scenario=="failure-before-queue" and not fired:fired.append(True);raise RuntimeError("fixture-failure-before-queue")
   unit["state"]="inactive";return ""
  if argv[1]=="enable":unit["enabled"]=True;return ""
  assert argv[1:3]==["--no-block","start"];return ""
 I=SimpleNamespace(RECORD=original_bootstrap,command=command,read=install.read,digest=install.digest)
 def native_gate(I,s,scope):
  assert r.digest(s.DESIRED.read_bytes())==scope["desired_state_initial_sha256"]
  assert unit["state"]=="inactive" and not unit["enabled"]
  if scenario=="native-failure" and not fired:fired.append(True);raise RuntimeError("fixture-native-revalidation-failed")
 r.revalidate_before_queue=native_gate
 row=r.claim(I,candidate,payload,scope,before,originals,r.canon(old_policy),desired.read_bytes(),
  "bee80bdc-ffb0-4c50-b453-c09d4d411f5f",{"fixture_only":True})
 frozen=r.ledger(candidate)/"source";I.REPO=frozen;I.__file__=str(frozen/"tools/audit_journal_install.py")
 def fault(at):
  if scenario in ("power-loss","tamper") and at=="replacement_published" and not fired:
   fired.append(True);raise SystemExit("fixture-power-loss")
 class Transaction(NativeTransaction):
  def __init__(self,*args,**kwargs):super().__init__(*args,**kwargs,fault=fault)
 r.InstallTransaction=Transaction
 try:r.apply(I,s,candidate,engine)
 except RuntimeError:
  assert scenario in ("failure-before-queue","native-failure")
  assert source.read_bytes()==b"old-code" and policy.read_bytes()==r.canon(old_policy)
  assert all((private/n).read_bytes()==raw for n,raw in originals.items())
  if scenario=="native-failure":
   previous_constants=(r.FAILED_CONTEXT_CANDIDATE,r.FAILED_CONTEXT_SCOPE)
   r.FAILED_CONTEXT_CANDIDATE=candidate;r.FAILED_CONTEXT_SCOPE=row["scope_sha256"]
   attested=r.verify_rolled_back_context(s,originals,r.canon(old_policy))
   assert attested["outcome"]=="rolled_back" and not attested["old_execution_authority_reused"]
   # An altered before-image, queued transaction, Owner grant or retry denies.
   source.write_bytes(b"unknown-restored-code");source.chmod(0o444)
   try:r.verify_rolled_back_context(s,originals,r.canon(old_policy))
   except PermissionError:pass
   else:raise AssertionError("altered restored target accepted")
   source.write_bytes(b"old-code");source.chmod(0o444)
   txpath=r.ledger(candidate)/"transaction.json";txraw=txpath.read_bytes()
   transaction=json.loads(txraw);transaction["outcome"]="queued";txpath.write_bytes(r.canon(transaction))
   try:r.verify_rolled_back_context(s,originals,r.canon(old_policy))
   except PermissionError:pass
   else:raise AssertionError("queued prior execution accepted")
   txpath.write_bytes(txraw)
   authpath=r.ledger(candidate)/"authorization.json";authraw=authpath.read_bytes()
   grant=json.loads(authraw);grant["independently_verified_entra_owner"]=False;authpath.write_bytes(r.canon(grant))
   try:r.verify_rolled_back_context(s,originals,r.canon(old_policy))
   except PermissionError:pass
   else:raise AssertionError("unverified old Owner accepted")
   authpath.write_bytes(authraw)
   retry=r.ledger(candidate)/"retry.json";retry.write_bytes(b'{}');retry.chmod(0o400)
   try:r.verify_rolled_back_context(s,originals,r.canon(old_policy))
   except PermissionError:pass
   else:raise AssertionError("concurrently claimed old retry accepted")
   retry.unlink();r.FAILED_CONTEXT_CANDIDATE,r.FAILED_CONTEXT_SCOPE=previous_constants
  r.execute(I,candidate,{}, modules,None,None,{},resume=True)
 except SystemExit:
  assert scenario in ("power-loss","tamper")
  if scenario=="tamper":source.write_bytes(b"unknown-root-write");source.chmod(0o444)
  try:r.execute(I,candidate,{}, modules,None,None,{},resume=True)
  except PermissionError:
   assert scenario=="tamper" and source.read_bytes()==b"unknown-root-write"
  else:assert scenario=="power-loss"
 if scenario!="tamper":
  assert source.read_bytes()==b"new-code" and json.loads(policy.read_bytes())["candidate_sha"]==candidate
  assert json.loads((private/"release-plan.json").read_bytes())["scope_sha256"]==row["scope_sha256"]
  assert json.loads((private/"release-journal.json").read_bytes())["supersedes_failed_scope_sha256"]==r.OLD_SCOPE
  assert json.loads((r.ledger(candidate)/"transaction.json").read_bytes())["outcome"]=="queued" and unit["enabled"]
  if scenario=="queued-resume":r.execute(I,candidate,{}, modules,None,None,{},resume=True)
 for n,raw in originals.items():assert (r.ledger(candidate)/"before-private"/n).read_bytes()==raw
 assert sha256(sentinel.read_bytes()).hexdigest()==original_approval
 assert active.read_bytes()==b"canonical-not-cut-over" and (active.stat().st_dev,active.stat().st_ino)==identity
 assert not any("revalidate" in " ".join(argv) for argv in commands)
 if (r.ledger(candidate)/"retry.json").exists():
  try:r.execute(I,candidate,{}, modules,None,None,{},resume=True)
  except PermissionError as exc:assert "ONE_BOUNDED_RETRY" in str(exc)
  else:raise AssertionError("unbounded retry accepted")
 total+=1
print(json.dumps({"test":"isolated-root-precutover-context-repair","result":"passed","cases":total,
 "original_approval_preserved":True,"failed_execution_preserved":True,"prior_failed_context_restoration_cases":5,"new_exact_scope_binding":True,
 "power_loss_resumed_once":True,"unknown_changed_target_denied":True,"actual_immutable_file_modes":True,
 "canonical_data_unchanged":True,"provider_contacted":False,"production_authority_issued":False}))
