"""Adopted journal integrity evidence; all legacy authority checks remain separate."""
from __future__ import annotations
from datetime import datetime,timezone,timedelta
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import tempfile
from .segmented_journal import JournalProfile,PROFILE,need
from . import journal_sql

MAX_SCRUB_AGE=timedelta(days=31)

def canonical(value):
 return json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False).encode()

def covered_catalog(profile,*,now=None):
 now=now or datetime.now(timezone.utc)
 value=profile.catalog()
 need(value["mode"] in ("legacy","segmented"),"JOURNAL_HEALTH_UNSEALED_HISTORY")
 for record in value["segments"]:
  profile.artifact(record)
  need(record["state"]=="sealed","JOURNAL_HEALTH_PENDING_SEGMENT")
  proof=record["proof"]
  need(proof["integrity"]=="ok" and proof["restore_verified"] is True
       and type(proof["events"]) is int and proof["events"]>=0
       and len(proof["file_sha256"])==64,"JOURNAL_HEALTH_SEGMENT_PROOF")
  verified=datetime.fromisoformat(proof.get("last_scrub_at",proof["full_verified_at"]))
  need(verified.tzinfo is not None and timedelta(0)<=now-verified<=MAX_SCRUB_AGE,
       "JOURNAL_HEALTH_HISTORICAL_SCRUB_DUE")
  for item in record.get("filters",{}).values():
   profile.artifact(record,filter_record=item)
 return value,sha256(canonical(value)).hexdigest()

def full_integrity(path,*,profile=None,temp_root=None):
 if profile is None:need(enabled(),"JOURNAL_HEALTH_PROFILE_NOT_ENABLED")
 p=profile or JournalProfile.load(PROFILE)
 need(Path(path)==p.active,"JOURNAL_HEALTH_CANONICAL_PATH")
 with p.gate():
  catalog,digest=covered_catalog(p)
  p.active_identity()
  if catalog["mode"]=="legacy":
   with journal_sql.connection(p.active) as db:
    need(db.execute("PRAGMA integrity_check").fetchone()[0]=="ok","JOURNAL_FULL_INTEGRITY_FAILED")
   return {"integrity":"ok","mode":"legacy","catalog_sha256":digest,
           "generation":catalog["generation"],"epoch":catalog["epoch"],"closed_segments":0}
  need(p.active_bytes()<=p.ceiling_bytes,"JOURNAL_HEALTH_ACTIVE_CEILING_EXCEEDED")
  # The online backup is consistent while normal writers continue under SH.
  scratch=tempfile.TemporaryDirectory(prefix="journal-health-",dir=temp_root)
  try:
   snapshot=Path(scratch.name)/"snapshot.sqlite3"
   state=journal_sql.snapshot(p.active,snapshot,seconds=60)
  except BaseException:
   scratch.cleanup();raise
 try:
  need(state["epoch"]==catalog["epoch"],"JOURNAL_HEALTH_SNAPSHOT_EPOCH")
  original=journal_sql.proof(snapshot)
  restored=Path(scratch.name)/"restored.sqlite3"
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
 finally:scratch.cleanup()

def validate_full_evidence(evidence,*,profile=None):
 if profile is None:need(enabled(),"JOURNAL_HEALTH_PROFILE_NOT_ENABLED")
 p=profile or JournalProfile.load(PROFILE)
 with p.gate():
  catalog,digest=covered_catalog(p)
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

def enabled():
 value=os.getenv("JASON_ORCHESTRATION_EVENT_JOURNAL_PROFILE","")
 if value:need(value==str(PROFILE),"JOURNAL_FIXED_PROFILE_REQUIRED")
 return bool(value)
