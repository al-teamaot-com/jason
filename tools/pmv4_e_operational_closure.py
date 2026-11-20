#!/usr/bin/env python3
"""One exact Owner-approved operational closure after accepted Stage E.

Archive disabled legacy trigger files, bind the accepted watchdog/source,
and request the existing root transition's same-runtime LKG recapture.
Never changes accepted release code/policy, provider state, freeze or images.
"""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
from hashlib import sha256
import json,os,re,stat,subprocess,sys,time
from pathlib import Path

REPO=Path(__file__).resolve().parents[1]
ART=Path('/srv/jason/archive/engineering-artifacts')
BASE=Path('/usr/local/lib/jason/pmv4-e-bootstrap')
NATIVE=BASE/'native'
MANAGER=Path('/var/lib/jason/openclaw/release-manager')
CONTROL_SHA='1a7e7c1b03fce7dffa3ac6aab26480d614327e69'
ROLLBACK='d1b8c196dadd4b672ec8ba47075f27bb61c98d63'
ACCEPTED_POLICY='9110f982e7294fa789c8cd976223aa223143e924fd8bcec368f72b83a8d785b1'
ACCEPTED_SCOPE='837f719e01a6817846cdd095c9a527445c7f890dc79c5495adaf651902184ddd'
ACCEPTED_MANIFEST='aa00682975ce526fff9acb81577c726c9f248e2a47c8c5a433cf37aef0ef7d76'
INSTALLER_SHA='6d276b67538e1bf988a751dc9ef10ac6996cc6955ff6bc3e562a506da13282f7'
ACTION='COMPLETE-EXACT-PMV4-E-OPERATIONAL-CLOSURE'
LINK=Path('/home/al/.local/lib/jason/engineering-worker-source')
ENGINEERING=ART/('pmv4-e-engineering-source-'+CONTROL_SHA)
DROPIN=Path('/home/al/.config/systemd/user/jason-self-heal-watchdog.service.d/99-pmv4-e-accepted-source.conf')
DROPIN_BYTES=b'''[Service]\nExecStart=\nExecStart=/usr/bin/python3 -B /home/al/.local/lib/jason/jason_self_heal_watchdog.py --root /var/lib/jason/openclaw/self-heal --max-attempts 2\nEnvironment=PYTHONPATH=/opt/jason/current/tools\n'''
PAUSE=Path('/var/lib/jason/openclaw/support-repair/pmv3-engineering-owner-pause.json')
MARKER=Path('/etc/jason-owner-release/pmv4-e/replacement-retirement-accepted.json')
ROOT_POLICY=Path('/etc/jason/release-readback-recovery/production-desired-state.json')
OLD_USER=('jason-release-approval-only.timer','jason-release-manager.timer','jason-support-repair-worker.timer')
OLD_ROOT=('jason-release-control-readback.timer','jason-release-control-transition.timer','jason-release-host-reconcile.path')
NEW_USER=('jason-pmv4-component-release.timer','jason-pmv4-engineering.timer','jason-pmv4-release-approval.timer')
NEW_ROOT=('jason-pmv4-component-readback.timer','jason-pmv4-component-reconcile.path','jason-pmv4-component-transition.timer')
PEERS=('jason-runtime','jason-mcp-pilot','jason-pmv4-ticket-core','jason-pmv4-shadow-gateway','jason-teams-gateway','openbao')
USER=('/usr/sbin/runuser','-u','al','--','/usr/bin/env','XDG_RUNTIME_DIR=/run/user/1000','DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus')
SAFE_GIT=('GIT_CONFIG_NOSYSTEM=1','GIT_CONFIG_GLOBAL=/dev/null','GIT_OPTIONAL_LOCKS=0','GIT_NO_REPLACE_OBJECTS=1','GIT_GRAFT_FILE=/dev/null','GIT_CONFIG_COUNT=2','GIT_CONFIG_KEY_0=core.fsmonitor','GIT_CONFIG_VALUE_0=false','GIT_CONFIG_KEY_1=core.hooksPath','GIT_CONFIG_VALUE_1=/dev/null')

class ClosureDenied(PermissionError):pass

def need(ok,reason):
    if not ok:raise ClosureDenied('PMV4_E_CLOSURE_'+reason)

def canon(x):return json.dumps(x,sort_keys=True,separators=(',',':')).encode()
def digest(raw):return sha256(raw).hexdigest()

def read(path,uid,mode):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as f:
        m=os.fstat(f.fileno());link=path.lstat()
        need(stat.S_ISREG(m.st_mode) and (m.st_dev,m.st_ino)==(link.st_dev,link.st_ino)
             and m.st_uid==m.st_gid==uid and m.st_nlink==1
             and stat.S_IMODE(m.st_mode)==mode and 0<m.st_size<2000000,'FILE_IDENTITY:'+path.name)
        raw=f.read(2000001);need(len(raw)==m.st_size,'FILE_CHANGED:'+path.name);return raw

def directory(path,uid,mode=None):
    m=path.lstat();need(not path.is_symlink() and stat.S_ISDIR(m.st_mode)
        and m.st_uid==m.st_gid==uid and m.st_mode&0o022==0
        and (mode is None or stat.S_IMODE(m.st_mode)==mode),'DIRECTORY_IDENTITY:'+path.name)

def sync_dir(path):
    fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:os.fsync(fd)
    finally:os.close(fd)


def write(path,raw,mode=0o400,uid=0):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
    with os.fdopen(fd,'wb') as f:
        os.fchmod(f.fileno(),mode);os.fchown(f.fileno(),uid,uid);f.write(raw);f.flush();os.fsync(f.fileno())
    fd=os.open(path.parent,os.O_DIRECTORY|os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)

def run(argv,*,timeout=40):
    p=subprocess.run(list(argv),cwd='/',capture_output=True,text=True,timeout=timeout,check=False)
    need(p.returncode==0,'COMMAND_FAILED:'+Path(argv[0]).name)
    return p.stdout.strip()

def systemctl(args,*,user=False):
    return run([*(USER if user else ()), '/usr/bin/systemctl',*(['--user'] if user else []),*args])

def props(name,user):
    text=systemctl(['show',name,'--property=ActiveState,UnitFileState,ExecStart,Environment,FragmentPath,DropInPaths'],user=user)
    return dict(line.split('=',1) for line in text.splitlines() if '=' in line)

def verify_units(*,retired_files_absent=False):
    for user,names in ((True,NEW_USER),(False,NEW_ROOT)):
        for name in names:
            p=props(name,user);need(p.get('ActiveState')=='active' and p.get('UnitFileState')=='enabled','REPLACEMENT_NOT_ACTIVE:'+name)
    for user,names in ((True,OLD_USER),(False,OLD_ROOT)):
        for name in names:
            if retired_files_absent:
                argv=[*(USER if user else ()), '/usr/bin/systemctl',*(['--user'] if user else []),'is-active',name]
                result=subprocess.run(argv,capture_output=True,text=True,timeout=15,check=False)
                need(result.returncode in (3,4) and result.stdout.strip() in ('inactive','unknown'),'RETIRED_TRIGGER_NOT_INERT:'+name)
            else:
                p=props(name,user);need(p.get('ActiveState')=='inactive' and p.get('UnitFileState')=='disabled','RETIRED_TRIGGER_NOT_INERT:'+name)

def peers():
    rows=json.loads(run(['/usr/bin/docker','inspect','--type','container',*PEERS]))
    need(isinstance(rows,list) and len(rows)==len(PEERS),'PROTECTED_SET_INCOMPLETE')
    out={}
    for row in rows:
        name=row['Name'].lstrip('/');s=row['State'];h=(s.get('Health') or {}).get('Status','none')
        need(name in PEERS and s.get('Running') is True and h in ('healthy','none'),'PROTECTED_HEALTH:'+name)
        out[name]={'id':row['Id'],'image':row['Image'],'started_at':s['StartedAt']}
    need(set(out)==set(PEERS),'PROTECTED_SET_CHANGED');return out

def user_python(code,*args,timeout=90):
    return run([*USER,'/usr/bin/python3','-I','-B','-c',code,*map(str,args)],timeout=timeout)

CAPTURE='import json,sys;sys.path[:0]=["/home/al/.local/lib/jason","/opt/jason/current/tools"];import release_manager_host_runner as r;print(json.dumps(r.capture_production_manifest(sys.argv[1]),sort_keys=True))'

def expected_schedule(old,marker):
    out=dict(old)
    for name in marker['retired_user_units']+marker['retired_system_units']:out[name]='inactive'
    for name in marker['replacement_user_units']+marker['replacement_system_units']:out[name]='active'
    return out

def verify_manifest_delta(old,current,marker):
    keys=set(old)|set(current)
    for key in keys-{'observed_at','scheduled_control_units'}:
        need(old.get(key)==current.get(key),'LKG_FINGERPRINT_CHANGED:'+key)
    need(current.get('complete') is True and current.get('revision')==ROLLBACK,'LKG_NOT_VERIFIED')
    need(current['scheduled_control_units']==expected_schedule(old['scheduled_control_units'],marker),'SCHEDULE_DELTA_NOT_EXACT')


def approved_namespace():
    path=REPO/'tools/pmv4_e_dispatch_install.py';raw=path.read_bytes()
    need(digest(raw)==INSTALLER_SHA,'INSTALLER_SOURCE_CHANGED')
    ns={'__name__':'closure_reviewed_owner_primitives','__file__':str(path)}
    exec(compile(raw,str(path),'exec'),ns);return ns

def git(repo,*args):
    return run([*USER,'/usr/bin/env','-i','PATH=/usr/bin:/bin',*SAFE_GIT,'/usr/bin/git','-C',str(repo),*args])


def inspect(source_sha,ns):
    directory(BASE,0);directory(NATIVE,0,0o555)
    marker=json.loads(read(MARKER,0,0o444))
    need(marker.get('state')=='accepted' and marker.get('source_sha')==CONTROL_SHA
         and marker.get('source_rollback_sha')==ROLLBACK and marker.get('source_scope_sha256')==ACCEPTED_SCOPE
         and marker.get('accepted_policy_sha256')==ACCEPTED_POLICY,'ACCEPTED_STAGE_E_CHANGED')
    need(set(marker['retired_user_units'])==set(OLD_USER) and set(marker['retired_system_units'])==set(OLD_ROOT)
         and set(marker['replacement_user_units'])==set(NEW_USER) and set(marker['replacement_system_units'])==set(NEW_ROOT),'ACCEPTED_UNIT_SCOPE_CHANGED')
    native=json.loads(read(Path('/var/lib/jason/independent-component-release/receipts')/('owner-'+marker['owner_approval_id']+'.json'),0,0o600))
    need(native.get('state')=='accepted' and native.get('candidate_sha')==CONTROL_SHA
         and native.get('approval_id')==marker['owner_approval_id'],'ORIGINAL_NATIVE_ACCEPTANCE_MISSING')
    signer_path=Path('/usr/local/lib/jason/owner_signed_release.py');raw=read(signer_path,0,0o644)
    need(digest(raw)=='f50eea90102d9a1de82b3753ec8d0cd225280d385ac7a658ae2c2a303934a0e3','ORIGINAL_SIGNER_CHANGED')
    signer={'__name__':'closure_historical_native_verifier','__file__':str(signer_path)}
    exec(compile(raw,str(signer_path),'exec'),signer)
    signer['verify_exact_owner_release'](native['signed_owner_proof'],public_key=signer['read_pinned_root_owner_public_key'](Path('/etc/jason-owner-release/verified-owner-public-key.json')),
        expected_release_id='release-'+CONTROL_SHA[:16],expected_candidate_sha=CONTROL_SHA,expected_rollback_sha=ROLLBACK,
        expected_scope_sha256=ACCEPTED_SCOPE,expected_manifest_sha256=ACCEPTED_MANIFEST,expected_freeze_sha256=ns['FREEZE_HASH'],at=datetime.fromisoformat(native['started_at']))
    need(digest(read(ROOT_POLICY,0,0o600))==ACCEPTED_POLICY,'ACCEPTED_POLICY_CHANGED')
    need(Path('/opt/jason/current').resolve().name==ROLLBACK,'RUNTIME_BASELINE_CHANGED')
    need(digest(read(ns['FREEZE'],1000,0o600))==ns['FREEZE_HASH'] and digest(read(ns['HOLD'],1000,0o664))==ns['HOLD_HASH'],'FREEZE_OR_HOLD_CHANGED')
    need(digest(read(ns['WORKER'],0,0o755))==ns['WORKER_BEFORE'],'SHARED_WORKER_CHANGED')
    from_catalog=read(ns['CATALOG_POLICY'],0,0o600)
    need(json.loads(from_catalog).get('root_worker_sha256')==ns['WORKER_BEFORE'],'CATALOG_PIN_CHANGED')
    verify_units();before_peers=peers()
    control=json.loads(read(MANAGER/'production-control-state.json',0,0o600))
    need(control.get('circuit_breaker',{}).get('state')=='open' and control['circuit_breaker'].get('reason')=='continuous_production_drift_detected','UNRELATED_BREAKER_STATE')
    old_manifest=control['last_known_good']['manifest'];need(old_manifest.get('revision')==ROLLBACK,'LKG_REVISION_CHANGED')
    current=json.loads(user_python(CAPTURE,ROLLBACK));verify_manifest_delta(old_manifest,current,marker)
    drift=json.loads(read(MANAGER/'production-drift.json',0,0o600))
    allowed={('undeclared_installed_user_unit',n) for n in OLD_USER}|{('undeclared_installed_system_unit',n) for n in OLD_ROOT}
    required=set(allowed);allowed.add(('failed_system_unit','jason-production-drift-watchdog.service'))
    observed={(x.get('kind'),x.get('unit')) for x in drift.get('problems',[])}
    need(drift.get('status')=='drift_detected' and required<=observed<=allowed,'UNRELATED_DRIFT_PRESENT')
    originals=[]
    for user,names in ((True,OLD_USER),(False,OLD_ROOT)):
        root=Path('/home/al/.config/systemd/user' if user else '/etc/systemd/system')
        directory(root,1000 if user else 0)
        for name in names:
            path=root/name;m=path.lstat();uid=1000 if user else 0;mode=stat.S_IMODE(m.st_mode)
            raw=read(path,uid,mode)
            need(mode in (0o600,0o644) and len(raw)<25000,'TRIGGER_FILE_UNTRUSTED')
            originals.append({'path':str(path),'uid':uid,'mode':mode,'sha256':digest(raw)})
    need(LINK.is_symlink(),'ENGINEERING_SOURCE_NOT_LINK')
    old_link=os.readlink(LINK);need(LINK.resolve()==Path('/home/al/.local/lib/jason/engineering-source-repo'),'ENGINEERING_BASELINE_LINK_CHANGED')
    need(git(LINK.resolve(),'rev-parse','HEAD')==ROLLBACK and git(LINK.resolve(),'status','--porcelain')=='','ENGINEERING_BASELINE_SOURCE_CHANGED')
    directory(ENGINEERING,1000,0o700)
    need(git(ENGINEERING,'rev-parse','HEAD')==CONTROL_SHA and git(ENGINEERING,'status','--porcelain')=='','PREPARED_ENGINEERING_SOURCE_NOT_EXACT')
    need(not os.path.lexists(DROPIN),'WATCHDOG_DROPIN_ALREADY_PRESENT')
    watchdog=props('jason-self-heal-watchdog.service',True)
    need('/opt/jason/current/tools/jason_self_heal_watchdog.py' in watchdog.get('ExecStart',''),'WATCHDOG_BASELINE_COMMAND_CHANGED')
    need(watchdog.get('DropInPaths','')=='','WATCHDOG_BASELINE_DROPINS_CHANGED')
    need(read(Path('/home/al/.local/lib/jason/jason_self_heal_watchdog.py'),1000,0o700)==read(NATIVE/'tools/jason_self_heal_watchdog.py',0,0o444),'INSTALLED_WATCHDOG_NOT_ACCEPTED_SOURCE')
    pause_sha=digest(read(PAUSE,1000,0o600))
    # The accepted native tree and this executor must match protected source.
    handoff=json.loads(ns['read'](ART/('pmv4-e-root-admin-bundle-'+CONTROL_SHA)/'handoff-manifest.json',1000,0o400))
    files={name:read(NATIVE/name,0,0o444) for name in handoff['reviewed_hashes']}
    need(all(digest(raw)==handoff['reviewed_hashes'][name] for name,raw in files.items()),'ACCEPTED_NATIVE_TREE_CHANGED')
    files['tools/pmv4_e_operational_closure.py']=Path(__file__).read_bytes()
    ns['current_ci'](files,source_sha)
    state=BASE/('operational-closure-'+source_sha);need(not os.path.lexists(state),'ONE_USE_CLOSURE_ALREADY_ATTEMPTED')
    scope={'action':ACTION,'policy':{'candidate_sha':source_sha,'rollback_sha':ROLLBACK},'queue_cutover':False,
        'accepted_stage_e_sha':CONTROL_SHA,'accepted_marker_sha256':digest(read(MARKER,0,0o444)),
        'accepted_policy_sha256':ACCEPTED_POLICY,'owner_pause_sha256':pause_sha,'engineering_revision_after':CONTROL_SHA,'executor_sha256':digest(Path(__file__).read_bytes()),
        'trigger_before_images':originals,'watchdog_dropin_sha256':digest(DROPIN_BYTES),'engineering_link_before':old_link,
        'engineering_source_after':str(ENGINEERING),'old_lkg_manifest_sha256':digest(canon(old_manifest)),
        'new_lkg_schedule':current['scheduled_control_units'],'protected_peers':before_peers,
        'installation_targets':[*(x['path'] for x in originals),str(DROPIN),str(LINK),str(state),
            str(MANAGER/'production-control-state.json'),str(MANAGER/'production-drift.json'),
            str(MANAGER/'production-drift-watchdog.json'),str(MANAGER/'protected-transitions'),str(MANAGER/'protected-readback')],
        'native_metadata_refresh':'same_runtime_set_last_known_good','runtime_or_mcp_restart_allowed':False,
        'policy_or_accepted_code_changes_allowed':False,'standing_authority':False}
    return scope,marker,control


class Files:
    def __init__(self,state,scope,*,link=LINK,dropin=DROPIN,new_source=ENGINEERING,production=True):
        need(not production or (os.geteuid()==0 and link==LINK and dropin==DROPIN and new_source==ENGINEERING),'PRODUCTION_PATH_OVERRIDE')
        self.state=state;self.scope=scope;self.link=link;self.dropin=dropin;self.new_source=new_source
        self.removed=[];self.dropin_created=False;self.parent_created=False;self.link_changed=False

    def apply(self):
        before=self.state/'triggers';before.mkdir(mode=0o700);sync_dir(self.state)
        for item in self.scope['trigger_before_images']:
            path=Path(item['path']);raw=read(path,item['uid'],item['mode'])
            need(digest(raw)==item['sha256'],'TRIGGER_CHANGED_BEFORE_ARCHIVE')
            write(before/path.name,raw)
        for item in self.scope['trigger_before_images']:
            path=Path(item['path']);need(digest(read(path,item['uid'],item['mode']))==item['sha256'],'TRIGGER_CHANGED_BEFORE_RETIREMENT')
            path.unlink();self.removed.append(item);sync_dir(path.parent)
        if not self.dropin.parent.exists():
            self.dropin.parent.mkdir(mode=0o700);os.chown(self.dropin.parent,1000,1000);self.parent_created=True
        directory(self.dropin.parent,1000)
        write(self.dropin,DROPIN_BYTES,0o644,1000);self.dropin_created=True
        need(self.link.is_symlink() and os.readlink(self.link)==self.scope['engineering_link_before'],'ENGINEERING_LINK_RACE')
        pending=self.link.with_name('.'+self.link.name+'.pmv4-e-closure')
        need(not os.path.lexists(pending),'ENGINEERING_LINK_TEMP_CONFLICT')
        os.symlink(str(self.new_source),pending);os.lchown(pending,1000,1000);os.replace(pending,self.link);self.link_changed=True;sync_dir(self.link.parent)

    def restore(self):
        if self.link_changed:
            need(self.link.is_symlink() and os.readlink(self.link)==str(self.new_source),'FOREIGN_ENGINEERING_LINK')
            pending=self.link.with_name('.'+self.link.name+'.pmv4-e-restore')
            os.symlink(self.scope['engineering_link_before'],pending);os.lchown(pending,1000,1000);os.replace(pending,self.link);sync_dir(self.link.parent)
        if self.dropin_created:
            need(read(self.dropin,1000,0o644)==DROPIN_BYTES,'FOREIGN_WATCHDOG_DROPIN');self.dropin.unlink()
        if self.parent_created and not any(self.dropin.parent.iterdir()):self.dropin.parent.rmdir()
        for item in reversed(self.removed):
            path=Path(item['path']);need(not os.path.lexists(path),'FOREIGN_RETIRED_TRIGGER')
            raw=read(self.state/'triggers'/path.name,0,0o400);need(digest(raw)==item['sha256'],'ARCHIVED_TRIGGER_CHANGED')
            write(path,raw,item['mode'],item['uid'])


def reload():
    systemctl(['daemon-reload']);systemctl(['daemon-reload'],user=True)


def final_files(scope):
    for item in scope['trigger_before_images']:need(not os.path.lexists(item['path']),'RETIRED_FILE_REAPPEARED')
    verify_units(retired_files_absent=True)
    need(digest(read(PAUSE,1000,0o600))==scope['owner_pause_sha256'],'OWNER_PAUSE_CHANGED')
    wd=props('jason-self-heal-watchdog.service',True)
    need('/home/al/.local/lib/jason/jason_self_heal_watchdog.py' in wd.get('ExecStart','')
         and 'PYTHONPATH=/opt/jason/current/tools' in wd.get('Environment',''),'WATCHDOG_NOT_USING_ACCEPTED_CODE')
    code='import json,sys;sys.path[:0]=["/home/al/.local/lib/jason","/opt/jason/current/tools"];import jason_self_heal_watchdog as w;f,e=w.production_convergence_failures();print(json.dumps({"failures":f,"mode":e.get("pmv4_e_controlplane_mode")}))'
    result=json.loads(user_python(code));need(result=={'failures':[],'mode':'replacement'},'WATCHDOG_CONVERGENCE_FAILED')
    need(peers()==scope['protected_peers'],'PROTECTED_PEERS_CHANGED')
    need(digest(read(ROOT_POLICY,0,0o600))==ACCEPTED_POLICY and digest(read(MARKER,0,0o444))==scope['accepted_marker_sha256'],'ACCEPTED_POLICY_OR_MARKER_CHANGED')


def main(argv=None):
    cli=argparse.ArgumentParser();cli.add_argument('--source-sha',required=True);cli.add_argument('--apply',action='store_true');a=cli.parse_args(argv)
    need(os.geteuid()==0 and sys.flags.isolated==1 and re.fullmatch('[0-9a-f]{40}',a.source_sha),'EXACT_ROOT_ISOLATED_REQUIRED')
    ns=approved_namespace()
    with ns['locks']():scope,marker,control=inspect(a.source_sha,ns)
    if not a.apply:
        print(json.dumps({'status':'operational_closure_read_only_preflight_passed','scope_sha256':digest(canon(scope)),'scope':scope},sort_keys=True));return
    actor=ns['owner'](scope)
    with ns['locks']():
        again,marker,control=inspect(a.source_sha,ns);need(again==scope,'REVIEWED_CLOSURE_SCOPE_CHANGED')
        state=BASE/('operational-closure-'+a.source_sha);state.mkdir(mode=0o700)
        write(state/'approval.json',canon({'scope':scope,'owner_oid':actor,'approved_at':datetime.now(timezone.utc).isoformat()}))
        write(state/'control-before.json',canon(control));tx=Files(state,scope)
        try:tx.apply();reload();final_files(scope)
        except BaseException:
            tx.restore();reload();raise
    try:
        systemctl(['reset-failed','jason-production-drift-watchdog.service'])
        systemctl(['start','jason-production-drift-watchdog.service'])
        # The already-installed root worker verifies clean drift, the exact
        # approved runtime record and independently recaptured health.
        code='import sys;from pathlib import Path;sys.path[:0]=["/home/al/.local/lib/jason","/opt/jason/current/tools"];import release_manager_host_runner as r;r.request_root_control_transition(Path(sys.argv[1]),action="set_last_known_good",revision=sys.argv[2],release_id=sys.argv[3])'
        user_python(code,MANAGER,ROLLBACK,control['last_known_good']['release_id'],timeout=130)
        final_files(scope)
        current=json.loads(read(MANAGER/'production-control-state.json',0,0o600))
        verify_manifest_delta(control['last_known_good']['manifest'],current['last_known_good']['manifest'],marker)
        need(current.get('circuit_breaker',{}).get('state')=='closed','NATIVE_REVALIDATION_NOT_CLOSED')
        need(digest(read(ns['FREEZE'],1000,0o600))==ns['FREEZE_HASH'] and digest(read(ns['HOLD'],1000,0o664))==ns['HOLD_HASH'],'FREEZE_OR_HOLD_CHANGED')
        write(state/'accepted.json',canon({'status':'pmv4_e_operational_closure_accepted','scope_sha256':digest(canon(scope)),'accepted_stage_e_sha':CONTROL_SHA,'runtime_sha':ROLLBACK,'protected_services_changed':False,'policy_and_marker_unchanged':True,'accepted_at':datetime.now(timezone.utc).isoformat()}))
        print('PMV4_E_OPERATIONAL_CLOSURE=VERIFIED')
    except BaseException:
        # Never force-write protected state or replay the Owner decision.
        # Keep the explicit before-images and signed Stage E acceptance.
        write(state/'verification-failed.json',canon({'status':'closure_requires_readback_recovery','new_authority':False}))
        raise

if __name__=='__main__':
    try:main()
    except Exception as exc:raise SystemExit('DENIED:'+type(exc).__name__+':'+str(exc)[:1000])
