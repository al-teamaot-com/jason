"""Exact, reviewable scope of the bounded audit-journal installation."""
from __future__ import annotations
from hashlib import sha256
from datetime import datetime,timezone
import json
import os
import re
import stat
import subprocess
from pathlib import Path

ACTION="ADOPT-EXACT-DAILY-AUDIT-JOURNAL"
ROLLBACK="d1b8c196dadd4b672ec8ba47075f27bb61c98d63"
OWNER="bee80bdc-ffb0-4c50-b453-c09d4d411f5f"
TENANT="f7054323-d52b-4863-8c2f-1898f0b6077c"
BASE=Path("/usr/local/lib/jason/audit-journal")
PRIVATE=Path("/var/lib/jason-audit-journal/private")
POLICY=Path("/etc/jason-owner-release/audit-journal-v1.json")
ACTIVE=Path("/var/lib/jason/governed-ticket-shared/orchestration-events.sqlite3")
ARCHIVE=Path("/srv/jason/archive")
CONTROL=Path("/var/lib/jason-audit-journal/control")
PROFILE=Path("/run/jason/audit-journal/profile.json")
DESIRED=Path("/etc/jason/release-readback-recovery/production-desired-state.json")
STATE=Path("/var/lib/jason/openclaw/release-manager")
SOURCES=(
 "tools/audit_journal_control.py","tools/audit_journal_container_release.py",
 "tools/audit_journal_legacy_reconcile_worker.py","tools/audit_journal_release_scope.py",
 "tools/audit_journal_release_executor.py",
 "implementation/orchestrator/event_store.py","implementation/orchestrator/segmented_journal.py",
 "implementation/orchestrator/journal_sql.py","implementation/orchestrator/journal_health.py",
 "implementation/orchestrator/journal_recovery.py","implementation/orchestrator/journal_mount.py",
 "implementation/orchestrator/journal_outcomes.py",
)
NATIVE={
 "tools/audit_journal_operational_health.py":"openclaw_authority_operational_health.py",
 "tools/audit_journal_fast_health.py":"openclaw_authority_fast_health.py",
 "tools/audit_journal_full_health_snapshot.py":"openclaw_authority_live_audit_full_snapshot.py",
 "tools/openclaw_authority_health_snapshot.py":"openclaw_authority_health_snapshot.py",
}
UNITS=(
 "jason-audit-journal-data-recovery.service","jason-audit-journal-maintenance.service",
 "jason-audit-journal-maintenance.timer","jason-audit-journal-release.service",
)
TARGETS=(
 "/var/lib/jason-owner-release/audit-journal-install",str(BASE),str(POLICY),"/var/lib/jason-audit-journal",str(PROFILE.parent),
 "/var/lib/jason/governed-ticket-shared/journal-work",str(ACTIVE),
 str(ARCHIVE),str(ARCHIVE/"governed-audit"),str(ARCHIVE/"authority-health-scratch"),
 *(str(Path("/etc/systemd/system")/unit) for unit in UNITS),
 "/etc/systemd/system/multi-user.target.wants/jason-audit-journal-release.service",
 "/etc/systemd/system/timers.target.wants/jason-audit-journal-maintenance.timer",
 "/etc/systemd/system/docker.service.d/93-jason-audit-data-recovery.conf",
 "/etc/systemd/system/jason-pmv4-component-reconcile.service.d/94-audit-data-compatible-release.conf",
 "/etc/systemd/system/jason-release-host-reconcile.service.d/94-audit-data-compatible-release.conf",
 "/etc/systemd/system/jason-openclaw-authority-health.service.d/94-audit-journal.conf",
 "/etc/systemd/system/jason-openclaw-authority-full-integrity.service.d/94-audit-journal.conf",
 str(DESIRED),
)
PROTECTED={
 "/usr/local/lib/jason/release_host_reconcile_worker.py":
  "dca0c480265426c3c73f9cf8f7b8a9a4c5ab555640bd6953eb127cf3963a1896",
 "/etc/jason-owner-release/pmv4-e/replacement-retirement-accepted.json":
  "a74d159851ca82cd1d94e996ee9469cc7ad923046d36f642c341a8a90fd20141",
 str(STATE/"production-deployment-freeze"):
  "bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f",
 str(STATE/"auto-promotion-incident-hold"):
  "11f0f78904236c36ebd1aeee58f52fcecba035bce33d15ce323b36d36ad5a5a0",
 "/var/lib/jason/openclaw/support-repair/pmv3-engineering-owner-pause.json":
  "4a5de8286bf9d77842ca94dafe6f1d38c1a835e8f12bc0dfda46b7a3cf867747",
}
BASE_IMAGES={
 "jason-runtime":"sha256:c43f9f7364a4b2b16bdec261fa35db2b861eabe959ba818f689582bbb1b7d132",
 "jason-mcp-pilot":"sha256:b2f74bf1513568f6c9df7a2ffa764b1a5f43303c8317702741d646f223db1477",
 "jason-pmv4-ticket-core":"sha256:a949be281262b94da02c7438f7a2cd97521d83749a8e27f0c01768b3d0353185",
}
# The preproduction shadow is not an audit database writer or producer. P0
# health recovery and audit-only cutover must never mutate it. Its health state
# is recorded, but an otherwise exact, network-isolated and immutable shadow
# is not a prerequisite for genuine native SQLite recovery. The five actual
# production peers remain hard health requirements. No native drift exception.
OWNER_EXACT_ROOT_POLICY=Path("/etc/jason-owner-release/audit-journal-owner-executor-v1.json")
OWNER_MCP_BASE_IMAGE=BASE_IMAGES["jason-mcp-pilot"]


def current_base_images(candidate=None, *, observed_mcp_image=None):
 """Allow only a separately Root-attested exact additive Owner MCP image.

 An observed original MCP needs no optional overlay grant. Missing policy
 permits only the original immutable MCP; no request, environment
 variable, source-only change or model assertion can authorize a different
 production peer. The one-use Root-installed file binds image, code SHA,
 protected Main, LKG and expiry. All other production images stay exact.
 """
 images=dict(BASE_IMAGES)
 # The original immutable MCP image is independently allowed by the baseline.
 # Only an actual non-baseline image needs the optional overlay grant. Callers
 # obtain this selector from Docker inspection, never a request or environment.
 if observed_mcp_image==OWNER_MCP_BASE_IMAGE:return images
 policy_path=OWNER_EXACT_ROOT_POLICY
 if not os.path.lexists(policy_path):return images
 try:
  m=policy_path.lstat();parent=policy_path.parent.lstat()
  if (policy_path.is_symlink() or not stat.S_ISREG(m.st_mode)
      or m.st_uid!=0 or stat.S_IMODE(m.st_mode)!=0o600
      or m.st_nlink!=1 or m.st_size>8192
      or parent.st_uid!=0 or parent.st_mode&0o022):
   raise ValueError("OWNER_ROOT_TRUST_CUSTODY")
  policy=json.loads(policy_path.read_bytes())
  candidate_sha=policy.get("candidate_sha")
  overlay=policy.get("mcp_overlay_image_id")
  base=policy.get("mcp_base_image_id")
  expire=datetime.fromisoformat(policy["expires_at"])
  if (policy.get("schema_version")!="1.0"
      or policy.get("action")!="ADOPT-EXACT-DAILY-AUDIT-JOURNAL"
      or not isinstance(candidate_sha,str)
      or re.fullmatch(r"[0-9a-f]{40}",candidate_sha) is None
      or candidate is not None and candidate!=candidate_sha
      or policy.get("rollback_sha")!=ROLLBACK
      or base!=OWNER_MCP_BASE_IMAGE
      or not isinstance(overlay,str)
      or re.fullmatch(r"sha256:[0-9a-f]{64}",overlay) is None
      or policy.get("one_use_executor") is not True
      or policy.get("global_freeze_unchanged") is not True
      or policy.get("standing_authority") is not False
      or expire.tzinfo is None
      or not datetime.now(timezone.utc)<expire):
   raise ValueError("OWNER_ROOT_TRUST_SCOPE")
  cmd=subprocess.run(["/usr/bin/docker","image","inspect",overlay],
                     capture_output=True,text=True,timeout=18,check=False)
  if cmd.returncode:raise ValueError("OWNER_ADDON_IMAGE_MISSING")
  rows=json.loads(cmd.stdout)
  if not isinstance(rows,list) or len(rows)!=1:raise ValueError("OWNER_ADDON_AMBIGUOUS")
  row=rows[0];labels=row.get("Config",{}).get("Labels",{})
  if (row.get("Id")!=overlay
      or labels.get("com.teamaot.jason.audit_overlay_reviewed_main_sha")!=candidate_sha
      or labels.get("com.teamaot.jason.audit_overlay_base_image_sha256")!=base[7:]
      or labels.get("com.teamaot.jason.audit_overlay_purpose")!=
       "one-use-owner-archive-adoption"
      or row.get("Config",{}).get("User")!="1000:1000"):
   raise ValueError("OWNER_ADDON_IMAGE_PROVENANCE")
  images["jason-mcp-pilot"]=overlay
  return images
 except (OSError,ValueError,KeyError,TypeError,subprocess.TimeoutExpired) as exc:
  raise PermissionError("AUDIT_OWNER_MCP_EXACT_PROVENANCE_DENIED") from exc


EXPECTED_PEER_IMAGES={
 **BASE_IMAGES,
 "jason-pmv4-shadow-gateway":"sha256:679d3334efe7fbe32878b10fb06077912b57473bc3998316d26e9fd7a3d46bbd",
 "jason-teams-gateway":"sha256:0a3529f8052ee85516b3fd73e2f2f4edae7748fd7633ecaf7ae5a318602eb4f5",
 "openbao":"sha256:5b2486ab0fb90bbc788cc345b0a08616dfb375873ee8be5df3a2fd4d378a67e0",
}

def protected_peer_inventory():
 """Exact reviewed P0 and journal-scope peers, no preprod health waiver elsewhere."""
 try:
  result=subprocess.run(["/usr/bin/docker","inspect","--type","container",
     *EXPECTED_PEER_IMAGES],capture_output=True,text=True,timeout=28,check=False)
  if result.returncode:raise ValueError("AUDIT_PEER_INSPECT_FAILED")
  rows=json.loads(result.stdout)
 except (OSError,ValueError,subprocess.TimeoutExpired) as exc:
  raise PermissionError("AUDIT_PEER_INVENTORY_UNAVAILABLE") from exc
 if not isinstance(rows,list) or len(rows)!=len(EXPECTED_PEER_IMAGES):
  raise PermissionError("AUDIT_PEER_INVENTORY_INCOMPLETE")
 verified={}
 mcp=[row for row in rows if isinstance(row,dict)
      and str(row.get("Name","")).lstrip("/")=="jason-mcp-pilot"]
 if len(mcp)!=1:raise PermissionError("AUDIT_PEER_NAME_UNTRUSTED:mcp_inventory")
 active_expected={**EXPECTED_PEER_IMAGES,**current_base_images(
     observed_mcp_image=mcp[0].get("Image"))}
 for row in rows:
  name=str(row.get("Name","")).lstrip("/")
  if name not in EXPECTED_PEER_IMAGES or name in verified:
   raise PermissionError("AUDIT_PEER_NAME_UNTRUSTED")
  state=row.get("State") or {}
  health=(state.get("Health") or {}).get("Status","none")
  if (row.get("Image")!=active_expected[name]
      or not state.get("StartedAt")
      or not isinstance(row.get("Id"),str) or len(row["Id"])<30):
   raise PermissionError("AUDIT_PEER_IDENTITY_UNTRUSTED:"+name)
  # A separately constrained *nonproduction* shadow may have reached its
  # signed 4 GiB Docker OOM limit while the genuine ~45 GB FULL scan ran.
  # Only this exact already-terminated, no-restart, no-network, no-provider
  # case is admissible to unrelated audit Root cleanup. All actual production
  # peers MUST still be running and healthy; no Stage E readiness waiver.
  is_shadow=name=="jason-pmv4-shadow-gateway"
  shadow_oom_stopped=(is_shadow and state.get("Running") is False
      and state.get("Status")=="exited" and state.get("OOMKilled") is True
      and state.get("ExitCode")==137 and state.get("Pid")==0
      and row.get("RestartCount")==0 and health=="unhealthy")
  need_running=state.get("Running") is True
  if not (need_running or shadow_oom_stopped):
   raise PermissionError("AUDIT_PEER_RUNNING_STATE_UNTRUSTED:"+name)
  if is_shadow:
   h=row.get("HostConfig") or {};conf=row.get("Config") or {};labels=conf.get("Labels") or {}
   mounts=row.get("Mounts") or []
   isolated=(h.get("NetworkMode")=="none" and h.get("ReadonlyRootfs") is True
      and h.get("Memory")==4294967296 and h.get("NanoCpus")==1000000000
      and h.get("PidsLimit")==256 and h.get("Privileged") is False
      and (h.get("RestartPolicy") or {}).get("Name")=="no"
      and h.get("CapDrop")==["ALL"]
      and "no-new-privileges:true" in (h.get("SecurityOpt") or [])
      and conf.get("User")=="1000:1000"
      and labels.get("com.aot.jason.component")=="pmv4-shadow"
      and labels.get("com.aot.jason.lifecycle")=="preproduction-only"
      and labels.get("com.aot.jason.provider-mutation")=="disabled"
      and labels.get("com.aot.jason.production-core")=="excluded"
      and labels.get("com.aot.jason.source_revision")=="75f2b4c0c48a15bd17d700b9f039fe56623e3f52"
      and isinstance(mounts,list) and len(mounts)==1
      and mounts[0].get("Type")=="volume"
      and mounts[0].get("Destination")=="/home/node/.openclaw"
      and not h.get("PortBindings") and not h.get("Devices"))
   if not isolated or health not in ("healthy","unhealthy"):
    raise PermissionError("AUDIT_PREPRODUCTION_SHADOW_ISOLATION_UNTRUSTED")
  else:
   if health not in ("healthy","none"):
    raise PermissionError("AUDIT_PRODUCTION_PEER_UNHEALTHY:"+name)
   if name in ("jason-runtime","jason-pmv4-ticket-core") and health!="healthy":
    raise PermissionError("AUDIT_REQUIRED_PRODUCTION_HEALTH_MISSING:"+name)
   if name in ("jason-runtime","jason-mcp-pilot"):
    if (row.get("Config",{}).get("Labels") or {}).get("com.teamaot.jason.source_revision")!=ROLLBACK:
     raise PermissionError("AUDIT_PRODUCTION_LKG_LABEL_CHANGED:"+name)
  verified[name]={"id":row["Id"],"image":row["Image"],
                  "started_at":state["StartedAt"],"health":health,
                  "preproduction_only":is_shadow}
  if is_shadow:
   verified[name].update({"running":need_running,
       "oom_killed":shadow_oom_stopped,
       "exit_code":137 if shadow_oom_stopped else None,
       "observed_state":"exact_oom_stopped" if shadow_oom_stopped
                        else "running_isolated_preproduction"})
 if set(verified)!=set(EXPECTED_PEER_IMAGES):
  raise PermissionError("AUDIT_PRODUCTION_PEER_SET_CHANGED")
 return verified

BASE_STORE="9648faaa0007f95cbc0ad616c99551c90ba49aef462bbf0db5bb6203f6bb91b9"
DESIRED_BEFORE="9110f982e7294fa789c8cd976223aa223143e924fd8bcec368f72b83a8d785b1"

def canonical(value):return json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
def digest(value):return sha256(canonical(value)).hexdigest()

def public_profile(candidate):
 return {"schema_version":"1.0","enabled":True,"adoption":"root_adopted",
  "component_source_sha":candidate,"active":str(ACTIVE),"control":str(CONTROL),
  "archives":str(ARCHIVE/"governed-audit/orchestration"),"pending":"/var/lib/jason-audit-journal/pending",
  "writer_uid":1000,"target_bytes":1073741824,"ceiling_bytes":2147483648,
  "maximum_event_bytes":262144,"execution_reserve_bytes":25165824,"maximum_inflight":32,"cached_archives":32}

def desired_after(before):
 value=json.loads(json.dumps(before))
 for field,unit in (("required_system_units","jason-audit-journal-data-recovery.service"),
                    ("required_system_units","jason-audit-journal-maintenance.timer"),
                    ("allowed_system_units","jason-audit-journal-maintenance.service"),
                    ("allowed_system_units","jason-audit-journal-release.service")):
  if unit not in value[field]:value[field].append(unit);value[field].sort()
 prefix="jason-pmv4-ticket-core-rollback-audit-"
 if prefix not in value["rollback_container_prefixes"]:value["rollback_container_prefixes"].append(prefix)
 return value

def desired_rollback(before):
 # Legacy applications still need the event-preserving archive mount at boot.
 # The archive maintenance timer stays installed but is explicitly stopped.
 value=desired_after(before)
 value["required_system_units"].remove("jason-audit-journal-maintenance.timer")
 value["allowed_system_units"].append("jason-audit-journal-maintenance.timer")
 value["allowed_system_units"].sort()
 return value

def reviewed_scope(candidate,code_hashes,native_hashes,unit_hashes,facts):
 return {"schema_version":"1.0","action":ACTION,"policy":{"candidate_sha":candidate,"rollback_sha":ROLLBACK},
  "installation_targets":list(TARGETS),"queue_cutover":True,"source_sha256":code_hashes,
  "native_health_sha256":native_hashes,"unit_source_sha256":unit_hashes,
  "source_dataset_identity":facts["dataset_identity"],
  "producer_before":facts["producer_before"],"producer_after_configuration_sha256":facts["producer_after"],
  "same_base_images":current_base_images(candidate,observed_mcp_image=
      facts.get("producer_before",{}).get("jason-mcp-pilot",{}).get("image")),
  "initial_container_replacements":3,
  "possible_recovery_container_replacements":3,"availability_interruption_authorized":True,
  "inflight_write_drain_required":True,"historical_consumed_claims_unchanged":True,
  "cross_release_transaction_exclusion_required":True,
  "release_initiated_business_provider_writes":0,
  "docker_boot_waits_for_journal_data_recovery":True,"docker_daemon_restart_performed":False,
  "claimed_temporary_work_cleanup_allowed":True,"published_archive_cleanup_allowed":False,
  "interrupted_sql_helper_cleanup":"exact_spawned_process_group_only",
  "archive_root_metadata_before":facts["archive_root_metadata"],
  "archive_root_metadata_after":{"uid":0,"gid":0,"mode":"0o755","recursive":False},
  "desired_state_before_sha256":DESIRED_BEFORE,"desired_state_after_sha256":facts["desired_after_sha256"],
  "protected_unchanged_sha256":PROTECTED,"business_provider_writes":0,"approval_database_mutations":0,
  "off_host_backup_claimed":False,"archive_history_delete_allowed":False,
  "maximum_source_bytes":68719476736,"maximum_execution_seconds":28800,"maximum_recovery_seconds":28800,
  "initial_owner_claim_one_use":True,"daily_storage_maintenance_explicitly_adopted":True,
  "rollback_preserves_post_cutover_events":True,
  "rollback_retains_data_recovery_support_and_archive_custody":True,
  "legacy_whole_host_reconciliation_requires_data_compatibility":True,
  "existing_native_health_deadline_seconds":5400,
  "legacy_first_verification_operation_deadline_seconds":10800}
