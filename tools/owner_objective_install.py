#!/usr/bin/env python3
"""Exact governed installation; no arbitrary Root command or provider write."""
from __future__ import annotations
import argparse
from datetime import datetime,timedelta,timezone
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time

REPO=Path(__file__).resolve().parents[1]
ART=Path("/srv/jason/archive/engineering-artifacts")
BASE=Path("/usr/local/lib/jason/owner-objective")
PUBLIC=BASE/"public"
TRUSTED=BASE/"trusted"
CONFIG=Path("/etc/jason-owner-release/owner-objective.json")
PRIVATE=Path("/var/lib/jason-owner-release/objectives")
INSTALL=PRIVATE/"installation"
SPOOL=Path("/var/lib/jason-owner-release/owner-objective-inbox")
STATE=Path("/var/lib/jason/openclaw/owner-objective")
OLD_PLANS=Path("/var/lib/jason/openclaw/universal-approvals.sqlite3")
AUTHORITY=Path("/var/lib/jason/authority/authority.sqlite3")
BINDINGS=Path("/var/lib/jason/governed-ticket-shared/teams-identity-bindings.sqlite3")
KEYS=Path("/var/lib/jason/openclaw/trusted-keys/registry.json")
TOKEN=Path("/var/lib/jason/openclaw/teams-proactive-token")
ROOT_POLICY=Path("/etc/jason/release-readback-recovery/production-desired-state.json")
DOC_BASE=Path("/usr/local/lib/jason/documentation-reconciliation")
DOC_OVERRIDE=Path("/etc/systemd/system/jason-documentation-reconciliation.service.d/20-reviewed-publisher.conf")
MARKER=Path("/etc/jason-owner-release/pmv4-e/replacement-retirement-accepted.json")
SYSTEMD=Path("/etc/systemd/system")
TENANT="f7054323-d52b-4863-8c2f-1898f0b6077c"
OID="bee80bdc-ffb0-4c50-b453-c09d4d411f5f"
OWNER="person-entra-bee80bdcffb04c50b453c09d4d411f5f"
SERVICE="jason-autonomy-worker"
ROLLBACK="d1b8c196dadd4b672ec8ba47075f27bb61c98d63"
PRIMITIVES="31af4fcfa40e6e976c10dc2bef8709f32e542358f89929b232dc18b8295f027a"
SHA=re.compile("[0-9a-f]{40}\\Z")
IMAGE=re.compile("sha256:[0-9a-f]{64}\\Z")
EXTRA_CODE=(
 "tools/owner_objective_install.py","tools/owner_objective_install_scope.py",
 "tools/owner_objective_root_worker.py","tools/owner_objective_source_verifier.py",
 "tools/owner_objective_ci.py","tools/owner_objective_teams_delivery.py",
 "tools/pmv4_teams_objective_admission.py","tools/pmv4_teams_objective_store.py",
 "tools/pmv4_objective_documentation.py","tools/documentation_publisher_install.py",
 "tools/pmv4_e_operational_closure.py","tools/deploy_live_container.py",
 "tools/pmv4_mcp_projection.py",
 "implementation/connectors/openclaw/src/jason_openclaw/signed_transport.py",
)
PROFILES=(
 "infrastructure/jason-owner-objective/jason-owner-objective-executor.service",
 "infrastructure/jason-owner-objective/jason-owner-objective-executor.path",
 "docs/engineering/Owner-Objective-Approval-Policy-v1.md",
)
KEY_PROBE="""const fs=require('node:fs'),c=require('node:crypto');
const privatePath=process.env.JASON_INGRESS_PRIVATE_KEY_PATH||'/run/jason/ingress.pem';
const publicKey=c.createPublicKey(fs.readFileSync(privatePath));
console.log(JSON.stringify({key_id:process.env.JASON_INGRESS_KEY_ID||'openclaw-gateway-2',
pem:publicKey.export({type:'spki',format:'pem'}),
fingerprint:c.createHash('sha256').update(publicKey.export({type:'spki',format:'der'})).digest('hex')}));"""


def need(value,code):
    if not value:raise PermissionError("OBJECTIVE_INSTALL_"+code)


def canonical(value):return json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
def digest(raw):return sha256(raw).hexdigest()


def primitives():
    path=REPO/"tools/documentation_publisher_install.py"
    raw=path.read_bytes()
    need(digest(raw)==PRIMITIVES,"PINNED_NATIVE_PRIMITIVES_CHANGED")
    ns={"__name__":"objective_install_primitives","__file__":str(path)}
    exec(compile(raw,str(path),"exec"),ns)
    return ns["primitives"]()


def trusted_source(c,candidate,name):
    need(isinstance(name,str) and not name.startswith("/") and ".." not in name.split("/")
         and "\n" not in name and "\x00" not in name,"SOURCE_PATH")
    path=REPO/name
    meta=path.lstat()
    need(not path.is_symlink() and stat.S_ISREG(meta.st_mode) and meta.st_uid==1000
         and meta.st_nlink==1 and not meta.st_mode&0o022 and meta.st_size<2000000,"SOURCE_FILE_IDENTITY")
    raw=path.read_bytes()
    expected=subprocess.run([*c["USER"],"/usr/bin/env",*c["SAFE_GIT"],"/usr/bin/git","-C",str(REPO),
                             "show",candidate+":"+name],capture_output=True,timeout=20,check=True).stdout
    need(raw==expected,"SOURCE_BYTES_NOT_EXACT")
    return raw


def load_module(c,candidate,name,module_name):
    raw=trusted_source(c,candidate,name)
    module=type(sys)(module_name)
    module.__file__=str(REPO/name)
    sys.modules[module_name]=module
    exec(compile(raw,module.__file__,"exec"),module.__dict__)
    return module


def ci(c,candidate):
    helper=load_module(c,candidate,"tools/pmv4_e_ci_refresh.py","objective_install_existing_ci")
    ns=helper.load_pinned_attestor(helper.SOURCE,production=True)
    api=ns["gh_api"]
    helper.paginate_required_checks(ns)
    evidence=ns["verify_ci"](candidate)
    need(evidence["required_ci_passed"] is True and evidence["protected_main_ancestor"] is True,"PROTECTED_CI")
    own=load_module(c,candidate,"tools/owner_objective_ci.py","objective_install_acceptance_ci")
    own.require_acceptance(api,candidate)
    source=load_module(c,candidate,"tools/owner_objective_source_verifier.py","objective_install_source_evidence")
    touched=source.newer_touched_paths(ns,candidate,evidence["protected_main"])
    need(touched.issubset(source.DERIVED_OUTPUTS),"NEWER_MATERIAL_MAIN_CHANGE")
    return evidence


def identity(c,grant_rows):
    def observe():
        a=sqlite3.connect("file:"+str(AUTHORITY)+"?mode=ro",uri=True)
        b=sqlite3.connect("file:"+str(BINDINGS)+"?mode=ro",uri=True)
        try:
            binding=b.execute("SELECT jason_identity_id,client_id,status FROM microsoft_identity_bindings "
                "WHERE microsoft_tenant_id=? AND microsoft_object_id=?",(TENANT,OID)).fetchone()
            need(binding==(OWNER,None,"active"),"LICENSED_OWNER_BINDING")
            for subject,kind in ((OWNER,"human"),(SERVICE,"service")):
                row=a.execute("SELECT payload FROM identities WHERE identity_id=?",(subject,)).fetchone()
                need(row is not None,"IDENTITY_MISSING")
                record=json.loads(row[0])
                need(record==dict(identity_id=subject,identity_type=kind,organization_id="aot",status="active"),
                     "IDENTITY_CHANGED")
            for grant in grant_rows:
                need(a.execute("SELECT payload FROM authority_grants WHERE grant_id=?",
                    (grant["grant_id"],)).fetchone() is None,"GRANT_TARGET_ALREADY_EXISTS")
        finally:a.close();b.close()
    observe()
    # Public key is independently derived by the already-running bot. Private
    # key bytes stay inside that existing container and never enter stdout.
    key=json.loads(c["run"](["/usr/bin/docker","exec","--user","node","jason-teams-gateway","node","-e",KEY_PROBE]))
    registry=json.loads(KEYS.read_bytes())
    matching=[r for r in registry["keys"] if r["key_id"]==key["key_id"] and r.get("status","active")=="active"
              and r["sha256_fingerprint"]==key["fingerprint"]]
    need(len(matching)==1,"GATEWAY_PUBLIC_KEY_NOT_REGISTERED")
    key["machine_identity"]=matching[0]["machine_identity"]
    return key


def image_identity(c,image,candidate,base,user):
    row=json.loads(c["run"](["/usr/bin/docker","image","inspect",image]))[0]
    baseline=json.loads(c["run"](["/usr/bin/docker","image","inspect",base]))[0]
    labels=row["Config"].get("Labels") or {}
    need(row["Id"]==image and labels.get("org.opencontainers.image.revision")==candidate,"IMAGE_SOURCE_IDENTITY")
    layers=row["RootFS"]["Layers"];old=baseline["RootFS"]["Layers"]
    need(layers[:len(old)]==old and len(layers)==len(old)+2,"EXACT_TWO_SOURCE_LAYERS_REQUIRED")
    need(row["Config"]["User"]==user,"IMAGE_EXECUTION_IDENTITY")
    return row


def prepare_images(c,candidate,peers):
    """Build the two exact artifacts from protected source, before Owner review.

    No build command executes candidate code: reviewed Dockerfiles contain only
    source COPY and fixed metadata over the independently observed live bases.
    No service, authority store or production configuration is changed here.
    """
    import tarfile
    with tempfile.TemporaryDirectory(prefix="owner-objective-build-") as temporary:
        context=Path(temporary)
        command=[*c["USER"],"/usr/bin/env",*c["SAFE_GIT"],"/usr/bin/git","-C",str(REPO),
            "archive","--format=tar",candidate,"implementation","tools","infrastructure/jason-owner-objective",
            "infrastructure/jason-teams-gateway"]
        result=subprocess.run(command,capture_output=True,timeout=90,check=True)
        need(len(result.stdout)<150000000,"SOURCE_ARCHIVE_OVER_LIMIT")
        import io
        with tarfile.open(fileobj=io.BytesIO(result.stdout),mode="r:") as archive:
            members=archive.getmembers()
            need(all((m.isfile() or m.isdir()) and not m.name.startswith("/")
                     and ".." not in Path(m.name).parts for m in members),"SOURCE_ARCHIVE_ENTRY")
            archive.extractall(context,filter="data")
        outputs={}
        for component,base,dockerfile,user in (
            ("component",peers["jason-runtime"]["image"],"Dockerfile","1000:1000"),
            ("gateway",peers["jason-teams-gateway"]["image"],"gateway.Dockerfile","node"),
        ):
            print("ROOT_ARTIFACT_PREPARATION="+component,flush=True)
            base_tag="owner-objective-root-base:"+component+"-"+base[7:19]
            tag="owner-objective-root-prepared:"+component+"-"+candidate[:12]
            c["run"](["/usr/bin/docker","tag",base,base_tag])
            c["run"](["/usr/bin/env","DOCKER_BUILDKIT=0","/usr/bin/docker","build","--network","none",
                "--pull=false","--no-cache","--build-arg","BASE_IMAGE="+base_tag,
                "--build-arg","SOURCE_REVISION="+candidate,
                "-f",str(context/"infrastructure/jason-owner-objective"/dockerfile),
                "-t",tag,str(context)],timeout=300)
            image=c["run"](["/usr/bin/docker","image","inspect",tag,"--format","{{.Id}}"])
            image_identity(c,image,candidate,base,user)
            outputs[component+"_image"]=image
        return outputs


def plan_database(c):
    m=OLD_PLANS.lstat()
    need(not OLD_PLANS.is_symlink() and stat.S_ISREG(m.st_mode) and m.st_uid==1000
         and m.st_nlink==1 and stat.S_IMODE(m.st_mode)==0o600,"CANONICAL_PLAN_DATABASE_IDENTITY")
    with sqlite3.connect("file:"+str(OLD_PLANS)+"?mode=ro",uri=True,timeout=5) as db:
        rows=list(db.iterdump())
    return digest("\n".join(rows).encode())


def inspect(c,ns,candidate,artifacts,campaign):
    scope_module=load_module(c,candidate,"tools/owner_objective_install_scope.py","objective_install_scope")
    need(c["git"](REPO,"rev-parse","HEAD")==candidate
         and c["git"](REPO,"status","--porcelain","--untracked-files=all")=="","EXACT_CLEAN_SOURCE_REQUIRED")
    ci(c,candidate)
    need(Path("/opt/jason/current").resolve().name==ROLLBACK,"RUNTIME_ROLLBACK_CHANGED")
    for parent in (BASE.parent,CONFIG.parent,PRIVATE.parent,SYSTEMD):
        c["directory"](parent,0)
    for path in (BASE,CONFIG,PRIVATE,SPOOL,STATE):
        need(not os.path.lexists(path),"INSTALLATION_TARGET_ALREADY_PRESENT")
    need(not os.path.lexists(DOC_OVERRIDE) and not os.path.lexists(DOC_BASE/"accepted.json"),
         "DOCUMENTATION_TARGET_ALREADY_ACCEPTED_OR_OVERRIDDEN")
    for unit in scope_module.UNITS:
        need(not os.path.lexists(SYSTEMD/unit),"UNIT_TARGET_ALREADY_PRESENT")
    peers=c["peers"]()
    for name in ("component","gateway"):
        base=peers["jason-runtime" if name=="component" else "jason-teams-gateway"]["image"]
        image_identity(c,artifacts[name+"_image"],candidate,base,"1000:1000" if name=="component" else "node")
    policy_raw=c["read"](ROOT_POLICY,0,0o600)
    need(digest(policy_raw)==scope_module.BASE_POLICY,"ACCEPTED_POLICY_CHANGED")
    before=json.loads(policy_raw)
    after=scope_module.desired_policy(before)
    marker=c["read"](MARKER,0,0o444)
    accepted=json.loads(marker)
    need(accepted["state"]=="accepted" and accepted["source_sha"]==c["CONTROL_SHA"],"STAGE_E_ACCEPTANCE")
    inventory_path=Path("/var/lib/jason/independent-component-release/releases")/c["CONTROL_SHA"]/"source-scope.json"
    inventory=json.loads(c["read"](inventory_path,0,0o444))
    need(digest(canonical(inventory))==c["ACCEPTED_SCOPE"],"ACCEPTED_NATIVE_INVENTORY")
    native=inventory["exact_replacement_files_sha256"]
    need(len(native)==64,"ACCEPTED_NATIVE_CLOSURE")
    c["directory"](c["NATIVE"],0,0o555)
    for name,value in native.items():
        need(digest(c["read"](c["NATIVE"]/name,0,0o444))==value,"ACCEPTED_NATIVE_CODE_CHANGED")
    fixed={}
    for path,uid,mode,expected in (
        (ns["FREEZE"],1000,0o600,ns["FREEZE_HASH"]),
        (ns["HOLD"],1000,0o664,ns["HOLD_HASH"]),
        (ns["WORKER"],0,0o755,ns["WORKER_BEFORE"]),
    ):
        need(digest(c["read"](path,uid,mode))==expected,"PROTECTED_CONTROL_CHANGED")
        fixed[str(path)]=expected
    pause=digest(c["read"](c["PAUSE"],1000,0o600))
    control=json.loads(c["read"](c["MANAGER"]/"production-control-state.json",0,0o600))
    drift=json.loads(c["read"](c["MANAGER"]/"production-drift.json",0,0o600))
    need(control["circuit_breaker"]["state"]=="closed" and drift["status"]=="pass"
         and drift["problems"]==[],"PRODUCTION_BREAKER_OR_DRIFT")
    observed=datetime.fromisoformat(drift["observed_at"].replace("Z","+00:00"))
    need(0<=(datetime.now(timezone.utc)-observed).total_seconds()<=180,"DRIFT_STALE")
    gateway=json.loads(c["run"](["/usr/bin/docker","inspect","jason-teams-gateway"]))[0]
    for consumer in ("jason-runtime","jason-mcp-pilot"):
        runtime_mode=c["run"](["/usr/bin/docker","exec","--user","1000:1000",consumer,
            "python3","-B","-c","from jason_runtime.composition import RuntimeSettings;print(RuntimeSettings.from_env().universal_approval_mode)"])
        need(runtime_mode=="off","EXISTING_CANONICAL_PLAN_CONSUMER_ACTIVE")
    grants=scope_module.grants(OWNER,SERVICE)
    key=identity(c,grants)
    code={}
    identity_files=c["git"](REPO,"ls-tree","-r","--name-only",candidate,"--",
        "implementation/kernel").splitlines()
    names=set(native)|set(EXTRA_CODE)|set(identity_files)|{
        "implementation/__init__.py","implementation/kernel/__init__.py",
        "tools/pmv4_e_ci_refresh.py"}
    # Namespace-package __init__ files need not exist in this repository.
    for name in sorted(names):
        if (REPO/name).is_file():
            code[name]=trusted_source(c,candidate,name)
    for name in PROFILES:trusted_source(c,candidate,name)
    from_payload=(
        ("tools/documentation_source_reconciler.py","7eacdf6e368c13da13807ebba513acc6481f97f2bce852bff09423960b56f5fc"),
        ("tools/publish_documentation_reconciliation.sh","1c5ff7a73835cd55710cf01c16f2efc39e44986618ed88d44d6f66e35b9a46dd"),
    )
    for name,expected in from_payload:
        need(digest(c["read"](DOC_BASE/"49d386bf9472c5b2adc78499fe5d6041e6167ebe"/name,0,0o444))==expected,
             "APPROVED_PUBLISHER_BYTES_CHANGED")
    publisher=c["props"]("jason-documentation-reconciliation.service",False)
    need(publisher["ActiveState"] in ("inactive","failed") and publisher.get("DropInPaths","")=="",
         "DOCUMENTATION_SERVICE_BUSY_OR_OVERRIDDEN")
    repo=Path("/home/al/.local/lib/jason/documentation-source-repo")
    worktree=Path("/home/al/jason-worktrees/documentation-reconcile-current")
    common=("rev-parse","--path-format=absolute","--git-common-dir")
    need(c["git"](repo,*common)==c["git"](worktree,*common)
         and c["git"](repo,"status","--porcelain","--untracked-files=all")==""
         and c["git"](worktree,"status","--porcelain","--untracked-files=all")=="","DOCUMENTATION_WORKTREE_STATE")
    snapshot={
        "action":scope_module.ACTION,"policy":{"candidate_sha":candidate,"rollback_sha":ROLLBACK},
        "queue_cutover":False,"installation_targets":list(scope_module.ROOT_TARGETS),
        "artifacts":artifacts,"protected_peers":peers,"protection_files":fixed,
        "accepted_marker_sha256":digest(marker),"root_policy_before_sha256":digest(policy_raw),
        "root_policy_after_sha256":digest(canonical(after)),"owner_pause_sha256":pause,
        "canonical_plan_rows_sha256":plan_database(c),"canonical_plan_migration":"preserve-all-rows-and-compatibility-link",
        "new_grants":grants,"gateway_public_key_sha256":key["fingerprint"],
        "gateway_key_id":key["key_id"],"gateway_machine_identity":key["machine_identity"],
        "teams_proactive_token_sha256":digest(c["read"](TOKEN,1000,0o600)),
        "trusted_code_sha256":{n:digest(raw) for n,raw in code.items()},
        "adopted_policy_sha256":digest(trusted_source(c,candidate,PROFILES[2])),
        "campaign":campaign,"gateway_replacements":1,"runtime_or_mcp_restarts":0,
        "ticket_core_changes":False,"provider_writes":False,"standing_root_shell":False,
        "native_metadata_refresh":"existing-root-set-last-known-good",
        "rollback":"restore-exact-before-images-preserve-all-decisions",
    }
    return snapshot,dict(code=code,policy_raw=policy_raw,policy_after=after,key=key,grants=grants,
        marker=marker,native=native,control=control,gateway=gateway,scope_module=scope_module)


GRANT_WRITE="""import json,sys;from pathlib import Path
sys.path[:0]=[sys.argv[1],str(Path(sys.argv[1])/'implementation')]
from kernel.identity_authority import SQLiteIdentityAuthorityStore,SQLiteAuthorityGrantRepository,AuthorityGrant,PermissionMode
rows=json.loads(sys.argv[2]);store=SQLiteIdentityAuthorityStore(sys.argv[3]);repo=SQLiteAuthorityGrantRepository(store)
for item in rows:
    prior=repo.get(item['grant_id'])
    assert prior is None,'grant target changed'
for item in rows:
    item['permission']=PermissionMode(item['permission']);repo.put(AuthorityGrant(**item))
"""
GRANT_REVOKE="""import json,sys;from pathlib import Path
sys.path[:0]=[sys.argv[1],str(Path(sys.argv[1])/'implementation')]
from kernel.identity_authority import SQLiteIdentityAuthorityStore,SQLiteAuthorityGrantRepository
repo=SQLiteAuthorityGrantRepository(SQLiteIdentityAuthorityStore(sys.argv[3]))
for item in json.loads(sys.argv[2]):
    prior=repo.get(item['grant_id'])
    if prior is not None:repo.revoke(item['grant_id'])
"""


def replace_root(c,path,expected,raw,mode=0o600):
    need(c["read"](path,0,mode)==expected,"ROOT_TARGET_CHANGED_BEFORE_REPLACEMENT")
    temporary=path.with_name("."+path.name+".owner-objective")
    need(not os.path.lexists(temporary),"ROOT_TEMPORARY_TARGET_EXISTS")
    c["write"](temporary,raw,mode)
    os.replace(temporary,path)
    c["sync_dir"](path.parent)


class Installation:
    def __init__(self,c,ns,candidate,scope,facts):
        self.c,self.ns,self.candidate,self.scope,self.facts=c,ns,candidate,scope,facts
        self.directories=[];self.files=[];self.policy_changed=False
        self.grants_written=False;self.database_moved=False;self.container_created=False
        self.gateway_changed=False;self.units_started=False
        self.gateway_rollback="jason-teams-gateway-rollback-owner-objective-"+candidate[:12]

    def directory(self,path,uid=0,mode=0o755):
        need(not os.path.lexists(path),"DIRECTORY_TARGET_PRESENT")
        if uid == 1000 and path.parent.lstat().st_uid != 0:
            # No privileged chown through an operator-controlled ancestor.
            self.c["user_python"]("from pathlib import Path;import sys;p=Path(sys.argv[1]);p.mkdir(mode=int(sys.argv[2],8))",path,oct(mode))
            self.c["directory"](path,1000,mode)
        else:
            self.c["directory"](path.parent,0)
            path.mkdir(mode=mode)
            fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
            try:os.fchown(fd,uid,uid);os.fchmod(fd,mode)
            finally:os.close(fd)
            self.c["directory"](path,uid,mode)
        self.directories.append(path)

    def write(self,path,raw,mode=0o444,uid=0):
        self.c["write"](path,raw,mode,uid)
        self.files.append((path,uid,mode,digest(raw)))

    def public(self,name,value):
        self.write(PUBLIC/name,canonical(value))

    def migrate_database(self):
        # The live generic consumer is disabled and independently checked by
        # inspect(). Checkpoint and capture the complete canonical database,
        # including all existing approvals/audit, before changing its location.
        code="""import sqlite3,sys
p=sys.argv[1];db=sqlite3.connect(p,timeout=5)
db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
db.execute('BEGIN EXCLUSIVE')
db.execute('COMMIT');db.close()
"""
        self.c["user_python"](code,OLD_PLANS)
        need(plan_database(self.c)==self.scope["canonical_plan_rows_sha256"],"CANONICAL_ROWS_CHANGED")
        self.write(INSTALL/"canonical-plans-before.sqlite3",
            self.c["read"](OLD_PLANS,1000,0o600),0o400)
        destination=STATE/"universal-approvals.sqlite3"
        self.c["user_python"]("import os,sys;os.rename(sys.argv[1],sys.argv[2]);os.symlink(sys.argv[2],sys.argv[1])",OLD_PLANS,destination)
        self.database_moved=True
        self.c["sync_dir"](OLD_PLANS.parent);self.c["sync_dir"](STATE)

    def apply(self,actor):
        c,f=self.c,self.facts
        self.directory(BASE);self.directory(TRUSTED);self.directory(PUBLIC)
        self.directory(PRIVATE,mode=0o700);self.directory(INSTALL,mode=0o700)
        self.directory(PRIVATE/"native-receipts",mode=0o700)
        self.write(INSTALL/"approval.json",canonical({
            "schema_version":"1.0","scope":self.scope,"scope_sha256":digest(canonical(self.scope)),
            "owner_oid":actor,"independently_verified_entra_owner":True,
            "approved_at":datetime.now(timezone.utc).isoformat(),
        }),0o400)
        self.write(INSTALL/"control-before.json",canonical(f["control"]),0o400)
        # Contains the original container's private environment. Never print or
        # publish this Root-only rollback evidence.
        self.write(INSTALL/"gateway-before.json",canonical(f["gateway"]),0o400)
        self.write(INSTALL/"policy-before.json",f["policy_raw"],0o400)
        created=set()
        for name,raw in f["code"].items():
            target=TRUSTED/name
            pending=[]
            parent=target.parent
            while parent!=TRUSTED and not parent.exists():
                pending.append(parent);parent=parent.parent
            for directory in reversed(pending):
                directory.mkdir(mode=0o755);created.add(directory)
            self.write(target,raw)
        for directory in sorted(created,key=lambda p:len(p.parts),reverse=True):
            directory.chmod(0o555)
        TRUSTED.chmod(0o555)
        self.directory(SPOOL)
        for name,uid,mode in (("requests",1000,0o700),("staging",1000,0o700),
                              ("results",0,0o755),("processed",0,0o700)):
            self.directory(SPOOL/name,uid,mode)
        self.directory(STATE,1000,0o700)
        grant_rows=f["grants"]
        self.grants_written=True
        c["user_python"](GRANT_WRITE,TRUSTED,canonical(grant_rows).decode(),AUTHORITY)
        self.migrate_database()
        campaign=self.scope["campaign"]
        self.write(PUBLIC/"gateway.pem",f["key"]["pem"].encode())
        key_record=dict(key_id=f["key"]["key_id"],machine_identity=f["key"]["machine_identity"],
            public_key_path="/run/jason/owner-objective/gateway.pem",
            sha256_fingerprint=f["key"]["fingerprint"],status="active")
        self.public("keys.json",{"keys":[key_record]})
        self.public("activation.json",{"ready":False,"source_sha":self.candidate})
        # A policy's exact request allowlist is sealed only after the Root
        # manifest below binds the actual post-replacement gateway identity.
        if not DOC_OVERRIDE.parent.exists():
            self.directory(DOC_OVERRIDE.parent)
        replace_root(c,ROOT_POLICY,f["policy_raw"],canonical(f["policy_after"]))
        self.policy_changed=True
        for name in f["scope_module"].UNITS:
            raw=trusted_source(c,self.candidate,"infrastructure/jason-owner-objective/"+name)
            self.write(SYSTEMD/name,raw,0o644)
        c["systemctl"](["daemon-reload"])

    def replace_gateway(self):
        script=TRUSTED/"tools/deploy_live_container.py"
        self.gateway_changed=True
        loader="import runpy,sys;sys.path.insert(0,sys.argv[1]);p=sys.argv[2];sys.argv=[p,*sys.argv[3:]];runpy.run_path(p,run_name=\"__main__\")"
        self.c["run"](["/usr/bin/python3","-I","-B","-c",loader,str(TRUSTED/"tools"),str(script),
            "--live","jason-teams-gateway","--image",self.scope["artifacts"]["gateway_image"],
            "--rollback",self.gateway_rollback,"--source-revision",self.candidate,
            "--health-url","http://127.0.0.1:3979/health","--health-runtime","node",
            "--set-env","JASON_OWNER_OBJECTIVE_URL=http://jason-owner-objective:8097/v1/openclaw/teams/conversation"],
            timeout=150)

    def seal_profiles(self):
        c,f=self.c,self.facts
        campaign=self.scope["campaign"]
        after=c["peers"]()
        for name,before in self.scope["protected_peers"].items():
            if name=="jason-teams-gateway":
                need(after[name]["image"]==self.scope["artifacts"]["gateway_image"],"GATEWAY_IMAGE_READBACK")
            else:need(after[name]==before,"PROTECTED_PEER_CHANGED")
        facts={
            "candidate_sha":self.candidate,"protected_peers":after,
            "freeze_path":str(self.ns["FREEZE"]),"freeze_sha256":self.ns["FREEZE_HASH"],
            "hold_path":str(self.ns["HOLD"]),"hold_sha256":self.ns["HOLD_HASH"],
            "root_policy_path":str(ROOT_POLICY),"root_policy_sha256":digest(canonical(f["policy_after"])),
            "stage_e_marker_path":str(MARKER),"stage_e_marker_sha256":digest(f["marker"]),
            "original_unit_sha256":digest(c["read"](SYSTEMD/"jason-documentation-reconciliation.service",0,0o644)),
            "engineering_pause_sha256":self.scope["owner_pause_sha256"],
            "shared_worker_sha256":self.ns["WORKER_BEFORE"],
            "accepted_native_files_sha256":f["native"],
        }
        manifest_hash=digest(canonical(facts))
        reviewed_scope={
            "schema_version":"1.0","objective":"restore-and-verify-documentation-publisher",
            "native_manifest_sha256":manifest_hash,"candidate_sha":self.candidate,"rollback_sha":ROLLBACK,
            "ordered_capabilities":list(f["scope_module"].CAPABILITIES[:2]),
            "business_provider_writes":False,"github_documentation_publication_allowed":True,"protected_runtime_changes":False,
            "maximum_job_starts":1,"original_failed_approval_reused":False,
        }
        args=dict(component_id="documentation-publisher",candidate_sha=self.candidate,
            rollback_sha=ROLLBACK,scope_sha256=digest(canonical(reviewed_scope)),
            manifest_sha256=manifest_hash,freeze_sha256=self.ns["FREEZE_HASH"],hold_sha256=self.ns["HOLD_HASH"])
        self.write(INSTALL/"documentation-manifest.json",canonical(dict(facts,step_arguments=args)),0o444)
        self.write(INSTALL/"documentation-scope.json",canonical(reviewed_scope),0o444)
        caps=f["scope_module"].CAPABILITIES
        rules=[dict(principal_id=SERVICE,capability=cap,permission_mode="execute",client_id=None,
            arguments_sha256=digest(canonical(
                {"test_only":True,"execution_permitted":False} if cap==caps[2] else args))) for cap in caps]
        policy={"schema_version":"1.0","organizations":{"aot":{
            "role_members":{"owner":[OWNER]},"capability_roles":{cap:["owner"] for cap in caps},
            "disabled_principals":[],"max_risk":3,"production_allowed":True,
            "request_retention_allowed":True,"max_ttl_seconds":86400,
            "service_requesters":{SERVICE:{"microsoft_tenant_id":TENANT,"maximum_plan_steps":12}},
            "request_allowlist":rules}}}
        self.public("policy.json",policy)
        profile=dict(schema_version="1.0",enabled=True,source_sha=self.candidate,
            activation_path="/run/jason/owner-objective/activation.json",
            state_dir="/var/lib/jason-owner-objective",plans_db="/var/lib/jason-owner-objective/universal-approvals.sqlite3",
            authority_db=str(AUTHORITY),bindings_db=str(BINDINGS),
            trusted_keys_registry="/run/jason/owner-objective/keys.json",
            allowed_machine_identities=[f["key"]["machine_identity"]],
            policy_path="/run/jason/owner-objective/policy.json",spool="/var/lib/jason/owner-objective-inbox",
            requester_identity_id=SERVICE,objective_ttl_seconds=86400,
            teams_gateway_url="http://jason-teams-gateway:3979",
            teams_token_file="/run/jason/owner-objective-token",
            campaign=dict(campaign,step_arguments=args))
        self.public("profile.json",profile)
        root_config=dict(schema_version="1.0",enabled=True,source_sha=self.candidate,
            activation_path=str(PUBLIC/"activation.json"),files_sha256=self.scope["trusted_code_sha256"],
            documentation_manifest=str(INSTALL/"documentation-manifest.json"),policy_path=str(PUBLIC/"policy.json"),
            policy_digest=digest(canonical(policy)),tenant_id=TENANT,owner_oid=OID,owner_identity_id=OWNER,
            requester_identity_id=SERVICE,authority_db=str(AUTHORITY),bindings_db=str(BINDINGS),
            campaign_approval_id=campaign["approve_approval_id"],
            required_grants_sha256={g["grant_id"]:digest(canonical(g)) for g in f["grants"]},
            gateway_keys=[dict(key_id=f["key"]["key_id"],machine_identity=f["key"]["machine_identity"],
                sha256_fingerprint=f["key"]["fingerprint"],public_key_path=str(PUBLIC/"gateway.pem"))],
            teams_gateway_url="http://127.0.0.1:3978",
            teams_token_sha256=self.scope["teams_proactive_token_sha256"])
        self.write(CONFIG,canonical(root_config),0o600)


    def start_component(self):
        image=self.scope["artifacts"]["component_image"]
        args=["/usr/bin/docker","run","-d","--name","jason-owner-objective","--network","jason-core",
            "--restart","unless-stopped","--user","1000:1000","--read-only","--cap-drop","ALL",
            "--security-opt","no-new-privileges","--pids-limit","128","--memory","512m",
            "--tmpfs","/tmp:rw,nosuid,nodev,noexec,size=32m"]
        for source,destination,readonly in (
            (PUBLIC,"/run/jason/owner-objective",True),(STATE,"/var/lib/jason-owner-objective",False),
            (AUTHORITY.parent,str(AUTHORITY.parent),True),(BINDINGS.parent,str(BINDINGS.parent),True),
            (SPOOL,"/var/lib/jason/owner-objective-inbox",False),(TOKEN,"/run/jason/owner-objective-token",True),
        ):
            args+=["--mount","type=bind,src="+str(source)+",dst="+destination+(",readonly" if readonly else "")]
        args+=[image]
        self.container_created=True
        self.c["run"](args)
        for _ in range(30):
            row=json.loads(self.c["run"](["/usr/bin/docker","inspect","jason-owner-objective"]))[0]
            if row["State"].get("Health",{}).get("Status")=="healthy":return
            need(row["State"]["Running"] is True,"COMPONENT_EXITED")
            time.sleep(2)
        raise PermissionError("OBJECTIVE_INSTALL_COMPONENT_HEALTH_TIMEOUT")

    def native_acceptance(self):
        c=self.c
        self.units_started=True
        c["systemctl"](["enable","--now","jason-owner-objective-executor.path"])
        c["systemctl"](["start","jason-production-drift-watchdog.service"])
        code='import sys;from pathlib import Path;sys.path[:0]=["/home/al/.local/lib/jason","/opt/jason/current/tools"];import release_manager_host_runner as r;r.request_root_control_transition(Path(sys.argv[1]),action="set_last_known_good",revision=sys.argv[2],release_id=sys.argv[3])'
        c["user_python"](code,c["MANAGER"],ROLLBACK,
                         self.facts["control"]["last_known_good"]["release_id"],timeout=130)
        drift=json.loads(c["read"](c["MANAGER"]/"production-drift.json",0,0o600))
        control=json.loads(c["read"](c["MANAGER"]/"production-control-state.json",0,0o600))
        need(drift["status"]=="pass" and drift["problems"]==[]
             and control["circuit_breaker"]["state"]=="closed","NATIVE_ACCEPTANCE_NOT_CLEAN")
        before=self.facts["control"]["last_known_good"]["manifest"]
        after=control["last_known_good"]["manifest"]
        for key in ("revision","runtime_revision","runtime_image_id","mcp_revision","mcp_image_id",
                    "host_revision","host_release","release_manager_source_revision",
                    "mobile_release_approval_policy_digest","mobile_release_approval_mode"):
            need(before[key]==after[key],"PROTECTED_LKG_FIELD_CHANGED")
        need(c["props"]("jason-owner-objective-executor.path",False)["ActiveState"]=="active","ROOT_PATH_NOT_ACTIVE")
        need(c["read"](MARKER,0,0o444)==self.facts["marker"],"STAGE_E_MARKER_CHANGED")
        need(digest(c["read"](c["PAUSE"],1000,0o600))==self.scope["owner_pause_sha256"],"OWNER_PAUSE_CHANGED")
        for path,expected in self.scope["protection_files"].items():
            uid,mode=(1000,0o664) if Path(path)==self.ns["HOLD"] else (
                (1000,0o600) if Path(path)==self.ns["FREEZE"] else (0,0o755))
            need(digest(c["read"](Path(path),uid,mode))==expected,"PROTECTED_CONTROL_CHANGED")
        for name,expected in self.facts["native"].items():
            need(digest(c["read"](c["NATIVE"]/name,0,0o444))==expected,"ACCEPTED_NATIVE_CODE_CHANGED")
        ready=dict(ready=True,source_sha=self.candidate)
        replace_root(c,PUBLIC/"activation.json",canonical({"ready":False,"source_sha":self.candidate}),
                     canonical(ready),0o444)
        self.write(INSTALL/"accepted.json",canonical({
            "status":"owner_objective_installation_verified","candidate_sha":self.candidate,
            "scope_sha256":digest(canonical(self.scope)),"adopted_policy_sha256":self.scope["adopted_policy_sha256"],
            "runtime_mcp_ticket_core_changed":False,"live_teams_acceptance_required":True,
            "accepted_at":datetime.now(timezone.utc).isoformat(),
        }),0o400)

    def restore(self):
        """Reverse only this transaction's effects; preserve all human evidence."""
        c=self.c
        if (PUBLIC/"activation.json").exists():
            raw=c["read"](PUBLIC/"activation.json",0,0o444)
            replace_root(c,PUBLIC/"activation.json",raw,
                canonical({"ready":False,"source_sha":self.candidate}),0o444)
        if self.units_started:
            c["systemctl"](["disable","--now","jason-owner-objective-executor.path"])
        if self.container_created:
            c["run"](["/usr/bin/docker","rm","-f","jason-owner-objective"])
        if self.gateway_changed:
            current=json.loads(c["run"](["/usr/bin/docker","inspect","jason-teams-gateway"]))[0]
            if current["Id"]!=self.facts["gateway"]["Id"]:
                need(current["Image"]==self.scope["artifacts"]["gateway_image"],"FOREIGN_GATEWAY_ON_ROLLBACK")
                c["run"](["/usr/bin/docker","rm","-f","jason-teams-gateway"])
                prior=json.loads(c["run"](["/usr/bin/docker","inspect",self.gateway_rollback]))[0]
                need(prior["Id"]==self.facts["gateway"]["Id"],"EXACT_GATEWAY_ROLLBACK_NOT_PRESENT")
                c["run"](["/usr/bin/docker","rename",self.gateway_rollback,"jason-teams-gateway"])
                c["run"](["/usr/bin/docker","start","jason-teams-gateway"])
        if self.grants_written:
            c["user_python"](GRANT_REVOKE,TRUSTED,canonical(self.facts["grants"]).decode(),AUTHORITY)
        if self.database_moved:
            need(OLD_PLANS.is_symlink() and os.readlink(OLD_PLANS)==str(STATE/"universal-approvals.sqlite3"),
                 "FOREIGN_DATABASE_COMPATIBILITY_LINK")
            # Preserve all newer canonical rows; never restore an old database
            # snapshot over a decision that may have been recorded meanwhile.
            c["user_python"]("import os,sys;os.unlink(sys.argv[1]);os.rename(sys.argv[2],sys.argv[1])",
                OLD_PLANS,STATE/"universal-approvals.sqlite3")
            c["sync_dir"](OLD_PLANS.parent)
        if self.policy_changed:
            replace_root(c,ROOT_POLICY,canonical(self.facts["policy_after"]),self.facts["policy_raw"])
        # Keep private approvals, before-images and native outcomes. Read-only
        # installed source is also retained for auditable recovery.
        for path,uid,mode,expected in reversed(self.files):
            if PRIVATE in path.parents or TRUSTED in path.parents or PUBLIC in path.parents:continue
            if path.exists():
                need(digest(c["read"](path,uid,mode))==expected,"FOREIGN_FILE_ON_ROLLBACK")
                path.unlink()
        c["systemctl"](["daemon-reload"])
        for directory in reversed(self.directories):
            if (directory not in (BASE,TRUSTED,PUBLIC,PRIVATE,INSTALL)
                    and PRIVATE not in directory.parents and TRUSTED not in directory.parents
                    and PUBLIC not in directory.parents and directory.exists() and not any(directory.iterdir())):
                directory.rmdir()
        c["systemctl"](["start","jason-production-drift-watchdog.service"])
        code='import sys;from pathlib import Path;sys.path[:0]=["/home/al/.local/lib/jason","/opt/jason/current/tools"];import release_manager_host_runner as r;r.request_root_control_transition(Path(sys.argv[1]),action="set_last_known_good",revision=sys.argv[2],release_id=sys.argv[3])'
        c["user_python"](code,c["MANAGER"],ROLLBACK,
            self.facts["control"]["last_known_good"]["release_id"],timeout=130)


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument("--source-sha",required=True)
    parser.add_argument("--apply",action="store_true")
    args=parser.parse_args(argv)
    need(os.geteuid()==0 and sys.flags.isolated==1 and SHA.fullmatch(args.source_sha),"EXACT_ISOLATED_ROOT_REQUIRED")
    c,ns=primitives()
    need(c["git"](REPO,"rev-parse","HEAD")==args.source_sha,"SOURCE_REVISION_MISMATCH")
    ci(c,args.source_sha)
    peers=c["peers"]()
    print("ROOT_SOURCE_AND_REQUIRED_CI=VERIFIED",flush=True)
    artifacts=prepare_images(c,args.source_sha,peers)
    import secrets
    campaign=dict(deny_approval_id="planapproval-objective-"+secrets.token_hex(16),
                  approve_approval_id="planapproval-objective-"+secrets.token_hex(16),
                  issued_at=datetime.now(timezone.utc).isoformat())
    with ns["locks"]():
        scope,facts=inspect(c,ns,args.source_sha,artifacts,campaign)
    print("FULL_ROOT_PREFLIGHT=PASS;PRODUCTION_MUTATIONS=false",flush=True)
    print("PREPARED_COMPONENT_IMAGE="+artifacts["component_image"],flush=True)
    print("PREPARED_GATEWAY_IMAGE="+artifacts["gateway_image"],flush=True)
    print("GATEWAY_REPLACEMENTS=1;RUNTIME_RESTARTS=0;MCP_RESTARTS=0;TICKET_CORE_CHANGES=0",flush=True)
    print("NARROW_GRANTS=6;INITIAL_NATIVE_OBJECTIVE=DOCUMENTATION_RESTORE_AND_VERIFY",flush=True)
    if not args.apply:
        print(json.dumps({"scope_sha256":digest(canonical(scope)),"scope":scope},sort_keys=True));return
    actor=ns["owner"](scope)
    transaction=Installation(c,ns,args.source_sha,scope,facts)
    try:
        with ns["locks"]():
            again,_=inspect(c,ns,args.source_sha,artifacts,campaign)
            need(again==scope,"APPROVED_SCOPE_CHANGED")
            transaction.apply(actor)
            transaction.replace_gateway()
            transaction.seal_profiles()
            transaction.start_component()
        transaction.native_acceptance()
    except BaseException as original:
        try:
            transaction.restore()
        except Exception as recovery:
            if INSTALL.is_dir():
                c["write"](INSTALL/"recovery-required.json",canonical({
                    "status":"root_readback_required","failure_type":type(original).__name__,
                    "recovery_type":type(recovery).__name__,"approval_reused":False}),0o400)
            raise PermissionError("OBJECTIVE_INSTALL_ROLLBACK_NOT_VERIFIED_SEE_ROOT_RECEIPTS") from recovery
        if INSTALL.is_dir():
            c["write"](INSTALL/"rolled-back.json",canonical({
                "status":"exact_rollback_completed","failure_type":type(original).__name__,
                "original_evidence_preserved":True}),0o400)
        raise
    print("OWNER_OBJECTIVE_INSTALLATION=VERIFIED",flush=True)
    print("LIVE_TEAMS_DENY_AND_ORIGINAL_APPROVE_ACCEPTANCE_REQUIRED=true",flush=True)


if __name__=="__main__":
    try:main()
    except Exception as exc:
        raise SystemExit("DENIED:"+type(exc).__name__+":"+str(exc)[:300])
