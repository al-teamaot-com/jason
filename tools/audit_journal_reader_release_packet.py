"""Prepare one exact governed Root release scope for archive-reader handle repair.

Source-only, no production writes, signatures, approvals, Root calls, Docker
actions, or restart. The actual release executor must independently verify
all this evidence again at immutable Root preflight.
"""
from __future__ import annotations

from hashlib import sha256
import json
import re

ACTION="RELEASE-EXACT-AUDIT-READER-HANDLE-CLOSURE"
READERS=("jason-pmv4-ticket-core","jason-runtime","jason-mcp-pilot")
READING_SOURCE="implementation/orchestrator/segmented_journal.py"
ROOT_SOURCE="tools/audit_journal_no_restore_worker.py"
SUFFIX_RE=re.compile(r"sha256:[0-9a-f]{64}\Z")
SHA_RE=re.compile(r"[0-9a-f]{40}\Z")
GATES=(
    "independent_protected_main_ci_pass",
    "root_owned_candidate_source_and_previous_source_sha256",
    "independently_authenticated_licensed_owner_exact_scope",
    "immutable_one_use_transaction_and_explicit_production_freeze_exception",
    "root_readback_native_breaker_and_drift_pass",
    "three_live_consumer_id_and_image_preflight",
    "verified_retained_archive_identity_and_active_journal",
    "no_prior_release_worker_running_or_outstanding_rotation",
)
POSTFLIGHT=(
    "all_three_consumers_healthy_same_mounts_and_no_config_drift",
    "zero_sealed_archive_SQLite_fds_after_read_or_exception",
    "historical_and_active_event_read_parity",
    "genuine_current_event_append_and_read_no_provider_write",
    "actual_maintenance_service_result_success_and_real_rollover",
    "native_full_fast_integrity_and_independent_drift_pass",
    "same_global_freeze_state_and_root_journal_policy",
)
ROLLBACK=(
    "atomically_restore_before_images_of_exact_root_worker_and_runtime_containers",
    "restore_exact_original_three_consumer_images_and_configuration",
    "verify_old_instances_running_or_safe_maintenance_pause",
    "verify_original_sealed_and_active_journal_unchanged",
    "record_immutable_failure_without_replaying_or_resetting_approval",
)
NO_ACTION=(
    "no_historical_record_deletion",
    "no_sqlite_db_reconstruction_or_storage_relocation",
    "no_root_approval_claim_from_source_packet",
    "no_provider_writes_or_external_ticket_mutations",
    "no_reboot_or_network_reset",
)


def need(ok,why):
    if not ok:
        raise ValueError("AUDIT_READER_RELEASE_"+why)


def canon(payload):
    return json.dumps(payload,sort_keys=True,separators=(",",":"),allow_nan=False).encode()


def bind_scope(*,candidate,rollback_main,source_blobs,prior_images,prior_source_digests,
               desired_policy_sha256,freeze_sha256,archive_sha256,
               protected_peer_ids):
    need(isinstance(candidate,str) and SHA_RE.fullmatch(candidate),"CANDIDATE_SHA")
    need(isinstance(rollback_main,str) and SHA_RE.fullmatch(rollback_main)
         and candidate!=rollback_main,"ROLLBACK_SHA")
    need(set(source_blobs)=={READING_SOURCE,ROOT_SOURCE}
         and all(isinstance(x,bytes) and x for x in source_blobs.values()),
         "EXACT_TWO_SOURCES")
    need(b"with closing(self._archive(record)) as db" in source_blobs[READING_SOURCE]
         and b"with closing(sqlite3.connect(" in source_blobs[ROOT_SOURCE],
         "CLOSED_READERS_REQUIRED")
    need(set(prior_images)==set(READERS)
         and all(isinstance(x,str) and SUFFIX_RE.fullmatch(x) for x in prior_images.values()),
         "EXACT_THREE_ORIGINAL_IMAGES")
    need(set(prior_source_digests)=={READING_SOURCE,ROOT_SOURCE}
         and all(isinstance(x,str) and re.fullmatch("[0-9a-f]{64}",x)
                 for x in prior_source_digests.values()),
         "BEFORE_IMAGES_REQUIRED")
    need(set(protected_peer_ids)==set(READERS)
         and all(isinstance(x,str) and re.fullmatch("[0-9a-f]{64}",x)
                 for x in protected_peer_ids.values()),
         "PEER_IDENTITY_REQUIRED")
    for v in (desired_policy_sha256,freeze_sha256,archive_sha256):
        need(isinstance(v,str) and re.fullmatch("[0-9a-f]{64}",v),"IMMUTABLE_CONTROL_SHA")
    payload={
        "schema_version":"1.0",
        "stage":"engineering_source_only_no_root_grant",
        "exact_action":ACTION,
        "candidate_main_sha":candidate,
        "rollback_source_main_sha":rollback_main,
        "reviewed_source_sha256":{x:sha256(data).hexdigest() for x,data in source_blobs.items()},
        "rollback_original_source_sha256":dict(sorted(prior_source_digests.items())),
        "exact_consumers":list(READERS),
        "original_consumer_image_ids":dict(sorted(prior_images.items())),
        "original_consumer_ids":dict(sorted(protected_peer_ids.items())),
        "source_control_proofs":{
            "production_desired_sha256":desired_policy_sha256,
            "global_freeze_sha256":freeze_sha256,
            "sealed_archive_sha256":archive_sha256,
        },
        "independent_root_admission_gates":list(GATES),
        "ordered_release_actions":[
            "capture_exact_root_backup_before_image_and_live_image_mount_env_restart_identity",
            "verify_exact_gate_after_owner_one_use_authorization",
            "install_new_reviewed_root_forward_worker_and_three_signed_runtime_images",
            "restart_only_three_named_consumers_with_existing_approved_interruption",
            "run_automatic_native_postflight_and_persist_readback",
            "mark_accepted_only_if_all_full_postflight_gates_pass",
        ],
        "automatic_acceptance_gates":list(POSTFLIGHT),
        "on_failed_check":list(ROLLBACK),
        "out_of_scope":list(NO_ACTION),
        "owner_signature_claimed":False,
        "root_installation_performed":False,
        "production_state_changed":False,
        "separate_30day_deletion_release_required":True,
    }
    return {"scope":payload,"scope_sha256":sha256(canon(payload)).hexdigest()}


def verify_packet(receipt):
    scope=receipt["scope"]
    need(sha256(canon(scope)).hexdigest()==receipt["scope_sha256"],
         "SCOPE_HASH_TAMPERED")
    need(scope["stage"]=="engineering_source_only_no_root_grant"
         and scope["owner_signature_claimed"] is False
         and scope["root_installation_performed"] is False
         and scope["production_state_changed"] is False,
         "SOURCE_PACKET_CANNOT_GRANT_RELEASE")
    need(tuple(scope["exact_consumers"])==READERS and
         tuple(scope["automatic_acceptance_gates"])==POSTFLIGHT and
         tuple(scope["on_failed_check"])==ROLLBACK and
         tuple(scope["independent_root_admission_gates"])==GATES and
         tuple(scope["out_of_scope"])==NO_ACTION and
         scope["separate_30day_deletion_release_required"] is True,
         "RELEASE_SCOPE_CHANGE")
    return True
