#!/usr/bin/env python3
"""Exact first no-paid-AI containment profile over the accepted Docker release engine.

No new service, standing approval, provider authority, image promotion, or
database mutation. Source-only until protected CI and native Owner approval.
Both forward and recovery use the SAME immutable base image and compliant
configuration; the old paid-enabled container is never a rollback target.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
from hashlib import sha256
from http.client import HTTPException
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import subprocess
import sys
import time
import types

ACTION = "ENFORCE-EXACT-NO-PAID-AI-FIRST-TRANSITION"
ORDER = ("jason-runtime", "jason-mcp-pilot", "jason-pmv4-ticket-core")
LKG = "d1b8c196dadd4b672ec8ba47075f27bb61c98d63"
TICKET_REVISION = "13917410bb0ea1d5d37a314b3a3f131d416bf154"
TICKET_IMAGE = "sha256:a949be281262b94da02c7438f7a2cd97521d83749a8e27f0c01768b3d0353185"
MANAGER = Path("/var/lib/jason/openclaw/release-manager")
RECORDS = Path("/var/lib/jason-owner-release/no-paid-ai-first-transition")
TICKET = Path("/var/lib/jason/ticket-core/autonomy-operational-work.sqlite3")
DESIRED = Path("/etc/jason/release-readback-recovery/production-desired-state.json")
CONTROL_PINS = {
    MANAGER/"production-deployment-freeze": (1000, 0o600, "bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f"),
    MANAGER/"auto-promotion-incident-hold": (1000, 0o664, "11f0f78904236c36ebd1aeee58f52fcecba035bce33d15ce323b36d36ad5a5a0"),
}
TRUST = {
    "engine": (Path("/usr/local/lib/jason/audit-journal/trusted/tools/audit_journal_container_release.py"), "30d9617edffa3e7b17ca1ec50acacdaf02d0d7132dc8d85322208f9316cc0d3e"),
    "ci": (Path("/usr/local/lib/jason/pmv4-e-bootstrap/native/tools/pmv4_e_ci_refresh.py"), "f4d24dad7f69d0add18d7d852df1add7bc36981242c4725ee33b07f7583108d7"),
    "guard": (Path("/opt/jason/independent-component-release/trusted/tools/pmv4_host_release_guard.py"), "378239512b4da241adb027e7c88f5067c68388904b4b936eed10b3883e95dc22"),
}
DISPATCH_HASH = "6d276b67538e1bf988a751dc9ef10ac6996cc6955ff6bc3e562a506da13282f7"
MCP_PROJECTION_HASH = "14cf45ae64a913503e89f97fe508b348a6965c1a70cbeda52397f7eed7c9c235"
REPO = Path(__file__).resolve().parents[1]
SHA = re.compile(r"[0-9a-f]{40}\Z")
ID = re.compile(r"[0-9a-f]{64}\Z")
IMAGE = re.compile(r"sha256:[0-9a-f]{64}\Z")
SOURCE = "tools/no_paid_ai_first_transition.py"
GIT = ["/usr/sbin/runuser","-u","al","--","/usr/bin/env","-i",
       "PATH=/usr/bin:/bin","HOME=/home/al","GIT_CONFIG_NOSYSTEM=1",
       "GIT_CONFIG_GLOBAL=/dev/null","GIT_OPTIONAL_LOCKS=0","GIT_NO_REPLACE_OBJECTS=1",
       "/usr/bin/git","-c","core.fsmonitor=false","-c","core.hooksPath=/dev/null",
       "-C",str(REPO)]
# These are exact profile dependencies, not a generic caller-supplied module set.
SOURCE_FILES = (SOURCE, "tools/deploy_live_container.py",
                "tools/pmv4_mcp_projection.py","tools/pmv4_e_dispatch_install.py")


class TransitionDenied(PermissionError):
    pass


def need(ok, reason):
    if not ok:
        raise TransitionDenied("NO_PAID_FIRST_" + reason)


def canon(obj):
    # Exactly the existing native Owner authorization digest encoding.
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


def digest(obj):
    return sha256(canon(obj)).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def read_file(path, uid, mode=None, maximum=4_000_000):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as f:
        st = os.fstat(f.fileno())
        link = path.lstat()
        # The existing PMv3 incident hold is intentionally al:al 0664.
        # Its sole group-writable exception is exact path/owner/group/mode;
        # fixed_controls also verifies the immutable approved digest.
        legacy_hold = (path == MANAGER/"auto-promotion-incident-hold"
                       and uid == 1000 and mode == 0o664
                       and st.st_uid == st.st_gid == 1000
                       and stat.S_IMODE(st.st_mode) == 0o664)
        need(stat.S_ISREG(st.st_mode) and (st.st_dev,st.st_ino)==(link.st_dev,link.st_ino)
             and st.st_uid==uid and (uid!=0 or st.st_gid==0)
             and st.st_nlink==1 and (not st.st_mode&0o022 or legacy_hold)
             and (mode is None or stat.S_IMODE(st.st_mode)==mode)
             and 0<st.st_size<=maximum,"FILE_CUSTODY:"+path.name)
        raw=f.read(maximum+1)
        need(len(raw)==st.st_size,"FILE_CHANGED:"+path.name)
        return raw


def module(name, raw, path):
    m=types.ModuleType(name);m.__file__=str(path);m.__package__=name.rpartition(".")[0];sys.modules[name]=m
    exec(compile(raw,str(path),"exec"),m.__dict__)
    return m


def git(*args):
    return subprocess.check_output([*GIT,*args],timeout=45)


def sources(candidate, *, recovery=False):
    need(os.geteuid()==0 and sys.flags.isolated==1 and SHA.fullmatch(candidate) is not None,
         "ROOT_ISOLATED_EXACT_SOURCE_REQUIRED")
    need(git("rev-parse","HEAD").decode().strip()==candidate
         and not git("status","--porcelain","--untracked-files=all").strip()
         and git("remote","get-url","origin").decode().strip()=="https://github.com/al-teamaot-com/jason.git"
         and git("rev-parse","--is-shallow-repository").decode().strip()=="false",
         "CLEAN_REVIEWED_CHECKOUT_REQUIRED")
    data={}
    for name in SOURCE_FILES:
        raw=git("show",candidate+":"+name)
        need(raw==read_file(REPO/name,1000),"SOURCE_BYTES_CHANGED:"+name)
        data[name]=raw
    need(sha256(data["tools/pmv4_e_dispatch_install.py"]).hexdigest()==DISPATCH_HASH
         and sha256(data["tools/pmv4_mcp_projection.py"]).hexdigest()==MCP_PROJECTION_HASH,
         "PINNED_RELEASE_DEPENDENCY_CHANGED")
    # Root-installed CI helper and verifier enforce protected main and all
    # required checks. A branch test or an operator's assertion is not proof.
    loaded={}
    for name,(path,hash_) in TRUST.items():
        raw=read_file(path,0,0o444)
        need(sha256(raw).hexdigest()==hash_,"NATIVE_DEPENDENCY_CHANGED:"+name)
        loaded[name]=module("no_paid_native_"+name,raw,path)
    ci=loaded["ci"]
    ns=ci.load_pinned_attestor(ci.SOURCE,production=True)
    ci.paginate_required_checks(ns)
    evidence=ns["verify_ci"](candidate)
    head=evidence["protected_main"]
    need(evidence["candidate_sha"]==candidate and evidence["required_ci_passed"] is True
         and evidence["protected_main_ancestor"] is True
         and (recovery or head==candidate),"PROTECTED_CI_NOT_EXACT")
    if recovery and head!=candidate:
        for name in SOURCE_FILES:
            need(git("show",head+":"+name)==data[name],"RECOVERY_SOURCE_CHANGED:"+name)
    # No import from mutable working-directory paths as Root.
    pkg=types.ModuleType("tools");pkg.__path__=[];sys.modules["tools"]=pkg
    module("tools.pmv4_mcp_projection",data["tools/pmv4_mcp_projection.py"],REPO/"tools/pmv4_mcp_projection.py")
    loaded["policy"]=module("tools.deploy_live_container",data["tools/deploy_live_container.py"],REPO/"tools/deploy_live_container.py")
    loaded["owner"]=module("no_paid_native_owner",data["tools/pmv4_e_dispatch_install.py"],REPO/"tools/pmv4_e_dispatch_install.py")
    loaded["hashes"]={name:sha256(raw).hexdigest() for name,raw in data.items()}
    return loaded


def body_for(before, policy, engine):
    """Reuse exact original-config projection, never its unsafe restore method."""
    role=before.get("Name","").removeprefix("/")
    need(role in ORDER and ID.fullmatch(before.get("Id","")) is not None
         and IMAGE.fullmatch(before.get("Image","")) is not None,"EXACT_ROLE_IMAGE")
    h=before["HostConfig"]
    need(before["Config"].get("User")=="1000:1000"
         and h.get("Privileged") is False and not h.get("AutoRemove")
         and h.get("ReadonlyRootfs") is True
         and "ALL" in h.get("CapDrop",[])
         and "no-new-privileges:true" in h.get("SecurityOpt",[]),
         "CONTAINER_HARDENING")
    need(all(x["Type"]=="bind" for x in before["Mounts"])
         and not before["Config"].get("Volumes"),"NON_BIND_STATE_DENIED")
    need(all(not x.get("IPAMConfig") or not any(x["IPAMConfig"].get(k) for k in ("IPv4Address","IPv6Address"))
             for x in before["NetworkSettings"]["Networks"].values()),"STATIC_NETWORK_DENIED")
    after=policy.project_container(before)
    policy.validate_no_paid_container(after)
    body=engine.exact_original_configuration(after)
    need(body["Image"]==before["Image"],"IMAGE_CHANGED")
    need(body["HostConfig"]["Mounts"]==after["HostConfig"]["Mounts"],"HOST_MOUNTS_CHANGED")
    return body


def compliant(current, body, policy, engine):
    if current is None:
        return False
    try:
        policy.validate_no_paid_container(current)
        if not engine.configuration_matches(current,body):
            return False
        wanted=sorted(body["HostConfig"]["Mounts"],key=lambda x:x["Target"])
        actual=sorted(current["HostConfig"]["Mounts"],key=lambda x:x["Target"])
        if wanted!=actual:
            return False
        # The existing engine matches desired mounts but does not reject extras.
        # This profile additionally requires the entire effective mount set.
        return {m["Destination"]:(m["Type"],m["Source"],m["RW"]) for m in current["Mounts"]} == {
            m["Target"]:(m["Type"],m["Source"],not m.get("ReadOnly",False)) for m in wanted}
    except (KeyError,TypeError,ValueError,PermissionError):
        return False


def retired_name(role, original_id):
    need(role in ORDER and ID.fullmatch(original_id) is not None,"UNKNOWN_ROLE_OR_ID")
    return role+"-rollback-audit-no-paid-retired-"+original_id[:12]


def predecessor_evidence(current, role, row, body, policy, *, recovery):
    """Only the exact, recorded original can enter retirement.

    A crash may leave that ID renamed and with automatic restart disabled.
    Normalize ONLY those two pre-authorized retirement metadata changes.
    """
    from copy import deepcopy
    name=current["Name"].removeprefix("/")
    need(current["Id"]==row["original_id"] and current["Image"]==row["image_id"]
         and name in (role,retired_name(role,row["original_id"])),"PREDECESSOR_IDENTITY")
    normalized=deepcopy(current)
    if recovery:
        restart=current["HostConfig"]["RestartPolicy"]
        if name!=role:
            need(restart=={"Name":"no","MaximumRetryCount":0},"RETIRED_RESTART_NOT_DISABLED")
        need(restart in (body["HostConfig"]["RestartPolicy"],{"Name":"no","MaximumRetryCount":0}),
             "PREDECESSOR_RESTART_SCOPE_CHANGED")
        normalized["Name"]="/"+role
        normalized["HostConfig"]["RestartPolicy"]=body["HostConfig"]["RestartPolicy"]
    need(digest(policy.release_evidence(normalized))==row["baseline_sha256"]
         and digest(current["Config"])==row["original_config_sha256"]
         and set(current["NetworkSettings"]["Networks"])==set(body["NetworkingConfig"]["EndpointsConfig"]),
         "LIVE_PREDECESSOR_SCOPE_CHANGED")


def transition(engine, policy, contract, role, original_id, body, checkpoint):
    """Idempotent forward recovery. Never starts the predecessor."""
    need(role in ORDER and ID.fullmatch(original_id) is not None,"UNKNOWN_ROLE_OR_ID")
    # Validate BEFORE any stop/create/start, including recovery.
    wanted={"Config":{"Env":body["Env"]},"HostConfig":body["HostConfig"],
            "Mounts":[{"Destination":m["Target"],"Source":m["Source"],"Type":m["Type"],
                       "RW":not m.get("ReadOnly",False)} for m in body["HostConfig"]["Mounts"]]}
    policy.validate_no_paid_container(wanted)
    current=engine.lookup(role)
    old=engine.lookup(original_id)
    if old is not None:
        need(old["Image"]==body["Image"] and old["Id"]==original_id
             and old["Name"] in ("/"+role,"/"+retired_name(role,original_id))
             and (current is None or current["Id"]==original_id),"ORIGINAL_IDENTITY_CHANGED")
        checkpoint(role,"retiring_paid_predecessor")
        # Disable Docker restart and remove the canonical service name BEFORE
        # stopping. After a crash, neither Docker restart nor name-based
        # native recovery can start the stopped paid predecessor.
        if old["HostConfig"]["RestartPolicy"]!={"Name":"no","MaximumRetryCount":0}:
            engine.call("POST","/containers/"+original_id+"/update",
                        {"RestartPolicy":{"Name":"no","MaximumRetryCount":0}},timeout=30)
        old=engine.lookup(original_id,required=True)
        need(old["HostConfig"]["RestartPolicy"]=={"Name":"no","MaximumRetryCount":0},
             "PREDECESSOR_RESTART_DISABLED_UNVERIFIED")
        if old["Name"]=="/"+role:
            engine.call("POST","/containers/"+original_id+"/rename?name="+retired_name(role,original_id),timeout=30)
        old=engine.lookup(original_id,required=True)
        need(old["Name"]=="/"+retired_name(role,original_id)
             and engine.lookup(role) is None,"PREDECESSOR_QUARANTINE_UNVERIFIED")
        if old["State"]["Running"]:
            engine.call("POST","/containers/"+original_id+"/stop?t=30",timeout=60)
        old=engine.lookup(original_id,required=True)
        need(old["Id"]==original_id and not old["State"]["Running"]
             and old["HostConfig"]["RestartPolicy"]=={"Name":"no","MaximumRetryCount":0},
             "PREDECESSOR_STOP_UNVERIFIED")
        # Never delete a named volume or force-remove an active container.
        engine.call("DELETE","/containers/"+original_id+"?v=false&force=false",timeout=60)
        need(engine.lookup(original_id) is None and engine.lookup(role) is None,
             "PREDECESSOR_REMOVAL_UNVERIFIED")
        current=None
    if current is None:
        checkpoint(role,"creating_compliant_same_image")
        result=engine.call("POST","/containers/create?name="+role,body,timeout=90)
        current=engine.lookup(role,required=True)
        need(ID.fullmatch(result.get("Id","")) is not None and current["Id"]==result["Id"],
             "CREATED_ID_CHANGED")
    need(current["Id"]!=original_id and compliant(current,body,policy,contract),
         "SUCCESSOR_CONFIGURATION_UNVERIFIED")
    checkpoint(role,"compliant_configuration_verified")
    if not current["State"]["Running"]:
        engine.call("POST","/containers/"+current["Id"]+"/start",timeout=60)
    after=engine.lookup(role,required=True)
    need(after["Id"]==current["Id"] and after["Id"]!=original_id
         and after["State"]["Running"] is True and compliant(after,body,policy,contract),
         "SUCCESSOR_START_UNVERIFIED")
    checkpoint(role,"compliant_running")
    return after["Id"]


def run_transition(engine, policy, contract, role, row, body, checkpoint, health):
    # A lost response may be reconciled once by exact native readback. A health
    # failure is NOT permission to restart the retired paid-enabled container.
    try:
        cid=transition(engine,policy,contract,role,row["original_id"],body,checkpoint)
    except (OSError,HTTPException,TimeoutError):
        checkpoint(role,"reconciling_transport_once")
        cid=transition(engine,policy,contract,role,row["original_id"],body,checkpoint)
    health(role,body,cid)
    checkpoint(role,"healthy_compliant")
    return cid


def fixed_controls():
    out={}
    for path,(uid,mode,pin) in CONTROL_PINS.items():
        got=sha256(read_file(path,uid,mode)).hexdigest()
        need(got==pin,"FREEZE_OR_HOLD_CHANGED")
        out[str(path)]=got
    need(Path("/opt/jason/current").resolve(strict=True).name==LKG,"LKG_CHANGED")
    out[str(DESIRED)]=sha256(read_file(DESIRED,0,0o600)).hexdigest()
    return out


def protected_fresh():
    control=json.loads(read_file(MANAGER/"production-control-state.json",0,0o600))
    drift=json.loads(read_file(MANAGER/"production-drift.json",0,0o600))
    last=control["last_known_good"]["manifest"]
    breaker=control["circuit_breaker"]
    age=(datetime.now(timezone.utc)-datetime.fromisoformat(drift["observed_at"])).total_seconds()
    need(last.get("complete") is True and all(last.get(k)==LKG for k in ("revision","runtime_revision","mcp_revision","host_revision"))
         and breaker.get("state")=="closed" and breaker.get("revalidated_revision")==LKG
         and drift.get("status")=="pass" and drift.get("problems")==[] and 0<=age<=180,
         "NATIVE_HEALTH_OR_BREAKER")
    return {k:last[k] for k in ("revision","runtime_image_id","mcp_image_id")}


def recovery_gate(scope, engine):
    control=json.loads(read_file(MANAGER/"production-control-state.json",0,0o600))
    drift=json.loads(read_file(MANAGER/"production-drift.json",0,0o600))
    last=control["last_known_good"]["manifest"]
    breaker=control["circuit_breaker"]
    need(last.get("complete") is True and all(last.get(k)==v for k,v in scope["lkg"].items())
         and all(last.get(k)==LKG for k in ("runtime_revision","mcp_revision","host_revision")),
         "RECOVERY_LKG_CHANGED")
    if breaker.get("state")=="closed":
        need(breaker.get("revalidated_revision")==LKG and drift.get("status") in ("pass","drift_detected"),
             "RECOVERY_BREAKER_UNKNOWN")
    else:
        need(breaker.get("state")=="open" and breaker.get("reason")=="continuous_production_drift_detected"
             and drift.get("status")=="drift_detected" and bool(drift.get("problems")),
             "RECOVERY_BREAKER_NOT_TRANSITION_BOUND")
    allowed=[]
    for role,row in scope["components"].items():
        current=engine.lookup(role)
        old=engine.lookup(row["original_id"])
        if current is None or not current["State"]["Running"]:
            allowed.append({"kind":"required_container_not_running","container":role})
        if old is not None and old["Name"]=="/"+retired_name(role,row["original_id"]) and old["State"]["Running"]:
            allowed.append({"kind":"undeclared_running_container","container":retired_name(role,row["original_id"])})
    need(all(p in allowed for p in drift.get("problems",[])),"UNRELATED_RECOVERY_DRIFT")
    current=live_drift()
    need(current.get("status") in ("pass","drift_detected")
         and all(p in allowed for p in current.get("problems",[])),
         "UNRELATED_CURRENT_RECOVERY_DRIFT")
    return breaker["state"]


def live_drift():
    # The native evaluator's documented drift-detected exit status is 2.
    # Parse that real result during interrupted recovery, never treat arbitrary
    # process failures or inconsistent status/exit pairs as valid evidence.
    result=subprocess.run(["/usr/bin/python3","-I","-B",
        "/opt/jason/current/tools/production_drift_guard.py","--config",str(DESIRED)],
        capture_output=True,text=True,timeout=120,check=False)
    need(result.returncode in (0,2),"NATIVE_DRIFT_EXECUTION_FAILED")
    observed=json.loads(result.stdout)
    expected="pass" if result.returncode==0 else "drift_detected"
    need(isinstance(observed,dict) and observed.get("status")==expected
         and isinstance(observed.get("problems"),list)
         and (bool(observed["problems"])==(result.returncode==2)),
         "NATIVE_DRIFT_RESULT_INCONSISTENT")
    return observed


def native_docker(*args, timeout=30):
    return subprocess.check_output(["/usr/bin/docker",*args],timeout=timeout)


def peers():
    # Fixed policy names, with additional running services checked by native
    # drift. Ignore disposable CI builders, not production peers.
    names=("jason-pmv4-shadow-gateway","jason-teams-gateway","openbao",
           "jason-ollama","jason-autonomy-flight-recorder","jason-kfs-postgres",
           "jason-grafana","jason-prometheus","jason-node-exporter",
           "jason-work-item-exporter","openclaw-openclaw-gateway-1")
    result={}
    running=set(native_docker("ps","--format","{{.Names}}").decode().splitlines())
    for name in names:
        if name not in running:
            # An already stopped optional peer must stay stopped/absent.
            need(name=="jason-pmv4-shadow-gateway","REQUIRED_PEER_MISSING:"+name)
            result[name]=None
            continue
        d=json.loads(native_docker("inspect","--type","container",name))[0]
        need(d["Name"]=="/"+name and d["State"]["Running"] is True
             and (d["State"].get("Health") or {}).get("Status") in (None,"healthy"),
             "PEER_NOT_HEALTHY:"+name)
        result[name]={"id":d["Id"],"image":d["Image"],"started_at":d["State"]["StartedAt"]}
    return result


def ticket_identity():
    st=TICKET.lstat()
    need(stat.S_ISREG(st.st_mode) and not TICKET.is_symlink() and st.st_uid==1000
         and stat.S_IMODE(st.st_mode)==0o600 and st.st_nlink==1,"TICKET_LEDGER_CUSTODY")
    return [st.st_dev,st.st_ino]


def ticket_scan():
    with closing(sqlite3.connect(TICKET.as_uri()+"?mode=ro",uri=True,timeout=2)) as db:
        hb=db.execute("SELECT last_completed_at,state FROM autonomy_ticket_worker_heartbeat WHERE singleton_id=1").fetchone()
        last=db.execute("SELECT cycle_id,scanned_at,pages_traversed,provider_items,duplicate_items,evaluated FROM autonomy_ticket_scan_cycle ORDER BY scanned_at DESC LIMIT 1").fetchone()
    need(hb is not None and last is not None,"TICKET_SCAN_UNAVAILABLE")
    return hb,last


def await_idle():
    deadline=time.monotonic()+120
    while time.monotonic()<deadline:
        hb,last=ticket_scan()
        if hb[1] in ("idle","completed") and hb[0]==last[1]:
            return last[1]
        time.sleep(2)
    raise TransitionDenied("NO_PAID_FIRST_TICKET_WORKER_NOT_IDLE")


def await_scans(after):
    deadline=time.monotonic()+360
    while time.monotonic()<deadline:
        with closing(sqlite3.connect(TICKET.as_uri()+"?mode=ro",uri=True,timeout=2)) as db:
            rows=db.execute("SELECT cycle_id,scanned_at,pages_traversed,provider_items,duplicate_items,evaluated FROM autonomy_ticket_scan_cycle WHERE scanned_at>? ORDER BY scanned_at",(after,)).fetchall()
        good=[r for r in rows if r[2]>0 and r[3]>0 and r[4]==0 and r[5]>0]
        if len({r[0] for r in good})>=2:
            return [list(r) for r in good[:2]]
        time.sleep(5)
    raise TransitionDenied("NO_PAID_FIRST_TWO_REAL_TICKET_SCANS_PENDING")


def plan(candidate, libs, engine):
    controls=fixed_controls(); lkg=protected_fresh()
    libs["guard"].IndependentHostGuard().core_health_evidence()
    rows={}; bodies={}
    for role in ORDER:
        old=engine.lookup(role,required=True)
        need(old["State"]["Running"] is True,"PREDECESSOR_NOT_RUNNING:"+role)
        if role=="jason-runtime":
            need(old["Image"]==lkg["runtime_image_id"],"RUNTIME_LKG_IMAGE")
        if role=="jason-mcp-pilot":
            need(old["Image"]==lkg["mcp_image_id"],"MCP_LKG_IMAGE")
        if role==ORDER[-1]:
            need(old["Image"]==TICKET_IMAGE and libs["policy"].environment(old).get("JASON_SOURCE_REVISION")==TICKET_REVISION,
                 "TICKET_CORE_EXACT_ACCEPTED_IMAGE")
        body=body_for(old,libs["policy"],libs["engine"])
        evidence=libs["policy"].release_evidence(old)
        rows[role]={"original_id":old["Id"],"image_id":old["Image"],
                    "baseline_sha256":digest(evidence),
                    "original_config_sha256":digest(old["Config"]),
                    "configuration_sha256":digest(body),
                    "rollback_configuration_sha256":digest(body)}
        bodies[role]=body
    scope={"action":ACTION,"policy":{"candidate_sha":candidate,"rollback_sha":LKG},
           "installation_targets":list(ORDER)+[str(RECORDS/candidate)],
           "queue_cutover":False,"controls":controls,"lkg":lkg,
           "protected_peers":peers(),"ticket_identity":ticket_identity(),
           "source_sha256":libs["hashes"],"components":rows,
           "same_image_non_paid_recovery_only":True}
    return scope,bodies


def health_check(engine, policy, contract, role, body, cid):
    deadline=time.monotonic()+180
    while time.monotonic()<deadline:
        current=engine.lookup(role,required=True)
        need(current["Id"]==cid and compliant(current,body,policy,contract),
             "POST_START_CONFIGURATION_CHANGED")
        state=current["State"]
        if state["Running"] is True and (state.get("Health") or {}).get("Status") in (None,"healthy"):
            if role=="jason-mcp-pilot":
                script="import urllib.request; r=urllib.request.urlopen('http://127.0.0.1:8000/healthz',timeout=3); assert r.status==200"
                p=subprocess.run(["/usr/bin/docker","exec",role,"python","-B","-c",script],
                                 capture_output=True,timeout=10,check=False)
                if p.returncode!=0:
                    time.sleep(2);continue
            code = (
                "from jason_runtime.composition import RuntimeSettings; "
                "s=RuntimeSettings.from_env(); "
                "assert not s.hosted_semantics_enabled and not s.hosted_conversation_enabled; "
                "assert not s.openai_conversation_model and not s.openai_semantic_model; "
                "assert not s.openai_openbao_role_id_path.exists() and not s.openai_openbao_secret_id_path.exists(); "
                "print('NO_PAID_EFFECTIVE_SETTINGS_PASS')"
            )
            p=subprocess.run(["/usr/bin/docker","exec","--user","1000:1000",role,"python","-B","-c",code],
                             capture_output=True,text=True,timeout=30,check=False)
            need(p.returncode==0 and p.stdout.strip()=="NO_PAID_EFFECTIVE_SETTINGS_PASS",
                 "EFFECTIVE_PAID_ROUTE_UNVERIFIED:"+role)
            return
        time.sleep(2)
    raise TransitionDenied("NO_PAID_FIRST_COMPONENT_HEALTH_UNVERIFIED:"+role)


def execute(scope,bodies,libs,engine,record,*,recovery=False):
    owner=libs["owner"]
    def checkpoint(role,phase):
        name=str(time.time_ns())+"-"+role+"-"+phase+".json"
        owner.write(record/name,canon({"role":role,"phase":phase,"at":now()}),0o400)
        print(role+":"+phase,flush=True)
    need(fixed_controls()==scope["controls"] and peers()==scope["protected_peers"]
         and ticket_identity()==scope["ticket_identity"],"PROTECTED_SCOPE_CHANGED")
    if recovery:
        recovery_gate(scope,engine)
    for role in ORDER:
        row=scope["components"][role];body=bodies[role]
        need(digest(body)==row["configuration_sha256"]==row["rollback_configuration_sha256"]
             and body["Image"]==row["image_id"],"SAFE_RECREATION_SPEC_CHANGED")
        current=engine.lookup(role)
        old=engine.lookup(row["original_id"])
        if old is not None:
            predecessor_evidence(old,role,row,body,libs["policy"],recovery=recovery)
            need(current is None or current["Id"]==old["Id"],"FOREIGN_CANONICAL_CONTAINER")
        elif not recovery:
            need(False,"UNEXPECTED_PREDECESSOR_CHANGED")
        elif current is not None:
            need(compliant(current,body,libs["policy"],libs["engine"]),"RECOVERY_FOREIGN_CONFIGURATION")
    # Runtime and MCP are external ticket-worker clients; keep the actual
    # worker running until its separately bounded replacement.
    baseline=None
    for role in ORDER:
        if role==ORDER[-1]:
            current=engine.lookup(role)
            old=engine.lookup(scope["components"][role]["original_id"])
            if ((current is not None and current["State"]["Running"])
                    or (old is not None and old["State"]["Running"])):
                baseline=await_idle()
            else:
                baseline=ticket_scan()[1][1]
        run_transition(engine,libs["policy"],libs["engine"],role,scope["components"][role],
                       bodies[role],checkpoint,
                       lambda r,b,c:health_check(engine,libs["policy"],libs["engine"],r,b,c))
        need(fixed_controls()==scope["controls"] and peers()==scope["protected_peers"]
             and ticket_identity()==scope["ticket_identity"],"UNRELATED_STATE_CHANGED")
    scans=await_scans(baseline)
    for role in ORDER:
        current=engine.lookup(role,required=True)
        need(current["State"]["Running"] is True and compliant(current,bodies[role],libs["policy"],libs["engine"]),
             "FINAL_NO_PAID_CONFIGURATION_UNVERIFIED")
    need(fixed_controls()==scope["controls"] and peers()==scope["protected_peers"]
         and ticket_identity()==scope["ticket_identity"],"FINAL_PROTECTED_STATE_CHANGED")
    drift=live_drift()
    need(drift.get("status")=="pass" and drift.get("problems")==[],"FINAL_NATIVE_DRIFT_UNVERIFIED")
    breaker=json.loads(read_file(MANAGER/"production-control-state.json",0,0o600))["circuit_breaker"]
    accepted=breaker.get("state")=="closed" and breaker.get("revalidated_revision")==LKG
    status="configuration_and_operational_acceptance_verified" if accepted else "configuration_verified_pending_native_breaker_revalidation"
    owner.write(record/"result.json",canon({"status":status,
         "scope_sha256":digest(scope),"at":now(),"ticket_scans":scans,
         "native_drift":"pass","freeze_and_hold_unchanged":True,
         "paid_model_route_disabled":True,"source_images_unchanged":True,
         "provider_ai_probes":0,"production_authority_extended":False}),0o400)
    print("NO_PAID_FIRST_TRANSITION_VERIFIED" if accepted else
          "NO_PAID_FIRST_TRANSITION_PENDING_NATIVE_BREAKER_REVALIDATION",flush=True)


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument("--candidate",required=True)
    parser.add_argument("--scope-sha")
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight",action="store_true")
    mode.add_argument("--apply",action="store_true")
    mode.add_argument("--recover",action="store_true")
    args=parser.parse_args(argv)
    libs=sources(args.candidate,recovery=args.recover)
    owner=libs["owner"];engine=libs["engine"].DockerEngine()
    record=RECORDS/args.candidate
    if args.recover:
        owner.directory(RECORDS,0o700);owner.directory(record,0o700)
        receipt=json.loads(read_file(record/"authorization.json",0,0o400))
        packet=json.loads(read_file(record/"approved-safe-plan.json",0,0o400))
        scope=packet["scope"];bodies=packet["bodies"]
        need(not (record/"result.json").exists() and receipt.get("independently_verified_entra_owner") is True
             and receipt["scope_sha256"]==args.scope_sha==digest(scope)
             and receipt.get("action")==ACTION
             and scope["action"]==ACTION and scope["policy"]["candidate_sha"]==args.candidate
             and scope["source_sha256"]==libs["hashes"],"EXACT_RECOVERY_RECEIPT_REQUIRED")
        with owner.locks():
            execute(scope,bodies,libs,engine,record,recovery=True)
        return 0
    with owner.locks():
        scope,bodies=plan(args.candidate,libs,engine)
        need(not record.exists() and not record.is_symlink(),"RELEASE_ALREADY_CLAIMED")
    print(json.dumps({"status":"read_only_native_preflight","scope":scope,
                      "scope_sha256":digest(scope),"production_changes":False},sort_keys=True),flush=True)
    if args.preflight:
        return 0
    need(args.scope_sha==digest(scope),"EXACT_SCOPE_REQUIRED")
    actor=owner.owner(scope)
    with owner.locks():
        again,verified=plan(args.candidate,libs,engine)
        need(again==scope and verified==bodies,"SCOPE_CHANGED_AFTER_OWNER_DECISION")
        if not RECORDS.exists():
            RECORDS.mkdir(mode=0o700)
            owner.sync_dir(RECORDS.parent)
        owner.directory(RECORDS,0o700)
        record.mkdir(mode=0o700);owner.sync_dir(RECORDS)
        # The only durable recovery spec contains the safe configuration, never
        # an unsafe original. Root-only because unrelated env may be sensitive.
        owner.write(record/"approved-safe-plan.json",canon({"scope":scope,"bodies":bodies}),0o400)
        owner.write(record/"authorization.json",canon({"scope_sha256":digest(scope),
             "independently_verified_entra_owner":True,"owner":actor,
             "approved_at":now(),"action":ACTION}),0o400)
        execute(scope,bodies,libs,engine,record)
    return 0


if __name__=="__main__":
    try:
        raise SystemExit(main())
    except (PermissionError,OSError,ValueError,KeyError,TimeoutError,subprocess.SubprocessError) as exc:
        # Never emit Docker request bodies, environments, or credentials.
        print("NO_PAID_FIRST_TRANSITION_NOT_ACCEPTED:"+type(exc).__name__+
              (":"+str(exc) if isinstance(exc,TransitionDenied) else ""),file=sys.stderr)
        raise SystemExit(1)
