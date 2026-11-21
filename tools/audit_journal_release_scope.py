"""Exact, reviewable scope of the bounded audit-journal installation."""
from __future__ import annotations
from hashlib import sha256
import json
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
  "same_base_images":BASE_IMAGES,"initial_container_replacements":3,
  "possible_recovery_container_replacements":3,"availability_interruption_authorized":True,
  "inflight_write_drain_required":True,"historical_consumed_claims_unchanged":True,
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
