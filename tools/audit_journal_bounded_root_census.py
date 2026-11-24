"""Read-only forensic census of the exact Root-owned audit journal scope.

Never changes a source, credential, policy, ticket, journal, service, approval,
container, database or audit file. No Owner authentication is invoked.
Outputs ONLY safe field names, hash equalities, enums, age and capacity values.
"""
from __future__ import annotations
import hashlib,json,os,stat,sys,shutil
from datetime import datetime,timezone
from pathlib import Path

BASE=Path("/var/lib/jason-audit-journal")
PLAN=BASE/"private/release-plan.json"
JOURNAL=BASE/"private/release-journal.json"
BEFORE=BASE/"private/producer-before.json"
ADOPTION=BASE/"private/adoption.json"
CATALOG=BASE/"control/catalog.json"
POLICY=Path("/etc/jason-owner-release/audit-journal-v1.json")
DESIRED=Path("/etc/jason/release-readback-recovery/production-desired-state.json")
DESIRED_FILES=("desired-final.json","desired-rollback.json")
STATE=Path("/var/lib/jason/openclaw/release-manager")
DB=Path("/var/lib/jason/governed-ticket-shared/orchestration-events.sqlite3")
ARCHIVE=Path("/srv/jason/archive")
EXPECTED_SCOPE="ac1fd3d27c31875cdb263c614aaea11fae72f54d0bc2df9db79dc0f28d1ecac3"
EXPECTED_CANDIDATE="20b32548402d160f9c6a5ee33a0a17592eb9fa68"
EXPECTED_OWNER="bee80bdc-ffb0-4c50-b453-c09d4d411f5f"
HISTORIC_FIELDS=(
 "rollback_container_limit_before",
 "rollback_container_limit_after",
 "rollback_container_reserve",
 "rollback_container_capacity_before",
 "desired_state_after_sha256",
 "desired_state_initial_sha256",
 "rollback_desired_state_sha256",
 "source_dataset_identity",
 "protected_peer_before",
 "producer_before",
 "producer_after_configuration_sha256",
)
def canonical(obj):
 return json.dumps(obj,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
def sha(value):
 return hashlib.sha256(value if isinstance(value,bytes) else canonical(value)).hexdigest()
def read_json(path,mode):
 fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
 try:
  m=os.fstat(fd)
  assert stat.S_ISREG(m.st_mode) and m.st_uid==0 and m.st_gid==0
  assert stat.S_IMODE(m.st_mode)==mode and m.st_nlink==1
  assert 0<m.st_size<=2_000_000
  out=os.read(fd,m.st_size+1)
  assert len(out)==m.st_size
 finally:os.close(fd)
 return json.loads(out)
def check():
 assert os.geteuid()==0 and sys.flags.isolated==1
 p=read_json(PLAN,0o400)
 j=read_json(JOURNAL,0o400)
 prior=read_json(BEFORE,0o400)
 a=read_json(ADOPTION,0o400)
 policy=read_json(POLICY,0o600)
 cat=read_json(CATALOG,0o444)
 scope=p.get("scope")
 assert isinstance(scope,dict)
 # Do not emit private Owner identity, source hashes or full scope values.
 result={"action":"read_only_protected_audit_journal_evidence",
         "production_mutations":False,"owner_challenge":False,
         "exact_plan_sha256_matches_current_scope":p.get("scope_sha256")==EXPECTED_SCOPE,
         "plan_scope_content_matches_sha256":sha(scope)==EXPECTED_SCOPE,
         "old_exact_candidate_matches":p.get("candidate_sha")==EXPECTED_CANDIDATE,
         "licensed_owner_recorded":p.get("owner_oid")==EXPECTED_OWNER and
                                   p.get("independently_verified_entra_owner") is True,
         "scope_field_presence":{k:k in scope for k in HISTORIC_FIELDS},
         "scalar_rollback_field_values":{
          k:(scope.get(k) if isinstance(scope.get(k),(int,float,str,type(None))) else "NONSCALAR")
          for k in HISTORIC_FIELDS[:3]},
         "historical_retention_snapshot_summary":{},
         "scope_extra_keys":sorted(k for k in scope if
                                  "rollback" in k or "desired_state" in k),
         "journal_steps":sorted(j.get("steps",{})),
         "journal_outcome_present":"outcome" in j,
         "journal_recovery_marker_present":"recovery_started_at" in j,
         "journal_scope_matches":j.get("scope_sha256")==EXPECTED_SCOPE,
         "before_matches_plan":sha(prior)==p.get("producer_before_sha256"),
         "producer_role_names":sorted(prior),
         "policy_candidate_matches":policy.get("candidate_sha")==EXPECTED_CANDIDATE,
         "policy_trusted_source_matches":policy.get("trusted_source_sha256")==scope.get("source_sha256"),
         "adoption_scope_matches":a.get("scope_sha256")==EXPECTED_SCOPE,
         "legacy_catalog_matches":cat.get("mode")=="legacy" and
                                  cat.get("generation")==0 and
                                  cat.get("epoch") is None and
                                  cat.get("segments")==[],
         "desired_proofs":{},
         "protected_native_state":{}}
 snap=scope.get("rollback_container_capacity_before")
 if isinstance(snap,dict):
  result["historical_retention_snapshot_summary"]={
     "key_names":sorted(snap),
     "existing_count":snap.get("existing_count") if isinstance(snap.get("existing_count"),int) else None,
     "limit_before":snap.get("limit_before") if isinstance(snap.get("limit_before"),int) else None,
     "reserved_slots":snap.get("reserved_slots") if isinstance(snap.get("reserved_slots"),int) else None,
     "existing_names_length":len(snap.get("existing_names",[])) if isinstance(snap.get("existing_names"),list) else None}
 else:result["historical_retention_snapshot_summary"]={"type":type(snap).__name__}
 for name in DESIRED_FILES:
  data=read_json(BASE/"private"/name,0o400)
  expected_key=("desired_state_after_sha256" if name=="desired-final.json"
                else "rollback_desired_state_sha256")
  result["desired_proofs"][name+"_matches_approved_scope"]=sha(data)==scope.get(expected_key)
 current=read_json(DESIRED,0o600)
 result["desired_proofs"]["live_desired_matches_canonical_initial_or_rollback"]=sha(current) in {
  scope.get("desired_state_initial_sha256"),scope.get("rollback_desired_state_sha256")}
 result["desired_proofs"]["live_desired_json_sha256_equals_raw_bytes_sha256"]=(
   sha(current)==hashlib.sha256(DESIRED.read_bytes()).hexdigest())
 d=DB.lstat()
 result["dataset_dev_inode_identity_matches"]=(d.st_dev,d.st_ino)==(66306,10261846)
 result["dataset_size_bytes"]=d.st_size
 free=shutil.disk_usage(ARCHIVE).free
 result["archive_free_bytes"]=free
 result["archive_required_bytes"]=d.st_size*3+4563402752
 result["archive_capacity_pass"]=free>d.st_size*3+4563402752
 try:
  ctrl=read_json(STATE/"production-control-state.json",0o600)
  drift=read_json(STATE/"production-drift.json",0o600)
  observed=datetime.fromisoformat(drift["observed_at"].replace("Z","+00:00"))
  result["protected_native_state"]={
   "breaker_state":ctrl.get("circuit_breaker",{}).get("state"),
   "breaker_reason":ctrl.get("circuit_breaker",{}).get("reason"),
   "drift_status":drift.get("status"),
   "drift_age_seconds":round((datetime.now(timezone.utc)-observed).total_seconds(),1),
   "problem_codes":[[x.get("kind"),x.get("unit") or x.get("name"),x.get("state")]
        for x in drift.get("problems",[]) if isinstance(x,dict)]}
 except Exception as exc:
  result["protected_native_state"]={"read_failed_type":type(exc).__name__}
 assert result["exact_plan_sha256_matches_current_scope"]
 assert result["plan_scope_content_matches_sha256"]
 assert result["old_exact_candidate_matches"]
 assert result["licensed_owner_recorded"]
 print(json.dumps(result,sort_keys=True,separators=(",",":"),allow_nan=False),flush=True)
 print("READONLY_PROTECTED_SCOPE_CENSUS=PASS",flush=True)

if __name__=="__main__":check()
