"""Archive-backed, event-preserving legacy data reconstruction and publication."""
from __future__ import annotations
from datetime import datetime,timezone
from hashlib import sha256
import os,stat
from pathlib import Path
import shutil
from uuid import uuid4
from .segmented_journal import need,fingerprint,read_control
from . import journal_sql

class ArchiveRecovery:
 def __init__(self,controller):
  self.c=controller;self.p=controller.p
  self.storage=self.p.archives.parent/"rollback"
  meta=self.storage.lstat()
  need(not self.storage.is_symlink() and stat.S_ISDIR(meta.st_mode)
       and meta.st_uid==self.p.custody_uid and not meta.st_mode&0o022,
       "JOURNAL_ROLLBACK_STORAGE_CUSTODY")

 def prepare(self):
  c,p=self.c,self.p
  with c.serialized():
   with p.gate():
    catalog=p.catalog()
    need(catalog["mode"] in ("segmented","segmented_initializing"),"JOURNAL_ROLLBACK_MODE")
    paths=[str(p.artifact(r)) for r in catalog["segments"]]
    job=c._job();snapshot=job/"active.snapshot.sqlite3"
    state=c._sql("snapshot",{"source":str(p.active),"target":str(snapshot)},seconds=60)
    need(state["pending_outcomes"]==0,"JOURNAL_ROLLBACK_UNRECONCILED_OUTCOMES")
   required=snapshot.stat().st_size+sum(Path(path).stat().st_size for path in paths)
   need(shutil.disk_usage(self.storage).free>required*2+4294967296,
        "JOURNAL_ROLLBACK_ARCHIVE_SPACE_REQUIRED")
   target=job/"legacy.prepared.sqlite3"
   proof=c._sql("rebuild",{"paths":[*paths,str(snapshot)],"target":str(target),
       "proofs":[*(r["proof"] if r["state"]=="sealed" else None for r in catalog["segments"]),None]})
   adopted=self.storage/(uuid4().hex+".prepared.sqlite3")
   meta=target.stat()
   claim=c.private/("prepared-"+adopted.name+".json")
   c._json(claim,{"path":str(adopted),"identity":[meta.st_dev,meta.st_ino],
       "file_sha256":proof["file_sha256"],"finished":False},0o400)
   c._move(target,adopted,p.custody_uid,0o444)
   c.no_handles(adopted)
   need(journal_sql.file_hash(adopted)==proof["file_sha256"],"JOURNAL_ROLLBACK_PROOF_CHANGED")
   plan={"generation":catalog["generation"],"epoch":catalog["epoch"],"watermark":state["watermark"],
    "target":str(adopted),"proof":proof,"target_fingerprint":fingerprint(adopted.stat()),
    "covered_segments":{r["id"]:r["fingerprint"] for r in catalog["segments"]},
    "catalog":catalog,"prepared_at":datetime.now(timezone.utc).isoformat()}
   c._json(c.rollback,plan,0o400)
   c._cleanup_job(job)
   return {"status":"rollback_prepared_on_archive_drive","events":proof["events"]}

 def cleanup_prepared(self):
  c,p=self.c,self.p
  protected=set()
  for marker in (c.rollback,c.intent):
   if not marker.exists():continue
   row=read_control(marker,p.custody_uid,0o400)
   for value in (row.get("target"),row.get("sealed_target"),row.get("plan",{}).get("target")):
    if value:protected.add(value)
  cleaned=0
  for claim in sorted(c.private.glob("prepared-*.json")):
   row=read_control(claim,p.custody_uid,0o400)
   if row["finished"] or row["path"] in protected:continue
   target=Path(row["path"]);identifier=target.name.removesuffix(".prepared.sqlite3")
   need(target.parent==self.storage and target.name.endswith(".prepared.sqlite3")
        and len(identifier)==32 and all(ch in "0123456789abcdef" for ch in identifier),
        "JOURNAL_PREPARED_CLEANUP_SCOPE")
   if target.exists():
    m=target.lstat()
    need(not target.is_symlink() and stat.S_ISREG(m.st_mode) and m.st_nlink==1
         and [m.st_dev,m.st_ino]==row["identity"]
         and m.st_uid in (p.custody_uid,p.writer_uid) and not m.st_mode&0o022,
         "JOURNAL_PREPARED_CLEANUP_IDENTITY")
    c.no_handles(target)
    need(journal_sql.file_hash(target)==row["file_sha256"],"JOURNAL_PREPARED_CLEANUP_CONTENT")
    target.unlink()
    from os import open as osopen,close as osclose,fsync,O_RDONLY,O_DIRECTORY
    fd=osopen(self.storage,O_RDONLY|O_DIRECTORY)
    try:fsync(fd)
    finally:osclose(fd)
   c._json(claim,{**row,"finished":True},0o400);cleaned+=1
   if cleaned>=8:break
  return {"prepared_temporary_copies_cleaned":cleaned}

 def accept_recipe(self):
  c,p=self.c,self.p
  with c.serialized():
   plan=read_control(c.rollback,p.custody_uid,0o400)
   target=Path(plan["target"])
   need(target.parent==self.storage and fingerprint(target.stat())==plan["target_fingerprint"],
        "JOURNAL_RECONSTRUCTION_TARGET_CHANGED")
   job=c._job()
   try:
    restored=c._sql("legacy_restore_proof",{"source":str(target),
        "target":str(job/"legacy.restored.sqlite3")})
    for key in ("integrity","events","content_sha256","schema_sha256"):
     need(restored["proof"][key]==plan["proof"][key],"JOURNAL_LEGACY_RESTORE_PARITY")
   finally:c._cleanup_job(job)
   recipe={"format":"legacy-event-preserving-reconstruction-v1",
     "verifier_source_sha256":c.verifier_digest(),
     "schema_sha256":plan["proof"]["schema_sha256"],"initial_full_reconstruction":plan["proof"],
     "legacy_reader_restore":restored,"covered_segments":plan["covered_segments"],
     "ordered_segment_ids":[r["id"] for r in plan["catalog"]["segments"]],
     "verified_at":datetime.now(timezone.utc).isoformat(),"off_host_backup_claimed":False}
   c._json(c.private/"recovery-recipe.json",recipe,0o400)
   return {"status":"full_reconstruction_and_legacy_restore_verified"}

 def extend_recipe(self):
  c,p=self.c,self.p
  with c.serialized(),p.gate():
   recipe=read_control(c.private/"recovery-recipe.json",p.custody_uid,0o400)
   need(recipe["verifier_source_sha256"]==c.verifier_digest(),
        "JOURNAL_RECONSTRUCTION_VERIFIER_CHANGED")
   catalog=p.catalog();ids=[r["id"] for r in catalog["segments"]]
   old=recipe["ordered_segment_ids"]
   need(ids[:len(old)]==old,"JOURNAL_RECONSTRUCTION_LINEAGE_CHANGED")
   for record in catalog["segments"]:
    p.artifact(record)
    need(record["state"]=="sealed" and record["proof"]["integrity"]=="ok"
         and record["proof"]["restore_verified"] is True
         and record["proof"]["schema_sha256"]==recipe["schema_sha256"],
         "JOURNAL_RECONSTRUCTION_SEGMENT_NOT_COMPATIBLE")
    if record["id"] in recipe["covered_segments"]:
     need(record["fingerprint"]==recipe["covered_segments"][record["id"]],
          "JOURNAL_RECONSTRUCTION_HISTORY_CHANGED")
   # This extends a reconstruction FORMAT proof; it never labels an unbuilt
   # whole legacy file as freshly integrity-checked. Each added segment has its
   # own actual full integrity/restore proof; admitted writers enforce global
   # event-ID uniqueness. Actual rollback always rebuilds and checks the target.
   updated={**recipe,"covered_segments":{r["id"]:r["fingerprint"] for r in catalog["segments"]},
      "ordered_segment_ids":ids,"coverage_extended_at":datetime.now(timezone.utc).isoformat(),
      "whole_legacy_target_rebuilt_for_this_extension":False}
   c._json(c.private/"recovery-recipe.json",updated,0o400)
   return {"status":"verified_reconstruction_recipe_extended","segments":len(ids)}

 def discard_prepared(self):
  c,p=self.c,self.p
  with c.serialized():
   plan=read_control(c.rollback,p.custody_uid,0o400)
   recipe=read_control(c.private/"recovery-recipe.json",p.custody_uid,0o400)
   need(recipe["initial_full_reconstruction"]==plan["proof"],"JOURNAL_DISCARD_RECONSTRUCTION_PROOF")
   target=Path(plan["target"])
   need(target.parent==self.storage and fingerprint(target.stat())==plan["target_fingerprint"],
        "JOURNAL_DISCARD_TARGET_IDENTITY")
   c.no_handles(target);target.unlink()
   c._json(c.private/"last-reconstruction.json",plan,0o400)
   c.rollback.unlink()
   return {"status":"prepared_recovery_copy_discarded_history_retained"}

 def publish(self,tx):
  c,p=self.c,self.p;target=Path(tx["plan"]["target"])
  marker=c.private/"rollback-mounted.json"
  final=self.storage/(tx["preserved"].removesuffix(".sqlite3")+".legacy.sqlite3")
  if not marker.exists():
   if c.fixture:
    if target.exists():c._move(target,p.active,p.writer_uid,0o600)
    meta=p.active.stat()
    need({"device":meta.st_dev,"inode":meta.st_ino}==tx["target_identity"],
         "JOURNAL_FIXTURE_ROLLBACK_IDENTITY")
    c._json(marker,{"fixture_only":True,"source":str(p.active),
       "source_identity":tx["target_identity"]},0o400)
   else:
    if target.exists():
     c._sql("checkpoint",{"path":str(target)},seconds=30)
     c._move(target,final,p.writer_uid,0o600)
    meta=final.lstat()
    need(not final.is_symlink() and meta.st_nlink==1 and meta.st_uid==p.writer_uid
         and {"device":meta.st_dev,"inode":meta.st_ino}==tx["target_identity"],
         "JOURNAL_ROLLBACK_PERMANENT_SOURCE_IDENTITY")
    c._json(marker,{"fixture_only":False,"source":str(final),
       "source_identity":tx["target_identity"],"source_epoch":tx["source_epoch"],
       "canonical":str(p.active),"prepared_proof":tx["plan"]["proof"]},0o400)
  return self.restore_mount()

 def restore_mount(self):
  c,p=self.c,self.p
  marker=read_control(c.private/"rollback-mounted.json",p.custody_uid,0o400)
  if c.fixture:
   need(marker.get("fixture_only") is True,"JOURNAL_FIXTURE_MOUNT_MARKER")
   return {"status":"fixture_legacy_published_no_native_mount"}
  need(marker.get("fixture_only") is False and marker["canonical"]==str(p.active),
       "JOURNAL_ROLLBACK_MOUNT_SCOPE")
  source=Path(marker["source"])
  need(source.parent==self.storage and source.name.endswith(".legacy.sqlite3"),
       "JOURNAL_ROLLBACK_MOUNT_SOURCE_SCOPE")
  meta=source.lstat()
  need(not source.is_symlink() and stat.S_ISREG(meta.st_mode) and meta.st_uid==p.writer_uid
       and meta.st_gid==p.writer_uid and stat.S_IMODE(meta.st_mode)==0o600 and meta.st_nlink==1
       and {"device":meta.st_dev,"inode":meta.st_ino}==marker["source_identity"],
       "JOURNAL_ROLLBACK_MOUNT_SOURCE_CHANGED")
  if not os.path.lexists(p.active):
   fd=os.open(p.active,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
   os.fchown(fd,p.writer_uid,p.writer_uid);os.fchmod(fd,0o600);os.fsync(fd);os.close(fd)
  p.active_identity()
  current=p.active.stat()
  if (current.st_dev,current.st_ino)==(meta.st_dev,meta.st_ino):
   return {"status":"rollback_data_already_bound"}
  from .journal_mount import bind_database
  return bind_database(source,p.active,writer_uid=p.writer_uid)
