"""One exact migration of the obsolete freeze into the existing release policy.

Loaded only from the independently reviewed native manager installer. Its
parent approval binds this entire fixed scope; no separate approval, generic
privileged command interface, provider write, or standing authority is added.
The accepted preparation phase remains frozen. The final phase uses the same
production locks, exact before images, and existing Docker/native health ports.
"""
from __future__ import annotations

from copy import deepcopy
from contextlib import ExitStack
from datetime import datetime, timezone
from hashlib import sha256
import json
import fcntl
import os
from pathlib import Path
import stat
import shutil

ACTION = "RETIRE-EXACT-GLOBAL-PRODUCTION-FREEZE"
BASE = "d1b8c196dadd4b672ec8ba47075f27bb61c98d63"
PROJECTION = "2a56474968a45161bbdfb9f0c341bd85cb486241"
IMAGE = "sha256:384285f9282ddb7627994fdfefe84d2abb26abc19a84d41f550e9528b90137ba"
REF = "refs/heads/prep/normal-config-mcp-2a56474968a4"
ORIGIN = "https://github.com/al-teamaot-com/jason.git"
INSTALL = Path("/usr/local/lib/jason/scoped-backport")
ETC = Path("/etc/jason-owner-release")
STATE = Path("/var/lib/jason/openclaw/release-manager")
PRIVATE = Path("/var/lib/jason-scoped-backport/coordinated")
PUB = ETC / "normal-release-policy"
CONFIG = PUB / "deployment.json"
RETIRED = PUB / "production-freeze-retirement.json"
READBACK = ETC / "coordinated-readback/component.json"
MIGRATION = ETC / "coordinated-reader-migration.json"
POLICY = ETC / "scoped-backport-coordinated-installed.json"
FREEZE = STATE / "production-deployment-freeze"
BACKUP = STATE / "production-deployment-freeze.pmv3-one-release-backup"
HOLD = STATE / "auto-promotion-incident-hold"
FREEZE_HASH = "bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f"
HOLD_HASH = "11f0f78904236c36ebd1aeee58f52fcecba035bce33d15ce323b36d36ad5a5a0"
MCP = "jason-mcp-pilot"
ROLLBACK = MCP + "-rollback-scoped-retirement-" + PROJECTION[:12]
PEERS = ("jason-runtime", MCP, "jason-teams-gateway", "jason-pmv4-ticket-core", "openbao")
COMPONENTS = PEERS[:3]
SOURCES = {
    INSTALL / "tools/scoped_backport_coordinated.py": "tools/scoped_backport_coordinated.py",
    INSTALL / "tools/scoped_backport_coordinated_host.py": "tools/scoped_backport_coordinated_host.py",
    INSTALL / "tools/scoped_backport_coordinated_root.py": "tools/scoped_backport_coordinated_root.py",
    INSTALL / "tools/coordinated_deploy_live_container.py": "tools/deploy_live_container.py",
    INSTALL / "tools/pmv4_mcp_projection.py": "tools/pmv4_mcp_projection.py",
    INSTALL / "tools/release_control_transition_worker.py": "tools/scoped_backport_release_control_transition_worker.py",
    INSTALL / "implementation/kernel/signed_owner_release_v2.py": "implementation/kernel/signed_owner_release_v2.py",
}
UNITS = Path("/etc/systemd/system")
for unit in ("jason-scoped-backport-requests.service", "jason-scoped-backport-requests.path",
             "jason-scoped-backport-recovery.service"):
    rel = unit + ".d/95-coordinated-normal-release.conf"
    SOURCES[UNITS / rel] = "infrastructure/scoped-backport-release/" + rel
TRANSITIONS = {
    UNITS / (unit + ".d/95-coordinated-normal-reader.conf"):
    b"[Service]\nExecStart=\nExecStart=/usr/bin/python3 -I -B /usr/local/lib/jason/scoped-backport/tools/release_control_transition_worker.py\n"
    for unit in ("jason-release-control-transition.service", "jason-pmv4-component-transition.service")
}
DYNAMIC = (CONFIG, RETIRED, READBACK, MIGRATION, POLICY)
PROJECTION_SOURCES = (
    "implementation/kernel/signed_owner_release_v2.py",
    "implementation/mcp_service/src/jason_mcp/release_approval_request.py",
)
ORIGINAL_FILES = (
    INSTALL/"tools/scoped_backport_native_host.py",
    INSTALL/"tools/scoped_backport_release.py",
    INSTALL/"implementation/kernel/signed_owner_release.py",
    ETC/"scoped-backport-installed.json",
    Path("/usr/local/lib/jason/release_host_reconcile_worker.py"),
    Path("/etc/jason/release-readback-recovery/production-desired-state.json"),
    *(UNITS/unit for unit in ("jason-scoped-backport-requests.service",
                            "jason-scoped-backport-requests.path",
                            "jason-scoped-backport-recovery.service",
                            "jason-scoped-backport-recovery.timer",
                            "jason-release-control-transition.service",
                            "jason-pmv4-component-transition.service")),
)
DIRS = {PUB:0o755, READBACK.parent:0o755, PRIVATE:0o700,
        PRIVATE/"transactions":0o700, PRIVATE/"offers":0o700,
        PRIVATE/"freeze-backups":0o700, PRIVATE/"source.git":0o700,
        **{p.parent:0o755 for p in (*SOURCES, *TRANSITIONS) if p.parent.parent == UNITS}}


def need(ok, reason):
    if not ok:
        raise PermissionError("FREEZE_RETIREMENT_" + reason)


def digest(raw):
    return sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False).encode()


def static_files(adapter, ops):
    return {**{path:ops["image"](adapter.code[rel],0,0o644 if path.is_relative_to(UNITS) else 0o444)
               for path,rel in SOURCES.items()},
            **{p:ops["image"](raw,0,0o644) for p,raw in TRANSITIONS.items()}}


def container_rows(adapter):
    rows=json.loads(adapter.command(["/usr/bin/docker","inspect","--type","container",*PEERS],45))
    result={r["Name"].lstrip("/"):r for r in rows}
    need(set(result)==set(PEERS),"PEER_SET")
    return result


def config_fingerprint(row, *, remove_projection=False):
    c,h=row["Config"],row["HostConfig"]
    env=dict(s.split("=",1) for s in c["Env"])
    env.pop("JASON_SOURCE_REVISION",None)
    mounts=sorted((m["Type"],m["Source"],m["Destination"],m["RW"]) for m in row["Mounts"])
    if remove_projection:
        exact=("bind",str(PUB),str(PUB),False)
        need(mounts.count(exact)==1,"MCP_PROJECTION_MOUNT")
        mounts.remove(exact)
    return digest(canonical({
        "environment":env,"config":{k:c.get(k) for k in ("User","WorkingDir","Entrypoint","Cmd","Healthcheck")},
        "host":{k:h.get(k) for k in ("ReadonlyRootfs","Privileged","CapDrop","CapAdd",
            "SecurityOpt","Memory","NanoCpus","PidsLimit","NetworkMode","RestartPolicy",
            "PortBindings","Devices","Tmpfs","PidMode","IpcMode")},
        "mounts":mounts,"networks":sorted(row["NetworkSettings"]["Networks"])}))


def peer_state(rows):
    out={}
    for name,r in rows.items():
        need(r["State"]["Running"] is True and
             (r["State"].get("Health") or {}).get("Status") in (None,"healthy"),"PEER_UNHEALTHY")
        out[name]={"id":r["Id"],"image":r["Image"],"started_at":r["State"]["StartedAt"],
                   "configuration_sha256":config_fingerprint(r)}
    return out


def check_pending(adapter):
    # Do not invalidate any already-executing legacy release or recovery.
    for folder in (Path("/var/lib/jason-scoped-backport/transactions"),
                   Path("/var/lib/jason-catalog-scoped-promotion/transactions")):
        for p in folder.glob("release-*.json"):
            row=json.loads(adapter.p["read"](p,0,0o600))
            need(row.get("outcome") in ("production_pair_verified","rollback_verified",
                                       "failed_before_mutation"),"LEGACY_TRANSACTION_UNRESOLVED")
    for p in (STATE/"owner-unfreeze-receipts").glob("*.json"):
        row=json.loads(adapter.p["read"](p,1000,0o600))
        need(not (row.get("status") in ("authorized_pending","unfrozen_active")
                  and row.get("freeze_restored") is False),"LEGACY_FREEZE_TRANSACTION_UNRESOLVED")
    for folder in (STATE/"host-reconcile/requests",STATE/"owner-approval-requests",
                   Path("/var/lib/jason/authority/scoped-backport-release/requests")):
        need(not list(folder.glob("*.json")),"LEGACY_REQUEST_PENDING")


def prepare(adapter, manager_plan, ops):
    """Read-only exact scope; called under the existing production locks."""
    snap=ops["snapshot"]
    git=lambda *args: adapter.p["git"](ops["REPO"],*args)
    need(git("ls-remote","origin",REF).decode().split()==[PROJECTION,REF],"PROJECTION_REF")
    need(set(git("diff","--name-only",BASE,PROJECTION).decode().splitlines())==
         set(PROJECTION_SOURCES),"PROJECTION_SCOPE")
    for rel in PROJECTION_SOURCES:
        need(git("show",PROJECTION+":"+rel)==adapter.code[rel],"PROJECTION_SOURCE_CHANGED")
    images=json.loads(adapter.command(["/usr/bin/docker","image","inspect",IMAGE],30))
    need(len(images)==1 and images[0]["Id"]==IMAGE and
         images[0]["Config"]["Labels"].get("com.teamaot.jason.source_revision")==PROJECTION,
         "BOOTSTRAP_IMAGE")
    for marker in (FREEZE,BACKUP):
        value=snap(marker)
        need(value is not None and value[1:]==(1000,1000,0o600)
             and digest(value[0])==FREEZE_HASH,"LEGACY_FREEZE_CHANGED")
    need(digest(adapter.p["read"](HOLD,1000,0o664))==HOLD_HASH,"INCIDENT_HOLD_CHANGED")
    check_pending(adapter)
    files=static_files(adapter,ops)
    need(all(snap(p) is None for p in (*files,*DYNAMIC)),"NEW_TARGET_ALREADY_PRESENT")
    dirs={}
    for path,mode in DIRS.items():
        if os.path.lexists(path):
            st=path.lstat()
            need(stat.S_ISDIR(st.st_mode) and st.st_uid==st.st_gid==0
                 and stat.S_IMODE(st.st_mode)==mode,"DIRECTORY_CUSTODY")
            need(path.is_relative_to(UNITS),"PRIVATE_TARGET_EXISTS")
        else:
            dirs[str(path)]=oct(mode)
    rows=container_rows(adapter)
    peers=peer_state(rows)
    need(all({k:v[k] for k in ("id","image","started_at")}==
             manager_plan["protected_health"]["protected_peers"][name]
             for name,v in peers.items()),"PEER_PREDECESSOR_CHANGED")
    need(rows[MCP]["Config"]["Labels"]["com.teamaot.jason.source_revision"]==BASE,
         "MCP_BASELINE")
    names=adapter.command(["/usr/bin/docker","ps","-a","--format","{{.Names}}"],15).decode().splitlines()
    need(ROLLBACK not in names,"ROLLBACK_NAME_OCCUPIED")
    originals={str(p):ops["describe"](snap(p)) for p in ORIGINAL_FILES}
    need(all(v is not None for v in originals.values()),"ORIGINAL_SOURCE_MISSING")
    desired=json.loads(adapter.p["read"](Path("/etc/jason/release-readback-recovery/production-desired-state.json"),0,0o600))
    prefixes=tuple(desired["rollback_container_prefixes"])
    exited=adapter.command(["/usr/bin/docker","ps","-a","--filter","status=exited","--format","{{.Names}}"],15).decode().splitlines()
    need(ROLLBACK.startswith(prefixes) and sum(n.startswith(prefixes) for n in exited)+1<=
         desired["max_stopped_rollback_containers"],"ROLLBACK_CAPACITY")
    return {"schema_version":"1.0","action":ACTION,"candidate_sha":adapter.candidate,
            "bootstrap_revision":PROJECTION,"bootstrap_image":IMAGE,"bootstrap_ref":REF,
            "rollback_container":ROLLBACK,"configuration_after":{"schema_version":"1.0","production_freeze":False},
            "freeze_sha256":FREEZE_HASH,"incident_hold_sha256":HOLD_HASH,
            "original_files":originals,"new_files":{str(p):ops["describe"](v) for p,v in files.items()},
            "create_directories":dirs,"peers_before":peers,"provider_writes":False,
            "standing_authority":False,"exact_release_approval_required":True,
            "rollback_authorized":True,"retain_accepted_preparation_on_rollback":True,
            "installation_targets":sorted([*map(str,files),*map(str,DYNAMIC),
                                            *dirs,str(FREEZE),str(BACKUP),MCP,ROLLBACK])}


def owner_scope(plan):
    final=plan.get("normal_retirement")
    if final is None:
        return plan
    need(final["action"]==ACTION and final["candidate_sha"]==plan["policy"]["candidate_sha"]
         and final["provider_writes"] is False and final["standing_authority"] is False
         and final["rollback_authorized"] is True
         and final["configuration_after"]=={"schema_version":"1.0","production_freeze":False},
         "EXACT_PARENT_SCOPE")
    return {"action":ACTION,"policy":plan["policy"],"queue_cutover":False,
            "installation_targets":sorted(set(plan["installation_targets"])|set(final["installation_targets"])),
            "manager_preparation_and_retirement":plan}


def installed_code(adapter):
    # Imports only the root-owned installed package. Never put the operator
    # checkout or user site directories on the root worker's module path.
    code=("import json,sys;sys.path.insert(0,"+repr(str(INSTALL))+");"
          "from tools import scoped_backport_coordinated_host as h;"
          "from tools import scoped_backport_component_readback as r;")
    return code


def root_observation(adapter, expression):
    return json.loads(adapter.command(["/usr/bin/python3","-I","-B","-c",
        installed_code(adapter)+"print(json.dumps("+expression+",sort_keys=True))"],180))


def deploy_args():
    bootstrap=("import runpy,sys;sys.path.insert(0,"+repr(str(INSTALL))+");"
               "runpy.run_module('tools.coordinated_deploy_live_container',run_name='__main__')")
    return ["/usr/bin/python3","-I","-B","-c",bootstrap,"--live",MCP,"--image",IMAGE,
            "--rollback",ROLLBACK,"--source-revision",PROJECTION,
            "--health-url","http://127.0.0.1:8000/healthz","--enforce-no-paid-ai",
            "--add-readonly-bind",str(PUB)+":"+str(PUB)]


def verify_mcp(adapter, scope):
    rows=container_rows(adapter)
    current=peer_state(rows)
    for name in PEERS:
        if name!=MCP:
            need(current[name]==scope["peers_before"][name],"PROTECTED_PEER_CHANGED")
    r=rows[MCP]
    need(r["Image"]==IMAGE and r["Config"]["Labels"]["com.teamaot.jason.source_revision"]==PROJECTION
         and config_fingerprint(r,remove_projection=True)==scope["peers_before"][MCP]["configuration_sha256"],
         "MCP_BOOTSTRAP_CONFIGURATION")
    old=json.loads(adapter.command(["/usr/bin/docker","inspect","--type","container",ROLLBACK],20))[0]
    need(old["Id"]==scope["peers_before"][MCP]["id"] and old["Image"]==scope["peers_before"][MCP]["image"]
         and old["State"]["Running"] is False,"MCP_ROLLBACK_CUSTODY")
    return {n:{"revision":rows[n]["Config"]["Labels"]["com.teamaot.jason.source_revision"],
               "image_id":rows[n]["Image"],"container_id":rows[n]["Id"]} for n in COMPONENTS}


def claim_existing_intent(adapter, path, lease):
    """Serialize this exact journal without introducing a new lock file or authority."""
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    lease.callback(os.close,fd)
    meta=os.fstat(fd)
    need(stat.S_ISREG(meta.st_mode) and meta.st_nlink==1
         and 0<meta.st_size<=8_000_000,"INTENT_FILE_CUSTODY")
    try:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError as exc:
        raise PermissionError("FREEZE_RETIREMENT_TRANSACTION_ALREADY_ACTIVE") from exc
    trusted=adapter.n["read"](path,0,0o400,8_000_000)
    with os.fdopen(os.dup(fd),"rb") as stream:
        raw=stream.read(8_000_001)
    live=path.lstat()
    need((meta.st_dev,meta.st_ino,meta.st_size,meta.st_mtime_ns)==
         (live.st_dev,live.st_ino,live.st_size,live.st_mtime_ns)
         and raw==trusted and len(raw)==meta.st_size,"INTENT_FILE_CHANGED")
    return json.loads(raw)


def activate(adapter, ops, *, recover=False):
    """Consume the already authenticated parent approval, not a second decision."""
    with ExitStack() as lease:
        return _activate(adapter,ops,lease,recover=recover)


def _activate(adapter,ops,lease,*,recover=False):
    sha=adapter.load_record()
    scope=adapter.plan.get("normal_retirement")
    need(isinstance(scope,dict),"PARENT_APPROVAL_REQUIRED")
    approved=adapter.n["read"](adapter.directory/"approval.json",0,0o400,8_000_000)
    approval=json.loads(approved)
    parent_sha=digest(canonical(owner_scope(adapter.plan)))
    need(approval.get("owner_scope_sha256")==parent_sha and
         approval.get("owner_action")==ACTION,"PARENT_APPROVAL_BINDING")
    accepted=json.loads(adapter.n["read"](adapter.directory/"scheduled-acceptance.json",0,0o400))
    need(accepted["scope_sha256"]==sha and accepted["status"]=="scheduled_engineering_acceptance_verified"
         and accepted["evidence"].get("two_distinct_scheduled_cycles_verified") is True,"PREPARATION_NOT_ACCEPTED")
    # No caller-defined paths or commands. Durable exact before/after images
    # are recorded once. A failed process can only recover this approved plan.
    intent_path=adapter.directory/"retirement-intent.json"
    readback_path=adapter.directory/"retirement-readback-intent.json"
    ready_path=adapter.directory/"retirement-ready.json"
    done_path=adapter.directory/"retirement-complete.json"
    rolled_path=adapter.directory/"retirement-rollback.json"
    snap=ops["snapshot"]; image=ops["image"]
    change=lambda p,b,a: ops["replace_exact"](p,b,a,adapter.p["rename_noreplace"])
    emit=lambda p,v: adapter.n["write"](p,canonical(v),0o400)
    frozen=image(canonical({"schema_version":"1.0","production_freeze":True}),0,0o644)
    unfrozen=image(canonical(scope["configuration_after"]),0,0o644)
    with adapter.n["locks"]():
        if os.path.lexists(done_path):
            completed=json.loads(adapter.n["read"](done_path,0,0o400))
            need(completed.get("parent_sha256")==parent_sha
                 and completed.get("source_sha")==adapter.candidate,
                 "HISTORICAL_COMPLETION_SCOPE")
            return {"status":"retirement_previously_committed","receipt":completed,
                    "live_verification_required":True}
        need(not os.path.lexists(rolled_path),"ATTEMPT_ALREADY_ROLLED_BACK")
        if recover:
            intent=claim_existing_intent(adapter,intent_path,lease)
            need(intent["parent_sha256"]==parent_sha,"RECOVERY_SCOPE")
            before=ops["decode"](intent["before"],set(static_files(adapter,ops))|set(DYNAMIC)|{FREEZE,BACKUP})
            after=ops["decode"](intent["after"],set(before))
            if os.path.lexists(readback_path):
                after[READBACK]=image(adapter.n["read"](readback_path,0,0o400),0,0o644)
            if snap(CONFIG)==unfrozen and os.path.lexists(ready_path):
                # This is historical commit recovery, not new live acceptance.
                # Never reverse a committed transaction after a later release.
                ready=json.loads(adapter.n["read"](ready_path,0,0o400))
                need(ready.get("parent_sha256")==parent_sha
                     and ready.get("source_sha")==adapter.candidate
                     and ready.get("status")=="global_production_freeze_retired",
                     "COMMIT_SCOPE")
                emit(done_path,ready)
                return {"status":"retirement_commit_recovered","receipt":ready,
                        "live_verification_required":True}
        else:
            need(not os.path.lexists(intent_path),"RECOVERY_REQUIRED")
            adapter.verify_successor_topology_and_source(resumed=True)
            need(prepare(adapter,adapter.plan,ops)==scope,"APPROVED_RETIREMENT_SCOPE_CHANGED")
            before={p:snap(p) for p in (*static_files(adapter,ops),*DYNAMIC,FREEZE,BACKUP)}
            after={**static_files(adapter,ops),CONFIG:frozen,FREEZE:None,BACKUP:None,
                   RETIRED:image(canonical({"schema_version":"1.0","authorization":"retire_global_production_freeze_only",
                       "retired_at":datetime.now(timezone.utc).isoformat(),"original_freeze_sha256":FREEZE_HASH,
                       "migration_scope_sha256":parent_sha,"owner_approval_reference":"owner-native-"+digest(approved)[:32],
                       "exact_release_approval_required":True,"standing_authority":False}),0,0o644),
                   READBACK:None,MIGRATION:None,POLICY:None}
            # All original freeze bytes remain in this root-private evidence.
            emit(intent_path,{"parent_sha256":parent_sha,"before":ops["encode"](before),"after":ops["encode"](after)})
            claimed=claim_existing_intent(adapter,intent_path,lease)
            need(claimed["parent_sha256"]==parent_sha,"INTENT_SCOPE")
            adapter.pause()
    try:
        if recover:
            raise RuntimeError("interrupted exact retirement recovery")
        adapter.quiesce((ops["SERVICES"][0],))
        with adapter.n["locks"]():
            need(adapter.protected()==adapter.plan["protected_health"],"PREMUTATION_HEALTH_CHANGED")
            check_pending(adapter)
            for path,mode in sorted(scope["create_directories"].items(),key=lambda x:len(Path(x[0]).parts)):
                p=Path(path);p.mkdir(mode=int(mode,8));adapter.n["sync_dir"](p.parent)
            for p in (*static_files(adapter,ops),CONFIG):
                change(p,before[p],after[p])
            repo=PRIVATE/"source.git"
            adapter.command(["/usr/bin/git","init","--bare",str(repo)],30)
            adapter.command(["/usr/bin/git","-C",str(repo),"remote","add","origin",ORIGIN],30)
            adapter.command(["/usr/bin/git","-C",str(repo),"-c","core.hooksPath=/dev/null","fetch",
                             "--no-tags","--no-recurse-submodules","origin",
                             "+refs/heads/main:refs/remotes/origin/main","+"+REF+":"+REF],240)
            adapter.systemctl(["daemon-reload"])
            artifacts=root_observation(adapter,"{k:[str(v[0]),v[1]] for k,v in h.verified_manager_artifacts().items()}")
            readers=[{"path":str(INSTALL/"tools/pmv4_host_release_guard.py"),
                      "sha256":digest(snap(INSTALL/"tools/pmv4_host_release_guard.py")[0])},
                     {"path":artifacts["jason_self_heal_watchdog.py"][0],
                      "sha256":artifacts["jason_self_heal_watchdog.py"][1]},
                     {"path":str(INSTALL/"tools/release_control_transition_worker.py"),
                      "sha256":digest(after[INSTALL/"tools/release_control_transition_worker.py"][0])}]
            migration={"schema_version":"2.0","source_sha":adapter.candidate,"native_readback_verified":True,
                       "original_authority_preserved":True,"installed_readers":readers}
            after[MIGRATION]=image(canonical(migration),0,0o600)
            pins=root_observation(adapter,"{k:h.sha256(h.trusted_bytes(v)).hexdigest() for k,v in h.FILES.items()}")
            policy={"schema_version":"3.0","source_sha":adapter.candidate,"file_sha256":pins,
                    "native_reader_migration_receipt_sha256":digest(after[MIGRATION][0]),
                    "allowed_targets":list(COMPONENTS),"per_release_review_required":True}
            after[POLICY]=image(canonical(policy),0,0o600)
            emit(adapter.directory/"retirement-policy-intent.json",
                 {"parent_sha256":parent_sha,"files":ops["encode"]({MIGRATION:after[MIGRATION],POLICY:after[POLICY]})})
            change(MIGRATION,None,after[MIGRATION]);change(POLICY,None,after[POLICY])
            root_observation(adapter,"h.verify_installed_policy()")
            adapter.command([*deploy_args(),"--preflight"],120)
            adapter.command(deploy_args(),240)
            components=verify_mcp(adapter,scope)
            readback={"schema_version":"3.0","status":"verified_component_release","host_revision":BASE,
                      "release_id":"release-"+PROJECTION[:16],"manifest_sha256":digest(canonical(scope)),
                      "scope_sha256":parent_sha,"release_policy_sha256":digest(after[RETIRED][0]),"components":components}
            after[READBACK]=image(canonical(readback),0,0o644)
            adapter.n["write"](readback_path,after[READBACK][0],0o400)
            change(RETIRED,None,after[RETIRED])
            change(BACKUP,before[BACKUP],None);change(FREEZE,before[FREEZE],None)
            change(READBACK,None,after[READBACK])
            need(root_observation(adapter,"r.verify_live()")==readback,"NATIVE_COMPONENT_READBACK")
        adapter.native_revalidation()
        with adapter.n["locks"]():
            components=verify_mcp(adapter,scope)
            root_observation(adapter,"h.verify_installed_policy()")
            need(root_observation(adapter,"r.verify_live()")["components"]==components,"FINAL_COMPONENT_READBACK")
            need(digest(adapter.p["read"](HOLD,1000,0o664))==HOLD_HASH,"INCIDENT_HOLD_CHANGED")
            # Prove the issuer can actually read its installed immutable
            # binding and the current configuration, without issuing a proof.
            code=("from kernel.signed_owner_release_v2 import read_retired_release_policy,"
                  "read_normal_deployment_freeze;import json;"
                  "print(json.dumps([read_retired_release_policy(),read_normal_deployment_freeze()]))")
            need(json.loads(adapter.command(["/usr/bin/docker","exec",MCP,"python","-c",code],30))
                 ==[digest(after[RETIRED][0]),True],"MCP_POLICY_READBACK")
            adapter.change(ops["PAUSE"],adapter.pause_image,None)
            result={"status":"global_production_freeze_retired","parent_sha256":parent_sha,
                    "source_sha":adapter.candidate,"components":components,
                    "production_freeze":False,"incident_hold_preserved":True,
                    "provider_writes":False,"exact_release_approval_required":True}
            emit(ready_path,result)
            change(CONFIG,frozen,unfrozen)
            emit(done_path,result)
            return result
    except BaseException:
        # A committed operation is never silently reversed by recovery.
        if snap(CONFIG)==unfrozen and os.path.lexists(ready_path):
            raise
        with adapter.n["locks"]():
            if os.path.lexists(adapter.directory/"retirement-policy-intent.json"):
                pi=json.loads(adapter.n["read"](adapter.directory/"retirement-policy-intent.json",0,0o400,2_000_000))
                need(pi["parent_sha256"]==parent_sha,"POLICY_RECOVERY_SCOPE")
                after.update(ops["decode"](pi["files"],{POLICY,MIGRATION}))
            names=adapter.command(["/usr/bin/docker","ps","-a","--format","{{.Names}}"],15).decode().splitlines()
            if ROLLBACK in names:
                old=json.loads(adapter.command(["/usr/bin/docker","inspect",ROLLBACK],20))[0]
                need(old["Id"]==scope["peers_before"][MCP]["id"],"FOREIGN_ROLLBACK_CONTAINER")
                if MCP in names:
                    cur=json.loads(adapter.command(["/usr/bin/docker","inspect",MCP],20))[0]
                    need(cur["Image"]==IMAGE and cur["Config"]["Labels"]["com.teamaot.jason.source_revision"]==PROJECTION,
                         "FOREIGN_MCP_CONTAINER")
                    adapter.command(["/usr/bin/docker","rm","-f",MCP],90)
                adapter.command(["/usr/bin/docker","rename",ROLLBACK,MCP],30)
                adapter.command(["/usr/bin/docker","start",MCP],90)
            else:
                cur=json.loads(adapter.command(["/usr/bin/docker","inspect",MCP],20))[0]
                need(cur["Id"]==scope["peers_before"][MCP]["id"],"ORIGINAL_MCP_NOT_FOUND")
                if not cur["State"]["Running"]:
                    adapter.command(["/usr/bin/docker","start",MCP],90)
            for p in (FREEZE,BACKUP,READBACK,RETIRED,POLICY,MIGRATION,CONFIG,*reversed(list(static_files(adapter,ops)))):
                cur=snap(p)
                need(cur in (before[p],after[p]),"FOREIGN_FILE:"+str(p))
                ops["cleanup_staged"](p,(before[p],after[p]))
                if cur!=before[p]: change(p,cur,before[p])
            for path in sorted(scope["create_directories"],key=lambda x:len(Path(x).parts),reverse=True):
                p=Path(path)
                if p==PRIVATE/"source.git" and p.is_dir() and not p.is_symlink() and p.stat().st_uid==0:
                    shutil.rmtree(p)
                elif p.exists(): p.rmdir()
                if p.parent.exists(): adapter.n["sync_dir"](p.parent)
            adapter.systemctl(["daemon-reload"])
        adapter.native_revalidation()
        with adapter.n["locks"]():
            adapter.change(ops["PAUSE"],snap(ops["PAUSE"]),None)
            emit(rolled_path,{"status":"original_freeze_and_mcp_restored","parent_sha256":parent_sha,
                              "accepted_manager_preparation_retained":True})
        if recover:
            return {"status":"original_freeze_and_mcp_restored"}
        raise
