"""Real Root transition protocol under a held production mutex; synthetic inventory.

No host mounts, providers, credentials, Docker socket or production authority.
Native controller/watchdog logic is unchanged. Only their fixture paths and the
independent inventory/manifest observation are synthetic.
"""
import ast,fcntl,importlib.util,json,os,sys,threading,time
from pathlib import Path
from hashlib import sha256
TRUST=Path('/usr/local/lib/jason/audit-journal/trusted')
sys.path[:0]=[str(TRUST),str(TRUST/'implementation'),'/test-source']
from tools import audit_journal_release_scope as s
assert os.geteuid()==0 and not Path('/var/run/docker.sock').exists()
base=Path('/tmp/native-admission-fixture');base.mkdir(mode=0o755)
state=base/'state';state.mkdir(mode=0o700);os.chown(state,1000,1000)
queue=state/'protected-transitions';queue.mkdir(mode=0o755)
for name in ('requests','results'):
 p=queue/name;p.mkdir(mode=0o700);os.chown(p,1000,1000)
lock=state/'production-transaction.lock';lock.touch();lock.chmod(0o664);os.chown(lock,1000,1000)
policy=base/'desired.json';policy.write_text('{}');policy.chmod(0o600)
inventory=base/'inventory.json'
guard=base/'guard.py';guard.write_text("import json,sys\nfrom pathlib import Path\nr=json.loads(Path(__file__).with_name('inventory.json').read_text());print(json.dumps(r));raise SystemExit(0 if r['status']=='pass' else 2)\n");guard.chmod(0o444)
original=Path('/test-source/release_control_transition_worker.py').read_text()
assert sha256(original.encode()).hexdigest()==s.PROTECTED[str(s.ROOT_TRANSITION)]
# Bind the unchanged native routines to this container's disposable records.
raw=original.replace("ROOT=Path('/var/lib/jason/openclaw/release-manager')",'ROOT=Path('+repr(str(state))+')')
raw=raw.replace("DRIFT_CONFIG=Path('/etc/jason/release-readback-recovery/production-desired-state.json')",'DRIFT_CONFIG=Path('+repr(str(policy))+')')
raw=raw.replace("DRIFT_EVALUATOR=Path('/opt/jason/current/tools/production_drift_guard.py')",'DRIFT_EVALUATOR=Path('+repr(str(guard))+')')
controller=base/'native-controller.py';controller.write_text(raw);controller.chmod(0o444)
s.ROOT_TRANSITION=controller;s.ROOT_DRIFT_EVALUATOR=guard
s.PROTECTED={str(p):sha256(p.read_bytes()).hexdigest() for p in (controller,guard)}
s.STATE=state
spec=importlib.util.spec_from_file_location('fixture_native_controller',controller)
ctl=importlib.util.module_from_spec(spec);spec.loader.exec_module(ctl)
manifest={key:'fixture-'+key for key in ctl.PROTECTED_LKG_FIELDS}
manifest.update(complete=True,revision=s.ROLLBACK)
observed=dict(manifest)
ctl.verify_health=lambda revision:dict(observed)

def write(path,row,owner=0):
 path.write_text(json.dumps(row));os.chown(path,owner,owner);path.chmod(0o600)
def reset():
 write(ctl.CONTROL,{'schema_version':'1.0','circuit_breaker':{'state':'open'},'last_known_good':{'manifest':manifest}})
 write(ctl.DRIFT,{'schema_version':'1.0','status':'drift_detected','observed_at':'2026-11-23T00:00:00+00:00','problems':[{'kind':'required_system_unit_not_active','unit':'jason-audit-journal-maintenance.timer','state':'inactive'}]})
def report(pass_=True):
 from datetime import datetime,timezone
 return {'schema_version':'1.0','status':'pass' if pass_ else 'drift_detected','observed_at':datetime.now(timezone.utc).isoformat(),'problems':[] if pass_ else [{'kind':'unexpected_container','name':'fixture-unknown'}]}
reset();write(inventory,report())
# Use the actual installed-client function bodies, not a simulated RPC.
client_source=Path('/test-source/release_manager_host_runner.py').read_text()
nodes=ast.parse(client_source).body
names={'request_root_control_transition','atomic_json','exact_sha'}
functions=[ast.get_source_segment(client_source,n) for n in nodes if isinstance(n,ast.FunctionDef) and n.name in names]
assert len(functions)==len(names)
client=base/'client';client.mkdir(mode=0o755)
client_code="from __future__ import annotations\nimport json,os,re,time\nfrom pathlib import Path\nfrom uuid import uuid4\nSHA=re.compile(r'^[0-9a-f]{40}$')\nclass ReleaseManagerError(RuntimeError):pass\ndef control_state_path(root):return root/'production-control-state.json'\n"+'\n\n'.join(functions)
(client/'release_manager_host_runner.py').write_text(client_code)
code=s.native_revalidation_code().replace("'/home/al/.local/lib/jason'",repr(str(client)))
# Root receives actual UID-1000 private request files and returns its actual
# independently evaluated response. The child has no supplemental groups.
stop=threading.Event();errors=[]
def worker():
 while not stop.is_set():
  try:ctl.process()
  except BaseException as exc:errors.append(repr(exc));break
  stop.wait(.02)
thread=threading.Thread(target=worker,daemon=True);thread.start()
def request():
 import subprocess
 result=subprocess.run(['/usr/bin/python3','-I','-B','-c',code],user=1000,group=1000,extra_groups=(),
  env={'PATH':'/usr/bin:/bin','HOME':'/home/al','USER':'al','LOGNAME':'al','LANG':'C.UTF-8'},capture_output=True,text=True,timeout=15)
 assert not errors,errors
 return result
try:
 with lock.open('rb') as held:
  fcntl.flock(held,fcntl.LOCK_EX|fcntl.LOCK_NB)
  # A scheduled watchdog exit of zero under this mutex leaves old drift intact.
  spec=importlib.util.spec_from_file_location('fixture_watchdog','/test-source/production_drift_watchdog.py')
  wd=importlib.util.module_from_spec(spec);spec.loader.exec_module(wd)
  actual_transaction_probe=wd.production_transaction_active
  wd.production_transaction_active=lambda:actual_transaction_probe(lock)
  sys.argv=['fixture-watchdog','--config',str(policy),'--evidence',str(ctl.DRIFT),'--control-state',str(ctl.CONTROL),'--watchdog-state',str(state/'watchdog.json')]
  before=ctl.DRIFT.read_bytes();assert wd.main()==0
  assert json.loads((state/'watchdog.json').read_text())['status']=='deferred' and ctl.DRIFT.read_bytes()==before
  rejected=request();assert rejected.returncode==1 and 'production drift is not clean' in rejected.stdout,(rejected.returncode,rejected.stdout,rejected.stderr)
  assert json.loads(ctl.CONTROL.read_text())['circuit_breaker']['state']=='open'
  # Our actual helper calls the pinned native evaluator while retaining lock.
  s.refresh_native_drift()
  assert json.loads(ctl.DRIFT.read_text())['status']=='pass'
  assert json.loads(ctl.CONTROL.read_text())['circuit_breaker']['state']=='open'
  accepted=request();assert accepted.returncode==0,(accepted.stdout,accepted.stderr)
  assert json.loads(ctl.CONTROL.read_text())['circuit_breaker']['state']=='closed'
  # Genuine failed independent evaluation cannot clear the breaker.
  reset();write(inventory,report(False))
  try:s.refresh_native_drift()
  except ValueError as exc:assert 'independent production drift refresh did not pass' in str(exc)
  else:raise AssertionError('failed independent evaluation accepted')
  assert json.loads(ctl.CONTROL.read_text())['circuit_breaker']['state']=='open'
  # A clean drift report cannot bypass the immutable baseline fingerprint.
  write(inventory,report());s.refresh_native_drift();observed['runtime_image_id']='fixture-wrong-image'
  denied=request();assert denied.returncode==1 and 'immutable last-known-good mismatch: runtime_image_id' in denied.stdout
  assert json.loads(ctl.CONTROL.read_text())['circuit_breaker']['state']=='open'
  observed['runtime_image_id']=manifest['runtime_image_id']
  # Forward/final/rollback workers use Root's service to regenerate an expired
  # PASS, retaining the caller mutex and all immutable manifest checks.
  write(ctl.DRIFT,{'schema_version':'1.0','status':'pass','problems':[],
   'observed_at':'2026-11-23T00:00:00+00:00'})
  assert request().returncode==0
  assert json.loads(ctl.DRIFT.read_text())['observed_at']!='2026-11-23T00:00:00+00:00'
  reset();write(inventory,report(False))
  write(ctl.DRIFT,{'schema_version':'1.0','status':'pass','problems':[],
   'observed_at':'2026-11-23T00:00:00+00:00'})
  rejected=request();assert rejected.returncode==1 and 'independent production drift refresh did not pass' in rejected.stdout
  assert json.loads(ctl.CONTROL.read_text())['circuit_breaker']['state']=='open'
  # Source tampering denies before any native code is executed.
  guard.write_text(guard.read_text()+'\n# unreviewed change\n')
  try:s.refresh_native_drift()
  except PermissionError as exc:assert 'SOURCE_CHANGED' in str(exc)
  else:raise AssertionError('unreviewed native source executed')
  assert json.loads(ctl.CONTROL.read_text())['circuit_breaker']['state']=='open'
finally:
 stop.set();thread.join(timeout=3)
 assert not thread.is_alive() and not errors,errors
print(json.dumps({'test':'isolated-root-native-admission-under-held-mutex','result':'passed','cases':7,
 'original_deferred_watchdog_bug_reproduced':True,'real_uid1000_request_protocol':True,
 'genuine_native_refresh_precedes_transition':True,'immutable_lkg_guard_retained':True,
 'independent_failure_and_source_tamper_denied':True,'synthetic_inventory_only':True,
 'provider_contacted':False,'production_authority_issued':False}))
