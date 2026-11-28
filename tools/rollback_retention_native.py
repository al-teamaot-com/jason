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


def run_action(args, n, p, code, planner, pending, verify_source, wait_fresh):
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
    host=host_module.CoordinatedHost()
    host.bind_for_stage(manifest,profile,review_sha)
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
