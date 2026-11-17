#!/usr/bin/env python3
"""One-Owner, root-only exact Stage C canonical host-health recovery.

Does not close a breaker, bypass full integrity, move or copy a database,
change a Docker container, write a provider, or grant standing authority.
A prior signed Stage C transaction must have recorded embedded fallback.
"""
from __future__ import annotations
from contextlib import contextmanager
from datetime import datetime,timezone
import argparse,fcntl,hashlib,importlib.util,json,os,stat,subprocess,sys
from pathlib import Path

ARTIFACT=Path(__file__).resolve().parents[1]
# NEVER import untrusted owner-staged Python modules before the exact signed
# manifest has been validated. The protected CI verifier is loaded only from
# the pinned immutable *production LKG* installation as root-owned source.
CI_PIN=Path("/opt/jason/current/tools/pmv4_shadow_ci.py")
CI_SHA="57a3fb97d95752cfb61e7956e1140a04dc09fb3d07433d41ea42f827de366139"
CANONICAL_ORCH=Path("/var/lib/jason/governed-ticket-shared/orchestration-events.sqlite3")
LEGACY_ORCH=Path("/var/lib/jason/openclaw/orchestration-events.sqlite3")
ADAPTER=Path("/usr/local/lib/jason/pmv4-c-canonical-health-v1/pmv4_c_authority_health_adapter.py")
EXPORTERS=(
    "jason-usage-exporter.service",
    "jason-usage-attribution-exporter.service",
    "jason-security-control-exporter.service",
    "jason-reflection-exporter.service",
    "jason-resolution-memory-exporter.service",
)
CANONICAL_NAMES=(
    "model-usage.sqlite3","orchestration-events.sqlite3",
    "teams-identity-bindings.sqlite3","reflection.sqlite3",
    "resolution-memory.sqlite3",
)

LKG="d1b8c196dadd4b672ec8ba47075f27bb61c98d63"
STAGE_C="13917410bb0ea1d5d37a314b3a3f131d416bf154"
ACTION="pmv4-c-one-owner-exact-canonical-host-recovery-v1"
SIGNER=Path("/usr/local/lib/jason/owner_signed_release.py")
SIGNER_SHA="f50eea90102d9a1de82b3753ec8d0cd225280d385ac7a658ae2c2a303934a0e3"
PUBLIC=Path("/etc/jason-owner-release/verified-owner-public-key.json")
FREEZE=Path("/var/lib/jason/openclaw/release-manager/production-deployment-freeze")
HOLD=Path("/var/lib/jason/openclaw/release-manager/auto-promotion-incident-hold")
CONTROL=Path("/var/lib/jason/openclaw/release-manager/production-control-state.json")
DRIFT=Path("/var/lib/jason/openclaw/release-manager/production-drift.json")
ROOT_STATE=Path("/var/lib/jason/pmv4-stage-c/control")
PRIOR=Path("/srv/jason/archive/engineering-artifacts")/("pmv4-c-"+STAGE_C)
LOCKS=(Path("/var/lib/jason/openclaw/release-manager/production-transaction.lock"),
       Path("/var/lib/jason/pmv4-shadow/control/host-mutation.lock"))
UNITS=("jason-openclaw-authority-health.service",
       "jason-openclaw-authority-full-integrity.service")
DROPIN_NAME="99-pmv4-c-canonical-state.conf"
HEALTH_DROPIN="99-pmv4-c-canonical-health.conf"
UNIT_ROOT=Path("/etc/systemd/system")

class HostRecoveryDenied(RuntimeError):pass
def need(ok,code):
    if not ok:raise HostRecoveryDenied(code)
def canon(obj):
    return json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
def sha(data):return hashlib.sha256(data).hexdigest()
def json_doc(path):
    need(not path.is_symlink() and path.is_file() and path.stat().st_size<=3_000_000,
         "HOST_RECOVERY_JSON_UNTRUSTED:"+path.name)
    value=json.loads(path.read_bytes())
    need(isinstance(value,dict),"HOST_RECOVERY_JSON_INVALID:"+path.name)
    return value
def run(*args,timeout=30,check=True):
    result=subprocess.run(list(args),capture_output=True,text=True,timeout=timeout)
    if check:need(result.returncode==0,"HOST_RECOVERY_COMMAND_FAILED:"+args[-1])
    return result
def as_al(args,**kwargs):
    return subprocess.run(["/usr/sbin/runuser","-u","al","--",*args],**kwargs)
def exact_path(plan):
    expected="pmv4-c-host-recovery-"+plan["candidate_sha"]
    need(ARTIFACT.name==expected and not ARTIFACT.is_symlink()
         and Path(__file__).resolve().parent==ARTIFACT/"tools",
         "HOST_RECOVERY_ARTIFACT_LOCATION_CHANGED")
def trust_lib(path,digest,name):
    s=path.lstat()
    need(not path.is_symlink() and stat.S_ISREG(s.st_mode)
         and s.st_uid==0 and not s.st_mode&0o022 and sha(path.read_bytes())==digest,
         "HOST_RECOVERY_NATIVE_SIGNER_CHANGED")
    spec=importlib.util.spec_from_file_location(name,path)
    need(spec and spec.loader,"HOST_RECOVERY_NATIVE_SIGNER_UNAVAILABLE")
    x=importlib.util.module_from_spec(spec);spec.loader.exec_module(x)
    return x
def previous_stage_c(plan):
    signed_plan=PRIOR/"root-release-plan.json"
    prior_proof=PRIOR/"root-oneowner-proof.json"
    need(sha(signed_plan.read_bytes())==plan["previous_stage_c_plan_sha256"]
         and sha(prior_proof.read_bytes())==plan["previous_stage_c_proof_sha256"],
         "HOST_RECOVERY_PREVIOUS_SIGNED_PACKET_CHANGED")
    prior=json_doc(signed_plan)
    signed=json_doc(prior_proof)
    need(prior.get("candidate_sha")==STAGE_C
         and signed.get("approval_id")==plan["previous_stage_c_approval_id"]
         and signed.get("scope_sha256")==prior["scope_sha256"],
         "HOST_RECOVERY_PREVIOUS_APPROVAL_CHANGED")
    audit=ROOT_STATE/("cutover-"+STAGE_C[:12]+".jsonl")
    s=audit.lstat()
    need(not audit.is_symlink() and s.st_uid==0
         and stat.S_ISREG(s.st_mode) and stat.S_IMODE(s.st_mode)==0o600
         and s.st_size<500000,"HOST_RECOVERY_PRIOR_AUDIT_UNTRUSTED")
    rows=[];prior_hash="0"*64
    for raw in audit.read_bytes().splitlines():
        rec=json.loads(raw);sig=rec.pop("hash")
        need(rec["index"]==len(rows) and
             rec["candidate_sha"]==STAGE_C and
             rec["approval_id"]==signed["approval_id"] and
             rec["previous_sha256"]==prior_hash and
             sha(canon(rec))==sig,"HOST_RECOVERY_PRIOR_AUDIT_CHAIN_INVALID")
        rows.append(rec);prior_hash=sig
    need(rows and rows[0]["event"]=="begin" and
         rows[-1]["event"]=="rolled_back_to_embedded_new_canonical"
         and rows[-1]["details"].get("new_canonical_state_retained") is True,
         "HOST_RECOVERY_PRIOR_EMBEDDED_ROLLBACK_NOT_VERIFIED")
    signer=trust_lib(SIGNER,SIGNER_SHA,"root_previous_c_owner")
    previous_time=datetime.fromisoformat(rows[0]["occurred_at"])
    approved=signer.verify_exact_owner_release(
        signed["signed_release"],
        public_key=signer.read_pinned_root_owner_public_key(PUBLIC),
        at=previous_time,
        expected_candidate_sha=prior["candidate_sha"],
        expected_rollback_sha=prior["rollback_sha"],
        expected_release_id="release-"+STAGE_C[:16],
        expected_scope_sha256=prior["scope_sha256"],
        expected_manifest_sha256=sha(canon(prior)),
        expected_freeze_sha256=prior["freeze_sha256"])
    need(approved["approval_id"]==signed["approval_id"],
         "HOST_RECOVERY_PREVIOUS_OWNER_SIGNATURE_INVALID")
    return rows
def active_state(plan):
    need(Path("/opt/jason/current").resolve().name==LKG,
         "HOST_RECOVERY_LKG_CHANGED")
    need(sha(FREEZE.read_bytes())==plan["freeze_sha256"] and
         sha(HOLD.read_bytes())==plan["hold_sha256"],
         "HOST_RECOVERY_CONTROL_CHANGED")
    root_control=json_doc(CONTROL)
    root_drift=json_doc(DRIFT)
    circuit=root_control.get("circuit_breaker") or {}
    need(circuit.get("state")=="open" and
         circuit.get("reason")=="continuous_production_drift_detected" and
         root_drift.get("status")=="drift_detected" and
         root_drift.get("problems")==[{
            "kind":"failed_system_unit","state":"failed",
            "unit":"jason-openclaw-authority-health.service"}],
         "HOST_RECOVERY_BREAKER_OR_DRIFT_NOT_EXACT")
    for name,identity in plan["existing_container_identities"].items():
        item=json.loads(run("/usr/bin/docker","inspect",name).stdout)[0]
        need(item["Id"]==identity["id"] and item["Image"]==identity["image"]
             and item["State"]["Running"] is True,
             "HOST_RECOVERY_RUNTIME_OR_MCP_CHANGED:"+name)
    need(not run("/usr/bin/docker","ps","--filter",
                 "name=^/jason-pmv4-ticket-core$","--format","{{.Names}}").stdout.strip(),
         "HOST_RECOVERY_EXTERNAL_WORKER_UNEXPECTED")
    runtime=json.loads(run("/usr/bin/docker","inspect","jason-runtime").stdout)[0]
    environment={v.split("=",1)[0]:v.split("=",1)[1]
                 for v in runtime["Config"]["Env"] if "=" in v}
    need(environment.get("JASON_TICKET_WORKER_HOSTING")=="embedded" and
         environment.get("JASON_AUTONOMY_WORKER_DB")==
         "/var/lib/jason/ticket-core/autonomy-operational-work.sqlite3" and
         environment.get("JASON_ORCHESTRATION_EVENTS_DB")==str(CANONICAL_ORCH),
         "HOST_RECOVERY_NOT_EMBEDDED_NEW_CANONICAL")
    for raw,expected in plan["db_identities"].items():
        p=Path(raw);s=p.lstat()
        need(not p.is_symlink() and stat.S_ISREG(s.st_mode)
             and s.st_dev==expected["device"] and s.st_ino==expected["inode"]
             and s.st_uid==1000 and stat.S_IMODE(s.st_mode)==0o600
             and s.st_nlink==1,"HOST_RECOVERY_CANONICAL_INODE_CHANGED:"+p.name)
        old=Path("/var/lib/jason/openclaw")/p.name
        need(not old.exists() and not old.is_symlink(),
             "HOST_RECOVERY_CANONICAL_SPLIT_BRAIN:"+p.name)
    need(not LEGACY_ORCH.exists() and not LEGACY_ORCH.is_symlink(),
         "HOST_RECOVERY_LEGACY_ORCH_PRESENT")
    for name in CANONICAL_NAMES:
        file=CANONICAL_ORCH.parent/name
        s=file.lstat()
        need(not file.is_symlink() and stat.S_ISREG(s.st_mode)
             and s.st_uid==1000 and s.st_gid==1000
             and s.st_nlink==1 and stat.S_IMODE(s.st_mode)==0o600,
             "HOST_RECOVERY_HOST_CONSUMER_DB_UNTRUSTED:"+name)
def root_source(plan):
    for name,expected in plan["source_hashes"].items():
        if name in ("native_signer","native_oauth"):
            filename=SIGNER if name=="native_signer" else Path("/usr/local/lib/jason/owner_signer_recovery.py")
        else:
            filename=(ARTIFACT/"tools"/Path(name).name
                      if name.endswith(("_owner.py","_root.py"))
                      else ARTIFACT/"src"/name)
        need(sha(filename.read_bytes())==expected,
             "HOST_RECOVERY_STAGED_SOURCE_CHANGED:"+name)
    for raw,digest in plan["root_baseline_hashes"].items():
        p=Path(raw);s=p.lstat()
        need(not p.is_symlink() and stat.S_ISREG(s.st_mode)
             and s.st_uid==0 and s.st_nlink==1 and not s.st_mode&0o022
             and sha(p.read_bytes())==digest,
             "HOST_RECOVERY_ROOT_BASELINE_CHANGED:"+p.name)
    for unit,digest in plan["dropin_hashes"].items():
        path=ARTIFACT/"dropins"/(unit+".conf")
        need(sha(path.read_bytes())==digest,
             "HOST_RECOVERY_DROPIN_SOURCE_CHANGED:"+unit)
    for unit in (*UNITS,*EXPORTERS):
        name=HEALTH_DROPIN if unit in UNITS else DROPIN_NAME
        target=UNIT_ROOT/(unit+".d")/name
        need(not target.exists() and not target.is_symlink(),
             "HOST_RECOVERY_DROPIN_ALREADY_PRESENT:"+unit)
    need(not ADAPTER.exists() and not ADAPTER.is_symlink(),
         "HOST_RECOVERY_ADAPTER_ALREADY_INSTALLED")
    need(not (ROOT_STATE/("host-recovery-"+plan["candidate_sha"][:12]+".jsonl")).exists(),
         "HOST_RECOVERY_ALREADY_ATTEMPTED")
def exact_plan(path):
    need(os.geteuid()==0,"HOST_RECOVERY_PRIVILEGED_ROOT_REQUIRED")
    plan=json_doc(path)
    unsigned=dict(plan);given=unsigned.pop("scope_sha256",None)
    need(plan.get("schema_version")=="1.0" and plan.get("action")==ACTION
         and plan.get("previous_stage_c_sha")==STAGE_C
         and plan.get("production_lkg_sha")==LKG
         and plan.get("owner_consents")==1
         and plan.get("standing_authority") is False
         and plan.get("rollback_sha")==LKG
         and plan.get("owner_consents")==1
         and plan.get("standing_authority") is False
         and plan.get("later_stages_authorized") is False
         and plan.get("no_database_relocation") is True
         and plan.get("no_provider_mutation") is True
         and plan.get("breaker_revalidation_native_only") is True
         and plan.get("requires_genuine_canonical_full_proof") is True
         and tuple(plan.get("service_restarts",[]))==EXPORTERS
         and given==sha(canon(unsigned)),
         "HOST_RECOVERY_SCOPE_NOT_EXACT")
    exact_path(plan)
    return plan
@contextmanager
def locked_host():
    fds=[]
    try:
        for path in LOCKS:
            fd=os.open(path,os.O_RDWR|os.O_NOFOLLOW|os.O_CLOEXEC)
            fds.append(fd)
            s=os.fstat(fd)
            expected_uid=1000 if path==LOCKS[0] else 0
            expected_mode=0o664 if path==LOCKS[0] else 0o600
            need(stat.S_ISREG(s.st_mode) and s.st_nlink==1
                 and s.st_uid==expected_uid
                 and stat.S_IMODE(s.st_mode)==expected_mode,
                 "HOST_RECOVERY_LOCK_UNTRUSTED")
            try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError as e:
                raise HostRecoveryDenied("HOST_RECOVERY_LOCK_BUSY") from e
        yield
    finally:
        for fd in reversed(fds):os.close(fd)
def verify_owner(plan):
    p=json_doc(ARTIFACT/"root-oneowner-proof.json")
    need(p.get("action")==ACTION and
         p.get("source_sha")==plan["candidate_sha"] and
         p.get("scope_sha256")==plan["scope_sha256"] and
         p.get("plan_sha256")==sha(canon(plan)),
         "HOST_RECOVERY_OWNER_PROOF_NOT_EXACT")
    signer=trust_lib(SIGNER,SIGNER_SHA,"root_c_health_owner_signer")
    result=signer.verify_exact_owner_release(
        p["signed_release"],
        public_key=signer.read_pinned_root_owner_public_key(PUBLIC),
        at=datetime.now(timezone.utc),
        expected_candidate_sha=plan["candidate_sha"],
        expected_rollback_sha=plan["rollback_sha"],
        expected_release_id="release-"+plan["candidate_sha"][:16],
        expected_scope_sha256=plan["scope_sha256"],
        expected_manifest_sha256=sha(canon(plan)),
        expected_freeze_sha256=plan["freeze_sha256"])
    need(result["approval_id"]==p["approval_id"],
         "HOST_RECOVERY_OWNER_SIGNATURE_MISMATCH")
    return result
def preflight(path):
    plan=exact_plan(path)
    protected_ci=trust_lib(CI_PIN,CI_SHA,"root_host_ci")
    need(protected_ci.protected_main_ci_verified(
        plan["candidate_sha"],runner=as_al),
        "HOST_RECOVERY_PROTECTED_MAIN_CI_NOT_VERIFIED")
    previous_stage_c(plan);active_state(plan);root_source(plan)
    with locked_host():active_state(plan)
    return plan
def audit(plan,approval,event,detail):
    path=ROOT_STATE/("host-recovery-"+plan["candidate_sha"][:12]+".jsonl")
    record={"schema_version":"1.0","event":event,"candidate_sha":plan["candidate_sha"],
            "approval_id":approval,"scope_sha256":plan["scope_sha256"],
            "occurred_at":datetime.now(timezone.utc).isoformat(),
            "details":detail}
    rows=path.read_bytes().splitlines()
    prior="0"*64
    for idx,raw in enumerate(rows):
        item=json.loads(raw);actual=item.pop("hash")
        need(item.get("index")==idx and item.get("previous_sha256")==prior
             and sha(canon(item))==actual,
             "HOST_RECOVERY_AUDIT_CHAIN_BROKEN")
        prior=actual
    record["index"]=len(rows)
    record["previous_sha256"]=prior
    record["hash"]=sha(canon(record))
    with path.open("ab") as fp:
        fp.write(canon(record)+b"\n");fp.flush();os.fsync(fp.fileno())
def install_bytes(path,data):
    need(not path.exists() and not path.is_symlink(),
         "HOST_RECOVERY_INSTALL_COLLISION:"+path.name)
    path.parent.mkdir(parents=True,exist_ok=True)
    parent=path.parent.lstat()
    need(not path.parent.is_symlink() and stat.S_ISDIR(parent.st_mode)
         and parent.st_uid==0 and not stat.S_IMODE(parent.st_mode)&0o022,
         "HOST_RECOVERY_INSTALL_PARENT_UNTRUSTED:"+path.name)
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o444)
    try:
        with os.fdopen(fd,"wb") as out:
            out.write(data);out.flush();os.fsync(out.fileno())
        os.chown(path,0,0);os.chmod(path,0o444)
        need(path.read_bytes()==data,"HOST_RECOVERY_INSTALL_READBACK_CHANGED")
    finally:
        pass
def execute(path):
    plan=preflight(path)
    signed=verify_owner(plan)
    approval=signed["approval_id"]
    changed=[]
    full_started=False
    journal=ROOT_STATE/("host-recovery-"+plan["candidate_sha"][:12]+".jsonl")
    with locked_host():
        previous_stage_c(plan);active_state(plan);root_source(plan)
        need(not journal.exists(),"HOST_RECOVERY_ALREADY_CONSUMED")
        fd=os.open(journal,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        os.close(fd)
        audit(plan,approval,"begin",{"breaker_before":"open","no_database_relocation":True})
        try:
            # Root-owned adapter and seven *exact*, individually approved unit
            # dropins. Existing fragments and previous overrides are preserved.
            ADAPTER.parent.mkdir(mode=0o755,parents=True,exist_ok=False)
            os.chown(ADAPTER.parent,0,0)
            install_bytes(ADAPTER,(ARTIFACT/"src/tools/pmv4_c_authority_health_adapter.py").read_bytes())
            os.chmod(ADAPTER,0o555)
            changed.append(ADAPTER)
            for unit in (*UNITS,*EXPORTERS):
                name=HEALTH_DROPIN if unit in UNITS else DROPIN_NAME
                path=UNIT_ROOT/(unit+".d")/name
                install_bytes(path,(ARTIFACT/"dropins"/(unit+".conf")).read_bytes())
                changed.append(path)
            run("/usr/bin/systemctl","daemon-reload",timeout=45)
            audit(plan,approval,"reviewed_units_installed",{
                "exact_units":list((*UNITS,*EXPORTERS)),
                "adapter_sha256":plan["source_hashes"]["tools/pmv4_c_authority_health_adapter.py"]})
            for unit in EXPORTERS:
                run("/usr/bin/systemctl","restart",unit,timeout=50)
                need(run("/usr/bin/systemctl","is-active",unit).stdout.strip()=="active",
                     "HOST_RECOVERY_EXPORTER_RESTART_FAILED:"+unit)
            audit(plan,approval,"exporters_restarted",{"units":list(EXPORTERS)})
            # DO NOT report health PASS from pre-cutover full proof or from
            # fast checks. Start genuine full proof asynchronously via systemd.
            # Do NOT clear the failed fast-health state before actual fresh
            # full-integrity proof; otherwise drift could appear clean early.
            run("/usr/bin/systemctl","start","--no-block",UNITS[1],timeout=40)
            full_started=True
            audit(plan,approval,"full_proof_started_pending",{
                "canonical_orchestration_db":str(CANONICAL_ORCH),
                "integrity_bound_seconds":5400,"native_breaker_mutation":False})
        except BaseException:
            full_activity=run("/usr/bin/systemctl","is-active",UNITS[1],
                              timeout=10,check=False).stdout.strip()
            if full_started or full_activity in ("active","activating"):
                audit(plan,approval,"requires_review_full_proof_was_started",{
                    "never_rollback_live_full_proof":True,
                    "breaker_not_reset":True})
                raise
            audit(plan,approval,"installation_failed_rollback_attempt",{
                "changed":[str(x) for x in changed]})
            for installed in reversed(changed):
                if installed.exists():installed.unlink()
            if ADAPTER.parent.is_dir() and not any(ADAPTER.parent.iterdir()):
                ADAPTER.parent.rmdir()
            run("/usr/bin/systemctl","daemon-reload",timeout=45,check=False)
            for unit in EXPORTERS:
                run("/usr/bin/systemctl","try-restart",unit,timeout=45,check=False)
            audit(plan,approval,"pre_integrity_rollback_attempted",{
                "breaker_not_reset":True})
            raise
    print("HOST_RECOVERY_EXACT_INSTALL=VERIFIED")
    print("FULL_INTEGRITY=STARTED_NOT_YET_VERIFIED")
    print("PRODUCTION_BREAKER_RESET=false")
    print("INDEPENDENT_TICKET_WORKER_ACTIVATED=false")
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--plan",type=Path,required=True)
    modes=parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--preflight",action="store_true")
    modes.add_argument("--execute",action="store_true")
    args=parser.parse_args()
    try:
        if args.preflight:
            p=preflight(args.plan)
            print("HOST_RECOVERY_INDEPENDENT_ROOT_PREFLIGHT=PASS")
            print("EXACT_SCOPE_SHA256="+p["scope_sha256"])
            print("OWNER_APPROVAL_USED=false; PRODUCTION_MUTATIONS=false")
        else:execute(args.plan)
        return 0
    except BaseException as e:
        print("HOST_RECOVERY_ROOT_DENIED:"+type(e).__name__+":"+str(e)[:170],
              file=sys.stderr)
        return 2
if __name__=="__main__":raise SystemExit(main())
