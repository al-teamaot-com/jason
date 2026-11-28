"""Reusable exact-scope archive action for the existing native release entrypoint.

Policy is supplied by protected versioned configuration. The requested capacity
comes from the existing reviewed coordinated release offer, never a shell command
or caller-selected container. Use the existing Entra verifier, native release
locks, source attestation, readback and root-private receipt custody. This
operation is maintenance, not approval or promotion of the application release.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tarfile

INSTALL = Path("/usr/local/lib/jason/scoped-backport")
LEDGER = Path("/var/lib/jason-owner-release/rollback-retention")
ARCHIVE_MOUNT = Path("/srv/jason/archive")
ARCHIVE = ARCHIVE_MOUNT / "governed-audit/retired-rollback-containers"
DESIRED = Path("/etc/jason/release-readback-recovery/production-desired-state.json")
NORMAL = Path("/etc/jason-owner-release/normal-release-policy")
MANAGER = Path("/var/lib/jason/openclaw/release-manager")
AUDIT = Path("/var/lib/jason-audit-journal")
DOCKER = "/usr/bin/docker"
ACTION = "ARCHIVE-EXACT-HISTORICAL-ROLLBACK-CAPACITY"
CONFIG = "config/operations/rollback-retention-v1.json"
RESERVATION_CONFIG = "config/operations/rollback-capacity-reservation-v1.json"
RESERVATION_ACTION = "RESERVE-EXACT-ROLLBACK-CAPACITY"
RESERVATION_LEDGER = Path("/var/lib/jason-owner-release") / "rollback-capacity-reservations"
BINDING = Path("/etc/jason-owner-release/scoped-backport-coordinated-installed.json")
BINDING_ACTION = "RECONCILE-EXACT-ROLLBACK-CAPACITY-BINDING"
BINDING_LEDGER = Path("/var/lib/jason-owner-release") / "rollback-capacity-bindings"
OWNER_RECORDS = Path("/var/lib/jason-owner-release")
REFERENCE_ROOTS = (
    MANAGER/"records", MANAGER/"protected-readback",
    Path("/var/lib/jason-scoped-backport/transactions"),
    Path("/var/lib/jason-scoped-backport/coordinated/transactions"),
    Path("/var/lib/jason-scoped-backport/coordinated/offers"),
    Path("/var/lib/jason-catalog-scoped-promotion/transactions"),
    Path("/var/lib/jason/independent-component-release/releases"),
    OWNER_RECORDS, AUDIT/"private", AUDIT/"control",
)
HEX = re.compile(r"[0-9a-f]{64}\Z")
SHA = re.compile(r"[0-9a-f]{40}\Z")


def need(ok, reason):
    if not ok:
        raise PermissionError("ROLLBACK_RETENTION_NATIVE_" + reason)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def now():
    return datetime.now(timezone.utc)


def read(path, *, private=False, maximum=16_000_000):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        m = os.fstat(stream.fileno())
        need(stat.S_ISREG(m.st_mode) and m.st_nlink == 1 and 0 < m.st_size <= maximum,
             "RECORD_CUSTODY")
        if private:
            need(m.st_uid == m.st_gid == 0 and stat.S_IMODE(m.st_mode) == 0o400,
                 "PRIVATE_RECORD_CUSTODY")
        raw = stream.read(maximum + 1)
        after = os.fstat(stream.fileno())
        need(len(raw) == m.st_size and (m.st_size,m.st_mtime_ns) ==
             (after.st_size,after.st_mtime_ns), "RECORD_CHANGED")
    return raw


def private_directory(path, native, *, create=False):
    if create and not os.path.lexists(path):
        path.mkdir(mode=0o700)
        native["sync_dir"](path.parent)
    m = path.lstat()
    need(not path.is_symlink() and stat.S_ISDIR(m.st_mode) and
         m.st_uid == m.st_gid == 0 and stat.S_IMODE(m.st_mode) == 0o700,
         "PRIVATE_DIRECTORY_CUSTODY")


def immutable_record(native, path, value):
    raw = canonical(value)
    if os.path.lexists(path):
        need(read(path, private=True) == raw, "EXISTING_RECORD_CHANGED")
    else:
        native["write"](path, raw, 0o400)


def all_stopped(command, prefixes):
    need(isinstance(prefixes, list) and prefixes and len(prefixes) == len(set(prefixes))
         and all(isinstance(x,str) and re.fullmatch(r"jason-[A-Za-z0-9_.-]+-rollback-[A-Za-z0-9_.-]*",x)
                 for x in prefixes), "NATIVE_PREFIX_POLICY")
    lines = command([DOCKER,"ps","-a","--filter","status=exited","--format","{{.Names}}"]).decode().splitlines()
    need(len(lines)==len(set(lines)) and all(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*",x)
                                           for x in lines),"STOPPED_INVENTORY")
    names=sorted(x for x in lines if x.startswith(tuple(prefixes)))
    rows = json.loads(command([DOCKER,"inspect","--type","container","--size",*names])) if names else []
    need(sorted(r["Name"][1:] for r in rows)==names and
         len({r["Id"] for r in rows})==len(names) and
         all(HEX.fullmatch(r["Id"]) for r in rows),"EXACT_INVENTORY")
    return names, {r["Name"][1:]:r for r in rows}


def scan_references(planner, targets, *, roots=REFERENCE_ROOTS, historical_audit_accepted=False,
                    current_record=None):
    """Bounded native record scan; no raw provider/credential data is emitted."""
    blocked=set()
    for root in roots:
        if not root.exists():
            continue
        need(not root.is_symlink() and root.is_dir(),"REFERENCE_ROOT_CUSTODY")
        for directory,dirs,files in os.walk(root,followlinks=False):
            # The current exact approval is independently verified by the
            # caller; it is not an unrelated recovery dependency.
            if current_record is not None and Path(directory)==current_record:
                dirs[:]=[]
                continue
            # Immutable source copies are not execution ledgers. Secret/key
            # custody is a separate authority store; it has no container IDs.
            dirs[:]=[x for x in dirs if x not in ("source","trusted","native","secrets","keys","__pycache__")]
            need(not any((Path(directory)/x).is_symlink() for x in dirs),"REFERENCE_DIRECTORY_SYMLINK")
            for name in files:
                if not name.endswith(".json") or any(x in name.lower() for x in ("credential","secret","private-key","token")):
                    continue
                path=Path(directory)/name
                raw=read(path)
                possible=[d for d in targets if any(x.encode() in raw for x in (d["name"],d["id"],d["id"][:12]))]
                if not possible:
                    continue
                value=json.loads(raw)
                # Preserve all prior retirement and retained-sibling
                # identities. Only terminal, root-custodied prior inventory
                # snapshots are non-operative historical references.
                if (path.is_relative_to(LEDGER) and path.name=="approval.json"
                        and (path.parent/"result.json").is_file()):
                    approved=json.loads(read(path,private=True))
                    result=json.loads(read(path.parent/"result.json",private=True))
                    need(approved["scope_sha256"]==digest(approved["scope"])
                         and result["scope_sha256"]==approved["scope_sha256"]
                         and result["status"]=="historical_rollback_capacity_verified"
                         and approved["scope"]["action"]==ACTION,"HISTORICAL_RETENTION_RECEIPT")
                    value=json.loads(canonical(approved))
                    for key in ("before_names","after_names","before_ids"):
                        value["scope"]["plan"].pop(key)
                allowed=historical_audit_accepted and (
                    path.is_relative_to(AUDIT/"private") or
                    (path.is_relative_to(OWNER_RECORDS) and path.relative_to(OWNER_RECORDS).parts[0].startswith("audit-journal")))
                for d in possible:
                    if planner["unexpected_references"](value,d,allow_historical_inventory=allowed):
                        blocked.add(d["id"])
    # A checked-in plan describes a future action, never authority to remove
    # a rollback identity that any other live or historical receipt requires.
    return blocked


def tar_proof(path, maximum):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,"rb") as stream:
        m=os.fstat(stream.fileno())
        need(stat.S_ISREG(m.st_mode) and m.st_nlink==1 and m.st_uid==m.st_gid==0
             and stat.S_IMODE(m.st_mode)==0o400 and 0<m.st_size<=maximum,"ARCHIVE_CUSTODY")
        h=hashlib.sha256()
        for chunk in iter(lambda:stream.read(1024*1024),b""):
            h.update(chunk)
        stream.seek(0)
        count=0
        with tarfile.open(fileobj=stream,mode="r|*") as archive:
            for entry in archive:
                count+=1
                if entry.isfile():
                    member=archive.extractfile(entry)
                    need(member is not None,"ARCHIVE_MEMBER")
                    for _ in iter(lambda:member.read(1024*1024),b""):
                        pass
        need(count>0 and os.fstat(stream.fileno()).st_size==m.st_size,"ARCHIVE_EMPTY_OR_CHANGED")
        return {"sha256":h.hexdigest(),"bytes":m.st_size,"members":count}


def archive_proof(native, planner, directory, scope_sha, retirement, maximum):
    private_directory(directory,native)
    proof=json.loads(read(directory/"archive.json",private=True))
    metadata=read(directory/"container-inspect.json",private=True)
    need(proof=={"schema_version":"1.0","scope_sha256":scope_sha,
                 "retirement":retirement,"metadata_sha256":digest(metadata),
                 "rootfs":tar_proof(directory/"rootfs.tar",maximum)}
         and digest(json.loads(metadata))==retirement["target"]["metadata_sha256"],
         "ARCHIVE_RECEIPT_BINDING")
    return proof


def archive_exact(native, planner, directory, scope_sha, retirement, row, maximum):
    private_directory(directory,native,create=True)
    raw=canonical(planner["normalize_inspect"](row))
    need(digest(json.loads(raw))==retirement["target"]["metadata_sha256"],
         "APPROVED_METADATA_CHANGED")
    metadata=directory/"container-inspect.json"
    immutable_record(native,metadata,json.loads(raw))
    final=directory/"rootfs.tar"
    receipt=directory/"archive.json"
    if not os.path.lexists(receipt):
        temp=directory/".rootfs.tar.incomplete"
        if os.path.lexists(final) and os.path.lexists(temp):
            a,b=final.lstat(),temp.lstat()
            need(not final.is_symlink() and not temp.is_symlink()
                 and stat.S_ISREG(a.st_mode) and (a.st_dev,a.st_ino)==(b.st_dev,b.st_ino)
                 and a.st_nlink==2 and a.st_uid==a.st_gid==0
                 and stat.S_IMODE(a.st_mode)==0o400,"ARCHIVE_INTERRUPTED_LINK_CUSTODY")
            temp.unlink()
            native["sync_dir"](directory)
        if not os.path.lexists(final):
            temp=directory/".rootfs.tar.incomplete"
            if os.path.lexists(temp):
                m=temp.lstat()
                need(stat.S_ISREG(m.st_mode) and not temp.is_symlink() and m.st_nlink==1
                     and m.st_uid==m.st_gid==0 and stat.S_IMODE(m.st_mode) in (0o400,0o600),
                     "ARCHIVE_PARTIAL_CUSTODY")
                temp.unlink()
                native["sync_dir"](directory)
            fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
            with os.fdopen(fd,"wb") as stream:
                # Exact stopped container only; no mounted data/volume/image
                # removal. Export is capped and private, never extracted.
                r=subprocess.run(["/usr/bin/prlimit","--fsize="+str(maximum)+":"+str(maximum),"--",
                                  DOCKER,"export",retirement["target"]["id"]],
                                 stdout=stream,stderr=subprocess.DEVNULL,timeout=240,check=False)
                need(r.returncode==0,"EXPORT_FAILED")
                stream.flush()
                os.fchmod(stream.fileno(),0o400)
                os.fsync(stream.fileno())
            tar_proof(temp,maximum)
            os.link(temp,final,follow_symlinks=False)
            temp.unlink()
            native["sync_dir"](directory)
        proof={"schema_version":"1.0","scope_sha256":scope_sha,
               "retirement":retirement,"metadata_sha256":digest(raw),
               "rootfs":tar_proof(final,maximum)}
        immutable_record(native,receipt,proof)
    return archive_proof(native,planner,directory,scope_sha,retirement,maximum)


def verify_inventory(plan, names, rows, planner, policy):
    """No new target selection after approval; recognize only exact absences."""
    retired={r["target"]["name"]:r for r in plan["retirements"]}
    need(set(plan["after_names"])<=set(names)<=set(plan["before_names"]),"INVENTORY_CHANGED")
    need(all(plan["before_ids"].get(n)==rows[n]["Id"] for n in names),"CONTAINER_ID_CHANGED")
    for retirement in plan["retirements"]:
        for d in retirement["retained_siblings"]+[retirement["target"]]:
            if d["name"] not in names and d["name"] in retired:
                continue
            need(d["name"] in rows and planner["descriptor"](rows[d["name"]],now=now(),policy=policy)==d,
                 "APPROVED_CONTAINER_METADATA_CHANGED")
    return sorted(set(plan["before_names"])-set(names))


def retire_archived_exact(native, command, planner, policy, record, directory,
                          scope_sha, plan, retirement, current_source, healthy):
    """The only removal port: sealed exact archive + current approved identity."""
    d=retirement["target"]
    maximum=policy["maximum_archive_bytes_per_container"]
    approval=json.loads(read(record/"approval.json",private=True))
    need(approval["scope_sha256"]==scope_sha==digest(approval["scope"])
         and approval["scope"]["plan"]==plan and approval["scope"]["action"]==ACTION
         and retirement in plan["retirements"]
         and approval["owner_oid"]=="bee80bdc-ffb0-4c50-b453-c09d4d411f5f"
         and 0<=(now()-datetime.fromisoformat(approval["approved_at"])).total_seconds()<=28800,
         "REMOVAL_EXACT_APPROVAL_REQUIRED")
    proof=archive_proof(native,planner,directory,scope_sha,retirement,maximum)
    names,rows=all_stopped(command,plan["prefixes"])
    missing=verify_inventory(plan,names,rows,planner,policy)
    if d["name"] not in missing:
        current_source()
        need(audit_accepted() and healthy(),"PRE_REMOVAL_NATIVE_HEALTH")
        need(not scan_references(planner,[d],historical_audit_accepted=True,
                                 current_record=record),"REFERENCE_SCOPE_CHANGED")
        need(command([DOCKER,"image","inspect","--format","{{.Id}}",d["image"]]).decode().strip()
             ==d["image"],"RETAINED_IMAGE_CHANGED")
        # Re-read the actual inventory and target/siblings immediately
        # before the only non-force removal; a running, renamed, changed
        # or replaced target must never be selected by name.
        names,rows=all_stopped(command,plan["prefixes"])
        missing=verify_inventory(plan,names,rows,planner,policy)
        need(d["name"] not in missing,"TARGET_CHANGED_BEFORE_REMOVAL")
        command([DOCKER,"rm",d["id"]])
    all_names=command([DOCKER,"ps","-a","--no-trunc","--format","{{.ID}}|{{.Names}}"]).decode().splitlines()
    need(all(re.fullmatch(r"[0-9a-f]{64}\|[A-Za-z0-9][A-Za-z0-9_.-]*",line)
             for line in all_names),"ALL_CONTAINER_INVENTORY")
    need(not any(line.startswith(d["id"]+"|") or line.endswith("|"+d["name"])
                 for line in all_names),"RETIREMENT_NOT_VERIFIED")
    immutable_record(native,record/(d["id"]+".json"),{"scope_sha256":scope_sha,
          "retirement":retirement,"archive_receipt_sha256":digest(proof),"status":"archived_and_retired"})


def audit_accepted():
    def control(name):
        path=AUDIT/"control"/name
        m=path.lstat()
        need(not path.is_symlink() and m.st_uid==m.st_gid==0 and
             stat.S_IMODE(m.st_mode)==0o444,"AUDIT_CONTROL_CUSTODY")
        return json.loads(read(path))
    forward=control("forward-release-status.json")
    maintenance=control("maintenance-status.json")
    age=(now()-datetime.fromisoformat(maintenance["observed_at"])).total_seconds()
    return (forward.get("status")=="accepted" and forward.get("no_legacy_rebuild") is True
            and maintenance.get("status")=="scheduled_no_restore_verified"
            and maintenance.get("no_legacy_rebuild") is True and 0<=age<=1200)


def archive_destination(native, count, maximum, policy):
    need(ARCHIVE_MOUNT.is_mount() and ARCHIVE_MOUNT.stat().st_dev!=Path("/").stat().st_dev,
         "ARCHIVE_MOUNT")
    parent=ARCHIVE.parent.lstat()
    need(not ARCHIVE.parent.is_symlink() and stat.S_ISDIR(parent.st_mode) and parent.st_uid==0
         and not parent.st_mode&0o022,"ARCHIVE_PARENT_CUSTODY")
    private_directory(ARCHIVE,native)
    space=os.statvfs(ARCHIVE)
    need(space.f_bavail*space.f_frsize>=count*maximum+policy["minimum_archive_free_bytes_after_reservation"],
         "ARCHIVE_CAPACITY")


def completed_active_offer(host_module, release_id):
    """Capture a terminal prior offer without removing its pointer or audit."""
    offer = host_module.active_staged_offer()
    if offer is None:
        return None
    manifest = offer["manifest"]
    prior_id = manifest["release_id"]
    need(prior_id != release_id and re.fullmatch(r"release-[0-9a-f]{16}", prior_id),
         "ACTIVE_OFFER_EXISTS")
    path = host_module.PRIVATE / "transactions" / (prior_id + ".json")
    need(path.is_file() and not path.is_symlink(), "ACTIVE_OFFER_UNRESOLVED")
    journal = host_module.root_json(path)
    need(journal.get("release_id") == prior_id
         and journal.get("manifest_sha256") == digest(manifest)
         and journal.get("scope_sha256") == manifest["scope_sha256"]
         and journal.get("outcome") in ("production_components_verified", "rollback_verified",
                                        "failed_before_mutation"),
         "ACTIVE_OFFER_UNRESOLVED")
    return {"release_id": prior_id, "offer_sha256": digest(offer),
            "journal_sha256": digest(journal), "outcome": journal["outcome"]}


def state(host, manifest, p, n, pending):
    host.freshly_validate_live_scope(manifest)
    host.deny_unresolved_attempt(manifest)
    need(host.guard.host_mutation_quiescent(),"NATIVE_BREAKER_OR_DRIFT")
    # Reuse the original independent legacy/catalog pending checks.
    class Adapter:
        pass
    adapter=Adapter()
    adapter.p=p
    pending(adapter)
    need(audit_accepted(),"AUDIT_FORWARD_MAINTENANCE_NOT_VERIFIED")
    desired_raw=p["read"](DESIRED,0,0o600)
    desired=json.loads(desired_raw)
    need(type(desired["max_stopped_rollback_containers"]) is int,"NATIVE_LIMIT")
    control=json.loads(p["read"](n["ROOT_CONTROL"],0,0o600))
    baseline=control["last_known_good"]["manifest"]
    need(baseline["complete"] is True, "HOST_ROLLBACK_ANCHOR")
    previous = host.previous_readback
    if previous is None:
        need(baseline["host_revision"] == manifest["rollback_sha"], "HOST_ROLLBACK_ANCHOR")
    else:
        # The retained host LKG and the rollback image of the first target
        # are distinct in a coordinated component release.
        from tools import scoped_backport_component_readback as readback
        readback.verify_legacy_anchor(previous, baseline)
    hold=p["read"](n["HOLD"],1000,0o664)
    need(digest(hold)==n["HOLD_HASH"],"INCIDENT_HOLD_CHANGED")
    config=p["read"](NORMAL/"deployment.json",0,0o644)
    need(json.loads(config)=={"schema_version":"1.0","production_freeze":False},"FREEZE_POLICY")
    preserved={"desired_policy_sha256":digest(desired_raw),"hold_sha256":digest(hold),
               "deployment_config_sha256":digest(config),"release_policy_sha256":manifest["release_policy_sha256"],
               "components":host.original_components,"protected":host.snapshot_protected(),
               "target_configuration":host.original_configs,"host_anchor":baseline["host_revision"]}
    return desired,preserved


def run_action(args, n, p, code, planner, pending, verify_source, wait_fresh, *,
               replace_policy=None, cleanup_policy=None, replace_binding=None, cleanup_binding=None,
               recover_native=None, reporter_pins=None):
    need(os.geteuid()==0 and sys.flags.isolated==1,"ROOT_ISOLATED_REQUIRED")
    need(SHA.fullmatch(args.candidate) and re.fullmatch(r"release-[0-9a-f]{16}",args.release_id or ""),
         "EXACT_RELEASE_ID")
    policy=planner["validate_policy"](json.loads(code[CONFIG]))
    source_hashes={name:digest(raw) for name,raw in code.items()}
    # Only the existing installed root-owned coordinator supplies the actual
    # release offer, trusted source admission and live Docker identities.
    meta=INSTALL.lstat()
    need(not INSTALL.is_symlink() and meta.st_uid==meta.st_gid==0 and not meta.st_mode&0o022,
         "INSTALLED_COORDINATOR_CUSTODY")
    sys.path.insert(0,str(INSTALL))
    from tools import scoped_backport_coordinated_root as entry
    from tools import scoped_backport_coordinated_host as host_module
    manifest,profile,review_sha=entry.exact_public_offer(args.release_id)
    if getattr(args,"reconcile_capacity_binding",False):
        need(replace_binding is not None and cleanup_binding is not None,"NATIVE_BINDING_REPLACEMENT_PORT")
        return reconcile_binding(args,n,p,code,planner,pending,verify_source,wait_fresh,
                                 host_module,manifest,profile,review_sha,replace_binding,cleanup_binding,
                                 recover_native=recover_native,reporter_pins=reporter_pins)
    if getattr(args,"reserve_capacity",False) and args.resume:
        restore_interrupted_pair(args,n,p,code,planner,pending,verify_source,wait_fresh,
            host_module,manifest,profile,review_sha,replace_policy,cleanup_policy,replace_binding,cleanup_binding)
    host=host_module.CoordinatedHost()
    host.bind_for_stage(manifest,profile,review_sha)
    if getattr(args, "assess_capacity", False):
        need(not (args.apply or args.resume or args.scope_sha),"CAPACITY_ASSESSMENT_READ_ONLY")
        wait_fresh()
        with host.release_lock(manifest):
            need(p["command"]([*p["USER"],"/usr/bin/git","ls-remote",
                "https://github.com/al-teamaot-com/jason.git","refs/heads/main"]).decode().split()
                ==[args.candidate,"refs/heads/main"],"PROTECTED_SOURCE_ADVANCED")
            desired,_=state(host,manifest,p,n,pending)
            completed_active_offer(host_module,manifest["release_id"])
            names,rows=all_stopped(p["command"],desired["rollback_container_prefixes"])
            candidates=[d for r in rows.values() if (d:=planner["descriptor"](r,now=now(),policy=policy))]
            excluded=scan_references(planner,candidates,historical_audit_accepted=True)
            reservation=planner["validate_reservation_policy"](json.loads(code[RESERVATION_CONFIG]))
            report=capacity_report(planner,policy,reservation,desired,names,rows,len(manifest["targets"]),excluded)
            print(json.dumps({**report,"release_id":args.release_id,"read_only":True,
                "production_release_approved":False},sort_keys=True))
        return
    if getattr(args, "reserve_capacity", False):
        need(replace_policy is not None and cleanup_policy is not None,"NATIVE_POLICY_REPLACEMENT_PORT")
        return run_reservation(args,n,p,code,planner,pending,verify_source,wait_fresh,
                               host,manifest,review_sha,host_module,policy,source_hashes,
                               replace_policy,cleanup_policy,replace_binding=replace_binding,
                               cleanup_binding=cleanup_binding)
    record=LEDGER/args.candidate/args.release_id
    destination=ARCHIVE/args.candidate/args.release_id
    maximum=policy["maximum_archive_bytes_per_container"]
    def current_source():
        need(p["command"]([*p["USER"],"/usr/bin/git","ls-remote",
                  "https://github.com/al-teamaot-com/jason.git","refs/heads/main"]).decode().split()
             ==[args.candidate,"refs/heads/main"],"PROTECTED_SOURCE_ADVANCED")
    def inspect():
        desired,preserved=state(host,manifest,p,n,pending)
        prior = completed_active_offer(host_module, manifest["release_id"])
        if prior is not None:
            preserved["completed_active_offer"] = prior
        names,rows=all_stopped(p["command"],desired["rollback_container_prefixes"])
        candidates=[d for r in rows.values() if (d:=planner["descriptor"](r,now=now(),policy=policy))]
        excluded=scan_references(planner,candidates,historical_audit_accepted=True)
        plan=planner["choose"](list(rows.values()),inventory=names,
             maximum=desired["max_stopped_rollback_containers"],free_slots=len(manifest["targets"]),
             now=now(),policy=policy,excluded_ids=excluded)
        plan["before_ids"]={name:rows[name]["Id"] for name in names}
        plan["prefixes"]=desired["rollback_container_prefixes"]
        archive_destination(n,len(plan["retirements"]),maximum,policy)
        scope={"schema_version":"1.0","action":ACTION,
               "policy":{"candidate_sha":args.candidate,"rollback_sha":manifest["rollback_sha"]},
               "release_id":args.release_id,"manifest_sha256":digest(manifest),
               "release_scope_sha256":manifest["scope_sha256"],"review_source_sha":review_sha,
               "source_files_sha256":source_hashes,"retention_policy":policy,
               "installation_targets":[str(destination/r["target"]["id"]) for r in plan["retirements"]]
                   +[r["target"]["name"] for r in plan["retirements"]]+[str(record)],
               "queue_cutover":False,"plan":plan,"preserved":preserved,
               "image_or_volume_removal_allowed":False,"provider_writes":False,"standing_authority":False,
               "original_container_id_recreation_supported":False}
        return scope
    if args.resume:
        private_directory(LEDGER,n)
        private_directory(record.parent,n)
        private_directory(record,n)
        approval=json.loads(read(record/"approval.json",private=True))
        scope=approval["scope"]
        scope_sha=digest(scope)
        need(scope_sha==approval["scope_sha256"]==args.scope_sha
             and scope["source_files_sha256"]==source_hashes and scope["retention_policy"]==policy
             and scope["release_id"]==args.release_id and scope["manifest_sha256"]==digest(manifest)
             and scope["action"]==ACTION and scope["policy"]["candidate_sha"]==args.candidate
             and approval["owner_oid"]=="bee80bdc-ffb0-4c50-b453-c09d4d411f5f"
             and 0<=(now()-datetime.fromisoformat(approval["approved_at"])).total_seconds()<=28800,
             "RESUME_EXACT_AUTHENTICATED_SCOPE")
    else:
        need(not os.path.lexists(record) and not os.path.lexists(destination),"EXISTING_RETENTION_TRANSACTION")
        wait_fresh()
        with host.release_lock(manifest):
            current_source()
            scope=inspect()
        scope_sha=digest(scope)
        if not args.apply:
            print(json.dumps({"status":"exact_rollback_retention_preflight_passed",
                              "scope_sha256":scope_sha,"scope":scope},sort_keys=True))
            return
        need(args.scope_sha==scope_sha and bool(scope["plan"]["retirements"]),"EXACT_REVIEWED_SCOPE")
        owner=n["owner"](scope)
        need(owner=="bee80bdc-ffb0-4c50-b453-c09d4d411f5f","OWNER_IDENTITY")
        need(verify_source()==code,"APPROVED_SOURCE_CHANGED")
        wait_fresh()
        with host.release_lock(manifest):
            current_source()
            need(inspect()==scope,"APPROVED_SCOPE_CHANGED")
            private_directory(LEDGER,n,create=True)
            private_directory(record.parent,n,create=True)
            private_directory(record,n,create=True)
            immutable_record(n,record/"approval.json",{"scope":scope,"scope_sha256":scope_sha,
                            "owner_oid":owner,"approved_at":now().isoformat()})
    need(scope_sha==digest(scope) and bool(scope["plan"]["retirements"]),
         "EXACT_APPROVED_RETENTION_PLAN")
    approval=json.loads(read(record/"approval.json",private=True))
    need(approval["scope"]==scope and approval["scope_sha256"]==scope_sha
         and approval["owner_oid"]=="bee80bdc-ffb0-4c50-b453-c09d4d411f5f",
         "EXACT_DURABLE_APPROVAL_REQUIRED")
    plan=scope["plan"]
    wait_fresh()
    with host.release_lock(manifest):
        current_source()
        desired,preserved=state(host,manifest,p,n,pending)
        prior = completed_active_offer(host_module, manifest["release_id"])
        if prior is not None:
            preserved["completed_active_offer"] = prior
        need(preserved==scope["preserved"] and desired["rollback_container_prefixes"]==plan["prefixes"]
             and desired["max_stopped_rollback_containers"]==plan["maximum"],"PROTECTED_SCOPE_CHANGED")
        archive_destination(n,len(plan["retirements"]),maximum,policy)
        private_directory(destination.parent,n,create=True)
        private_directory(destination,n,create=True)
        names,rows=all_stopped(p["command"],plan["prefixes"])
        missing=verify_inventory(plan,names,rows,planner,policy)
        for retirement in plan["retirements"]:
            d=retirement["target"]
            sub=destination/d["id"]
            # An interrupted removal is recognized only with its exact sealed
            # archive. An unknown absent target or changed sibling denies.
            if d["name"] in missing:
                archive_proof(n,planner,sub,scope_sha,retirement,maximum)
            else:
                need(not scan_references(planner,[d],historical_audit_accepted=True,
                                         current_record=record),"REFERENCE_SCOPE_CHANGED")
                archive_exact(n,planner,sub,scope_sha,retirement,rows[d["name"]],maximum)
        for retirement in plan["retirements"]:
            d=retirement["target"]
            sub=destination/d["id"]
            retire_archived_exact(n,p["command"],planner,policy,record,sub,
                                  scope_sha,plan,retirement,current_source,
                                  host.guard.host_mutation_quiescent)
        names,rows=all_stopped(p["command"],plan["prefixes"])
        need(names==plan["after_names"],"AFTER_INVENTORY")
        verify_inventory(plan,names,rows,planner,policy)
        # Now the original native gate must actually pass with the freed
        # capacity, not a fabricated capacity or alternate safety check.
        host.ensure_breaker_closed_and_workers_quiescent()
        need(host.snapshot_protected()==scope["preserved"]["protected"]
             and host_module.readback.inspect_components()==scope["preserved"]["components"]
             and digest(p["read"](DESIRED,0,0o600))==scope["preserved"]["desired_policy_sha256"]
             and digest(p["read"](n["HOLD"],1000,0o664))==scope["preserved"]["hold_sha256"]
             and digest(p["read"](NORMAL/"deployment.json",0,0o644))==scope["preserved"]["deployment_config_sha256"]
             and completed_active_offer(host_module, manifest["release_id"])
                 == scope["preserved"].get("completed_active_offer")
             and host._frozen(manifest)==host.freeze_before,
             "PROTECTED_PEERS_OR_POLICY_CHANGED")
        result={"schema_version":"1.0","scope_sha256":scope_sha,"release_id":args.release_id,
                "status":"historical_rollback_capacity_verified","removed":len(plan["retirements"]),
                "remaining":len(names),"capacity":plan["maximum"],
                "provider_writes":False,"production_release_approved":False}
        immutable_record(n,record/"result.json",result)
        print(json.dumps(result,sort_keys=True))


def reservation_space(policy, command):
    # Space is independently observed at each gate, not embedded as a volatile
    # exact byte count in the approval. No pruning, exports or cleanup here.
    need(ARCHIVE_MOUNT.is_mount() and ARCHIVE_MOUNT.stat().st_dev != Path("/").stat().st_dev,
         "RESERVATION_ARCHIVE_MOUNT")
    docker_root=Path(command([DOCKER,"info","--format","{{.DockerRootDir}}"]).decode().strip())
    need(docker_root.is_absolute() and docker_root.is_dir(),"RESERVATION_DOCKER_STORAGE")
    for path, key in ((docker_root, "minimum_docker_free_bytes"),
                      (ARCHIVE_MOUNT, "minimum_archive_free_bytes")):
        space=os.statvfs(path)
        need(space.f_bavail*space.f_frsize >= policy[key], "RESERVATION_STORAGE_HEADROOM")

def inventory_digest(planner,names,rows):
    # Hash full normalized inspect metadata; never put container environments or
    # old IDs in a capacity receipt or a new historical reference exemption.
    return digest({name:digest(planner["normalize_inspect"](rows[name])) for name in names})

def reservation_plan(planner, policy, retention, desired, names, rows, targets, excluded):
    # Keep the native archival rule intact. A reservation is a separate
    # approved policy operation, only when duplicate archival cannot suffice.
    assessment=planner["assess"](list(rows.values()),inventory=names,
        maximum=desired["max_stopped_rollback_containers"],free_slots=targets,
        now=now(),policy=retention,excluded_ids=excluded)
    need(assessment["required_retirements"] > len(assessment["eligible_retirements"]),
         "RESERVATION_USE_EXISTING_CAPACITY_OR_ARCHIVAL")
    return planner["reserve_capacity"](desired,inventory_count=len(names),free_slots=targets,policy=policy)

def run_reservation(args,n,p,code,planner,pending,verify_source,wait_fresh,host,manifest,
                    review_sha,host_module,retention,source_hashes,replace_policy,cleanup_policy,*,
                    replace_binding=None,cleanup_binding=None):
    policy=planner["validate_reservation_policy"](json.loads(code[RESERVATION_CONFIG]))
    need(replace_binding is not None and cleanup_binding is not None,"NATIVE_BINDING_REPLACEMENT_PORT")
    record=RESERVATION_LEDGER/args.candidate/args.release_id
    def current_source():
        need(p["command"]([*p["USER"],"/usr/bin/git","ls-remote",
             "https://github.com/al-teamaot-com/jason.git","refs/heads/main"]).decode().split()
             ==[args.candidate,"refs/heads/main"],"PROTECTED_SOURCE_ADVANCED")
    def inspect(before=None,binding_before=None):
        desired,preserved=state(host,manifest,p,n,pending)
        raw=p["read"](DESIRED,0,0o600)
        need(json.loads(raw)==desired and digest(raw)==preserved["desired_policy_sha256"],
             "RESERVATION_POLICY_CHANGED")
        prior=completed_active_offer(host_module,manifest["release_id"])
        if prior is not None: preserved["completed_active_offer"]=prior
        reservation_space(policy,p["command"])
        # During authenticated crash recovery the file may already contain the
        # exact approved after-image. Recompute the original plan using the
        # sealed before-image, not a caller's guessed capacity.
        base=raw if before is None else before
        original=json.loads(base)
        need(set(original)==set(desired) and all(original[k]==desired[k] for k in original
             if k!="max_stopped_rollback_containers"),"RESERVATION_FOREIGN_POLICY")
        names,rows=all_stopped(p["command"],original["rollback_container_prefixes"])
        candidates=[d for r in rows.values() if (d:=planner["descriptor"](r,now=now(),policy=retention))]
        excluded=scan_references(planner,candidates,historical_audit_accepted=True)
        target=reservation_plan(planner,policy,retention,original,names,rows,len(manifest["targets"]),excluded)
        after=(json.dumps(target,sort_keys=True,indent=2)+"\n").encode()
        need(raw in (base,after),"RESERVATION_FOREIGN_POLICY")
        preserved["desired_policy_sha256"]=digest(base)
        current_binding=p["read"](BINDING,0,0o600)
        binding_base=current_binding if binding_before is None else binding_before
        binding_after=capacity_binding_image(binding_base,digest(base),digest(after))
        need(current_binding in (binding_base,binding_after),"RESERVATION_FOREIGN_BINDING")
        scope={"schema_version":"1.0","action":RESERVATION_ACTION,
            "policy":{"candidate_sha":args.candidate,"rollback_sha":manifest["rollback_sha"]},
            "release_id":args.release_id,"manifest_sha256":digest(manifest),
            "release_scope_sha256":manifest["scope_sha256"],"review_source_sha":review_sha,
            "source_files_sha256":source_hashes,"reservation_policy":policy,
            "retention_policy":retention,"installation_targets":[str(DESIRED),str(BINDING),str(record)],
            "plan":{"before_limit":original["max_stopped_rollback_containers"],
                    "after_limit":target["max_stopped_rollback_containers"],
                    "count":len(names),"required_slots":len(manifest["targets"]),
                    "inventory_sha256":inventory_digest(planner,names,rows),
                    "before_policy_sha256":digest(base),"after_policy_sha256":digest(after),
                    "before_binding_sha256":digest(binding_base),"after_binding_sha256":digest(binding_after)},
            "preserved":preserved,"queue_cutover":False,"provider_writes":False,
            "standing_authority":False,"container_image_volume_removal_allowed":False}
        return scope,base,after,raw,binding_base,binding_after,current_binding
    def exact_approval():
        private_directory(RESERVATION_LEDGER,n)
        private_directory(record.parent,n)
        private_directory(record,n)
        approval=json.loads(read(record/"approval.json",private=True))
        need(approval["scope_sha256"]==args.scope_sha==digest(approval["scope"])
             and approval["scope"]["action"]==RESERVATION_ACTION
             and approval["owner_oid"]=="bee80bdc-ffb0-4c50-b453-c09d4d411f5f"
             and 0<=(now()-datetime.fromisoformat(approval["approved_at"])).total_seconds()<=28800,
             "RESERVATION_APPROVAL_SCOPE")
        before=read(record/"before-policy.json",private=True)
        need(digest(before)==approval["scope"]["plan"]["before_policy_sha256"],"RESERVATION_BEFORE_IMAGE")
        binding_before=read(record/"before-binding.json",private=True)
        need(digest(binding_before)==approval["scope"]["plan"]["before_binding_sha256"],"RESERVATION_BEFORE_BINDING")
        return approval["scope"],before,binding_before
    if args.resume:
        scope,before,binding_before=exact_approval()
    else:
        need(not os.path.lexists(record),"RESERVATION_ALREADY_ATTEMPTED")
        wait_fresh()
        with host.release_lock(manifest):
            current_source()
            scope,before,after,raw,binding_before,binding_after,current_binding=inspect()
        sha=digest(scope)
        if not args.apply:
            print(json.dumps({"status":"exact_rollback_capacity_reservation_preflight_passed",
                              "scope_sha256":sha,"scope":scope},sort_keys=True)); return
        need(args.scope_sha==sha,"EXACT_REVIEWED_RESERVATION_SCOPE")
        owner=n["owner"](scope)
        need(owner=="bee80bdc-ffb0-4c50-b453-c09d4d411f5f","OWNER_IDENTITY")
        need(verify_source()==code,"APPROVED_SOURCE_CHANGED")
        wait_fresh()
        with host.release_lock(manifest):
            current_source()
            need(inspect()==(scope,before,after,raw,binding_before,binding_after,current_binding),"APPROVED_RESERVATION_CHANGED")
            private_directory(RESERVATION_LEDGER,n,create=True)
            private_directory(record.parent,n,create=True)
            private_directory(record,n,create=True)
            n["write"](record/"before-policy.json",before,0o400)
            n["write"](record/"before-binding.json",binding_before,0o400)
            immutable_record(n,record/"approval.json",{"scope":scope,"scope_sha256":sha,
                            "owner_oid":owner,"approved_at":now().isoformat()})
    need(verify_source()==code,"APPROVED_SOURCE_CHANGED")
    wait_fresh()
    with host.release_lock(manifest):
        current_source()
        need(not os.path.lexists(record/"result.json"),"RESERVATION_ALREADY_RESOLVED")
        approved,base,pin=exact_approval()
        need(approved==scope and base==before and pin==binding_before,"RESERVATION_DURABLE_APPROVAL")
        current,base,after,raw,pin,binding_after,current_binding=inspect(before,binding_before)
        need(current==scope and base==before and pin==binding_before,"RESERVATION_SCOPE_CHANGED")
        cleanup_policy(before,after)
        cleanup_binding(binding_before,binding_after)
        try:
            if raw==before: replace_policy(before,after)
            if current_binding==binding_before: replace_binding(binding_before,binding_after)
            need(p["read"](DESIRED,0,0o600)==after and p["read"](BINDING,0,0o600)==binding_after,
                 "RESERVATION_POLICY_READBACK")
            host_module.verify_installed_policy()
            # Use the existing effective native admission gate and actual
            # independent drift evaluator, not a manufactured PASS record.
            host.ensure_breaker_closed_and_workers_quiescent()
            guard=json.loads(p["command"](["/usr/bin/python3",
                "/opt/jason/current/tools/production_drift_guard.py","--config",str(DESIRED)]))
            need(guard.get("status")=="pass" and guard.get("problems")==[],"RESERVATION_DRIFT")
            need(inspect(before,binding_before)==(scope,before,after,after,binding_before,binding_after,binding_after),"RESERVATION_POSTFLIGHT_CHANGED")
        except BaseException:
            actual_binding=p["read"](BINDING,0,0o600)
            if actual_binding==binding_after: replace_binding(binding_after,binding_before)
            else: need(actual_binding==binding_before,"RESERVATION_ROLLBACK_FOREIGN_BINDING")
            actual=p["read"](DESIRED,0,0o600)
            if actual==after: replace_policy(after,before)
            else: need(actual==before,"RESERVATION_ROLLBACK_FOREIGN_POLICY")
            need(p["read"](DESIRED,0,0o600)==before and p["read"](BINDING,0,0o600)==binding_before,"RESERVATION_ROLLBACK_READBACK")
            host_module.verify_installed_policy()
            immutable_record(n,record/"result.json",{"status":"rollback_capacity_reservation_rolled_back",
                             "scope_sha256":args.scope_sha})
            raise
        result={"status":"rollback_capacity_reservation_verified","scope_sha256":args.scope_sha,
                "release_id":args.release_id,"before_limit":scope["plan"]["before_limit"],
                "capacity":scope["plan"]["after_limit"],"remaining":scope["plan"]["count"],
                "removed":0,"provider_writes":False,"production_release_approved":False}
        immutable_record(n,record/"result.json",result)
        print(json.dumps(result,sort_keys=True))


def capacity_report(planner,retention,reservation,desired,names,rows,targets,excluded):
    assessment=planner["assess"](list(rows.values()),inventory=names,
        maximum=desired["max_stopped_rollback_containers"],free_slots=targets,
        now=now(),policy=retention,excluded_ids=excluded)
    needed=assessment["required_retirements"]
    eligible=len(assessment["eligible_retirements"])
    report={"retained":len(names),"limit":desired["max_stopped_rollback_containers"],
        "available_slots":assessment["available_slots"],"release_slots_required":targets,
        "required_retirements":needed,"eligible_duplicate_retirements":eligible,
        "historical_equivalence_groups":assessment["historical_equivalence_groups"],
        "historical_candidates":assessment["historical_candidates"],
        "reservation_ceiling":reservation["maximum_stopped_rollback_containers"],
        "maximum_retirements_per_transaction":retention["maximum_retirements_per_approved_transaction"]}
    if not needed: report["status"]="capacity_available"
    elif eligible>=needed:
        report["status"]=("duplicate_archival_available" if needed<=report["maximum_retirements_per_transaction"]
                          else "duplicate_archival_batches_required")
    else:
        try: proposed=planner["reserve_capacity"](desired,inventory_count=len(names),free_slots=targets,policy=reservation)
        except PermissionError: report["status"]="capacity_policy_review_required"
        else:
            report.update(status="reservation_review_required",proposed_limit=proposed["max_stopped_rollback_containers"])
    return report


def capacity_binding_image(raw, before_hash, after_hash):
    """Change only the exact dependent pin, never another installed hash."""
    policy=json.loads(raw)
    need(isinstance(policy,dict) and policy.get("schema_version")=="3.0"
         and policy.get("per_release_review_required") is True
         and isinstance(policy.get("file_sha256"),dict)
         and HEX.fullmatch(before_hash) and HEX.fullmatch(after_hash) and before_hash!=after_hash
         and policy["file_sha256"].get("desired_state")==before_hash
         and raw.count(before_hash.encode())==1,"BINDING_BEFORE_PIN")
    after=raw.replace(before_hash.encode(),after_hash.encode(),1)
    expected={**policy,"file_sha256":{**policy["file_sha256"],"desired_state":after_hash}}
    need(json.loads(after)==expected,"BINDING_ONLY_DESIRED_PIN")
    return after


def reservation_evidence(n,planner,record,manifest,review_sha,source,*,completed,scope_sha=None):
    """Trust only the native root-custodied, exact previously approved transaction."""
    for path in (RESERVATION_LEDGER,record.parent,record):private_directory(path,n)
    approval_raw=read(record/"approval.json",private=True); approval=json.loads(approval_raw)
    scope=approval["scope"]; plan=scope["plan"]
    need(approval["scope_sha256"]==digest(scope)
         and (scope_sha is None or approval["scope_sha256"]==scope_sha)
         and approval["owner_oid"]=="bee80bdc-ffb0-4c50-b453-c09d4d411f5f"
         and 0<=(now()-datetime.fromisoformat(approval["approved_at"])).total_seconds()<=28800
         and scope["action"]==RESERVATION_ACTION and scope["policy"]["candidate_sha"]==source
         and scope["policy"]["rollback_sha"]==manifest["rollback_sha"]
         and scope["release_id"]==manifest["release_id"] and scope["manifest_sha256"]==digest(manifest)
         and scope["release_scope_sha256"]==manifest["scope_sha256"] and scope["review_source_sha"]==review_sha
         and all(scope[k] is False for k in ("queue_cutover","provider_writes","standing_authority","container_image_volume_removal_allowed")),
         "BINDING_RESERVATION_APPROVAL")
    before=read(record/"before-policy.json",private=True)
    need(digest(before)==plan["before_policy_sha256"]==scope["preserved"]["desired_policy_sha256"],"BINDING_RESERVATION_BEFORE")
    desired=json.loads(before)
    need(desired["max_stopped_rollback_containers"]==plan["before_limit"] and plan["required_slots"]==len(manifest["targets"]),"BINDING_RESERVATION_LIMIT")
    proposed=planner["reserve_capacity"](desired,inventory_count=plan["count"],free_slots=plan["required_slots"],policy=scope["reservation_policy"])
    after=(json.dumps(proposed,sort_keys=True,indent=2)+"\n").encode()
    need(digest(after)==plan["after_policy_sha256"] and proposed["max_stopped_rollback_containers"]==plan["after_limit"],"BINDING_RESERVATION_AFTER")
    if completed:
        # Legacy verified capacity receipts did not authorize modification of the
        # dependent controller pin. They cannot serve as binding-write authority.
        need(scope["installation_targets"]==[str(DESIRED),str(record)] and not os.path.lexists(record/"before-binding.json"),"BINDING_LEGACY_RESERVATION_REQUIRED")
        result_raw=read(record/"result.json",private=True); result=json.loads(result_raw)
        need(result=={"status":"rollback_capacity_reservation_verified","scope_sha256":approval["scope_sha256"],
              "release_id":manifest["release_id"],"before_limit":plan["before_limit"],"capacity":plan["after_limit"],
              "remaining":plan["count"],"removed":0,"provider_writes":False,"production_release_approved":False},"BINDING_RESERVATION_RESULT")
        return scope,before,after,{"approval_sha256":digest(approval_raw),"result_sha256":digest(result_raw)}
    need(not os.path.lexists(record/"result.json") and scope["installation_targets"]==[str(DESIRED),str(BINDING),str(record)],"RESERVATION_ALREADY_RESOLVED_OR_LEGACY")
    binding_before=read(record/"before-binding.json",private=True)
    binding_after=capacity_binding_image(binding_before,digest(before),digest(after))
    need(digest(binding_before)==plan["before_binding_sha256"] and digest(binding_after)==plan["after_binding_sha256"],"RESERVATION_APPROVED_BINDING_PAIR")
    return scope,before,after,binding_before,binding_after


def verify_binding_predecessor(h,pin,allowed_desired_hashes):
    # Maintenance-only inspection. The production release verifier itself is
    # unchanged. Never bless unrelated drift or grant a release while mismatched.
    policy=json.loads(pin)
    need(h.POLICY==BINDING and h.DESIRED==DESIRED and set(policy)==h.REUSABLE_POLICY_FIELDS
         and policy["schema_version"]=="3.0" and policy["allowed_targets"]==list(h.co.TARGET_ORDER)
         and policy["per_release_review_required"] is True and SHA.fullmatch(policy["source_sha"])
         and set(policy["file_sha256"])==set(h.FILES),"BINDING_INSTALLED_POLICY")
    need(policy["file_sha256"]["desired_state"] in allowed_desired_hashes,"BINDING_APPROVED_PIN")
    for key,path in h.FILES.items():
        actual=digest(h.trusted_bytes(path))
        need(actual in allowed_desired_hashes if key=="desired_state" else actual==policy["file_sha256"][key],"BINDING_UNRELATED_DRIFT:"+key)
    h.verify_effective_schedule()
    raw=h.trusted_bytes(h.MIGRATION)
    need(digest(raw)==policy["native_reader_migration_receipt_sha256"],"BINDING_READER_DRIFT")
    h.verify_reader_migration(json.loads(raw),policy)
    for unit in ("jason-scoped-backport-recovery.timer","jason-scoped-backport-requests.path"):
        for verb,value in (("is-enabled",b"enabled"),("is-active",b"active")):
            need(h.run("systemctl",verb,unit,timeout=12).stdout.strip()==value,"BINDING_TRIGGER_STATE")
    for path in (h.PRIVATE,h.PRIVATE/"offers",h.PRIVATE/"transactions",h.PRIVATE/"freeze-backups",h.ROOT_STATE/"consumed-owner-approvals"):
        h.trusted_directory(path); h.root_directory(path)
    h.trusted_directory(h.REPO); h.read_pinned_root_owner_public_key(h.TRUST_KEY)
    return policy


def verify_binding_live(args,n,p,planner,pending,h,manifest,scope,guard,*,recovery=False,repaired=False,reporter_pins=None):
    need(p["command"]([*p["USER"],"/usr/bin/git","ls-remote","https://github.com/al-teamaot-com/jason.git","refs/heads/main"]).decode().split()==[args.candidate,"refs/heads/main"],"BINDING_CURRENT_SOURCE")
    if recovery:
        verify_binding_fault(n,p,h,guard,scope["preserved"]["host_anchor"],repaired=repaired,reporter_pins=reporter_pins)
    else:
        need(guard.host_mutation_quiescent(),"BINDING_NATIVE_HEALTH")
    need(audit_accepted(),"BINDING_AUDIT_HEALTH")
    pending(SimpleNamespaceForPending(p))
    prior=completed_active_offer(h,manifest["release_id"]); preserved=scope["preserved"]
    need(prior==preserved.get("completed_active_offer"),"BINDING_PREDECESSOR_CHANGED")
    for path in (h.PRIVATE/"transactions").glob("release-*.json"):
        need(h.root_json(path).get("outcome") in h.RESOLVED,"BINDING_UNRESOLVED_RELEASE")
    h.require_normal_deployment_enabled(h.FREEZE.parent,manifest["release_policy_sha256"])
    readback=h.readback.verify_live()
    need(readback is not None and readback["host_revision"]==preserved["host_anchor"]
         and h.readback.inspect_components()==preserved["components"]
         and {name:h.peer_snapshot(h.required_container(name),name) for name in manifest["protected_services"]}==preserved["protected"]
         and {t["name"]:h.config_fingerprint(h.required_container(t["name"])) for t in manifest["targets"]}==preserved["target_configuration"],"BINDING_PROTECTED_COMPONENTS_CHANGED")
    need(digest(p["read"](n["HOLD"],1000,0o664))==preserved["hold_sha256"]
         and digest(p["read"](NORMAL/"deployment.json",0,0o644))==preserved["deployment_config_sha256"],"BINDING_HOLD_OR_FREEZE_CHANGED")
    desired=json.loads(p["read"](DESIRED,0,0o600)); names,rows=all_stopped(p["command"],desired["rollback_container_prefixes"])
    need(len(names)==scope["plan"]["count"] and inventory_digest(planner,names,rows)==scope["plan"]["inventory_sha256"],"BINDING_INVENTORY_CHANGED")
    reservation_space(scope["reservation_policy"],p["command"])


class SimpleNamespaceForPending:
    def __init__(self,p):self.p=p


def restore_interrupted_pair(args,n,p,code,planner,pending,verify_source,wait_fresh,h,manifest,profile,review_sha,replace_policy,cleanup_policy,replace_binding,cleanup_binding):
    """Recover an interrupted two-file reservation using only its original scope."""
    need(HEX.fullmatch(args.scope_sha or ""),"RESERVATION_RECOVERY_EXACT_SCOPE")
    record=RESERVATION_LEDGER/args.candidate/args.release_id
    scope,before,after,pin_before,pin_after=reservation_evidence(n,planner,record,manifest,review_sha,args.candidate,completed=False,scope_sha=args.scope_sha)
    need(verify_source()==code,"RESERVATION_RECOVERY_SOURCE")
    wait_fresh()
    guard=h.IndependentHostGuard()
    with guard.host_release_transaction():
        need(reservation_evidence(n,planner,record,manifest,review_sha,args.candidate,completed=False,scope_sha=args.scope_sha)==(scope,before,after,pin_before,pin_after),"RESERVATION_RECOVERY_SCOPE_CHANGED")
        raw=p["read"](DESIRED,0,0o600); pin=p["read"](BINDING,0,0o600)
        need(raw in (before,after) and pin in (pin_before,pin_after),"RESERVATION_RECOVERY_FOREIGN_PAIR")
        if (raw==before)==(pin==pin_before):return
        verify_binding_predecessor(h,pin,{digest(before),digest(after)})
        verify_binding_live(args,n,p,planner,pending,h,manifest,scope,guard)
        cleanup_policy(before,after);cleanup_binding(pin_before,pin_after)
        # Restore only the interrupted half to the exact approved rollback bytes.
        if raw==after:replace_policy(after,before)
        else:replace_binding(pin_after,pin_before)
        h.verify_installed_policy(profile)
        need(p["read"](DESIRED,0,0o600)==before and p["read"](BINDING,0,0o600)==pin_before,"RESERVATION_RECOVERY_READBACK")


def reconcile_binding(args,n,p,code,planner,pending,verify_source,wait_fresh,h,manifest,profile,review_sha,replace_binding,cleanup_binding,*,recover_native=None,reporter_pins=None):
    """Repair a completed legacy reservation under a separate exact Owner decision."""
    recovery=getattr(args,"recover_binding_fault",False)
    need(not recovery or (recover_native is not None and reporter_pins),"BINDING_RECOVERY_NATIVE_PORTS")
    def wait_health():
        if not recovery:wait_fresh()
    def check_live(old,guard,*,repaired=False,final=False):
        if recovery and not final:
            verify_binding_live(args,n,p,planner,pending,h,manifest,old,guard,recovery=True,repaired=repaired,reporter_pins=reporter_pins)
        else:verify_binding_live(args,n,p,planner,pending,h,manifest,old,guard)
    source=args.reservation_source
    need(isinstance(source,str) and SHA.fullmatch(source),"BINDING_RESERVATION_SOURCE")
    prior=RESERVATION_LEDGER/source/args.release_id
    record=BINDING_LEDGER/args.candidate/args.release_id
    def inspect(pin_before=None):
        old,before,after,evidence=reservation_evidence(n,planner,prior,manifest,review_sha,source,completed=True)
        need(p["read"](DESIRED,0,0o600)==after,"BINDING_LIVE_APPROVED_POLICY")
        pin=p["read"](BINDING,0,0o600); base=pin if pin_before is None else pin_before
        target=capacity_binding_image(base,digest(before),digest(after))
        need(pin in (base,target),"BINDING_FOREIGN_POLICY")
        verify_binding_predecessor(h,pin,{digest(before),digest(after)})
        scope={"schema_version":"1.0","action":BINDING_ACTION,
            "policy":{"candidate_sha":args.candidate,"rollback_sha":manifest["rollback_sha"]},
            "release_id":args.release_id,"reservation_source":source,"reservation_scope_sha256":digest(old),
            "reservation_evidence":evidence,"source_files_sha256":{k:digest(v) for k,v in code.items()},
            "installation_targets":[str(BINDING),str(record)],"before_binding_sha256":digest(base),
            "after_binding_sha256":digest(target),"desired_policy_sha256":digest(after),
            "approved_capacity":old["plan"]["after_limit"],"queue_cutover":False,"provider_writes":False,"standing_authority":False}
        if recovery:
            scope.update(recovery_fault="exact_stale_capacity_pin_failed_recovery_service",
                recovery_steps=[RECOVERY_UNIT,DRIFT_REPORTER_UNIT,"native_root_breaker_revalidation"],
                retain_verified_binding_if_native_revalidation_pending=True)
        return old,base,target,pin,scope
    def locked():return h.IndependentHostGuard()
    if args.resume:
        for path in (BINDING_LEDGER,record.parent,record):private_directory(path,n)
        a=json.loads(read(record/"approval.json",private=True)); base=read(record/"before-binding.json",private=True); scope=a["scope"]
        need(a["scope_sha256"]==args.scope_sha==digest(scope) and a["owner_oid"]=="bee80bdc-ffb0-4c50-b453-c09d4d411f5f" and 0<=(now()-datetime.fromisoformat(a["approved_at"])).total_seconds()<=28800 and digest(base)==scope["before_binding_sha256"],"BINDING_RESUME_APPROVAL")
    else:
        need(not os.path.lexists(record),"BINDING_ALREADY_ATTEMPTED")
        wait_health();guard=locked()
        with guard.host_release_transaction():
            old,base,target,pin,scope=inspect()
            check_live(old,guard)
        sha=digest(scope)
        if not args.apply:
            print(json.dumps({"status":"exact_rollback_capacity_binding_preflight_passed","scope_sha256":sha,"scope":scope},sort_keys=True));return
        need(args.scope_sha==sha,"BINDING_EXACT_SCOPE")
        owner=n["owner"](scope);need(owner=="bee80bdc-ffb0-4c50-b453-c09d4d411f5f","BINDING_OWNER_IDENTITY")
        need(verify_source()==code,"BINDING_SOURCE_CHANGED")
        wait_health();guard=locked()
        with guard.host_release_transaction():
            need(inspect()==(old,base,target,pin,scope),"BINDING_APPROVED_STATE_CHANGED")
            check_live(old,guard)
            for path in (BINDING_LEDGER,record.parent,record):private_directory(path,n,create=True)
            n["write"](record/"before-binding.json",base,0o400)
            immutable_record(n,record/"approval.json",{"scope":scope,"scope_sha256":sha,"owner_oid":owner,"approved_at":now().isoformat()})
    need(verify_source()==code,"BINDING_SOURCE_CHANGED")
    wait_health();guard=locked()
    with guard.host_release_transaction():
        need(not os.path.lexists(record/"result.json"),"BINDING_ALREADY_RESOLVED")
        old,base2,target,pin,current=inspect(base)
        need(base2==base and current==scope and digest(scope)==args.scope_sha,"BINDING_APPROVED_SCOPE_CHANGED")
        approval=json.loads(read(record/"approval.json",private=True));need(approval["scope"]==scope and approval["scope_sha256"]==args.scope_sha and approval["owner_oid"]=="bee80bdc-ffb0-4c50-b453-c09d4d411f5f" and 0<=(now()-datetime.fromisoformat(approval["approved_at"])).total_seconds()<=28800 and read(record/"before-binding.json",private=True)==base,"BINDING_DURABLE_APPROVAL")
        check_live(old,guard,repaired=pin==target)
        cleanup_binding(base,target)
        try:
            if pin==base:replace_binding(base,target)
            h.verify_installed_policy(profile)
            need(inspect(base)==(old,base,target,target,scope),"BINDING_POSTFLIGHT_CHANGED")
            if recovery:
                check_live(old,guard,repaired=True)
                immutable_record(n,record/"binding-verified.json",{"scope_sha256":args.scope_sha,
                    "status":"exact_binding_verified_native_revalidation_pending","binding_sha256":digest(target)})
            else:
                verify_binding_drift_pass(p)
                check_live(old,guard)
        except BaseException:
            actual=p["read"](BINDING,0,0o600)
            if actual==target:replace_binding(target,base)
            else:need(actual==base,"BINDING_ROLLBACK_FOREIGN_POLICY")
            need(p["read"](BINDING,0,0o600)==base,"BINDING_ROLLBACK_READBACK")
            immutable_record(n,record/"result.json",{"status":"rollback_capacity_binding_rolled_back","scope_sha256":args.scope_sha})
            raise
        if not recovery:
            record_binding_success(n,record,scope,args)
            return
    # The failed unit and native root breaker transition take the same shared
    # locks themselves. Never hold those locks while asking them to run. The
    # installed pin is independently verified; the original open breaker is
    # left to its native revalidation, never edited or forcibly closed here.
    recover_native()
    wait_fresh()
    guard=locked()
    with guard.host_release_transaction():
        need(verify_source()==code and not os.path.lexists(record/"result.json"),"BINDING_FINAL_SOURCE_OR_RESULT")
        need(inspect(base)==(old,base,target,target,scope),"BINDING_FINAL_SCOPE_CHANGED")
        h.verify_installed_policy(profile)
        verify_binding_drift_pass(p)
        check_live(old,guard,final=True)
        record_binding_success(n,record,scope,args)


RECOVERY_UNIT="jason-scoped-backport-recovery.service"
DRIFT_REPORTER_UNIT="jason-production-drift-watchdog.service"
RECOVERY_FAULT={"kind":"failed_system_unit","state":"failed","unit":RECOVERY_UNIT}
REPORTER_FAULT={"kind":"failed_system_unit","state":"failed","unit":DRIFT_REPORTER_UNIT}
DRIFT_EVALUATOR=Path("/opt/jason/current/tools/production_drift_guard.py")


def verify_binding_drift_pass(p):
    report=json.loads(p["command"](["/usr/bin/python3",str(DRIFT_EVALUATOR),"--config",str(DESIRED)]))
    need(report.get("status")=="pass" and report.get("problems")==[],"BINDING_POSTFLIGHT_DRIFT")


def record_binding_success(n,record,scope,args):
    result={"status":"rollback_capacity_binding_verified","scope_sha256":args.scope_sha,"release_id":args.release_id,"capacity":scope["approved_capacity"],"removed":0,"production_release_approved":False,"provider_writes":False}
    if scope.get("recovery_fault"):result["native_breaker_revalidated"]=True
    immutable_record(n,record/"result.json",result);print(json.dumps(result,sort_keys=True))


def exact_binding_fault(control,recorded,evaluated,*,repaired,anchor):
    """Maintenance admission for this single known failed-unit fault only."""
    baseline=control["last_known_good"]["manifest"]; breaker=control["circuit_breaker"]
    need(baseline.get("complete") is True and all(baseline.get(k)==anchor for k in
         ("revision","host_revision","runtime_revision","mcp_revision")),"BINDING_RECOVERY_LKG")
    need(breaker.get("state")=="open" and breaker.get("source")=="production_drift_watchdog"
         and breaker.get("reason")=="continuous_production_drift_detected"
         and breaker.get("problem_count")==1 and breaker.get("problem_kinds")==["failed_system_unit"],"BINDING_RECOVERY_BREAKER")
    for report in (recorded,evaluated):
        stamp=datetime.fromisoformat(report["observed_at"])
        need(stamp.utcoffset() is not None and 0<=(now()-stamp).total_seconds()<=180,"BINDING_RECOVERY_STALE_DRIFT")
    recorded_fault=recorded.get("status")=="drift_detected" and recorded.get("problems")==[RECOVERY_FAULT]
    recorded_clean=recorded.get("status")=="pass" and recorded.get("problems")==[]
    need(recorded_fault or (repaired and recorded_clean),"BINDING_RECOVERY_RECORDED_DRIFT")
    problems=evaluated.get("problems"); expected=sorted([RECOVERY_FAULT,REPORTER_FAULT],key=lambda r:r["unit"])
    failed=evaluated.get("status")=="drift_detected" and problems in ([RECOVERY_FAULT],expected)
    recovering=repaired and ((evaluated.get("status")=="drift_detected" and problems==[REPORTER_FAULT]) or
                             (evaluated.get("status")=="pass" and problems==[]))
    need(failed or recovering,"BINDING_RECOVERY_UNRELATED_DRIFT")
    return problems


def unit_properties(p,unit,keys):
    raw=p["command"](["/usr/bin/systemctl","show",unit,*["-p"+k for k in keys]]).decode()
    values=dict(line.split("=",1) for line in raw.splitlines() if "=" in line)
    need(set(values)==set(keys),"BINDING_RECOVERY_UNIT_PROPERTIES")
    return values


def verify_binding_fault(n,p,h,guard,anchor,*,repaired,reporter_pins):
    need(guard._held and guard._source_sha()==anchor,"BINDING_RECOVERY_LOCK_OR_SOURCE")
    if repaired and guard.host_mutation_quiescent():return
    control=json.loads(p["read"](n["ROOT_CONTROL"],0,0o600));recorded=json.loads(p["read"](MANAGER/"production-drift.json",0,0o600))
    h.readback.verify_legacy_anchor(h.readback.verify_live(),control["last_known_good"]["manifest"])
    need(digest(p["read"](DRIFT_EVALUATOR,0))==p["PINNED"][str(DRIFT_EVALUATOR)],"BINDING_RECOVERY_DRIFT_EVALUATOR_PIN")
    probe=("import json,sys;from pathlib import Path;p=Path(sys.argv[1]);n={'__name__':'native_drift_preflight','__file__':str(p)};"
           "exec(compile(p.read_bytes(),str(p),'exec'),n);print(json.dumps(n['evaluate'](json.loads(Path(sys.argv[2]).read_text()))))")
    evaluated=json.loads(p["command"](["/usr/bin/python3","-I","-B","-c",probe,str(DRIFT_EVALUATOR),str(DESIRED)],75))
    problems=exact_binding_fault(control,recorded,evaluated,repaired=repaired,anchor=anchor)
    if RECOVERY_FAULT in problems:
        keys=("LoadState","ActiveState","MainPID","Result","InvocationID")
        unit=unit_properties(p,RECOVERY_UNIT,keys); invocation=unit.pop("InvocationID")
        need(unit=={"LoadState":"loaded","ActiveState":"failed","MainPID":"0","Result":"exit-code"} and re.fullmatch(r"[0-9a-f]{32}",invocation),"BINDING_RECOVERY_UNIT_STATE")
        log=p["command"](["/usr/bin/journalctl","--no-pager","--output=cat","_SYSTEMD_INVOCATION_ID="+invocation])
        need(b"ScopedBackportDenied: SCOPED_BACKPORT_COORDINATED_INSTALLED_SOURCE_DRIFT" in log,"BINDING_RECOVERY_CAUSE")
    if REPORTER_FAULT in problems:
        need(bool(reporter_pins) and all(digest(p["read"](Path(path),0))==pin for path,pin in reporter_pins.items()),"BINDING_RECOVERY_REPORTER_PIN")
        keys=("LoadState","ActiveState","MainPID","Result","ExecMainCode","ExecMainStatus")
        need(unit_properties(p,DRIFT_REPORTER_UNIT,keys)=={"LoadState":"loaded","ActiveState":"failed","MainPID":"0","Result":"exit-code","ExecMainCode":"1","ExecMainStatus":"2"},"BINDING_RECOVERY_REPORTER_STATE")
    need(not list((MANAGER/"protected-transitions/requests").glob("*.json")),"BINDING_RECOVERY_PENDING_TRANSITION")
