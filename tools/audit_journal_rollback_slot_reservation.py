"""One explicit archived retirement, only if native rollback reservation needs it.

No historical authorization is replayed. The caller binds the native inventory,
exact immutable container identities and this optional action into the new Owner
scope before invoking apply(). All other stopped containers, images and mounts
remain untouched. Private inspect data is retained only in Root-only storage.
"""
from __future__ import annotations
import hashlib,json,os,re,stat,subprocess,tarfile
from pathlib import Path
from tools import audit_journal_install_transaction as tx

NAME="jason-runtime-rollback-20261111T145735Z"
ID="084338ebfe9f7bf28c5b128adca4bc5bb570830a26fd47d2d970520803dec2ec"
SIBLING="jason-runtime-rollback-20261111T153442Z"
SIBLING_ID="d5f488f344e1ac5642fd2b2005c2965a509b480b5068be838bc9c16d5f7e5f41"
IMAGE="sha256:66606ecec03a094ac9de2dc794a6c063698f2e6e6d088e890fabbb479e0b18d7"
REVISION="c43e88e072c0b35c5b342d5e712fe34565b3e0cd"
MAX_TAR=536870912
ARCHIVE_RESERVE=1073741824
DOCKER="/usr/bin/docker"

def need(ok,reason):
    if not ok:raise PermissionError("AUDIT_ROLLBACK_SLOT_"+reason)

def digest(obj):
    return tx.digest(obj if isinstance(obj,bytes) else tx.canonical(obj))

def inventory(I,prefixes):
    need(isinstance(prefixes,list) and prefixes and len(prefixes)==len(set(prefixes))
         and all(isinstance(p,str) and re.fullmatch(r"jason-[A-Za-z0-9_.-]+-rollback-[A-Za-z0-9_.-]*",p)
                 for p in prefixes),"NATIVE_PREFIX_POLICY")
    names=I.command([DOCKER,"ps","-a","--filter","status=exited","--format","{{.Names}}"]).splitlines()
    need(len(names)==len(set(names)) and all(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*",n)
         for n in names),"MALFORMED_STOPPED_CONTAINER_INVENTORY")
    return sorted(n for n in names if any(n.startswith(p) for p in prefixes))

def _inspect(I,identifier,name):
    rows=json.loads(I.command([DOCKER,"inspect","--type","container","--size",identifier]))
    need(isinstance(rows,list) and len(rows)==1,"EXACT_CONTAINER_INSPECTION")
    row=rows[0];state=row.get("State",{})
    need(row.get("Id")==identifier and row.get("Name")=="/"+name and row.get("Image")==IMAGE
         and state.get("Status")=="exited" and state.get("Running") is False and state.get("Pid")==0
         and row.get("Config",{}).get("Labels",{}).get("com.teamaot.jason.source_revision")==REVISION
         and row.get("HostConfig",{}).get("AutoRemove") is False
         and isinstance(row.get("Mounts"),list)
         and all(m.get("Type")=="bind" for m in row["Mounts"])
         and type(row.get("SizeRootFs")) is int and 0<row["SizeRootFs"]<MAX_TAR
         and type(row.get("SizeRw")) is int and 0<=row["SizeRw"]<MAX_TAR,
         "HISTORIC_CONTAINER_IDENTITY_OR_MOUNT_CHANGED")
    return row

def retained_sibling(I):
    row=_inspect(I,SIBLING_ID,SIBLING)
    need(I.command([DOCKER,"image","inspect","--format","{{.Id}}",IMAGE])==IMAGE,
         "HISTORIC_IMAGE_NOT_PRESENT")
    return row

def descriptor(I):
    row=_inspect(I,ID,NAME)
    retained_sibling(I)
    return {"name":NAME,"id":ID,"image":IMAGE,"source_revision":REVISION,
            "retained_same_image_sibling":SIBLING,"retained_sibling_id":SIBLING_ID,
            "container_metadata_sha256":digest(row),"writable_bytes":row["SizeRw"],
            "rootfs_bytes":row["SizeRootFs"],"maximum_archive_bytes":MAX_TAR,
            "image_removal_allowed":False,"volume_removal_allowed":False,
            "archive_restore_preserves_metadata_and_rootfs_not_container_id":True}

def archive_path(s,candidate):
    need(re.fullmatch(r"[0-9a-f]{40}",candidate) is not None,"EXACT_CANDIDATE")
    return s.ARCHIVE/"governed-audit"/"retired-rollback-containers"/candidate

def _private_dir(path,*,create=False):
    if create and not os.path.lexists(path):
        path.mkdir(mode=0o700);tx.sync(path.parent)
    m=path.lstat()
    need(not path.is_symlink() and stat.S_ISDIR(m.st_mode) and m.st_uid==m.st_gid==0
         and stat.S_IMODE(m.st_mode)==0o700,"ROOT_ARCHIVE_DIRECTORY")

def check_archive_destination(s,candidate,*,resuming=False):
    """Inspect custody before the human challenge, without making directories."""
    directory=archive_path(s,candidate)
    base=directory.parent.parent
    m=base.lstat()
    need(not base.is_symlink() and stat.S_ISDIR(m.st_mode) and m.st_uid==0
         and not m.st_mode&0o022,"ROOT_ARCHIVE_PARENT")
    if os.path.lexists(directory.parent):_private_dir(directory.parent)
    if os.path.lexists(directory):
        need(resuming,"NEW_RETIREMENT_ARCHIVE_ALREADY_PRESENT")
        _private_dir(directory)


def _archive_dirs(s,candidate,*,create=False):
    directory=archive_path(s,candidate)
    base=directory.parent.parent
    m=base.lstat()
    need(not base.is_symlink() and stat.S_ISDIR(m.st_mode) and m.st_uid==0
         and not m.st_mode&0o022,"ROOT_ARCHIVE_PARENT")
    _private_dir(directory.parent,create=create)
    _private_dir(directory,create=create)
    return directory

def _tar_proof(path):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,"rb") as stream:
        m=os.fstat(stream.fileno())
        need(stat.S_ISREG(m.st_mode) and m.st_uid==m.st_gid==0 and m.st_nlink==1
             and stat.S_IMODE(m.st_mode)==0o400 and 0<m.st_size<=MAX_TAR,"ARCHIVE_FILE_CUSTODY")
        h=hashlib.sha256()
        for chunk in iter(lambda:stream.read(1024*1024),b""):h.update(chunk)
        stream.seek(0)
        count=0
        with tarfile.open(fileobj=stream,mode="r|*") as archive:
            for entry in archive:
                count+=1
                if entry.isfile():
                    source=archive.extractfile(entry)
                    need(source is not None,"ARCHIVE_MEMBER_UNREADABLE")
                    for _ in iter(lambda:source.read(1024*1024),b""):pass
        need(count>0,"ARCHIVE_EMPTY")
        return {"sha256":h.hexdigest(),"bytes":m.st_size,"members":count}

def _all_containers(I):
    rows=I.command([DOCKER,"ps","-a","--no-trunc","--format","{{.ID}}|{{.Names}}"]).splitlines()
    pairs=[line.split("|",1) for line in rows]
    need(all(len(p)==2 and re.fullmatch(r"[0-9a-f]{64}",p[0])
         and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*",p[1]) for p in pairs)
         and len({p[0] for p in pairs})==len(pairs)
         and len({p[1] for p in pairs})==len(pairs),"AMBIGUOUS_ALL_CONTAINER_INVENTORY")
    return dict(pairs)

def _archive_proof(I,s,candidate,ledger,scope_sha,planned):
    directory=_archive_dirs(s,candidate)
    proof=json.loads(tx.raw_file(ledger/"retirement-archive.json",0o400))
    need(proof.get("scope_sha256")==scope_sha and proof.get("candidate_sha")==candidate
         and proof.get("retirement")==planned and proof.get("archive_path")==str(directory),
         "ARCHIVE_RECEIPT_BINDING")
    metadata=tx.raw_file(directory/"container-inspect.json",0o400)
    need(digest(json.loads(metadata))==planned["container_metadata_sha256"]
         and digest(metadata)==proof.get("metadata_sha256"),"ARCHIVE_METADATA_CHANGED")
    need(_tar_proof(directory/"rootfs.tar")==proof.get("rootfs"),"ARCHIVE_CONTENT_CHANGED")
    retained_sibling(I)
    return proof

def verified_absence(I,s,candidate,ledger,scope_sha,planned):
    """For one approved continuation after an interrupted remove/readback."""
    rows=_all_containers(I)
    need(ID not in rows and NAME not in rows.values(),"RETIRED_CONTAINER_STILL_PRESENT")
    return _archive_proof(I,s,candidate,ledger,scope_sha,planned)

def plan_capacity(I,s,eng,desired,*,approved=None,retirement_verified=False):
    need(type(desired.get("max_stopped_rollback_containers")) is int
         and desired["max_stopped_rollback_containers"]==27
         and s.ROLLBACK_LIMIT_BEFORE==21 and s.ROLLBACK_CONTAINER_RESERVE==6,
         "CURRENT_PROTECTED_ROLLBACK_LIMITS_CHANGED")
    prefixes=desired.get("rollback_container_prefixes")
    stopped=inventory(I,prefixes)
    need(all(any((role+"-rollback-audit-before-"+"a"*12).startswith(p) for p in prefixes)
             for role in eng.ROLES),"REVIEWED_ROLLBACK_ROLES_NOT_COUNTED")
    if approved is not None and retirement_verified:
        need(approved.get("retirement") is not None
             and stopped==approved.get("after_stopped_names")
             and approved.get("native_policy_sha256")==digest(desired),
             "POST_RETIREMENT_INVENTORY_CHANGED")
        return approved
    need(len(stopped)<=22,"INSUFFICIENT_RECOVERY_CONTAINER_SLOTS")
    retiring=None
    if len(stopped)==22:
        need(NAME in stopped and SIBLING in stopped,"EXACT_HISTORICAL_RETIREMENT_NOT_AVAILABLE")
        retiring=descriptor(I)
    after=[n for n in stopped if retiring is None or n!=NAME]
    need(len(after)<=21 and len(after)+6<=27,"INSUFFICIENT_RECOVERY_CONTAINER_SLOTS")
    result={"count":len(stopped),"stopped_names":stopped,"after_stopped_names":after,
            "limit_before":21,"reserve_for_new_release":6,"new_release_slots_after":len(after)+6,
            "native_policy_sha256":digest(desired),"native_prefixes":prefixes,"retirement":retiring}
    need(approved is None or result==approved,"APPROVED_RETENTION_PLAN_CHANGED")
    return result

def apply(I,s,candidate,ledger,scope_sha,slots):
    """After authenticated scope only. Archive/readback precedes exact non-force removal."""
    need(os.geteuid()==0,"ROOT_REQUIRED")
    planned=slots.get("retirement")
    if planned is None:
        need(inventory(I,slots["native_prefixes"])==slots["after_stopped_names"],
             "CAPACITY_CHANGED_BEFORE_QUEUE")
        return
    rows=_all_containers(I)
    if ID in rows:
        need(rows[ID]==NAME and descriptor(I)==planned
             and inventory(I,slots["native_prefixes"])==slots["stopped_names"],
             "RETIREMENT_TARGET_OR_INVENTORY_CHANGED")
        directory=_archive_dirs(s,candidate,create=True)
        archive_receipt=ledger/"retirement-archive.json"
        if not archive_receipt.exists():
            row=_inspect(I,ID,NAME)
            metadata=tx.canonical(row)
            need(digest(row)==planned["container_metadata_sha256"],"RETIREMENT_METADATA_CHANGED")
            tx.atomic(directory/"container-inspect.json",metadata,0o400)
            temp=directory/".rootfs.tar.incomplete"
            if os.path.lexists(temp):
                m=temp.lstat()
                need(not temp.is_symlink() and stat.S_ISREG(m.st_mode)
                     and m.st_uid==m.st_gid==0 and m.st_nlink==1 and
                     stat.S_IMODE(m.st_mode) in (0o400,0o600),"ARCHIVE_PARTIAL_CUSTODY")
                temp.unlink();tx.sync(directory)
            # The daemon reads the stopped container. No image/volume deletion,
            # no provider operation, and no archive is extracted on this host.
            fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
            with os.fdopen(fd,"wb") as stream:
                result=subprocess.run(["/usr/bin/prlimit","--fsize="+str(MAX_TAR)+":"+str(MAX_TAR),"--",DOCKER,"export",ID],stdout=stream,
                    stderr=subprocess.DEVNULL,timeout=240,check=False)
                need(result.returncode==0,"HISTORICAL_ROOTFS_EXPORT_FAILED")
                stream.flush();os.fsync(stream.fileno());os.fchmod(stream.fileno(),0o400)
            proof=_tar_proof(temp)
            need(descriptor(I)==planned,"HISTORICAL_CONTAINER_CHANGED_DURING_EXPORT")
            os.replace(temp,directory/"rootfs.tar");tx.sync(directory)
            tx.atomic(archive_receipt,tx.canonical({"schema_version":"1.0",
                "candidate_sha":candidate,"scope_sha256":scope_sha,"retirement":planned,
                "archive_path":str(directory),"metadata_sha256":digest(metadata),"rootfs":proof}),0o400)
        _archive_proof(I,s,candidate,ledger,scope_sha,planned)
        # Re-read the exact stopped identity immediately before the only removal.
        need(descriptor(I)==planned,"RETIREMENT_CHANGED_BEFORE_REMOVE")
        I.command([DOCKER,"rm",ID])  # no force, no -v, no image prune
    else:
        need(NAME not in rows.values(),"RETIREMENT_NAME_REUSED")
    _archive_proof(I,s,candidate,ledger,scope_sha,planned)
    rows=_all_containers(I)
    need(ID not in rows and NAME not in rows.values(),"EXACT_RETIREMENT_NOT_VERIFIED")
    need(inventory(I,slots["native_prefixes"])==slots["after_stopped_names"],
         "POST_RETIREMENT_INVENTORY_CHANGED")
    result=ledger/"retirement-result.json"
    expected={"schema_version":"1.0","scope_sha256":scope_sha,"candidate_sha":candidate,
              "status":"retired_and_archive_verified","retired_id":ID,
              "archive_receipt_sha256":digest(tx.raw_file(ledger/"retirement-archive.json",0o400))}
    if result.exists():
        need(json.loads(tx.raw_file(result,0o400))==expected,"RETIREMENT_RESULT_CHANGED")
    else:tx.atomic(result,tx.canonical(expected),0o400)
    print("EXACT_HISTORICAL_ROLLBACK_ARCHIVED_AND_RETIRED=PASS",flush=True)
