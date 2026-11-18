#!/usr/bin/env python3
"""One-use PMv4 A1 existing-release OOM recovery: source-only builder.

Uses reviewed v4 root/Owner/launcher rendering, but pins 75f2 as the actual
prior accepted root release, never the original empty baseline. This module
never obtains authorization or touches production.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Callable

from tools import pmv4_a1_v4_immutable_builder as v4
from tools import pmv4_shadow_candidate_packet as packet
from tools.pmv4_shadow_ci import protected_main_ci_verified

PRIOR="75f2b4c0c48a15bd17d700b9f039fe56623e3f52"
PRIOR_APPROVAL="owner-mcp-a25d97e3e8564cf8920de4dd049c68bd"
PRIOR_IMAGE="sha256:679d3334efe7fbe32878b10fb06077912b57473bc3998316d26e9fd7a3d46bbd"
ACTION="pmv4-a1-one-owner-exact-existing-shadow-oom-recovery-v5"
CONFIRM="APPROVE-ONE-EXACT-PMV4-A1-V5-SHADOW-RECOVERY"
PRODUCTION_ROOT=Path("/var/lib/jason/pmv4-shadow")
PRIOR_PACKET=packet.ARTIFACT_PARENT/("pmv4-a1-"+PRIOR)
SOURCE_FILES=v4.FILES
PINNED_ROOT_V4_SHA="c6951fc2c8c0dcde82f6ece7a49586727f53f0b01b1d11ff33915770cf2b9bac"

class V5BuildDenied(PermissionError):pass

def need(ok:bool,code:str):
    if not ok:raise V5BuildDenied("A1_V5_"+code)

def replace_once(raw:str, old:str,new:str)->str:
    need(raw.count(old)==1,"ROOT_TEMPLATE_CHANGED")
    return raw.replace(old,new)

def replace_function(raw:str, start:str,end:str,new:str)->str:
    need(raw.count(start)==1 and raw.count(end)==1,"FUNCTION_TEMPLATE_CHANGED")
    lo=raw.index(start);hi=raw.index(end,lo)
    need(lo<hi,"FUNCTION_BOUNDARIES_CHANGED")
    return raw[:lo]+new.rstrip()+"\n\n\n"+raw[hi:]

PRIOR_BASELINE = '''
def empty_baseline()->None:
    """Root-only acceptance of the actual stopped prior release."""
    need(CURRENT.is_symlink() and os.readlink(CURRENT)=="releases/"+ROLLBACK,
         "A1_V5_CURRENT_PRIOR_POINTER_CHANGED")
    prior=ROOT/"releases"/ROLLBACK
    prior_archive=Path("/srv/jason/archive/engineering-artifacts/pmv4-a1-"+ROLLBACK)
    prev_m=read_json(prior_archive/"release"/"release-manifest.json")
    prev_s=read_json(prior_archive/"reviewed-scope.json")
    need(prev_m.get("candidate_sha")==ROLLBACK
         and prev_m.get("rollback_sha")=="0"*40
         and prev_m.get("image_digest")==PRIOR_IMAGE
         and prev_s.get("candidate_sha")==ROLLBACK
         and shadow.manifest_check(prev_m) is None,
         "A1_V5_PRIOR_RELEASE_MANIFEST_UNTRUSTED")
    need(prior.is_dir() and not prior.is_symlink()
         and prior.lstat().st_uid==0
         and stat.S_IMODE(prior.lstat().st_mode)==0o700
         and shadow.bundle_digest(prior/"bundle")==prev_m["bundle_sha256"]
         and read_json(prior/"release-manifest.json")==prev_m,
         "A1_V5_PRIOR_ROOT_BUNDLE_CHANGED")
    for path,expected in ((APPROVED,canon(prev_m)),(REVIEWED,canon(prev_s))):
        m=path.lstat()
        need(m.st_uid==0 and not path.is_symlink()
             and stat.S_ISREG(m.st_mode) and m.st_nlink==1
             and stat.S_IMODE(m.st_mode)==0o400
             and path.read_bytes()==expected,
             "A1_V5_PRIOR_PROTECTED_CONTROL_CHANGED")
    t=TOKEN.lstat()
    need(t.st_uid==0 and stat.S_ISREG(t.st_mode) and t.st_nlink==1
         and stat.S_IMODE(t.st_mode)==0o400 and not TOKEN.is_symlink()
         and 32<=t.st_size<=128,"A1_V5_PRIOR_TOKEN_NOT_PRESERVED")
    receipt=ROOT/"receipts"/("owner-"+PRIOR_APPROVAL+".json")
    r=read_json(receipt,maxsize=30000)
    need(receipt.lstat().st_uid==0 and stat.S_IMODE(receipt.lstat().st_mode)==0o600
         and r.get("state")=="accepted"
         and r.get("candidate_sha")==ROLLBACK
         and r.get("rollback_sha")=="0"*40
         and r.get("approval_id")==PRIOR_APPROVAL,
         "A1_V5_PRIOR_ROOT_ACCEPTANCE_MISSING")
    rows=v5_prior_root_audit()
    need(rows and rows[-1]["event"]=="committed",
         "A1_V5_PRIOR_ROOT_AUDIT_NOT_COMMITTED")
    proof=read_json(prior_archive/"root-oneowner-proof.json")
    need(proof.get("approval_id")==PRIOR_APPROVAL
         and proof.get("source_sha")==ROLLBACK
         and proof.get("action")=="pmv4-a1-one-owner-exact-disconnected-shadow-bootstrap-v4",
         "A1_V5_PRIOR_SIGNED_OWNER_EVIDENCE_CHANGED")
    receipts=list((ROOT/"receipts").iterdir())
    expected={
       "owner-owner-mcp-319c697027a146beac98818e5305a971.json",
       "owner-owner-mcp-5bb561044cd444908d06280377822a9d.json",
       "owner-"+PRIOR_APPROVAL+".json",
    }
    need(set(p.name for p in receipts)==expected
         and all(p.is_file() and not p.is_symlink()
                 and p.lstat().st_uid==0
                 and stat.S_IMODE(p.lstat().st_mode)==0o600
                 for p in receipts),
         "A1_V5_ROOT_HISTORICAL_RECEIPTS_CHANGED")
    need(not TARGET.exists() and not TARGET.is_symlink() and not AUDIT.exists(),
         "A1_V5_CANDIDATE_OR_AUDIT_ALREADY_EXISTS")
    adapter=verified_reviewed_module(
        "tools/pmv4_shadow_docker_adapter.py","adapter").DockerShadowAdapter(
             root=ROOT,core_continuity_probe=lambda:True,
             runner=exact_docker_29_compat_runner)
    old=adapter._owned_or_absent(expected_memory_bytes=2*1024**3)
    need(old is not None and old.get("Image")==PRIOR_IMAGE
         and old.get("State",{}).get("Running") is False
         and old.get("State",{}).get("OOMKilled") is True
         and old.get("State",{}).get("ExitCode")==137,
         "A1_V5_PRIOR_STOPPED_OOM_CONTAINER_CHANGED")
    for p in (ROOT,ROOT/"control",ROOT/"releases",ROOT/"receipts"):
        m=p.lstat()
        need(stat.S_ISDIR(m.st_mode) and m.st_uid==0 and not p.is_symlink()
             and not m.st_mode&0o022,"A1_V5_ROOT_PARENT_NOT_TRUSTED")


def v5_prior_root_audit()->list[dict]:
    path=ROOT/"control"/"a1-exact-atomic-bootstrap-v4-75f2b4c0c48a.jsonl"
    m=path.lstat()
    need(path.is_file() and not path.is_symlink()
         and m.st_uid==0 and m.st_nlink==1
         and stat.S_IMODE(m.st_mode)==0o600 and 0<m.st_size<200000,
         "A1_V5_PRIOR_AUDIT_NOT_ROOT_TRUSTED")
    prev="0"*64;rows=[]
    for line in path.read_bytes().splitlines():
        need(0<len(line)<20000,"A1_V5_PRIOR_AUDIT_ROW_OVERSIZE")
        d=json.loads(line)
        digest=d.pop("hash")
        need(d.get("index")==len(rows)
             and d.get("previous_sha256")==prev
             and d.get("source_sha")==ROLLBACK
             and d.get("approval_id")==PRIOR_APPROVAL
             and sha(canon(d))==digest,
             "A1_V5_PRIOR_AUDIT_HASH_CHANGED")
        prev=digest;rows.append(d)
    need(len(rows)>5 and rows[0]["event"]=="begin"
         and rows[-1]["event"]=="committed"
         and not any(x["event"]=="requires_review" for x in rows),
         "A1_V5_PRIOR_AUDIT_NOT_ACCEPTED")
    return rows
'''

STAGE_EXACT = '''
def stage_exact(plan:dict[str,Any],manifest:dict[str,Any],
                scope:dict[str,Any],approval_id:str)->None:
    """Stage one new release and replace only signed root control pointers."""
    def record_file(path:Path,raw:bytes)->None:
        append("intent-create-file",approval_id,
               {"path":str(path),"sha256":sha(raw),"mode":"0400"})
        write_exclusive(path,raw)
        append("created-file",approval_id,
               {"path":str(path),"sha256":sha(raw),
                "inode":path.lstat().st_ino,"mode":"0400"})
    append("intent-create-root",approval_id,
           {"path":str(TARGET),"mode":"0700"})
    owned_stage_directory(TARGET)
    owned_stage_directory(TARGET/"bundle")
    created=[TARGET,TARGET/"bundle"]
    for rel in FILES:
        cursor=TARGET/"bundle"
        for part in Path(rel).parts[:-1]:
            cursor=cursor/part
            if cursor not in created:
                owned_stage_directory(cursor)
                created.append(cursor)
        raw=(ARCHIVE/"release"/"bundle"/rel).read_bytes()
        need(sha(raw)==plan["source_files"][rel],
             "A1_V5_STAGED_SOURCE_CHANGED")
        record_file(TARGET/"bundle"/rel,raw)
    record_file(TARGET/"release-manifest.json",canon(manifest))
    prev=Path("/srv/jason/archive/engineering-artifacts/pmv4-a1-"+ROLLBACK)
    for path,old,new in (
      (REVIEWED,canon(read_json(prev/"reviewed-scope.json")),canon(scope)),
      (APPROVED,canon(read_json(prev/"release"/"release-manifest.json")),canon(manifest)),
    ):
        need(path.is_file() and path.lstat().st_uid==0
             and stat.S_IMODE(path.lstat().st_mode)==0o400
             and not path.is_symlink() and path.read_bytes()==old,
             "A1_V5_PRIOR_ROOT_CONTROL_CHANGED")
        tmp=ROOT/"control"/(".v5-"+CANDIDATE[:12]+"-"+path.name)
        append("intent-replace-root-control",approval_id,
               {"path":str(path),"old_sha256":sha(old),"new_sha256":sha(new)})
        write_exclusive(tmp,new)
        os.replace(tmp,path)
        dfd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(dfd)
        finally:os.close(dfd)
        need(path.read_bytes()==new and path.lstat().st_uid==0
             and stat.S_IMODE(path.lstat().st_mode)==0o400,
             "A1_V5_ROOT_CONTROL_READBACK_FAILED")
        append("replaced-root-control",approval_id,
               {"path":str(path),"old_sha256":sha(old),"new_sha256":sha(new)})
    append("root-stage-verified",approval_id,
           {"source_files":len(FILES),"bundle_sha256":plan["bundle_sha256"],
            "shadow_manifest_sha256":plan["shadow_manifest_sha256"],
            "source_tree":str(TARGET),"prior_release_preserved":ROLLBACK,
            "root_token_reused":True})
'''

ROOT_CONTROL_RECOVERY = '''
def restore_prior_root_control()->None:
    prev=Path("/srv/jason/archive/engineering-artifacts/pmv4-a1-"+ROLLBACK)
    current=read_json(prev/"release"/"release-manifest.json")
    scope=read_json(prev/"reviewed-scope.json")
    for path,old,new in (
       (APPROVED,canon(current),canon(read_json(ARCHIVE/"release"/"release-manifest.json"))),
       (REVIEWED,canon(scope),canon(read_json(ARCHIVE/"reviewed-scope.json"))),
    ):
        need(path.is_file() and not path.is_symlink()
             and path.lstat().st_uid==0 and
             stat.S_IMODE(path.lstat().st_mode)==0o400
             and path.read_bytes() in (old,new),
             "A1_V5_ROLLBACK_CONTROL_FOREIGN")
        if path.read_bytes()==new:
            tmp=ROOT/"control"/(".v5-restore-"+CANDIDATE[:12]+"-"+path.name)
            write_exclusive(tmp,old)
            os.replace(tmp,path)
        need(path.read_bytes()==old,"A1_V5_ROLLBACK_CONTROL_NOT_RESTORED")


def restore_prior_shadow_stopped(adapter,prior:Path)->None:
    """Restore old image/profile but never restart the previously OOM-stopped gateway."""
    need(prior.name==ROLLBACK,"A1_V5_ROLLBACK_RELEASE_NOT_EXACT")
    image=adapter._manifest_image(prior)
    need(image==PRIOR_IMAGE,"A1_V5_PRIOR_IMAGE_NOT_PINNED")
    compose=adapter._candidate_compose(prior)
    need(adapter._signed_memory_bytes(prior)==2*1024**3,
         "A1_V5_PRIOR_MEMORY_NOT_SIGNED")
    adapter._exec(["/usr/bin/docker","image","inspect",image])
    env={"PATH":"/usr/bin:/bin","PMV4_SHADOW_IMAGE_SHA":image,
         "PMV4_SHADOW_GATEWAY_TOKEN":adapter._token()}
    adapter._exec(
      ["/usr/bin/docker","compose","--project-name",docker_shadow.SHADOW_PROJECT,
       "-f",str(compose),"create","--force-recreate","--no-build","--pull","never",
       docker_shadow.SERVICE],
      env=env,
    )
    info=adapter._owned_or_absent(expected_memory_bytes=2*1024**3)
    need(info is not None and info.get("Image")==image
         and info.get("State",{}).get("Running") is False,
         "A1_V5_STOPPED_PRIOR_ROLLBACK_NOT_VERIFIED")
'''



RECOVER_EXISTING_APPROVAL = r'''
def recover_exact_consumed_v5()->None:
    """Restore ONLY the exact previously authorized incomplete v5 transaction."""
    root_script_trusted()
    plan,manifest,_=plan_and_source()
    rows=audit_rows()
    need(rows and rows[0].get("event")=="begin"
         and rows[-1].get("event") not in ("committed","rolled_back")
         and rows[0].get("source_sha")==CANDIDATE,
         "A1_V5_RECOVERY_NOT_INCOMPLETE_EXACT_OWNER")
    proof=read_json(OWNER_PROOF,maxsize=30000)
    approval=rows[0].get("approval_id")
    need(set(proof)=={
        "schema_version","action","source_sha","scope_sha256",
        "manifest_sha256","approval_id",
        "signed_root_release","signed_shadow_release"
    } and proof.get("schema_version")=="1.0"
         and proof.get("action")==ACTION
         and proof.get("source_sha")==CANDIDATE
         and proof.get("scope_sha256")==plan["scope_sha256"]
         and proof.get("manifest_sha256")==sha(canon(plan))
         and proof.get("approval_id")==approval,
         "A1_V5_RECOVERY_OWNER_SCOPE_DIFFERENT")
    moment=datetime.fromisoformat(rows[0]["occurred_at"])
    need(moment.tzinfo is not None,"A1_V5_RECOVERY_OWNER_TIME_INVALID")
    public=shadow.read_pinned_root_owner_public_key(
        ROOT_PIN,require_root_owned=True)
    common={
        "public_key":public,"at":moment,
        "expected_candidate_sha":CANDIDATE,
        "expected_rollback_sha":ROLLBACK,
        "expected_release_id":"release-"+CANDIDATE[:16],
        "expected_freeze_sha256":plan["shadow_freeze_sha256"],
    }
    parent=shadow.verify_exact_owner_release(
        proof["signed_root_release"],
        expected_scope_sha256=plan["scope_sha256"],
        expected_manifest_sha256=sha(canon(plan)),**common)
    child=shadow.verify_exact_owner_release(
        proof["signed_shadow_release"],
        expected_scope_sha256=manifest["scope_sha256"],
        expected_manifest_sha256=sha(canon(manifest)),**common)
    need(parent["approval_id"]==approval
         and child["approval_id"]==approval
         and parent["owner_oid"]==child["owner_oid"]
         and parent["owner_principal"]==child["owner_principal"],
         "A1_V5_RECOVERY_SIGNED_OWNER_MISMATCH")
    source_git_attestation(plan)
    watchdog_before=active_shadow_allowlist()
    host=protected_source_and_health()
    with host.host_release_transaction():
        need(active_shadow_allowlist()==watchdog_before
             and sha(GLOBAL_FREEZE.read_bytes())==FREEZE_SHA
             and sha(GLOBAL_HOLD.read_bytes())==HOLD_SHA,
             "A1_V5_RECOVERY_HOST_BOUNDARY_CHANGED")
        adapter,worker=controller(host)
        signed_native=ROOT/"receipts"/("owner-"+approval+".json")
        if (signed_native.exists()
            and read_json(signed_native).get("state")=="accepted"):
            raise A1RootDenied("A1_V5_NATIVE_ACCEPTED_REQUIRES_ROOT_REVIEW")
        need(CURRENT.is_symlink() and os.readlink(CURRENT) in
             ("releases/"+ROLLBACK,"releases/"+CANDIDATE),
             "A1_V5_RECOVERY_POINTER_FOREIGN")
        if os.readlink(CURRENT)=="releases/"+CANDIDATE:
            worker._switch(CURRENT,ROLLBACK)
        info=adapter._owned_or_absent()
        if (info is None or info.get("Image")!=PRIOR_IMAGE
            or info.get("HostConfig",{}).get("Memory")!=2*1024**3
            or info.get("State",{}).get("Running") is not False):
            restore_prior_shadow_stopped(adapter,ROOT/"releases"/ROLLBACK)
        restore_prior_root_control()
        native=worker._reconcile_pending_rollback_locked(
            rollback_acceptance=lambda prior:(
                prior.name==ROLLBACK
                and CURRENT.is_symlink()
                and os.readlink(CURRENT)=="releases/"+ROLLBACK
                and (adapter._owned_or_absent(expected_memory_bytes=2*1024**3)
                     or {}).get("State",{}).get("Running") is False
            )
        )
        need(native.get("status") in
             ("nothing_pending","shadow_rollback_verified"),
             "A1_V5_RECOVERY_NATIVE_RECEIPT_NOT_RECONCILED")
        cleanup_exact_unpromoted(approval)
        append("rolled_back",approval,{
            "prior_release":ROLLBACK,
            "root_prior_scope_restored":True,
            "prior_shadow_running":False,
            "reused_exact_historical_owner_approval":True,
        })
    print("PMV4_A1_V5_PREVIOUS_OWNER_EXACT_ROLLBACK=VERIFIED")
    print("NEW_OWNER_APPROVALS=0; PROTECTED_CORE_MCP_UNCHANGED=true")


'''



def render_root(source:str,sha:str,image:str)->str:
    """Create exact new root from protected source; never patch installed v4."""
    need(bool(v4.SHA.fullmatch(sha) and v4.IMAGE.fullmatch(image)),
         "SOURCE_OR_IMAGE_NOT_PINNED")
    text=v4.render_root(source,sha,image)
    text=replace_once(text,'ROLLBACK="0"*40','ROLLBACK="'+PRIOR+'"')
    text=replace_once(text,
        'ACTION="'+v4.NEW_ACTION+'"','ACTION="'+ACTION+'"')
    text=replace_once(text,
        "tools.pmv4_a1_v4_",
        "tools.pmv4_a1_v5_")
    text=replace_once(text,
        'AUDIT=ROOT/"control"/("a1-exact-atomic-bootstrap-v4-"+CANDIDATE[:12]+".jsonl")',
        'AUDIT=ROOT/"control"/("a1-exact-atomic-bootstrap-v5-"+CANDIDATE[:12]+".jsonl")')
    text=replace_once(text,
        'TRUSTED_SCRIPT=Path("/run/jason-pmv4-a1-v4-'+sha[:12]+'/installer.py")',
        'TRUSTED_SCRIPT=Path("/run/jason-pmv4-a1-v5-'+sha[:12]+'/installer.py")')
    text=replace_once(text,
        'and plan["gateway_secret_generation"]=="root_secure_random_48"',
        'and plan["gateway_secret_generation"]=="existing_protected_root_token_reused"')
    # Historical c999 rollback was to zero. The new current 75f2 rollback
    # must never be substituted into the historical audit's original facts.
    mark='def original_v3_rollback_audit()->None:'
    end='def preapproval_candidate_compose_pair(manifest:dict[str,Any])->None:'
    need(text.count(mark)==1 and text.count(end)==1,"PRIOR_AUDIT_TEMPLATE_CHANGED")
    a=text.index(mark);b=text.index(end,a)
    segment=text[a:b]
    need(segment.count('and r.get("rollback_sha")==ROLLBACK')==1,
         "PRIOR_AUDIT_ROLLBACK_ANCHOR_CHANGED")
    segment=segment.replace('and r.get("rollback_sha")==ROLLBACK',
                            'and r.get("rollback_sha")==("0"*40)')
    text=text[:a]+segment+text[b:]
    text=replace_function(text,"def empty_baseline()->None:",
                          "def preflight()->",PRIOR_BASELINE)
    text=replace_function(text,
                          "def stage_exact(plan:dict[str,Any],",
                          "def cleanup_exact_unpromoted",STAGE_EXACT)
    text=replace_once(text,
        '    need(not TARGET.exists() and not REVIEWED.exists()\n'
        '         and not APPROVED.exists() and not TOKEN.exists(),\n'
        '         "A1_ROLLBACK_NOT_EXACT_ORIGINAL_ABSENCE")',
        '    need(not TARGET.exists() and TOKEN.is_file()\n'
        '         and APPROVED.read_bytes()==canon(read_json(\n'
        '             Path("/srv/jason/archive/engineering-artifacts/pmv4-a1-"+ROLLBACK)\n'
        '             /"release"/"release-manifest.json"))\n'
        '         and REVIEWED.read_bytes()==canon(read_json(\n'
        '             Path("/srv/jason/archive/engineering-artifacts/pmv4-a1-"+ROLLBACK)\n'
        '             /"reviewed-scope.json")),\n'
        '         "A1_V5_PRIOR_CONTROL_OR_CANDIDATE_NOT_RESTORED")')
    text=replace_once(text,
        'def controller(host:guard_lib.IndependentHostGuard):',
        'PRIOR_APPROVAL="'+PRIOR_APPROVAL+'"\n'
        'PRIOR_IMAGE="'+PRIOR_IMAGE+'"\n\n'
        +ROOT_CONTROL_RECOVERY.rstrip()+'\n\n\n'
        +'def controller(host:guard_lib.IndependentHostGuard):')
    text=replace_once(text,
        '        restore_shadow=adapter.restore_shadow,',
        '        restore_shadow=lambda prior:restore_prior_shadow_stopped(adapter,prior),')
    text=replace_once(text,
        '"A1_ORIGINAL_ZERO_BASELINE_MOVED"',
        '"A1_V5_PRIOR_ROOT_POINTER_MOVED"')
    # The native controller has its own receipt. On a failed/new A1 release
    # the exact prior pointer and the old stopped shadow configuration must
    # both be restored before any root-created candidate files are removed.
    old='''                if promoted and CURRENT.is_symlink() and os.readlink(CURRENT)=="releases/"+CANDIDATE:
                    worker._switch(CURRENT,ROLLBACK)
                    adapter.restore_shadow(ROOT/"releases"/ROLLBACK)
                need(CURRENT.is_symlink()
                     and os.readlink(CURRENT)=="releases/"+ROLLBACK
                     and adapter._owned_or_absent() is None,
                     "A1_ROLLBACK_SHADOW_STILL_ACTIVE")
                cleanup_exact_unpromoted(approval)
                append("rolled_back",approval,{"root_exact_absence":True})'''
    new='''                if CURRENT.is_symlink() and os.readlink(CURRENT)=="releases/"+CANDIDATE:
                    worker._switch(CURRENT,ROLLBACK)
                need(CURRENT.is_symlink()
                     and os.readlink(CURRENT)=="releases/"+ROLLBACK,
                     "A1_V5_PRIOR_POINTER_NOT_RESTORED")
                info=adapter._owned_or_absent()
                if (info is None or info.get("Image")!=PRIOR_IMAGE
                    or info.get("HostConfig",{}).get("Memory")!=2*1024**3
                    or info.get("State",{}).get("Running") is not False):
                    restore_prior_shadow_stopped(adapter,ROOT/"releases"/ROLLBACK)
                restore_prior_root_control()
                cleanup_exact_unpromoted(approval)
                append("rolled_back",approval,
                       {"prior_release":ROLLBACK,
                        "root_prior_scope_restored":True,
                        "prior_shadow_running":False})'''
    new=new.replace(
        """                restore_prior_root_control()
                cleanup_exact_unpromoted(approval)""",
        """                restore_prior_root_control()
                recovery=worker._reconcile_pending_rollback_locked(
                    rollback_acceptance=lambda prior:(
                        prior.name==ROLLBACK
                        and (adapter._owned_or_absent(
                            expected_memory_bytes=2*1024**3) or {}
                            ).get("State",{}).get("Running") is False
                        and CURRENT.is_symlink()
                        and os.readlink(CURRENT)=="releases/"+ROLLBACK
                    )
                )
                need(recovery.get("status") in
                     ("nothing_pending","shadow_rollback_verified"),
                     "A1_V5_NATIVE_RECEIPT_NOT_RECONCILED")
                cleanup_exact_unpromoted(approval)""",
    )
    need("A1_V5_NATIVE_RECEIPT_NOT_RECONCILED" in new,
         "ROLLBACK_RECONCILIATION_MISSING")
    text=replace_once(text,old,new)
    # A native acceptance receipt must never be silently changed to a
    # rollback by a later root postflight error. Stop for exact review.
    text=replace_once(text,
        """                if CURRENT.is_symlink() and os.readlink(CURRENT)=="releases/"+CANDIDATE:
                    worker._switch(CURRENT,ROLLBACK)""",
        """                accepted_receipt=ROOT/"receipts"/("owner-"+approval+".json")
                if (accepted_receipt.exists()
                    and read_json(accepted_receipt).get("state")=="accepted"):
                    raise A1RootDenied("A1_V5_NATIVE_ACCEPTED_REQUIRES_ROOT_REVIEW")
                if CURRENT.is_symlink() and os.readlink(CURRENT)=="releases/"+CANDIDATE:
                    worker._switch(CURRENT,ROLLBACK)""",
    )
    text=replace_once(text,"def postflight()->None:",
                      RECOVER_EXISTING_APPROVAL+"def postflight()->None:")
    text=replace_once(text,
        '    mode.add_argument("--postflight",action="store_true")',
        '    mode.add_argument("--postflight",action="store_true")\n'
        '    mode.add_argument("--recover-existing-owner",action="store_true")')
    text=replace_once(text,
        '        elif args.execute: execute()\n        else: postflight()',
        '        elif args.execute: execute()\n'
        '        elif args.recover_existing_owner:recover_exact_consumed_v5()\n'
        '        else: postflight()')
    compile(text,"reviewed-a1-v5-root","exec")
    need('restore_shadow=lambda prior:restore_prior_shadow_stopped(adapter,prior)' in text,
         "STOPPED_ROLLBACK_CALLBACK_NOT_BOUND")
    need('and r.get("rollback_sha")==("0"*40)' in text,
         "HISTORICAL_RECEIPT_REWRITTEN")
    need('A1_V4_EXACT_TWO_ROLLED_BACK_RECEIPTS_REQUIRED' not in text,
         "EMPTY_BASELINE_GUARD_STILL_LIVE")
    need('def recover_exact_consumed_v5()->None:' in text
         and 'A1_V5_NATIVE_ACCEPTED_REQUIRES_ROOT_REVIEW' in text
         and 'elif args.recover_existing_owner:recover_exact_consumed_v5()' in text,
         "RELEASE_RECOVERY_NOT_VERIFIABLE")
    return text


def render_owner(source:str,sha:str)->str:
    text=v4.render_owner(source,sha)
    text=replace_once(text,
                      "tools.pmv4_a1_v4_verified_root",
                      "tools.pmv4_a1_v5_verified_root")
    text=replace_once(text,
                      'APPROVE-ONE-EXACT-PMV4-A1-V4-DISCONNECTED-SHADOW',
                      CONFIRM)
    text=replace_once(text,
        '"gateway_secret_generation":"root_secure_random_48"',
        '"gateway_secret_generation":"existing_protected_root_token_reused"')
    compile(text,"reviewed-a1-v5-owner","exec")
    return text


def render_local(source:str,sha:str,root_sha:str,owner_sha:str)->str:
    text=v4.render_local(source,sha,root_sha,owner_sha)
    text=replace_once(text,
                      '/run/jason-pmv4-a1-v4-'+sha[:12],
                      '/run/jason-pmv4-a1-v5-'+sha[:12])
    text=replace_once(text,
                      '/srv/jason/archive/engineering-worktrees/pmv4-a1-v4-main-'+sha[:12],
                      '/srv/jason/archive/engineering-worktrees/pmv4-a1-v5-main-'+sha[:12])
    test=subprocess.run(["/usr/bin/bash","-n"],input=text,
                        text=True,capture_output=True,timeout=12)
    need(test.returncode==0,"LOCAL_LAUNCHER_SYNTAX_INVALID")
    return text


def render_recovery_local(sha:str,root_hash:str)->str:
    need(bool(v4.SHA.fullmatch(sha)
              and re.fullmatch(r"[0-9a-f]{64}",root_hash)),
         "RECOVERY_LAUNCHER_NOT_PINNED")
    archive=str(packet.ARTIFACT_PARENT/("pmv4-a1-"+sha))
    stage="/run/jason-pmv4-a1-v5-"+sha[:12]
    script=f'''#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
[[ "$#" == 1 && "$1" == "--recover" ]] || exit 2
[[ "$(id -u)" == "1000" ]] || exit 2
ROOT="{archive}/tools/pmv4_a1_atomic_shadow_root.py"
PROOF="{archive}/root-oneowner-proof.json"
STAGE="{stage}"
ROOT_SHA="{root_hash}"
[[ -f "$PROOF" && ! -L "$PROOF" ]] ||
  {{ echo "A1_V5_RECOVERY=DENIED ORIGINAL_OWNER_PROOF_MISSING" >&2; exit 2; }}
printf '%s  %s\n' "$ROOT_SHA" "$ROOT" |
  /usr/bin/sha256sum --check --status
if [[ ! -e "$STAGE" && ! -L "$STAGE" ]]; then
    sudo /usr/bin/install -d -o root -g root -m 0700 "$STAGE"
    sudo /usr/bin/install -o root -g root -m 0400 "$ROOT" "$STAGE/installer.py"
fi
printf '%s  %s\n' "$ROOT_SHA" "$STAGE/installer.py" |
  sudo /usr/bin/sha256sum --check --status
sudo /usr/bin/python3 -I -B "$STAGE/installer.py" --recover-existing-owner
'''
    result=subprocess.run(["/usr/bin/bash","-n"],input=script,text=True,
                          capture_output=True,timeout=12)
    need(result.returncode==0,"RECOVERY_LAUNCHER_SYNTAX_INVALID")
    return script


def canonical(obj)->bytes:
    return json.dumps(obj,sort_keys=True,separators=(",",":"),
                      ensure_ascii=False,allow_nan=False).encode()

def build_plan(*,sha:str,image:str,root_hash:str,
               evidence:dict,manifest:dict,freeze_sha:str,hold_sha:str,
               shadow_freeze_sha:str,lkg:str,
               runtime_images:dict[str,str])->dict:
    need(bool(v4.SHA.fullmatch(sha)
              and v4.IMAGE.fullmatch(image)
              and re.fullmatch(r"[a-f0-9]{64}",root_hash)),
         "PLAN_SOURCE_IDENTITY_INVALID")
    need(evidence.get("source_sha")==sha
         and evidence.get("rollback_sha")==PRIOR
         and evidence.get("image_digest")==image
         and evidence.get("status")=="preproduction_candidate_not_authorized"
         and evidence.get("production_mutations") is False
         and evidence.get("shadow_activation_performed") is False
         and manifest.get("candidate_sha")==sha
         and manifest.get("rollback_sha")==PRIOR
         and manifest.get("image_digest")==image
         and manifest.get("bundle_sha256")==evidence.get("bundle_sha256")
         and evidence.get("manifest_sha256")==sha256(canonical(manifest)).hexdigest(),
         "RELEASE_MANIFEST_NOT_CURRENT_PRIOR")
    need(all(re.fullmatch(r"[a-f0-9]{64}",x) for x in
             (freeze_sha,hold_sha,shadow_freeze_sha))
         and bool(v4.SHA.fullmatch(lkg))
         and set(runtime_images)=={"jason-runtime","jason-mcp-pilot"}
         and all(v4.IMAGE.fullmatch(x) for x in runtime_images.values()),
         "ROOT_ATTESTATION_INPUT_INVALID")
    plan={
        "schema_version":"1.0","action":ACTION,
        "candidate_sha":sha,"rollback_sha":PRIOR,
        "root_executor_sha256":root_hash,
        "image_digest":image,"bundle_sha256":evidence["bundle_sha256"],
        "shadow_scope_sha256":manifest["scope_sha256"],
        "shadow_manifest_sha256":evidence["manifest_sha256"],
        "shadow_freeze_sha256":shadow_freeze_sha,
        "global_freeze_sha256":freeze_sha,
        "global_hold_sha256":hold_sha,
        "production_lkg_sha":lkg,
        "original_runtime_images":runtime_images,
        "gateway_secret_generation":"existing_protected_root_token_reused",
        "source_files":evidence["source_files"],
        "owner_consents":1,
        "standing_authority":False,
        "root_stage_before_owner_authorization":False,
    }
    plan["scope_sha256"]=sha256(canonical(plan)).hexdigest()
    return plan


def read_signed_host_baseline()->dict:
    def hash_file(p:Path)->str:
        need(p.is_file() and not p.is_symlink(),"BASELINE_FILE_UNAVAILABLE")
        return sha256(p.read_bytes()).hexdigest()
    images={}
    for name in ("jason-runtime","jason-mcp-pilot"):
        result=subprocess.run(["/usr/bin/docker","inspect",name,
                              "--format","{{.Image}}"],
                              capture_output=True,text=True,timeout=15,check=True)
        image=result.stdout.strip()
        need(bool(v4.IMAGE.fullmatch(image)),
             "PROTECTED_IMAGE_UNAVAILABLE")
        images[name]=image
    freeze=Path("/var/lib/jason/openclaw/release-manager/production-deployment-freeze")
    hold=Path("/var/lib/jason/openclaw/release-manager/auto-promotion-incident-hold")
    shadow_freeze=PRODUCTION_ROOT/"control"/"shadow-freeze.json"
    lkg=Path("/opt/jason/current").resolve(strict=True).name
    need(Path("/var/lib/jason/pmv4-shadow/current").is_symlink()
         and os.readlink("/var/lib/jason/pmv4-shadow/current")==
         "releases/"+PRIOR,"LIVE_PRIOR_RELEASE_POINTER_CHANGED")
    img=subprocess.run(["/usr/bin/docker","inspect",
                       "jason-pmv4-shadow-gateway","--format",
                       "{{.Image}}|{{.State.Status}}|{{.State.OOMKilled}}|{{.HostConfig.Memory}}"],
                       capture_output=True,text=True,timeout=15,check=True).stdout.strip()
    need(img==PRIOR_IMAGE+"|exited|true|2147483648",
         "LIVE_OOM_BASELINE_CHANGED")
    return {
        "freeze_sha":hash_file(freeze),
        "hold_sha":hash_file(hold),
        "shadow_freeze_sha":hash_file(shadow_freeze),
        "lkg":lkg,
        "runtime_images":images,
    }


def write_exclusive(path:Path, raw:bytes,mode:int=0o400):
    need(not path.exists() and not path.is_symlink() and len(raw)<100_000,
         "CANDIDATE_FILE_ALREADY_EXISTS")
    fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,mode)
    with os.fdopen(fd,"wb") as stream:
        stream.write(raw);stream.flush();os.fsync(stream.fileno())
    path.chmod(mode)
    need(sha256(path.read_bytes()).digest()==sha256(raw).digest(),
         "CANDIDATE_FILE_READBACK_MISMATCH")


def prepare(sha:str,image:str,*,repo:Path=v4.REPO,
            verify_main:Callable[[str],bool]=protected_main_ci_verified,
            baseline:dict|None=None)->dict:
    need(bool(v4.SHA.fullmatch(sha) and v4.IMAGE.fullmatch(image)),
         "SOURCE_OR_IMAGE_NOT_PINNED")
    need(verify_main(sha) is True,"PROTECTED_MAIN_CI_NOT_GREEN")
    archive=packet.ARTIFACT_PARENT/("pmv4-a1-"+sha)
    need(archive.is_dir() and not archive.is_symlink()
         and not (archive/"tools").exists()
         and not (archive/"root-oneowner-proof.json").exists()
         and not (archive/"root-release-plan.json").exists(),
         "PREPRODUCTION_PACKET_NOT_FRESH")
    evidence=json.loads((archive/"evidence.json").read_bytes())
    manifest=json.loads((archive/"release"/"release-manifest.json").read_bytes())
    hashes=evidence.get("source_files")
    need(isinstance(hashes,dict) and set(hashes)==set(packet.EXACT_SOURCE_FILES),
         "BUNDLE_SOURCE_FILE_HASHES_INVALID")
    for name in packet.EXACT_SOURCE_FILES:
        raw=(archive/"release"/"bundle"/name).read_bytes()
        expected=subprocess.run(["/usr/bin/git","-C",str(repo),"show",sha+":"+name],
                                capture_output=True,timeout=30,check=True).stdout
        need(raw==expected and sha256(raw).hexdigest()==hashes[name],
             "PREPRODUCTION_SOURCE_DIFFERENT_FROM_PROTECTED_MAIN")
    src=[v4.read_git(repo,sha,name) for name in SOURCE_FILES]
    root=render_root(src[0],sha,image)
    owner=render_owner(src[1],sha)
    local=render_local(src[2],sha,sha256(root.encode()).hexdigest(),
                       sha256(owner.encode()).hexdigest())
    recovery=render_recovery_local(sha,sha256(root.encode()).hexdigest())
    live=baseline if baseline is not None else read_signed_host_baseline()
    # The reviewed generic v4 root source still has these exact immutable
    # production preflight pins. Detect mismatch BEFORE making the new packet
    # available or asking the Owner for a device-code approval.
    need(live.get("freeze_sha")==
           "bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f"
         and live.get("hold_sha")==
           "11f0f78904236c36ebd1aeee58f52fcecba035bce33d15ce323b36d36ad5a5a0"
         and live.get("shadow_freeze_sha")==
           "c1e6aa23c48df9f87aa98c549086ad65a6fd38716e5a1a5cafd727fbd69fe928"
         and live.get("lkg")=="d1b8c196dadd4b672ec8ba47075f27bb61c98d63"
         and live.get("runtime_images")=={
           "jason-runtime":
             "sha256:c43f9f7364a4b2b16bdec261fa35db2b861eabe959ba818f689582bbb1b7d132",
           "jason-mcp-pilot":
             "sha256:b2f74bf1513568f6c9df7a2ffa764b1a5f43303c8317702741d646f223db1477",
         }, "PINNED_ROOT_LIVE_PROTECTED_BASELINE_CHANGED")
    plan=build_plan(sha=sha,image=image,
                    root_hash=sha256(root.encode()).hexdigest(),
                    evidence=evidence,manifest=manifest,**live)
    target=archive/"tools"
    target.mkdir(mode=0o700)
    try:
        write_exclusive(target/"pmv4_a1_atomic_shadow_root.py",root.encode())
        write_exclusive(target/"pmv4_a1_atomic_one_owner.py",owner.encode())
        write_exclusive(target/"pmv4_a1_one_owner_local.sh",local.encode())
        write_exclusive(target/"pmv4_a1_v5_recover_existing_owner.sh",recovery.encode())
        write_exclusive(archive/"root-release-plan.json",canonical(plan))
        report={
            "status":"source_only_pmv4_a1_v5_existing_rollback_release_ready",
            "source_sha":sha,"rollback_sha":PRIOR,
            "image_digest":image,"action":ACTION,
            "root_executor_sha256":sha256(root.encode()).hexdigest(),
            "owner_issuer_sha256":sha256(owner.encode()).hexdigest(),
            "local_sha256":sha256(local.encode()).hexdigest(),
            "recover_sha256":sha256(recovery.encode()).hexdigest(),
            "plan_sha256":sha256(canonical(plan)).hexdigest(),
            "scope_sha256":plan["scope_sha256"],
            "owner_approval_issued":False,
            "production_mutations":False,
            "mcp_restart":False,"ticket_core_restart":False,
            "provider_calls":False,
        }
        write_exclusive(archive/"v5-release-build-evidence.json",canonical(report))
        return report
    except BaseException:
        for f in target.iterdir():f.unlink()
        target.rmdir()
        for filename in ("root-release-plan.json","v5-release-build-evidence.json"):
            p=archive/filename
            if p.exists():p.unlink()
        raise


def main():
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument("--source-sha",required=True)
    parser.add_argument("--image-digest",required=True)
    a=parser.parse_args()
    try:
        print(json.dumps(prepare(a.source_sha,a.image_digest),sort_keys=True))
    except BaseException as e:
        print("A1_V5_BUILD_DENIED:"+type(e).__name__+":"+str(e)[:140])
        raise SystemExit(2)

if __name__=="__main__":main()
