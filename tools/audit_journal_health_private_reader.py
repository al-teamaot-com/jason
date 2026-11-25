"""Native health adapter: private audit copies; frozen journal code stays unchanged.

Installed beside the three existing native health adapters. This module grants
no execution authority and never writes the canonical journal or its policy.
"""
from __future__ import annotations
from datetime import datetime,timezone,timedelta
from contextlib import contextmanager
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import tempfile
import stat
import time
from orchestrator.segmented_journal import JournalProfile,PROFILE,need
from orchestrator import journal_sql

from orchestrator.journal_health import canonical,covered_catalog,enabled

COPY_SECONDS=5.0

def _copy_locked(source, destination, uid, maximum, deadline):
    """Copy guarded bytes without ever opening live SQLite or creating live WAL."""
    need(time.monotonic()<deadline,"JOURNAL_HEALTH_COPY_BUDGET_EXCEEDED")
    prior=source.lstat()
    need(stat.S_ISREG(prior.st_mode) and prior.st_uid==uid and prior.st_nlink==1
         and stat.S_IMODE(prior.st_mode)==0o600 and 0<=prior.st_size<=maximum,
         "JOURNAL_HEALTH_COPY_SOURCE_IDENTITY")
    fd=os.open(source,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        actual=os.fstat(fd)
        need((actual.st_dev,actual.st_ino,actual.st_size,actual.st_mtime_ns)
             ==(prior.st_dev,prior.st_ino,prior.st_size,prior.st_mtime_ns),
             "JOURNAL_HEALTH_COPY_SOURCE_CHANGED")
        with os.fdopen(os.open(destination,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600),"wb") as out:
            with os.fdopen(fd,"rb",closefd=False) as inp:
                remaining=prior.st_size
                while remaining:
                    need(time.monotonic()<deadline,"JOURNAL_HEALTH_COPY_BUDGET_EXCEEDED")
                    chunk=inp.read(min(1048576,remaining))
                    need(bool(chunk),"JOURNAL_HEALTH_COPY_TRUNCATED")
                    out.write(chunk)
                    remaining-=len(chunk)
            out.flush()
            os.fsync(out.fileno())
        need(time.monotonic()<deadline,"JOURNAL_HEALTH_COPY_BUDGET_EXCEEDED")
        after=source.lstat()
        need((after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns)
             ==(prior.st_dev,prior.st_ino,prior.st_size,prior.st_mtime_ns),
             "JOURNAL_HEALTH_COPY_SOURCE_CHANGED")
    finally:os.close(fd)


@contextmanager
def readonly_active_copy(profile,*,temp_root=None):
    """Read SQLite only from a private copy, never from live WAL in sandbox.

    All governed journal writers hold shared p.gate(); exclusive gate prevents
    a torn data/WAL file snapshot. Live files are opened O_RDONLY|O_NOFOLLOW.
    The only new WAL/shm files are created in a private writable scratch dir.
    """
    with tempfile.TemporaryDirectory(prefix="journal-health-private-",dir=temp_root) as temp:
        dest=Path(temp)/"active.sqlite3"
        with profile.gate(exclusive=True):
            deadline=time.monotonic()+COPY_SECONDS
            catalog,digest=covered_catalog(profile)
            need(catalog["mode"]=="segmented","JOURNAL_HEALTH_PRIVATE_REQUIRES_SEGMENTED")
            profile.active_identity()
            need(profile.active.stat().st_size<=profile.ceiling_bytes,
                 "JOURNAL_HEALTH_ACTIVE_CEILING_EXCEEDED")
            _copy_locked(profile.active,dest,profile.writer_uid,profile.ceiling_bytes,deadline)
            wal=Path(str(profile.active)+"-wal")
            before=os.path.lexists(wal)
            if before:
                _copy_locked(wal,Path(str(dest)+"-wal"),profile.writer_uid,profile.ceiling_bytes,deadline)
            need(os.path.lexists(wal)==before,"JOURNAL_HEALTH_WAL_SOURCE_CHANGED")
        yield dest,catalog,digest


def full_integrity(path,*,profile=None,temp_root=None):
 if profile is None:need(enabled(),"JOURNAL_HEALTH_PROFILE_NOT_ENABLED")
 p=profile or JournalProfile.load(PROFILE)
 need(Path(path)==p.active,"JOURNAL_HEALTH_CANONICAL_PATH")
 with p.gate():
  catalog,digest=covered_catalog(p)
  if catalog["mode"]=="legacy":
   p.active_identity()
   active=journal_sql.active_state(p.active)
   need(active["oldest_outcome_age_seconds"] is None or active["oldest_outcome_age_seconds"]<=60,
        "JOURNAL_HEALTH_OUTCOME_RECONCILIATION_REQUIRED")
   with journal_sql.connection(p.active) as db:
    need(db.execute("PRAGMA integrity_check").fetchone()[0]=="ok","JOURNAL_FULL_INTEGRITY_FAILED")
   return {"integrity":"ok","mode":"legacy","catalog_sha256":digest,
           "generation":catalog["generation"],"epoch":catalog["epoch"],"closed_segments":0}
 with readonly_active_copy(p,temp_root=temp_root) as (private,catalog,digest):
  active=journal_sql.active_state(private)
  need(active["oldest_outcome_age_seconds"] is None or active["oldest_outcome_age_seconds"]<=60,
       "JOURNAL_HEALTH_OUTCOME_RECONCILIATION_REQUIRED")
  # Private SQLite copy is the only live-derived source used by backup().
  with tempfile.TemporaryDirectory(prefix="journal-health-proof-",dir=temp_root) as scratch:
   snapshot=Path(scratch)/"snapshot.sqlite3"
   state=journal_sql.snapshot(private,snapshot,seconds=60)
   need(state["epoch"]==catalog["epoch"],"JOURNAL_HEALTH_SNAPSHOT_EPOCH")
   original=journal_sql.proof(snapshot)
   restored=Path(scratch)/"restored.sqlite3"
   shutil.copyfile(snapshot,restored);restored.chmod(0o600)
   restore=journal_sql.proof(restored)
   need(original==restore,"JOURNAL_HEALTH_RESTORE_PARITY")
   with p.gate():
    _,current=covered_catalog(p)
    need(current==digest,"JOURNAL_HEALTH_GENERATION_CHANGED")
   return {"integrity":"ok","mode":"segmented","catalog_sha256":digest,
           "generation":catalog["generation"],"epoch":catalog["epoch"],
           "closed_segments":len(catalog["segments"]),"active_snapshot":original,
           "active_restore":restore,"provider_credentials_used":False}


def validate_full_evidence(evidence,*,profile=None,temp_root=None):
 if profile is None:need(enabled(),"JOURNAL_HEALTH_PROFILE_NOT_ENABLED")
 p=profile or JournalProfile.load(PROFILE)
 with p.gate():
  catalog,digest=covered_catalog(p)
 if catalog["mode"]=="segmented":
  # Native frequent checker has existing RW /var/lib/jason/openclaw.
  scratch=(Path("/var/lib/jason/openclaw") if profile is None and temp_root is None
           else p.archives if temp_root is None else Path(temp_root))
  with readonly_active_copy(p,temp_root=scratch) as (private,catalog,digest):
   active=journal_sql.active_state(private)
 else:
  with p.gate():
   active=journal_sql.active_state(p.active)
 need(active["oldest_outcome_age_seconds"] is None or active["oldest_outcome_age_seconds"]<=60,
      "JOURNAL_HEALTH_OUTCOME_RECONCILIATION_REQUIRED")
 proof=evidence.get("orchestration_journal")
 if catalog["mode"]=="legacy" and proof is None:return True
 need(isinstance(proof,dict) and proof.get("integrity")=="ok"
      and proof.get("catalog_sha256")==digest and proof.get("mode")==catalog["mode"]
      and proof.get("generation")==catalog["generation"]
      and proof.get("epoch")==catalog["epoch"],"JOURNAL_FULL_EVIDENCE_COVERAGE_CHANGED")
 if catalog["mode"]=="segmented":
  need(proof.get("active_snapshot",{}).get("integrity")=="ok"
       and proof.get("active_snapshot")==proof.get("active_restore")
       and proof.get("closed_segments")==len(catalog["segments"]),
       "JOURNAL_FULL_EVIDENCE_SNAPSHOT_REQUIRED")
 return True
